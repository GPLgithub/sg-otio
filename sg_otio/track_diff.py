# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging
from collections import defaultdict
import csv
from datetime import date

from .sg_settings import SGShotFieldsConfig
from .clip_group import ClipGroup
from .constants import _DIFF_TYPES
from .cut_clip import SGCutClip
from .cut_diff import SGCutDiff
from .utils import compute_clip_shot_name, get_entity_type_display_name

logger = logging.getLogger(__name__)

# Some counts are per Shot, some others per edits
# As a rule of thumb, everything which directly affects the Shot is per
# Shot:
# - Creation of new Shots (NEW)
# - Omission of existing Shots (OMITTED)
# - Re-enabling existing Shots (REINSTATED)
# - Need for a rescan (RESCAN)
# On the other hand, in and out point changes, some repeated Shots being
# added or removed are counted per item and are considered CUT_CHANGES
_PER_SHOT_TYPE_COUNTS = [
    _DIFF_TYPES.NEW,
    _DIFF_TYPES.OMITTED,
    _DIFF_TYPES.REINSTATED,
    _DIFF_TYPES.RESCAN
]


# Template used by summary report
_BODY_REPORT_FORMAT = """
%s
Links: %s

The changes in %s are as follows:

%d New Shots
%s

%d Omitted Shots
%s

%d Reinstated Shot
%s

%d Cut Changes
%s

%d Rescan Needed
%s

"""


