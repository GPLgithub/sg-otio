# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging
import os
import sys

from opentimelineio.opentime import RationalTime

# Relative imports don't work with the way OTIO loads adapters.
from .constants import _ENTITY_CUT_ORDER_FIELD, _ABSOLUTE_CUT_ORDER_FIELD
from .constants import _EFFECTS_FIELD, _RETIME_FIELD
# from .sg_settings import SGShotFieldsConfig
from .cut_track import CutTrack
from .cut_clip import CutClip

try:
    # For Python 3.4 or later
    import pathlib
except ImportError:
    # fallback to library in required packages
    import pathlib2 as pathlib

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class SGCutTrackWriter(object):
    """
    A class to save a :class:`otio.schema.Track` of kind ``otio.schema.TrackKind.Video``
    in Shotgrid.
    """

    # The CutItem schema in ShotGrid. Make it a class variable to get it only once.
    _cut_item_schema = None

    def __init__(self, sg, log_level=logging.INFO):
        """
        SGCutTrackWriter constructor.

        :param sg: A ShotGrid API session instance.
        :param log_level: The log level to use.
        """
        logger.setLevel(log_level)
        self._sg = sg
        # FIXME: if another SG site is later used the schema will not be updated.
        if not self._cut_item_schema:
            self._cut_item_schema = self._sg.schema_field_read("CutItem")

    def get_sg_cut_payload(self, cut_track, sg_user=None, description=""):
        """
        """
        # If the track starts at 00:00:00:00, for some reason it does not have a source range.
        if cut_track.source_range:
            # The source range is set with a negative offset to use it as an
            # offset when computing clips record times.
            track_start = -cut_track.source_range.start_time
        else:
            track_start = RationalTime(0, cut_track.duration().rate)
        track_end = track_start + cut_track.duration()
        cut_payload = {
            "code": cut_track.name,
            "fps": cut_track.duration().rate,
            "timecode_start_text": track_start.to_timecode(),
            "timecode_end_text": track_end.to_timecode(),
            "duration": cut_track.duration().to_frames(),
        }
        if sg_user:
            cut_payload["created_by"] = sg_user
            cut_payload["updated_by"] = sg_user
        if description:
            cut_payload["description"] = description
#        if input_media_version:
#            cut_payload["version"] = input_media_version
        return cut_payload

    def get_sg_cut_item_payload(self, cut_clip, sg_user=None, sg_shot=None):
        """
        Get a SG CutItem payload for a given :class:`sg_otio.CutClip` instance.

        An absolute cut order can be set on CutItems if the `sg_absolute_cut_order`
        integer field was added to the SG CutItem schema. This absolute cut order
        is meant to be the cut order of the CutItem in the Project and is based on
        a cut order value set on the Entity (Reel, Sequence, etc...) the Cut is
        imported against. The absolute cut order is then:
        `1000 * entity cut order + edit cut order`.

        :returns: A dictionary with the CutItem payload.
        :raises ValueError: If no SG payload can be generated for this Clip
        """
        description = ""
        cut_item_payload = {
            "code": cut_clip.name or "foo",
            "timecode_cut_item_in_text": cut_clip.source_in.to_timecode(),
            "timecode_cut_item_out_text": cut_clip.source_out.to_timecode(),
            "timecode_edit_in_text": cut_clip.record_in.to_timecode(),
            "timecode_edit_out_text": cut_clip.record_out.to_timecode(),
            "cut_item_in": cut_clip.cut_in.to_frames(),
            "cut_item_out": cut_clip.cut_out.to_frames(),
            "edit_in": cut_clip.edit_in.to_frames(),
            "edit_out": cut_clip.edit_out.to_frames(),
            "cut_item_duration": cut_clip.visible_duration.to_frames(),
            # TODO: Add support for Linking/Creating Versions + Published Files
            # "version": cut_diff.sg_version,
        }
        if sg_shot:
            cut_item_payload["shot"] = sg_shot
        if sg_user:
            cut_item_payload["created_by"] = sg_user
            cut_item_payload["updated_by"] = sg_user

        if cut_clip.has_effects:
            description = "%s\nEffects: %s" % (
                description,
                self.effects_str
            )
        if _EFFECTS_FIELD in self._cut_item_schema:
            cut_item_payload[_EFFECTS_FIELD] = cut_clip.has_effects

        if cut_clip.has_retime:
            description = "%s\nRetime: %s" % (description, self.retime_str)
        if _RETIME_FIELD in self._cut_item_schema:
            cut_item_payload[_RETIME_FIELD] = cut_clip.has_retime

        cut_item_payload["description"] = description
        return cut_item_payload

    def write_to(self, entity_type, entity_id, video_track, sg_user=None, description=""):
        """
        """
        sg_cut = None
        sg_project = None
        sg_linked_entity = None
        # Retrieve the target entity
        if entity_type == "Cut":
            sg_cut = self._sg.find_one(
                entity_type,
                [["id", "is", entity_id]],
                ["project"]
            )
            if not sg_cut:
                raise ValueError(
                    "Unable to retrieve a %s with the id %s" % (entity_type, entity_id)
                )
            sg_project = sg_cut["project"]
        elif entity_type == "Project":
            sg_project = self._sg.find_one(
                entity_type,
                [["id", "is", entity_id]],
            )
            if not sg_project:
                raise ValueError(
                    "Unable to retrieve a %s with the id %s" % (entity_type, entity_id)
                )
        else:
            sg_linked_entity = self._sg.find_one(
                entity_type,
                [["id", "is", entity_id]],
                ["project"]
            )
            if not sg_linked_entity:
                raise ValueError(
                    "Unable to retrieve a %s with the id %s" % (entity_type, entity_id)
                )
            sg_project = sg_linked_entity["project"]
        if not sg_project:
            raise ValueError("Unable to retrieve a Project from %s %s")

        cut_track = video_track
        sg_track_data = video_track.metadata.get("sg")
        if sg_track_data and sg_track_data["type"] != "Cut":
            raise ValueError(
                "Invalid {} SG data for a {}".format(sg_track_data["type"], "Cut")
            )
        # Convert to a CutTrack if one was not provided.
        if not isinstance(cut_track, CutTrack):
            cut_track = CutTrack.from_track(video_track)
        sg_cut_data = self.get_sg_cut_payload(cut_track, sg_user, description)
        sg_cut_items_data = []
        cut_item_clips = []
        # Loop over clips from the cut_track
        # Keep references to original clips
        video_clips = list(video_track.each_clip())
        for i, clip in enumerate(cut_track.each_clip()):
            if not isinstance(clip, CutClip):
                continue
            sg_data = self.get_sg_cut_item_payload(clip)
            sg_cut_items_data.append(sg_data)
            # Make sure we keep a reference to the original clip to able to set
            # SG metadata.
            cut_item_clips.append(video_clips[i])

