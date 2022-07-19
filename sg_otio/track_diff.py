# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging

from .sg_settings import SGShotFieldsConfig
from .clip_group import ClipGroup
from .cut_clip import SGCutClip
from .utils import compute_clip_shot_name

logger = logging.getLogger(__name__)


class SGCutDiff(SGCutClip):
    """
    """
    def __init__(self, *args, **kwargs):
        super(SGCutDiff, self).__init__(*args, **kwargs)
        self._old_clip = None

    @property
    def old_clip(self):
        return self._old_clip

    @old_clip.setter
    def old_clip(self, value):
        self._old_clip = value

class SGTrackDiff(object):
    """
    """
    def __init__(self, sg, sg_project, new_track, old_track=None):
        """

        :raises ValueError: For invalid tracks.
        """
        self._sg = sg
        self._sg_project = sg_project
        self._diffs_by_shots = {}
        # Retrieve the Shot fields we need to query from SG.
        sg_shot_fields = SGShotFieldsConfig(
            None, None
        ).all

        # Retrieve Shots from the old_track
        sg_shot_ids = []
        prev_clip_list = []
        if old_track:
            for i, clip in enumerate(old_track.each_clip()):
                # Check if we have some SG meta data
                sg_cut_item = clip.metadata.get("sg")
                if sg_cut_item:
                    shot_id = sg_cut_item.get("shot", {}).get("id")
                    if shot_id:
                        sg_shot_ids.append(shot_id)
                    prev_clip_list.append(
                        SGCutClip(clip, index=i + 1, sg_shot=sg_cut_item["shot"])
                    )
        sg_shots_dict = {}
        # Retrieve details for Shots linked to the Clips
        if sg_shot_ids:
            sg_shots = self._sg.find(
                "Shot",
                [["id", "in", list(sg_shot_ids)]],
                sg_shot_fields
            )
            # Build a dictionary where Shot names are the keys, use the Shot id
            # if the name is not set
            sg_shots_dict = dict(((x["code"] or str(x["id"])).lower(), x) for x in sg_shots)

        # Retrieve additional Shots from the new track if needed
        self._diffs_by_shots = {}
        more_shot_names = set()
        for i, clip in enumerate(new_track.each_clip()):
            shot_name = compute_clip_shot_name(clip)
            if shot_name:
                # Matching Shots must be case insensitive
                shot_name = shot_name.lower()
                more_shot_names.add(shot_name)
            # Ensure a ClipGroup and add SGCutDiff to it.
            if shot_name not in self._diffs_by_shots:
                self._diffs_by_shots[shot_name] = ClipGroup(shot_name)
            self._diffs_by_shots[shot_name].add_clip(
                SGCutDiff(clip, index=i + 1, sg_shot=None)
            )
        if more_shot_names:
            sg_more_shots = self._sg.find(
                "Shot",
                [
                    ["project", "is", self._sg_project],
                    ["code", "in", list(more_shot_names)]
                ],
                sg_shot_fields,
            )
            for sg_shot in sg_more_shots:
                shot_name = sg_shot["code"].lower()
                self._diffs_by_shots[shot_name].sg_shot = sg_shot

        # Duplicate the list of shots, allowing us to know easily which ones are
        # not part of the new track by removing entries when we use them.
        # We only need a shallow copy here
        leftover_shots = [x for x in sg_shots_dict.values()]
        seen_names = []
        duplicate_names = {}
        logger.debug("Matching clips...")
        for shot_name, clip_group in self._diffs_by_shots.items():
            sg_shot = clip_group.sg_shot
            for clip in clip_group.clips:
                # Ensure unique names
                if clip.name not in seen_names:
                    seen_names.append(clip.name)
                else:
                    if clip.name not in duplicate_names:
                        duplicate_names[clip.name] = 0
                    duplicate_names[clip.name] += 1
                    clip.cut_item_name = "%s_%03d" % (clip.name, duplicate_names[clip.name])
                # If we don't have a Shot name we can't match anything
                if not shot_name:
                    logger.debug("No Shot name for %s, not matching..." % clip)
                    continue

                logger.debug("Matching %s for %s" % (
                    shot_name, clip,
                ))
                # If we found a SG Shot, we can match with its id.
                if sg_shot:
                    old_clip = self.old_clip_for_shot(
                        clip,
                        prev_clip_list,
                        sg_shot,
                        clip.sg_version,
                    )
                    clip.old_clip = old_clip
                else:
                    matching_cut_item = None
                    # Do we have a matching Shot in SG ?
                    matching_shot = sg_shots_dict.get(lower_shot_name)
                    if matching_shot:
                        # yes we do
                        logger.debug("Found matching existing Shot %s" % shot_name)
                        # Remove this entry from the leftovers
                        if matching_shot in leftover_shots:
                            leftover_shots.remove(matching_shot)
                        old_clip = self.old_clip_for_shot(
                            clip,
                            prev_clip_list,
                            matching_shot,
                            clip.sg_version,
                        )
                        clip.old_clip = old_clip