class SGCutDiffGroup(ClipGroup):
    """
    A class representing groups of Cut differences.
    """
    def __init__(self, name, clips=None, sg_shot=None):
        """
        Override base implementation to add members we need.

        :param str name: A name.
        :param clips: A list of :class:`SGCutDiff` instances.
        :param sg_shot: A SG Shot as a dictionary.
        """
        super(SGCutDiffGroup, self).__init__(name, clips, sg_shot)
        self._old_earliest_clip = None
        self._old_last_clip = None

    @property
    def clips(self):
        """
        Returns the clips that are part of the group and are not omitted entries.

        :yields: :class:`SGCutDiff` instances.
        """
        # Don't return the original list, because it might be modified.
        for clip in self._clips:
            if clip.current_clip:
                yield clip

    @property
    def omitted_clips(self):
        """
        Returns the clips that are part of the group and are omitted entries.

        :yields: :class:`SGCutDiff` instances.
        """
        # Don't return the original list, because it might be modified.
        for clip in self._clips:
            if clip.current_clip is None:
                yield clip

    def remove_clip(self, clip):
        """
        Remove the given Cut Difference from our list, recompute group values.

        Override base implementation to deal with ommitted entries.

        :param clip: A :class:`SGCutDiff` instance.
        """
        super(SGCutDiffGroup, self).remove_clip(clip)
        if not clip.current_clip:
            self._old_earliest_clip = None
            self._old_last_clip = None
            for clip in self.omitted_clips:
                if self._old_earliest_clip is None or clip.source_in < self._old_earliest_clip.source_in:
                    self._old_earliest_clip = clip
                if self._old_last_clip is None or clip.source_out > self._old_last_clip.source_out:
                    self._old_last_clip = clip

    def add_clip(self, clip):
        """
        Adds a Cut difference to the group.

        Override base implementation to deal with ommitted entries.

        :param clip: A :class:`SGCutDiff` instance.
        """
        if not clip.current_clip:
            # Just append the clip without affecting the group values.
            self._append_clip(clip)
            if self._old_earliest_clip is None or clip.source_in < self._old_earliest_clip.source_in:
                self._old_earliest_clip = clip
            if self._old_last_clip is None or clip.source_out > self._old_last_clip.source_out:
                self._old_last_clip = clip
            logger.debug(
                "Added omitted clip %s %s %s" % (clip.name, clip.cut_in, clip.cut_out)
            )
            return

        # Just call the base implementation
        super(SGCutDiffGroup, self).add_clip(clip)

    @property
    def earliest_clip(self):
        """
        Return the earliest Clip in this group.

        :returns: A :class:`SGCutDiff`.
        """
        # We might have a mix of omitted edits (no new value) and non omitted edits
        # (with new values) in our list. If we have at least one entry which is
        # not omitted (has new value) we consider entries with new values, so we
        # will consider omitted edits only if all edits are omitted
        if self._earliest_clip:
            return self._earliest_clip
        return self._old_earliest_clip

    @property
    def last_clip(self):
        """
        Return the last Clip in this group.

        :returns: A :class:`SGCutDiff`.
        """
        # We might have a mix of omitted edits (no new value) and non omitted edits
        # (with new values) in our list. If we have at least one entry which is
        # not omitted (has new value) we consider entries with new values, so we
        # will consider omitted edits only if all edits are omitted
        if self._last_clip:
            return self._last_clip
        return self._old_last_clip

    @property
    def sg_shot_is_omitted(self):
        """
        Return ``True`` if the SG Shot for this group does not appear in the
        SG Cut anymore.

        :returns: A boolean.
        """
        for cut_diff in self:
            if cut_diff.diff_type == _DIFF_TYPES.OMITTED:
                return True
            elif cut_diff.diff_type != _DIFF_TYPES.OMITTED_IN_CUT:
                return False
        # If we reached that point it's because all entries are omitted in cut.
        return True

    def get_shot_values(self):
        """
        Returns values which should be set on the Shot this group is linked to.

        Loop over our :class:`SGCutDiff` list and return values which should be set on the
        Shot.

        The Shot difference type can be different from individual Cut difference
        types, for example a new edit can be added, but the Shot itself is not
        new.

        Return a tuple with :
        - A SG Shot dictionary or None
        - The smallest cut order
        - The earliest head in
        - The earliest cut in
        - The last cut out
        - The last tail out
        - The Shot difference type

        :returns: A tuple
        """
        min_cut_order = None
        min_head_in = None
        min_cut_in = None
        max_cut_out = None
        max_tail_out = None
        sg_shot = None
        shot_diff_type = None
        # Do a first pass with all entries to get min and max
        for cut_diff in self:
            if sg_shot is None and cut_diff.sg_shot:
                sg_shot = cut_diff.sg_shot
            cut_order = cut_diff.index
            if cut_order is not None and (min_cut_order is None or cut_order < min_cut_order):
                min_cut_order = cut_order
            if cut_diff.head_in is not None and (
                    min_head_in is None or cut_diff.head_in < min_head_in):
                min_head_in = cut_diff.head_in
            if cut_diff.cut_in is not None and (
                    min_cut_in is None or cut_diff.cut_in < min_cut_in):
                min_cut_in = cut_diff.cut_in
            if cut_diff.cut_out is not None and (
                    max_cut_out is None or cut_diff.cut_out > max_cut_out):
                max_cut_out = cut_diff.cut_out
            if cut_diff.tail_out is not None and (
                    max_tail_out is None or cut_diff.tail_out > max_tail_out):
                max_tail_out = cut_diff.tail_out
        # We do a second pass for the Shot difference type, as we might stop
        # iteration at some point. Given that the number of duplicated shots is
        # usually low, there shouldn't be a big performance hit in iterating twice
        for cut_diff in self:
            # Special cases for diff type:
            # - A Shot is NO_LINK if any of its items is NO_LINK (should be all of them)
            # - A Shot is OMITTED if all its items are OMITTED
            # - A Shot is NEW if any of its items is NEW (should be all of them)
            # - A Shot is REINSTATED if at least one of its items is REINSTATED (should
            #       be all of them)
            # - A Shot needs RESCAN if any of its items need RESCAN
            cut_diff_type = cut_diff.diff_type
            if cut_diff_type in [
                _DIFF_TYPES.NO_LINK,
                _DIFF_TYPES.NEW,
                _DIFF_TYPES.REINSTATED,
                _DIFF_TYPES.OMITTED,
                _DIFF_TYPES.RESCAN
            ]:
                shot_diff_type = cut_diff_type
                # Can't be changed by another entry, no need to loop further
                break

            if cut_diff_type == _DIFF_TYPES.OMITTED_IN_CUT:
                # Could be a repeated Shot entry removed from the Cut
                # or really the whole Shot being removed
                if shot_diff_type is None:
                    # Set initial value
                    shot_diff_type = _DIFF_TYPES.OMITTED
                elif shot_diff_type == _DIFF_TYPES.NO_CHANGE:
                    shot_diff_type = _DIFF_TYPES.CUT_CHANGE
                else:
                    # Shot is already with the right state, no need to do anything
                    pass

            elif cut_diff_type == _DIFF_TYPES.NEW_IN_CUT:
                shot_diff_type = _DIFF_TYPES.CUT_CHANGE
            else:    # _DIFF_TYPES.NO_CHANGE, _DIFF_TYPES.CUT_CHANGE
                if shot_diff_type is None:
                    # initial value
                    shot_diff_type = cut_diff_type
                elif shot_diff_type != cut_diff_type:
                    # If different values fall back to CUT_CHANGE
                    # If values are identical, do nothing
                    shot_diff_type = _DIFF_TYPES.CUT_CHANGE
        # Having _OMITTED_IN_CUT here means that all entries were _OMITTED_IN_CUT
        # so the whole Shot is _OMITTED
        if shot_diff_type == _DIFF_TYPES.OMITTED_IN_CUT:
            shot_diff_type = _DIFF_TYPES.OMITTED
        return (
            sg_shot,
            min_cut_order,
            min_head_in,
            min_cut_in,
            max_cut_out,
            max_tail_out,
            shot_diff_type,
        )