#        if input_media_version:
#            cut_payload["version"] = input_media_version
        if sg_cut:  # Update existing Cut
            logger.info("Cut update payload %s" % sg_cut_data)
            self._sg.update(
                sg_cut["type"],
                sg_cut["id"],
                sg_cut_data,
            )
        else:
            revision_number = 1
            previous_cut = self._sg.find_one(
                "Cut",
                [
                    ["code", "is", video_track.name],
                    ["entity", "is", sg_linked_entity or sg_project],
                ],
                ["revision_number"],
                order=[{"field_name": "revision_number", "direction": "desc"}]
            )
            if previous_cut:
                revision_number = (previous_cut.get("revision_number") or 0) + 1
            # Create a new Cut
            sg_cut_data["project"] = sg_project
            sg_cut_data["entity"] = sg_linked_entity or sg_project
            sg_cut_data["revision_number"] = revision_number
            logger.info("Cut create payload %s" % sg_cut_data)

            sg_cut = self._sg.create(
                "Cut",
                sg_cut_data,
            )
            # Update the track with the result
            logger.info("Updating %s SG metadata with %s" % (video_track, sg_cut))
            video_track.metadata["sg"] = sg_cut
        batch_data = []
        linked_entity = sg_linked_entity or sg_project
        for item_index, sg_cut_item_data in enumerate(sg_cut_items_data):
            sg_cut_item_data["cut"] = sg_cut
            sg_cut_item_data["project"] = sg_project
            sg_cut_item_data["cut_order"] = item_index + 1
            if (
                _ABSOLUTE_CUT_ORDER_FIELD in self._cut_item_schema
                and linked_entity.get(_ENTITY_CUT_ORDER_FIELD)
            ):
                sg_cut_item_data[_ABSOLUTE_CUT_ORDER_FIELD] = (
                    1000
                    * linked_entity[_ENTITY_CUT_ORDER_FIELD]
                    + sg_cut_item_data["cut_order"]
                )

            # Check if we should update an existing CutItem of create a new one
            sg_cut_item = cut_item_clips[item_index].metadata.get("sg") or {}
            if sg_cut_item.get("id"):
                # Check if the CutItem is linked to the Cut we updated or created.
                # If not, create a new CutItem.
                if sg_cut_item.get("cut") and sg_cut_item["cut"].get("id") == sg_cut["id"]:
                    batch_data.append({
                        "request_type": "update",
                        "entity_type": "CutItem",
                        "entity_id": sg_cut_item["id"],
                        "data": sg_cut_item_data
                    })
                else:
                    batch_data.append({
                        "request_type": "create",
                        "entity_type": "CutItem",
                        "data": sg_cut_item_data
                    })
            else:
                batch_data.append({
                    "request_type": "create",
                    "entity_type": "CutItem",
                    "data": sg_cut_item_data
                })
        if batch_data:
            res = self._sg.batch(batch_data)
            # Update the clips SG metadata
            for i, sg_cut_item in enumerate(res):
                cut_item_clips[i].metadata["sg"] = sg_cut_item
                logger.info("Updating %s SG metadata with %s" % (cut_item_clips[i], sg_cut_item))

    @staticmethod
    def _retrieve_local_storage(sg, local_storage_name):
        """
        Retrieve a Local Storage path given its name.

        :param sg: A ShotGrid API session instance.
        :param str local_storage_name: The name of the Local Storage.
        :raises ValueError: If LocalStorages can't be retrieved.
        :raises RuntimeError: If the platform is not supported.
        :returns: A SG Local Storage entity.
        """
        platform = sys.platform
        if platform == "win32":
            path_field = "windows_path"
        elif platform == "darwin":
            path_field = "mac_path"
        elif platform.startswith("linux"):
            path_field = "linux_path"
        else:
            raise RuntimeError("Platform %s is not supported" % platform)

        local_storage = sg.find_one(
            "LocalStorage",
            [["code", "is", local_storage_name]],
            [path_field]
        )
        if not local_storage:
            raise ValueError(
                "Unable to retrieve a Local Storage with the name %s" % local_storage_name
            )
        # Update the dictionary so that there is a "path" key no matter what the platform is.
        local_storage["path"] = local_storage[path_field]
        return local_storage

    def _create_input_media_version(self):
        """
        Creates a Version and a Published File for an input media
        representing the whole Timeline.

        :returns: A tuple of (SG Version, SG PublishedFile).
        """
        # Create the Version
        version_name, file_extension = os.path.splitext(os.path.basename(self._input_media))
        # Get the extension without '.' to use as a published_file_type
        file_extension = file_extension[1:]
        published_file_type = self._sg.find_one(
            "PublishedFileType",
            [["code", "is", file_extension]]
        )
        if not published_file_type:
            logger.info("Creating %s PublishedFileType..." % file_extension)
            published_file_type = self._sg.create(
                "PublishedFileType",
                {"code": file_extension}
            )
        version_payload = {
            "project": self._project,
            "code": version_name,
            "entity": self._linked_entity,
            "description": "Base media layer imported with Cut: %s" % self._track.name,
            "sg_first_frame": 1,
            "sg_movie_has_slate": False,
            "sg_path_to_movie": self._input_media,
        }
        if self._user:
            version_payload["created_by"] = self._user
            version_payload["updated_by"] = self._user
        version = self._sg.create("Version", version_payload)
        # Create the Published File
        # Check if we can publish it with a local file path instead of a URL
        if self._local_storage and self._input_media.startswith(self._local_storage["path"]):
            relative_path = self._input_media[len(self._local_storage["path"]):]
            # Get rid of double slashes and replace backslashes by forward slashes.
            # SG doesn't seem to accept backslashes when creating
            # PublishedFiles with relative paths to local storage
            relative_path = os.path.normpath(relative_path)
            relative_path = relative_path.replace("\\", "/")
            publish_path = {
                "relative_path": relative_path,
                "local_storage": self._local_storage
            }
        else:
            publish_path = {
                "url": pathlib.Path(os.path.abspath(self._input_media)).as_uri(),
                "name": version_name,
            }
        published_file_payload = {
            "code": version_name,
            "project": self._project,
            "entity": self._linked_entity,
            "path": publish_path,
            "published_file_type": published_file_type,
            "version_number": 1,
            "version": version
        }
        if self._user:
            published_file_payload["created_by"] = self._user
            published_file_payload["updated_by"] = self._user
        published_file = self._sg.create("PublishedFile", published_file_payload)

        # Upload media to the version.
        logger.info("Uploading movie...")
        self._sg.upload(
            "Version",
            version["id"],
            self._input_media,
            "sg_uploaded_movie"
        )
        return version, published_file

    def _create_or_update_sg_shots(self):
        """
        Create or update SG Shots based.
        """
        sg_batch_data = []
        sfg = self._shot_fields_config
        for shot_code, cut_items in self._cut_items_by_shot.items():
            sg_shot = cut_items[0].sg_shot
            # Some SGCutItems might not have information about their SG Shot name (ex: Gaps).
            # In this case we cannot create or update the SG Shot.
            if not shot_code:
                continue
            elif not sg_shot:
                logger.debug("Will create Shot %s" % shot_code)
                shot_index, head_in, cut_in, cut_out, tail_out, has_effects, has_retime = self._get_shot_cut_values(cut_items)
                shot_payload = {
                    "project": self._project,
                    "code": shot_code,
                    sfg.head_in: head_in.to_frames(),
                    sfg.cut_in: cut_in.to_frames(),
                    sfg.cut_out: cut_out.to_frames(),
                    sfg.tail_out: tail_out.to_frames(),
                    sfg.cut_duration: (cut_out - cut_in).to_frames() + 1,
                    sfg.cut_order: shot_index,
                }
                head_out_frames = cut_in.to_frames() - 1
                tail_in_frames = cut_out.to_frames() + 1
                if sfg.working_duration:
                    shot_payload[sfg.working_duration] = (tail_out - head_in).to_frames()
                if sfg.head_out:
                    shot_payload[sfg.head_out] = head_out_frames
                if sfg.head_duration:
                    shot_payload[sfg.head_duration] = head_out_frames - head_in.to_frames() + 1
                if sfg.tail_in:
                    shot_payload[sfg.tail_in] = tail_in_frames
                if sfg.tail_duration:
                    shot_payload[sfg.tail_duration] = tail_out.to_frames() - tail_in_frames + 1
                if self._flag_retimes_and_effects:
                    shot_payload[sfg.has_effects] = has_effects
                    shot_payload[sfg.has_retime] = has_retime
                if sfg.absolute_cut_order:
                    entity_cut_order = self._linked_entity.get(sfg.absolute_cut_order)
                    if entity_cut_order:
                        absolute_cut_order = 1000 * entity_cut_order + shot_index
                        shot_payload[sfg.absolute_cut_order] = absolute_cut_order
                if sfg.shot_link_field:
                    shot_payload[sfg.shot_link_field] = self._linked_entity
                sg_batch_data.append({
                    "request_type": "create",
                    "entity_type": "Shot",
                    "data": shot_payload
                })
            else:
                # TODO: Add update logic
                pass
        if sg_batch_data:
            shots = self._sg.batch(sg_batch_data)
            for shot in shots:
                cut_items = self._cut_items_by_shot[shot["code"]]
                for cut_item in cut_items:
                    if cut_item.sg_shot:
                        cut_item.sg_shot.update(shot)
                    else:
                        cut_item.sg_shot = shot

    def _get_shot_cut_values(self, cut_items):
        """
        Return data about the Shot cut values based on its SGCutItems.

        Return a tuple with :
        - The smallest clip index
        - The earliest head in
        - The earliest cut in
        - The last cut out
        - The last tail out
        - If at least one clip has effects
        - If at least one clip has retimes

        :returns: A tuple.
        """
        min_clip_index = None
        min_head_in = None
        min_cut_in = None
        max_cut_out = None
        max_tail_out = None
        has_effects = False
        has_retime = False
        for cut_item in cut_items:
            if min_clip_index is None or cut_item.clip_index < min_clip_index:
                min_clip_index = cut_item.clip_index
            if min_head_in is None or cut_item.head_in < min_head_in:
                min_head_in = cut_item.head_in
            if min_cut_in is None or cut_item.cut_in < min_cut_in:
                min_cut_in = cut_item.cut_in
            if max_cut_out is None or cut_item.cut_out > max_cut_out:
                max_cut_out = cut_item.cut_out
            if max_tail_out is None or cut_item.tail_out > max_tail_out:
                max_tail_out = cut_item.tail_out
            if cut_item.has_effects:
                has_effects = True
            if cut_item.has_retime:
                has_retime = True
        return min_clip_index, min_head_in, min_cut_in, max_cut_out, max_tail_out, has_effects, has_retime

    def _create_sg_cut_items(self):
        """
        Creates SG CutItems for each clip of the input :class:`otio.schema.Timeline` instance.

        :param sg_cut: The SG Cut to create the CutItems for.
        :returns: A list of SG CutItems.
        """
        batch_data = []
        logger.info("Creating CutItems...")
        # Get the cut items by name for easy update after creation.
        cut_items_by_name = dict((val.name, val) for lst in self._cut_items_by_shot.values() for val in lst)
        for cut_item in cut_items_by_name.values():
            batch_data.append({
                "request_type": "create",
                "entity_type": "CutItem",
                "data": cut_item.payload
            })
        if batch_data:
            res = self._sg.batch(batch_data)
            for sg_cut_item in res:
                cut_item = cut_items_by_name[sg_cut_item["code"]]
                cut_item.sg_cut_item = sg_cut_item