#
#        for clip in new_track.each_clip():
#            # Ensure unique names
#            cut_item_name = clip.name
#            if cut_item_name not in seen_names:
#                seen_names.append(cut_item_name)
#            else:
#                if cut_item_name not in duplicate_names:
#                    duplicate_names[cut_item_name] = 0
#                duplicate_names[cut_item_name] += 1
#                cut_item_name = "%s_%03d" % (clip.name, duplicate_names[clip.name])
#
#            shot_name = compute_clip_shot_name(clip)
#            if not shot_name:
#                # If we don't have a Shot name, we can't match anything
#                self.add_cut_diff(
#                    None,
#                    sg_shot=None,
#                    new_clip=clip,
#                    old_clip=None,
#                    cut_item_name=cut_item_name
#                )
#            else:
#                lower_shot_name = shot_name.lower()
#                logger.debug("Matching %s for %s" % (
#                    lower_shot_name, str(edit),
#                ))
#                existing = self.diffs_for_shot(shot_name)
#                # Is it a duplicate ?
#                if existing:
#                    logger.debug("Found duplicated Shot, Shot %s (%s)" % (
#                        shot_name, existing))
#                    old_clip = self.old_clip_for_shot(
#                        sg_cut_items,
#                        existing[0].sg_shot,
#                        edit.get_sg_version(),
#                        edit
#                    )
#                    self.add_cut_diff(
#                        shot_name,
#                        sg_shot=existing[0].sg_shot,
#                        new_clip=clip,
#                        old_clip=old_clip,
#                        cut_item_name=cut_item_name
#                    )
#                else:
#                    matching_cut_item = None
#                    # Do we have a matching Shot in SG ?
#                    matching_shot = sg_shots_dict.get(lower_shot_name)
#                    if matching_shot:
#                        # yes we do
#                        logger.debug("Found matching existing Shot %s" % shot_name)
#                        # Remove this entry from the leftovers
#                        if matching_shot in leftover_shots:
#                            leftover_shots.remove(matching_shot)
#                        old_clip = self.old_clip_for_shot(
#                            sg_cut_items,
#                            matching_shot,
#                            edit.get_sg_version(),
#                            edit,
#                        )
#                    self.add_cut_diff(
#                        shot_name,
#                        sg_shot=matching_shot,
#                        new_clip=clip,
#                        old_clip=old_clip,
#                        cut_item_name=cut_item_name
#                    )
#
#        # Process CutItems left over, they are all the CutItems which were
#        # not matched to an edit event in the loaded EDL.
#        for sg_cut_item in sg_cut_items:
#            # If not compliant to what we expect, just ignore it
#            if (
#                sg_cut_item["shot"]
#                and sg_cut_item["shot"]["id"]
#                and sg_cut_item["shot"]["type"] == "Shot"
#            ):
#                shot_name = "No Link"
#                matching_shot = None
#                for sg_shot in sg_shots_dict.values():
#                    if sg_shot["id"] == sg_cut_item["shot"]["id"]:
#                        # We found a matching Shot
#                        shot_name = sg_shot["code"]
#                        self._logger.debug(
#                            "Found matching existing Shot %s" % shot_name
#                        )
#                        matching_shot = sg_shot
#                        # Remove this entry from the list
#                        if sg_shot in leftover_shots:
#                            leftover_shots.remove(sg_shot)
#                        break
#                self.add_cut_diff(
#                    shot_name,
#                    sg_shot=matching_shot,
#                    edit=None,
#                    sg_cut_item=sg_cut_item,
#                    cut_item_name=sg_cut_item["code"]
#                )
#
#        if leftover_shots:
#            # This shouldn't happen, as our list of Shots comes from edits
#            # and CutItems, and we should have processed all of them. Issue
#            # a warning if it is the case.
#            logger.warning("Found %s left over Shots..." % leftover_shots)
#
#
#        # Match clips in the new track with:
#        # - Is it linked to the same Shot?
#        # - Is it linked to the same Version?
#        # - Is the Cut order the same?
#        # - Is the tc in the same?
#        # - Is the tc out the same?
#
#    def add_cut_diff(self, shot_name, sg_shot=None, new_clip=None, old_clip=None, cut_item_name=None):
#        """
#        """
#        pass
#
    def old_clip_for_shot(self, for_clip, prev_clip_list, sg_shot, sg_version=None):
        """
        Return a Clip for the given Clip and Shot from the given list of Clip list.

        The prev_clip_list list is modified inside this method, entries being
        removed as they are chosen.

        Best matching Clip is returned, a score is computed for each entry
        from:
        - Is it linked to the right Shot?
        - Is it linked to the right Version?
        - Is the index the same?
        - Is the tc in the same?
        - Is the tc out the same?

        :param for_clip: A Clip instance.
        :param prev_clip_list: A list of Clip instances to consider.
        :param sg_shot: A SG Shot dictionary
        :param sg_version: A SG Version dictionary
        :returns: A Clip, or ``None``
        """

        potential_matches = []
        for clip in prev_clip_list:
            sg_cut_item = clip.metadata.get("sg")
            # Is it linked to the given Shot ?
            if (
                sg_cut_item
                and sg_cut_item["shot"]
                and sg_cut_item["shot"]["id"] == sg_shot["id"]
                and sg_cut_item["shot"]["type"] == sg_shot["type"]
            ):
                # We can have multiple CutItems for the same Shot
                # use the linked Version to pick the right one, if
                # available
                if not sg_version:
                    # No particular Version to match, score is based on
                    # on differences between Cut order, tc in and out
                    # give score a bonus as we don't have an explicit mismatch
                    potential_matches.append((
                        clip,
                        100 + self._get_matching_score(clip, for_clip)
                    ))
                elif sg_cut_item["version"]:
                    if sg_version["id"] == sg_cut_item["version"]["id"]:
                        # Give a bonus to score as we matched the right
                        # Version
                        potential_matches.append((
                            clip,
                            1000 + self._get_matching_score(clip, for_clip)
                        ))
                    else:
                        # Version mismatch, don't give any bonus
                        potential_matches.append((
                            clip,
                            self._get_matching_score(clip, for_clip)
                        ))
                else:
                    # Will keep looking around but we keep a reference to
                    # CutItem since it is linked to the same Shot
                    # give score a little bonus as we didn't have any explicit
                    # mismatch
                    potential_matches.append((
                        clip,
                        100 + self._get_matching_score(clip, for_clip)
                    ))
            else:
                logger.debug("Rejecting %s for %s" % (clip, for_clip))
        if potential_matches:
            potential_matches.sort(key=lambda x: x[1], reverse=True)
            for pm in potential_matches:
                logger.debug("Potential matches %s score %s" % (
                    pm[0], pm[1],
                ))
            # Return just the CutItem, not including the score
            best = potential_matches[0][0]
            # Prevent this one to be matched multiple times
            prev_clip_list.remove(best)
            logger.debug("Best is %s for %s" % (best, for_clip))
            return best
        return None

    def _get_matching_score(self, clip_a, clip_b):
        """
        Return a matching score for the given two clips, based on:
        - Is the Cut order the same?
        - Is the tc in the same?
        - Is the tc out the same?

        So the best score is 3 if all of them match

        :param clip_a: a Clip.
        :param clip_b: a Clip.
        :returns: A score, as an integer
        """
        score = 0
        # Compute the Cut order difference (edit.id is the Cut order in an EDL)
        diff = clip_a.index - clip_b.index
        if diff == 0:
            score += 1
        diff = (clip_a.source_in - clip_b.source_in).to_frames()
        if diff == 0:
            score += 1
        diff = (clip_a.source_out - clip_b.source_out).to_frames()
        if diff == 0:
            score += 1

        return score

    def __len__(self):
        """
        Return the total number of :class:`SGCutDiff` entries in this SGTrackDiff.

        :returns: An integer
        """
        return sum([len(self._diffs_by_shots[k]) for k in self._diffs_by_shots], 0)

    def __iter__(self):
        """
        Iterate over Shots for this SGTrackDiff

        :yields: Shot names, as strings
        """
        for name in self._diffs_by_shots.keys():
            yield name

    def __getitem__(self, key):
        """
        Return the :class:`ClipGroup` for a given Shot

        :param str key: A Shot name.
        :returns: A list of :class:`SGCutDiff` instances or ``None``.
        """
        return self._diffs_by_shots.get(key.lower())

    def iteritems(self):
        """
        Iterate over Shot names for this summary, yielding (name, :class:`ClipGroup`)
        tuple

        :yields: (name, :class:`ClipGroup`) tuples
        """
        for name, item in self._diffs_by_shots.items():
            yield (name, item)

    # Follow Python3 iterators changes and provide an items method iterating
    # other the items
    items = iteritems