class SGTrackDiff(object):
    """
    A class to compare a track to one read from SG.
    """
    def __init__(self, sg, sg_project, new_track, old_track=None, sg_entity=None):
        """
        Instantiate a new SGTrackDiff for the given SG Project and SG Entity.

        If an old track is provided it must have been read from SG with `sg`
        metadata populated for each of its Clips.

        If an SG Entity is explicitly defined, only SG Shots linked to this Entity
        will be considered. If it is not explicitly defined, one will be retrieved
        from the SG Cut linked the to the tracks, if any.

        :param sg: A connected SG handle.
        :param sg_project: A SG Project as a dictionary.
        :param new_track: A :class:`opentimelineio.schema.Track` instance.
        :param old_track: An optional :class:`opentimelineio.schema.Track` instance
                          read from SG.
        :param sg_entity: An optional SG Entity dictionary to explicitly define
                          the SG Entity for which the difference is made.
        :raises ValueError: For invalid old tracks.
        """
        self._sg = sg
        self._sg_project = sg_project
        self._sg_entity = sg_entity
        self._sg_shot_link_field_name = None
        self._counts = defaultdict(int)
        self._active_count = 0
        # We need to keep references on the tracks otherwise underlying C++ objects
        # might be freed.
        self._old_track = old_track
        self._new_track = new_track
        self._diffs_by_shots = {}

        # Retrieve the Shot fields we need to query from SG.
        sg_shot_fields = SGShotFieldsConfig(
            self._sg, None
        ).all

        # Retrieve the SG Entity we should use for the comparison
        # and do some sanity check
        if self._sg_entity:
            if self._sg_entity["type"] == "Project":
                if self._sg_entity["id"] != self._sg_project["id"]:
                    raise ValueError(
                        "Invalid explicit SG Entity %s different from SG Project %s" % (
                            self._sg_entity,
                            self._sg_project
                        )
                    )
            elif self._sg_entity["project"]["id"] != self._sg_project["id"]:
                raise ValueError(
                    "Invalid explicit SG Entity %s not linked to SG Project %s" % (
                        self._sg_entity,
                        self._sg_project
                    )
                )

        existing_sg_link = self._retrieve_sg_link_from_sg_cuts()
        if not self._sg_entity:
            self._sg_entity = existing_sg_link
        elif existing_sg_link and existing_sg_link["type"] != "Project":
            # We only allow refining existing link from a Project to something
            # more specific.
            # Arguably we could allow as well to generalise a Cut comparison
            # to the Project.
            if (
                self._sg_entity["type"] != existing_sg_link["type"]
                or self._sg_entity["id"] != existing_sg_link["id"]
            ):
                raise ValueError(
                    "Invalid explicit SG Entity %s not matching existing link %s" % (
                        self._sg_entity,
                        existing_sg_link,
                    )
                )
        # Now check what we got
        if not self._sg_entity:
            # Fallback on using the project
            self._sg_entity = self._sg_project
            self._sg_shot_link_field_name = "project"
        else:
            self._sg_shot_link_field_name = self._get_shot_link_field(
                self._sg_entity["type"]
            )
            if not self._sg_shot_link_field_name:
                raise ValueError(
                    "Unable to retrieve a SG field to link Shots to %s" % self._sg_entity["type"]
                )
        logger.debug("Cut comparison performed against %s" % self._sg_entity)

        # Retrieve SG Entities from the old_track
        sg_shot_ids = []
        prev_clip_list = []
        if self._old_track:
            for i, clip in enumerate(self._old_track.find_clips()):
                # Check if we have some SG meta data
                sg_cut_item = clip.metadata.get("sg")
                if not sg_cut_item or sg_cut_item.get("type") != "CutItem":
                    raise ValueError(
                        "Invalid clip %s not linked to a SG CutItem" % clip.name
                    )
                sg_cut_item = sg_cut_item.to_dict()
                sg_shot = sg_cut_item.get("shot")
                if sg_shot:
                    shot_id = sg_shot.get("id")
                    if shot_id:
                        sg_shot_ids.append(shot_id)
                prev_clip_list.append(
                    SGCutClip(clip, index=i + 1, sg_shot=sg_shot)
                )
            logger.debug(
                "Previous Cut list is %s" % ",".join(
                    ["%s (%s)" % (x.name, x.sg_shot) for x in prev_clip_list]
                )
            )

        # Add the linked Entity field to the fields to retrieve for Shots if
        # we have one from the previous Cut.
        if self._sg_shot_link_field_name:
            sg_shot_fields.append(self._sg_shot_link_field_name)

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
        for i, clip in enumerate(new_track.find_clips()):
            shot_name = compute_clip_shot_name(clip)
            if shot_name:
                more_shot_names.add(shot_name)
            # Ensure a SGCutDiffGroup and add SGCutDiff to it.
            self.add_cut_diff(shot_name, clip=clip, index=i + 1, sg_shot=None)
        if more_shot_names:
            logger.debug("Looking for additional Shots %s" % more_shot_names)
            filters = [
                ["project", "is", self._sg_project],
                ["code", "in", list(more_shot_names)]
            ]
            # If we have a linked SG Entity from a previous Cut, restrict
            # to Shots linked to this SG Entity.
            if self._sg_shot_link_field_name:
                filters.append(
                    [self._sg_shot_link_field_name, "is", self._sg_entity]
                )

            sg_more_shots = self._sg.find(
                "Shot",
                filters,
                sg_shot_fields,
            )
            logger.debug("Found additional Shots %s" % sg_more_shots)

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
            # Since we loop over all clips, take the opportunity to set their
            # repeated flag
            repeated = len(clip_group) > 1
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
                    logger.debug("No Shot name for %s, not matching..." % clip.cut_item_name)
                    continue
                clip.repeated = repeated
                logger.debug("Matching %s for %s (%s)" % (
                    shot_name, clip.shot_name, clip_group.sg_shot,
                ))
                # If we found a SG Shot, we can match with its id.
                if clip_group.sg_shot:
                    old_clip = self.old_clip_for_shot(
                        clip,
                        prev_clip_list,
                        clip_group.sg_shot,
                        clip.sg_version,
                    )
                    clip.old_clip = old_clip
                    # We still need to remove the Shot from leftovers
                    # Remove this entry from the leftovers
                    if clip_group.sg_shot in leftover_shots:
                        leftover_shots.remove(clip_group.sg_shot)
                else:
                    # Do we have a matching Shot in SG ?
                    matching_shot = sg_shots_dict.get(shot_name)
                    if matching_shot:
                        # yes we do
                        logger.debug("Found matching existing Shot %s" % shot_name)
                        # Remove this entry from the leftovers
                        if matching_shot in leftover_shots:
                            leftover_shots.remove(matching_shot)
                        else:
                            logger.warning("%s is not in existing Shots" % shot_name)
                        clip_group.sg_shot = matching_shot
                        old_clip = self.old_clip_for_shot(
                            clip,
                            prev_clip_list,
                            matching_shot,
                            clip.sg_version,
                        )
                        clip.old_clip = old_clip
        # Process clips left over, they are all the clips which were
        # not matched to a clip from the new track.
        for clip in prev_clip_list:
            logger.info("Processing un-matched old clip %s" % clip.cut_item_name)
            clip_sg_shot = clip.sg_shot
            # If no Shot, we don't really care about it
            if not clip_sg_shot:
                logger.debug("Ignoring old clip %s with no SG Shot" % (clip.cut_item_name))
                continue
            shot_name = "No Link"
            matching_shot = None
            for sg_shot in sg_shots_dict.values():
                if sg_shot["id"] == clip_sg_shot["id"]:
                    # We found a matching Shot
                    shot_name = sg_shot["code"]
                    logger.debug(
                        "Found matching existing Shot %s" % shot_name
                    )
                    matching_shot = sg_shot
                    # Remove this entry from the list
                    if sg_shot in leftover_shots:
                        logger.debug("Removing %s from leftovers..." % sg_shot)
                        leftover_shots.remove(sg_shot)
                    break

            sg_cut_diff = self.add_cut_diff(
                shot_name,
                clip=clip.clip,
                index=clip.index,
                sg_shot=clip.sg_shot,
                as_omitted=True,
            )
            logger.info(
                "Added %s as ommitted entry for %s" % (
                    sg_cut_diff.cut_item_name,
                    shot_name,
                )
            )
        self.recompute_counts()
        if leftover_shots:
            # This shouldn't happen, as our list of Shots comes from edits
            # and CutItems, and we should have processed all of them. Issue
            # a warning if it is the case.
            logger.warning("Found %s left over Shots..." % leftover_shots)

    @property
    def sg_link(self):
        """
        Return the SG Entity used for the Cut comparison.

        :returns: A SG Entity dictionary, or ``None``.
        """
        return self._sg_entity

    @property
    def sg_shot_link_field_name(self):
        """
        Return the SG field name used to link Shots to the SG Entity used
        for the Cut comparison.

        :returns: A SG field name as a string, or ``None``.
        """
        return self._sg_shot_link_field_name

    @property
    def diffs_by_shots(self):
        """
        Return the :class:`SGCutDiffGroup` grouped by Shots.

        :returns: A dictionary where keys are Shot names and values :class:`SGCutDiffGroup`
                  instances.
        """
        return self._diffs_by_shots

    @property
    def active_count(self):
        """
        Return the number of clips from the current track.

        :returns: A dictionary.
        """
        # Note: we could simply return len(self._new_track) here
        # instead of keeping this count internally.
        return self._active_count

    @property
    def counts(self):
        """
        Return a dictionary where keys are diff types and values their number for
        the current comparison.

        :returns: A dictionary.
        """
        return self._counts

    @classmethod
    def old_clip_for_shot(cls, for_clip, prev_clip_list, sg_shot, sg_version=None):
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

        :param for_clip: A SGCutClip instance.
        :param prev_clip_list: A list of SGCutClip instances to consider.
        :param sg_shot: A SG Shot dictionary.
        :param sg_version: A SG Version dictionary.
        :returns: A Clip, or ``None``.
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
                        100 + cls.get_matching_score(clip, for_clip)
                    ))
                elif sg_cut_item["version"]:
                    if sg_version["id"] == sg_cut_item["version"]["id"]:
                        # Give a bonus to score as we matched the right
                        # Version
                        potential_matches.append((
                            clip,
                            1000 + cls.get_matching_score(clip, for_clip)
                        ))
                    else:
                        # Version mismatch, don't give any bonus
                        potential_matches.append((
                            clip,
                            cls.get_matching_score(clip, for_clip)
                        ))
                else:
                    # Will keep looking around but we keep a reference to
                    # CutItem since it is linked to the same Shot
                    # give score a little bonus as we didn't have any explicit
                    # mismatch
                    potential_matches.append((
                        clip,
                        100 + cls.get_matching_score(clip, for_clip)
                    ))
            else:
                logger.debug("Rejecting %s for %s" % (clip.cut_item_name, for_clip.cut_item_name))
        if potential_matches:
            potential_matches.sort(key=lambda x: x[1], reverse=True)
            for pm in potential_matches:
                logger.debug("Potential matches %s score %s" % (
                    pm[0].cut_item_name, pm[1],
                ))
            # Return just the CutItem, not including the score
            best = potential_matches[0][0]
            # Prevent this one to be matched multiple times
            prev_clip_list.remove(best)
            logger.debug("Best is %s for %s" % (best.cut_item_name, for_clip.cut_item_name))
            return best
        return None

    def get_cut_diff_for_clip(self, clip, index, sg_shot=None, as_omitted=False, repeated=False):
        """
        Return a new :class:`SGCutDiff` for the given clip.

        This can be re-implemented in deriving classes to return a custom instance
        deriving from a :class:`SGCutDiff`.

        :param clip: A :class:`otio.schema.Clip` instance.
        :param int index: The index of the clip in its track.
        :param sg_shot: A SG Shot dictionary.
        :param bool as_omitted: Whether this is a difference for an omitted Shot or not.
        :param bool repeated: Whether this is a difference for a Shot with multiple edits.
        """
        return SGCutDiff(
            clip=clip,
            index=index,
            sg_shot=sg_shot,
            as_omitted=as_omitted,
            repeated=repeated,
        )

    @staticmethod
    def get_shot_key(shot_name, clip_index):
        """
        Return a case insensitive key based on the Shot name allowing to group together Clips
        for the same Shot.

        :param shot_name: A string or ``None``.
        :param clip_index: A value changing for each Clip, used to build a unique key if
                           no shot name is provided.
        :returns: A string.
        """
        if shot_name:
            return shot_name.lower()
        # If no Shot name, forge a key specific to this Clip so it will
        # not be grouped with other Clips without a Shot name.
        return "_no_shot_name_%s" % clip_index

    def add_cut_diff(self, shot_name, clip, index, sg_shot=None, as_omitted=False):
        """
        Add a new Cut difference to this :class:`TrackDiff`.

        :param shot_name: Shot name, as a string.
        :param clip: A :class:`otio.schema.Clip` instance.
        :param int index: The index of the clip in its track.
        :param sg_shot: A SG Shot dictionary.
        :param bool as_omitted: Whether this is a difference for an omitted Shot or not.
        """
        # Force a lowercase key to make Shot names case-insensitive. Shot names
        # we retrieve from editorial files may be uppercase, but actual SG Shots may be
        # lowercase.

        # We use a special `"_no_shot_name_%s" % index` Shot keys if the Shot name was not set
        # to avoid considering in the same Shot all entries not linked to a Shot since this
        # affects the repeated head in, tail out and handles values
        shot_key = self.get_shot_key(shot_name, index)

        repeated = False
        if shot_key not in self._diffs_by_shots:
            self._diffs_by_shots[shot_key] = SGCutDiffGroup(
                shot_name,
                sg_shot=sg_shot
            )
        else:
            repeated = bool(len(self._diffs_by_shots[shot_key]))
            for existing_clip in self._diffs_by_shots[shot_key].clips:
                existing_clip.repeated = True

        new_diff = self.get_cut_diff_for_clip(
            clip=clip,
            index=index,
            sg_shot=sg_shot,
            as_omitted=as_omitted,
            repeated=repeated,
        )
        self._diffs_by_shots[shot_key].add_clip(new_diff)
        # Enforce the shot name if one was given
        if shot_name:
            new_diff.shot_name = shot_name
        return new_diff

    def count_for_type(self, diff_type):
        """
        Return the number of entries for the given CutDiffType.

        :param diff_type: A CutDiffType.
        :returns: An integer.
        """
        return self._counts.get(diff_type, 0)

    def diffs_for_type(self, diff_type, just_earliest=False):
        """
        Iterate over SGCutDiff instances for the given CutDiffType.

        :param diff_type: A CutDiffType.
        :param just_earliest: Whether or not all matching SGCutDiff should be
                              returned or just the earliest(s).
        :yields: SGCutDiff instances.
        """
        for shot_name, clip_group in self._diffs_by_shots.items():
            if just_earliest:
                cut_diff = clip_group.earliest_clip
                if not cut_diff:
                    raise ValueError(clip_group._clips[0].name)
                if cut_diff.interpreted_diff_type == diff_type:
                    yield cut_diff
            else:
                for cut_diff in clip_group.clips:
                    if cut_diff.interpreted_diff_type == diff_type:
                        yield cut_diff

    def write_csv_report(self, csv_path, title, sg_links=None):
        """
        Write a csv report for this summary, highligting changes.

        :param str csv_path: Full path to the csv file to write.
        :param str title: A title for the report.
        :param sg_links: An optional list of SG URLs to display in the report as links.
        """
        header_row = ["Cut Order", "Status", "Shot", "Duration (fr)", "Start", "End", "Notes"]
        # We use utf-8-sig to make sure Excel opens the file with the right encoding.
        # no issues with other apps (e.g. Google Sheets, Numbers, etc.)
        with open(csv_path, "w", encoding="utf-8-sig") as csv_handle:
            csv_writer = csv.writer(csv_handle, lineterminator="\n")
            # Write some header information
            data_row = ["Changes Report:", title, "(previous values in parenthesis if different)"] + [""] * 4
            csv_writer.writerow(data_row)
            data_row = ["Report Date:", date.today().isoformat()] + [""] * 5
            csv_writer.writerow(data_row)
            csv_writer.writerow([""] * 7)
            data_row = ["To:", self._new_track.name] + [""] * 5
            csv_writer.writerow(data_row)
            data_row = ["From:", self._old_track.name if self._old_track else ""] + [""] * 5
            csv_writer.writerow(data_row)
            csv_writer.writerow([""] * 7)
            if sg_links:
                data_row = ["Links:", " ".join(sg_links)] + [""] * 5
                csv_writer.writerow(data_row)
                csv_writer.writerow([""] * 7)
            duration = self._new_track.duration()
            if self._old_track:
                old_duration = self._old_track.duration()
                if old_duration != duration:
                    duration_frame = "%s (%s)" % (duration.to_frames(), old_duration.to_frames())
                    duration_tc = "%s (%s)" % (duration.to_timecode(), old_duration.to_timecode())
                else:
                    duration_frame = "%s" % duration.to_frames()
                    duration_tc = "%s" % duration.to_timecode()
                if old_duration.rate != duration.rate:
                    duration_fps = "%s fps (%s)" % (duration.rate, old_duration.rate)
                else:
                    duration_fps = "%s fps" % duration.rate
            else:
                duration_frame = "%s" % duration.to_frames()
                duration_tc = "%s" % duration.to_timecode()
                duration_fps = "%s fps" % duration.rate
            data_row = ["Total Run Time [fr]:", duration_frame] + [""] * 5
            csv_writer.writerow(data_row)
            data_row = ["Total Run Time [tc]:", duration_tc, duration_fps] + [""] * 4
            csv_writer.writerow(data_row)
            count = (
                self.count_for_type(_DIFF_TYPES.NEW) + self.count_for_type(_DIFF_TYPES.CUT_CHANGE)
                + self.count_for_type(_DIFF_TYPES.REINSTATED) + self.count_for_type(_DIFF_TYPES.RESCAN)
                + self.count_for_type(_DIFF_TYPES.NO_CHANGE)
            )
            total_count = "%d" % count
            if self._old_track:
                old_count = len(list(self._old_track.find_clips()))
                if old_count != count:
                    total_count = "%d (%d)" % (count, old_count)
            data_row = ["Total Count:", "%s" % total_count] + [""] * 5
            csv_writer.writerow(data_row)

            # Write the data
            csv_writer.writerow([""] * 7)
            csv_writer.writerow(header_row)
            # Collect all rows so we can output values in cut orders
            data_rows = []
            for shot_name, clip_group in self._diffs_by_shots.items():
                # Omitted clips
                for cut_diff in clip_group.omitted_clips:
                    start = "%s" % cut_diff.old_cut_in.to_frames()
                    end = "%s" % cut_diff.old_cut_out.to_frames()
                    cut_order = "%s" % cut_diff.old_index
                    duration = "%s" % cut_diff.old_visible_duration.to_frames()
                    data_row = [
                        cut_order,
                        cut_diff.diff_type.name,
                        shot_name,
                        duration,
                        start,
                        end,
                        " ".join(cut_diff.reasons),
                    ]
                    data_rows.append(data_row)
                # Current clips
                for cut_diff in clip_group.clips:
                    # Old values can be None for new edits without
                    # an old counterpart.
                    if cut_diff.old_cut_in is not None and cut_diff.cut_in != cut_diff.old_cut_in:
                        start = "%s (%s)" % (cut_diff.cut_in.to_frames(), cut_diff.old_cut_in.to_frames())
                    else:
                        start = "%s" % cut_diff.cut_in.to_frames()
                    if cut_diff.old_cut_out is not None and cut_diff.cut_out != cut_diff.old_cut_out:
                        end = "%s (%s)" % (cut_diff.cut_out.to_frames(), cut_diff.old_cut_out.to_frames())
                    else:
                        end = "%s" % cut_diff.cut_out.to_frames()
                    if cut_diff.old_index is not None and cut_diff.index != cut_diff.old_index:
                        cut_order = "%s (%s)" % (cut_diff.index, cut_diff.old_index)
                    else:
                        cut_order = "%s" % cut_diff.index
                    if cut_diff.old_visible_duration is not None and cut_diff.visible_duration != cut_diff.old_visible_duration:
                        duration = "%s (%s)" % (cut_diff.visible_duration.to_frames(), cut_diff.old_visible_duration.to_frames())
                    else:
                        duration = "%s" % cut_diff.visible_duration.to_frames()
                    data_row = [
                        cut_order,
                        cut_diff.diff_type.name,
                        shot_name,
                        duration,
                        start,
                        end,
                        " ".join(cut_diff.reasons),
                    ]
                    data_rows.append(data_row)
            # Sort by cut order and then diff type.
            # We need to convert the cut order to an int otherwise
            # "2" is bigger than "10" and we ignore the (old value)
            # if one is present.
            data_rows.sort(key=lambda row: (int(row[0].split(" ")[0]), row[1]))
            csv_writer.writerows(data_rows)

    def get_report(self, title, sg_links):
        """
        Build a text report for this summary, highlighting changes.

        :param title: A title for the report.
        :param sg_links: Shotgun URLs to display in the report as links.
        :return: A (subject, body) tuple, as strings.
        """
        # Body should look like this:
        # The changes in {Name of Cut/EDL} are as follows:
        #
        # 5 New Shots
        # HT0500
        # HT0510
        # HT0520
        # HT0530
        # HT0540
        #
        # 2 Omitted Shots
        # HT0050
        # HT0060
        #
        # 1 Reinstated Shot
        # HT0110
        #
        # 4 Cut Changes
        # HT0070 - Head extended 2 frs
        # HT0080 - Tail extended 6 frs
        # HT0090 - Tail trimmed 5 frs
        # HT0100 - Head extended 5 frs
        #
        # 1 Rescan Needed
        # HT0120 - Head extended 15 frs

        subject = self.get_summary_title(title)
        # Note: Cut changes were previously reported with sometimes some reasons
        # and some other times no reasons at all. This was confusing for clients.
        # So for now we don't show any reason.
