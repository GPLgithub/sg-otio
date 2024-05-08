# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging

import opentimelineio as otio

from .constants import _PUBLISHED_FILE_FIELDS, _VERSION_FIELDS
from .constants import _CUT_ITEM_FIELDS, _CUT_FIELDS

from .utils import get_platform_name, compute_clip_version_name
from .sg_settings import SGShotFieldsConfig

logger = logging.getLogger(__name__)


class SGCutReader(object):
    """
    Helper class to read a Cut from SG.
    """
    def __init__(self, sg):
        """
        SGCutReader constructor.

        :param sg: A ShotGrid API session instance.
        """
        self._sg = sg

    def read(self, sg_cut_id):
        """
        Read the given Cut from SG.

        :param int sg_cut_id: A SG Cut id.
        :returns: A :class:`otio.schema.Timeline` instance.
        :raises ValueError: For invalid SG Cut id.
        """

        cut = self._sg.find_one(
            "Cut",
            [["id", "is", sg_cut_id]],
            _CUT_FIELDS
        )
        if not cut:
            raise ValueError("No Cut found with ID {}".format(sg_cut_id))
        if cut["created_at"]:
            cut["created_at"] = str(cut["created_at"])
        if cut["updated_at"]:
            cut["updated_at"] = str(cut["updated_at"])
        # TODO: check if we should just return a track or a timeline?
        timeline = otio.schema.Timeline(name=cut["code"])
        track = otio.schema.Track(name=cut["code"])
        track.metadata["sg"] = cut
        # TODO: check what should be done if these values are not set
        if cut["timecode_end_text"] and cut["timecode_start_text"]:
            start_time = otio.opentime.from_timecode(cut["timecode_start_text"], cut["fps"])
            duration = otio.opentime.from_timecode(cut["timecode_end_text"], cut["fps"]) - start_time
            # We use a negative start time which will be used as an offset for clip record times.
            track.source_range = otio.opentime.TimeRange(
                -start_time,
                duration,
            )
        timeline.tracks.append(track)

        # Retrieve all the Shot fields we need to retrieve from CutItems
        linked_entity_type = None
        if cut["entity"]:
            linked_entity_type = cut["entity"]["type"]
        sg_shot_fields = SGShotFieldsConfig(
            self._sg, linked_entity_type
        ).all
        # Shot fields as reachable from the CutItems
        shot_cut_item_fields = ["shot.Shot.%s" % field for field in sg_shot_fields]

        cut_items = self._sg.find(
            "CutItem",
            [["cut", "is", cut]],
            # TODO: respeed and effects are just checkboxes on SG, and some information added to the description,
            #       so we can't really retrieve them and include them in the clips.
            _CUT_ITEM_FIELDS + shot_cut_item_fields,
            order=[{"field_name": "cut_order", "direction": "asc"}]
        )
        if not cut_items:
            logger.warning(
                "Couldn't retrieve any SG CutItem linked to Cut %s (%s)" % (
                    cut["code"], cut["id"]
                )
            )
        cut_item_version_ids = [
            cut_item["version"]["id"] for cut_item in cut_items if cut_item["version"]
        ]
        published_files_by_version_id = {}
        versions_with_no_published_files_by_id = {}
        if cut_item_version_ids:
            # Find Published Files of type mov associated to the Version of the Cut Item.
            published_files = self._sg.find(
                "PublishedFile",
                [
                    ["version.Version.id", "in", cut_item_version_ids],
                    ["published_file_type.PublishedFileType.code", "is", "mov"]
                ],
                _PUBLISHED_FILE_FIELDS,
                order=[{"field_name": "id", "direction": "desc"}]
            )
            # If there are multiple Published Files for the same Version, take the first one.
            for published_file in published_files:
                if published_file["version.Version.id"] not in published_files_by_version_id:
                    published_files_by_version_id[published_file["version.Version.id"]] = published_file

            # If there are Cut Items without a Published File, check for a Version, and if found,
            # we can use its sg_uploaded_movie as a Media Reference's target_url.
            versions_with_no_published_files_ids = list(set(cut_item_version_ids) - set(published_files_by_version_id.keys()))
            if versions_with_no_published_files_ids:
                versions_with_no_published_files = self._sg.find(
                    "Version",
                    [["id", "in", versions_with_no_published_files_ids]],
                    _VERSION_FIELDS
                )
                versions_with_no_published_files_by_id = {version["id"]: version for version in versions_with_no_published_files}

        platform_name = get_platform_name()
        # Check for gaps and overlaps
        for i, cut_item in enumerate(cut_items):
            if i > 0:
                prev_cut_item = cut_items[i - 1]
                if prev_cut_item["edit_out"]:
                    prev_edit_out = otio.opentime.from_frames(prev_cut_item["edit_out"], cut["fps"])
                elif prev_cut_item["timecode_edit_out_text"]:
                    prev_edit_out = otio.opentime.from_timecode(prev_cut_item["timecode_edit_out_text"], cut["fps"])
                else:
                    raise ValueError(
                        "No edit_out nor timecode_edit_out_text found for cut_item %s" % prev_cut_item
                    )
                # We start frame numbering at one
                # since timecode out is exclusive we just use it to not do 1 + value -1
                if cut_item["edit_in"]:
                    edit_in = otio.opentime.from_frames(cut_item["edit_in"] - 1, cut["fps"])
                elif cut_item["timecode_edit_in_text"]:
                    edit_in = otio.opentime.from_timecode(cut_item["timecode_edit_in_text"], cut["fps"])
                else:
                    raise ValueError(
                        "No edit_in nor timecode_edit_in_text found for cut_item %s" % cut_item
                    )
                # Check if there's an overlap of clips and flag it.
                if prev_edit_out > edit_in:
                    raise ValueError("Overlapping cut items detected: %s ends at %s but %s starts at %s" % (
                        prev_cut_item["code"], prev_edit_out.to_timecode(), cut_item["code"], edit_in.to_timecode()
                    ))
                # Check if there's a gap between the two clips and add a gap if there is.
                if edit_in > prev_edit_out:
                    logger.debug("Adding gap between cut items %s (ends at %s) and %s (starts at %s)" % (
                        prev_cut_item["code"], prev_edit_out.to_timecode(), cut_item["code"], edit_in.to_timecode()
                    ))
                    gap = otio.schema.Gap()
                    gap.source_range = otio.opentime.TimeRange(
                        start_time=otio.opentime.RationalTime(0, cut["fps"]),
                        duration=edit_in - prev_edit_out
                    )
                    track.append(gap)
            # Populate Shot values directly on the "shot" key
            if cut_item["shot"]:
                for field in sg_shot_fields:
                    cut_item["shot"][field] = cut_item["shot.Shot.%s" % field]
            clip = otio.schema.Clip()
            # Not sure if there is a better way to allow writing to EDL and getting the right
            # Reel name without having this dependency to the CMX adapter.
            clip.metadata["cmx_3600"] = {"reel": cut_item["code"]}
            clip.metadata["sg"] = cut_item
            clip.name = cut_item["code"]
            # We don't use the cut in cut out values but rather the original source
            # range from the Clip.
            # It means that frame ranges for media references retrieved from SG need
            # to be remapped to the source range when added to the Clip.
            clip.source_range = otio.opentime.range_from_start_end_time(
                otio.opentime.from_timecode(cut_item["timecode_cut_item_in_text"], cut["fps"]),
                otio.opentime.from_timecode(cut_item["timecode_cut_item_out_text"], cut["fps"])
            )
            cut_item_version_id = cut_item["version.Version.id"]
            if cut_item_version_id in published_files_by_version_id.keys():
                # Cut Item has a Published File, use it to create a Media Reference,
                # with SG metadata about it.
                published_file = published_files_by_version_id[cut_item_version_id]
                self.add_publish_file_media_reference_to_clip(clip, published_file, platform_name, cut_item)
            elif cut_item_version_id in versions_with_no_published_files_by_id.keys():
                # Cut Item has no Published File, use its Version to create a Media Reference.
                # The SG Metadata is a Published File with ID None, and information about the Version
                # in version, and version.Version.XXX fields present in _PUBLISHED_FILE_FIELDS.
                version = versions_with_no_published_files_by_id[cut_item_version_id]
                # If there's no uploaded movie, we can't create a media reference.
                if version["sg_uploaded_movie"]:
                    self.add_version_media_reference_to_clip(clip, version, cut_item)
            # If it was linked to a Version or a Published File, prefer that as the reel name.
            pf = clip.media_reference.metadata.get("sg")
            if pf:
                pf_name = pf["code"] or pf["version.Version.code"]
                clip.metadata["cmx_3600"]["reel"] = pf_name
            track.append(clip)
        return timeline

    @staticmethod
    def add_publish_file_media_reference_to_clip(clip, published_file, platform_name, cut_item=None):
        """
        Add a Media Reference to a clip from a PublishedFile.

        :param clip: A :class:`otio.schema.Clip` or :class:`CutClip` instance.
        :param published_file: A SG PublishedFile entity.
        :param cut_item: A SG CutItem entity or ``None``.
        :param platform_name: The platform name.
        """
        path_field = "local_path_%s" % platform_name
        url = "file://%s" % published_file["path"][path_field]
        first_frame = published_file["version.Version.sg_first_frame"]
        last_frame = published_file["version.Version.sg_last_frame"]
        name = published_file["code"]
        media_available_range = None
        if cut_item and first_frame and last_frame:
            # The visible range of the clip is taken from
            # timecode_cut_item_in_text and timecode_cut_item_out_text,
            # but cut_item_in, cut_item_out (on CutItem) and first_frame,
            # last_frame (on Version) have an offset of head_in + head_duration.
            # Since we cannot know what the offset is, we check the offset between cut_item_in and first_frame,
            # and that tells us what is the offset between visible range and available range.
            start_time_offset = cut_item["cut_item_in"] - first_frame
            duration = last_frame - first_frame + 1
            rate = clip.source_range.start_time.rate
            media_available_range = otio.opentime.TimeRange(
                clip.source_range.start_time - otio.opentime.RationalTime(start_time_offset, rate),
                otio.opentime.RationalTime(duration, rate)
            )
        clip.media_reference = otio.schema.ExternalReference(
            target_url=url,
            available_range=media_available_range,
        )
        clip.media_reference.name = name
        for field in _PUBLISHED_FILE_FIELDS:
            if field.startswith("version.Version"):
                published_file["version"][field.replace("version.Version.", "")] = published_file[field]
        clip.media_reference.metadata["sg"] = published_file

    def add_media_references_from_sg(self, track, project):
        """
        Add Media References from SG to clips in a track.

        For clips that don't have a Media Reference, try to find one in SG.

        :param track: A :class:`otio.schema.Track` instance.
        :param sg: A SG session handle.
        :param project: A SG Project entity.
        """
        # TODO: check if this is needed? It seems it is only called in test_utils
        # and nowhere else. Should the add_publish_file_media_reference_to_clip and
        # add_version_media_reference_to_clip be tested instead? #9393
        clips_with_no_media_references = []
        clip_media_names = []
        for i, clip in enumerate(track.find_clips()):
            if clip.media_reference.is_missing_reference:
                clips_with_no_media_references.append(clip)
                clip_media_names.append(compute_clip_version_name(clip, i + 1))
            # TODO: Deal with clips with media references with local filepaths that cannot be found.
        if not clips_with_no_media_references:
            return
        sg_published_files = self._sg.find(
            "PublishedFile",
            [
                ["project", "is", project],
                ["code", "in", clip_media_names],
                # If there is no Version linked to the PublishedFile,
                # we don't want to consider it
                ["version", "is_not", None],
                ["published_file_type.PublishedFileType.code", "is", "mov"]
            ],
            _PUBLISHED_FILE_FIELDS,
            order=[{"field_name": "id", "direction": "desc"}]
        )
        # If there are multiple published files with the same name, take the first one only.
        sg_published_files_by_code = {}
        for published_file in sg_published_files:
            if published_file["code"] not in sg_published_files_by_code:
                sg_published_files_by_code[published_file["code"]] = published_file
        # If a published file is not found, maybe a Version can be used.
        missing_names = list(set(clip_media_names) - set(sg_published_files_by_code.keys()))
        sg_versions = []
        if missing_names:
            sg_versions = self._sg.find(
                "Version",
                [
                    ["project", "is", project],
                    ["code", "in", missing_names],
                ],
                _VERSION_FIELDS
            )
        if not sg_published_files and not sg_versions:
            # Nothing was found to link to the clips.
            return
        sg_versions_by_code = {v["code"]: v for v in sg_versions}
        all_versions = sg_versions + [pf["version"] for pf in sg_published_files if pf["version"]]
        sg_cut_items = self._sg.find(
            "CutItem",
            [["project", "is", project], ["version", "in", all_versions]],
            ["cut_item_in", "cut_item_out", "version.Version.id"]
        )
        sg_cut_items_by_version_id = {
            cut_item["version.Version.id"]: cut_item for cut_item in sg_cut_items
        }
        platform_name = get_platform_name()
        for clip, media_name in zip(clips_with_no_media_references, clip_media_names):
            published_file = sg_published_files_by_code.get(media_name)
            if published_file:
                cut_item = sg_cut_items_by_version_id.get(published_file["version.Version.id"])
                self.add_publish_file_media_reference_to_clip(clip, published_file, platform_name, cut_item)
                logger.debug(
                    "Added Media Reference to clip %s from Published File %s" % (
                        clip.name, published_file["code"]
                    )
                )
            else:
                version = sg_versions_by_code.get(media_name)
                if version and version["sg_uploaded_movie"]:
                    cut_item = sg_cut_items_by_version_id.get(version["id"])
                    self.add_version_media_reference_to_clip(clip, version, cut_item)
                    logger.debug(
                        "Added Media Reference to clip %s from Version %s" % (
                            clip.name, version["code"]
                        )
                    )

    @staticmethod
    def add_version_media_reference_to_clip(clip, version, cut_item=None):
        """
        Add a Media Reference to a clip from a Version.

        :param clip: A :class:`otio.schema.Clip` or :class:`CutClip` instance.
        :param version: A SG Version entity.
        :param cut_item: A SG CutItem entity or ``None``.
        """
        media_available_range = None
        rate = clip.source_range.start_time.rate
        if cut_item and version["sg_first_frame"] and version["sg_last_frame"]:
            # The visible range of the clip is taken from
            # timecode_cut_item_in_text and timecode_cut_item_out_text,
            # but cut_item_in, cut_item_out (on CutItem) and first_frame,
            # last_frame (on Version) have an offset of head_in + head_duration.
            # Since we cannot know what the offset is, we check the offset between cut_item_in and first_frame,
            # and that tells us what is the offset between visible range and available range.
            start_time_offset = cut_item["cut_item_in"] - version["sg_first_frame"]
            duration = version["sg_last_frame"] - version["sg_first_frame"] + 1
            media_available_range = otio.opentime.TimeRange(
                clip.source_range.start_time - otio.opentime.RationalTime(start_time_offset, rate),
                otio.opentime.RationalTime(duration, rate)
            )
        # TODO: what can be done with AWS links expiring? should we download the movie somewhere?
        clip.media_reference = otio.schema.ExternalReference(
            target_url=version["sg_uploaded_movie"]["url"],
            available_range=media_available_range,
        )
        clip.media_reference.name = version["code"]
        # The SG metadata should be a published file, but since we only have the Version,
        # set all Published File fields as None, except the version.Version.XXX fields.
        pf_data = {
            "type": "PublishedFile",
            "id": None,
        }
        for field in _PUBLISHED_FILE_FIELDS:
            if field.startswith("version.Version"):
                pf_data[field] = version[field.replace("version.Version.", "")]
            else:
                pf_data[field] = None
        clip.media_reference.metadata["sg"] = pf_data