#        cut_changes_details = [
#            "%s - %s" % (
#                edit.name, ", ".join(edit.reasons)
#            ) for edit in sorted(
#                self.diffs_for_type(_DIFF_TYPES.CUT_CHANGE),
#                key=lambda x: x.index
#            )
#        ]
        cut_changes_details = [
            "%s" % (
                diff.name
            ) for diff in sorted(
                self.diffs_for_type(_DIFF_TYPES.CUT_CHANGE),
                key=lambda x: x.index
            )
        ]
        rescan_details = [
            "%s - %s" % (
                diff.name, ", ".join(diff.reasons)
            ) for diff in sorted(
                self.diffs_for_type(_DIFF_TYPES.RESCAN),
                key=lambda x: x.index
            )
        ]
        no_link_details = [
            diff.sg_version_name or str(diff.index) for diff in sorted(
                self.diffs_for_type(_DIFF_TYPES.NO_LINK),
                key=lambda x: x.index
            )
        ]
        body = _BODY_REPORT_FORMAT % (
            # Let the user know that something is potentially wrong
            "WARNING, following edits couldn't be linked to any Shot :\n%s\n" % (
                "\n".join(no_link_details)
            ) if no_link_details else "",
            # Urls
            " , ".join(sg_links),
            # Title
            title,
            # And then counts and lists per type of changes
            self.count_for_type(_DIFF_TYPES.NEW),
            "\n".join([
                diff.shot_name for diff in sorted(
                    self.diffs_for_type(_DIFF_TYPES.NEW, just_earliest=True),
                    key=lambda x: x.index
                )
            ]),
            self.count_for_type(_DIFF_TYPES.OMITTED),
            "\n".join([
                diff.shot_name for diff in sorted(
                    self.diffs_for_type(_DIFF_TYPES.OMITTED, just_earliest=True),
                    key=lambda x: x.index or -1
                )
            ]),
            self.count_for_type(_DIFF_TYPES.REINSTATED),
            "\n".join([
                diff.shot_name for diff in sorted(
                    self.diffs_for_type(_DIFF_TYPES.REINSTATED, just_earliest=True),
                    key=lambda x: x.index
                )
            ]),
            self.count_for_type(_DIFF_TYPES.CUT_CHANGE),
            "\n".join(cut_changes_details),
            self.count_for_type(_DIFF_TYPES.RESCAN),
            "\n".join(rescan_details),
        )
        return subject, body

    def get_summary_title(self, subject):
        """
        Return a string suitable as a title for Cut changes reports.

        :param str subject: A string, usually a SG Cut name.
        """
        # If we're comparing an existing SG Cut to something,
        # use their names for the title.
        if self._new_track.metadata.get("sg") and self._old_track:
            return "%s Cut Summary changes between %s and %s" % (
                subject,
                self._new_track.name,
                self._old_track.name,
            )
        # If we have a SG Entity, use it for the title.
        if self._sg_entity:
            return "%s Cut Summary changes on %s" % (
                self._sg_entity["type"].title(),
                subject
            )
        # Fallback to a generic title.
        return "Cut Summary for %s" % subject

    def get_diffs_by_change_type(self):
        """
        Returns a dictionary with lists of CutDiffs grouped by cut change type.

        :returns: A dictionary where keys are cut change types and values are sorted
                  list of :class:`CutDiff` instances.
        """
        diff_groups = {}
        diff_groups[_DIFF_TYPES.CUT_CHANGE] = sorted(
            self.diffs_for_type(_DIFF_TYPES.CUT_CHANGE),
            key=lambda x: x.index
        )
        diff_groups[_DIFF_TYPES.RESCAN] = sorted(
            self.diffs_for_type(_DIFF_TYPES.RESCAN),
            key=lambda x: x.index
        )
        diff_groups[_DIFF_TYPES.NO_LINK] = sorted(
            self.diffs_for_type(_DIFF_TYPES.NO_LINK),
            key=lambda x: x.index
        )
        diff_groups[_DIFF_TYPES.NEW] = sorted(
            self.diffs_for_type(_DIFF_TYPES.NEW, just_earliest=True),
            key=lambda x: x.index
        )
        diff_groups[_DIFF_TYPES.OMITTED] = sorted(
            self.diffs_for_type(_DIFF_TYPES.OMITTED, just_earliest=True),
            key=lambda x: x.old_index or -1
        )
        diff_groups[_DIFF_TYPES.REINSTATED] = sorted(
            self.diffs_for_type(_DIFF_TYPES.REINSTATED, just_earliest=True),
            key=lambda x: x.index
        )
        return diff_groups

    @classmethod
    def get_matching_score(cls, clip_a, clip_b):
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
        # Compute the Cut order difference (index is the Cut order)
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

    def recompute_counts(self):
        """
        Recompute internal counts from Cut differences
        """
        # Use a defaultdict so we don't have to worry about key existence
        self._counts = defaultdict(int)
        self._active_count = 0
        for shot_name, clip_group in self._diffs_by_shots.items():
            _, _, _, _, _, _, shot_diff_type = clip_group.get_shot_values()
            if shot_diff_type in _PER_SHOT_TYPE_COUNTS:
                # We count these per shots
                self._counts[shot_diff_type] += 1
                # We don't want to include omitted entries in our total
                if shot_diff_type != _DIFF_TYPES.OMITTED:
                    self._active_count += 1
            else:
                # We count others per entries
                for cut_diff in clip_group:
                    # We don't use cut_diff.interpreted_type here, as it will
                    # loop over all siblings, repeated shots cases are handled
                    # with the shot_diff_type
                    diff_type = self._interpreted_diff_type(cut_diff.diff_type)
                    self._counts[diff_type] += 1
                    # We don't want to include omitted entries in our total
                    if cut_diff.diff_type not in [
                        _DIFF_TYPES.OMITTED_IN_CUT,
                        _DIFF_TYPES.OMITTED
                    ]:
                        self._active_count += 1
        logger.debug("%s" % self._counts)

    def _retrieve_sg_link_from_sg_cuts(self):
        """
        Retrieve the SG Entity we should use for the comparison and do some sanity check.

        The SG Entity is retrieved from the tracks being compared, if they are linked to SG Cuts.
        The current SG Project is used if none can be retrieved.

        :returns: A SG Entity dictionary or ``None``.
        :raises ValueError: For invalid retrieved SG Entities.
        """

        new_track_sg_link = None
        new_track = self._new_track
        sg_cut = new_track.metadata.get("sg")
        if sg_cut:
            sg_cut = sg_cut.to_dict()
            if sg_cut["type"] != "Cut":
                raise ValueError(
                    "Invalid track %s not linked to a SG Cut" % new_track.name
                )
            new_track_sg_link = sg_cut.get("entity")
            # We don't support comparing Cuts from different SG Projects
            if sg_cut["project"]["id"] != self._sg_project["id"]:
                raise ValueError(
                    "Can't compare Cuts from different SG Projects"
                )
        if self._old_track:
            sg_cut = self._old_track.metadata.get("sg")
            if not sg_cut or sg_cut["type"] != "Cut":
                raise ValueError(
                    "Invalid track %s not linked to a SG Cut" % self._old_track.name
                )
            sg_cut = sg_cut.to_dict()
            # We don't support comparing Cuts from different SG Projects
            if sg_cut["project"]["id"] != self._sg_project["id"]:
                raise ValueError(
                    "Can't compare Cuts from different SG Projects"
                )
            old_track_sg_link = sg_cut.get("entity")
            # If the two SG Cuts are linked to a common Entity, use it.
            if new_track_sg_link:
                if (
                    new_track_sg_link["type"] == old_track_sg_link["type"]
                    and new_track_sg_link["id"] == old_track_sg_link["id"]
                ):
                    return new_track_sg_link
            else:
                # Just use the old track link, if any
                return old_track_sg_link
        else:  # Only a new track
            # Just use the new track link, if any
            return new_track_sg_link
        return None

    def _get_shot_link_field(self, sg_entity_type):
        """

        :returns: A SG Shot field name.
        """
        # Retrieve a "link" field on Shots which accepts our Entity type
        shot_schema = self._sg.schema_field_read("Shot")
        # Prefer a sg_<entity type> field if available
        type_display_name = get_entity_type_display_name(
            self._sg,
            sg_entity_type,
        )
        field_name = "sg_%s" % type_display_name.lower()
        field = shot_schema.get(field_name)
        if (
            field
            and field["data_type"]["value"] == "entity"
            and sg_entity_type in field["properties"]["valid_types"]["value"]
        ):
            logger.debug("Found preferred Shot field %s" % field_name)
            return field_name

        # General lookup
        for field_name, field in shot_schema.items():
            # the field has to accept entities and be editable.
            if field["data_type"]["value"] == "entity" and field["editable"]["value"]:
                if sg_entity_type in field["properties"]["valid_types"]["value"]:
                    logger.debug("Found field %s to link %s to shots" % (
                        field_name,
                        sg_entity_type
                    ))
                    return field_name

        logger.warning(
            "Couldn't retrieve a SG Shot field accepting %s" % (
                self._sg_entity_type,
            )
        )
        return None

    def _interpreted_diff_type(self, diff_type):
        """
        Some difference types are grouped under a common type, return
        this group type for the given difference type

        :returns: A _DIFF_TYPES
        """
        if diff_type in [_DIFF_TYPES.NEW_IN_CUT, _DIFF_TYPES.OMITTED_IN_CUT]:
            return _DIFF_TYPES.CUT_CHANGE
        return diff_type

    def __len__(self):
        """
        Return the total number of :class:`SGCutDiff` entries in this SGTrackDiff.

        :returns: An integer.
        """
        return sum([len(self._diffs_by_shots[k]) for k in self._diffs_by_shots], 0)

    def __iter__(self):
        """
        Iterate over Shots for this SGTrackDiff.

        :yields: Shot names, as strings.
        """
        for name in self._diffs_by_shots.keys():
            yield name

    def __getitem__(self, key):
        """
        Return the :class:`SGCutDiffGroup` for a given Shot name.

        :param str key: A Shot name or ``None``.
        :returns: A list of :class:`SGCutDiff` instances or ``None``.
        """
        if key:
            return self._diffs_by_shots.get(key.lower())
        return self._diffs_by_shots.get(key)

    def iteritems(self):
        """
        Iterate over Shot names for this SGTrackDiff, yielding (name, :class:`SGCutDiffGroup`)
        tuples.

        :yields: (name, :class:`SGCutDiffGroup`) tuples.
        """
        for name, item in self._diffs_by_shots.items():
            yield (name, item)

    # Follow Python3 iterators changes and provide an items method iterating
    # other the items
    items = iteritems
