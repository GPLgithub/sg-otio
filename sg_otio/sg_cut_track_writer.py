# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import datetime
import logging
import os
import shutil

import opentimelineio as otio
from opentimelineio.opentime import RationalTime

from .constants import _EFFECTS_FIELD, _RETIME_FIELD
from .constants import _ENTITY_CUT_ORDER_FIELD, _ABSOLUTE_CUT_ORDER_FIELD
from .cut_clip import CutClip
from .cut_track import CutTrack
from .media_uploader import MediaUploader
from .sg_settings import SGShotFieldsConfig, SGSettings
from .utils import get_available_filename, compute_clip_version_name, get_platform_name

try:
    # For Python 3.4 or later
    import pathlib
except ImportError:
    # fallback to library in required packages
    import pathlib2 as pathlib

logger = logging.getLogger(__name__)


class SGCutTrackWriter(object):
    """
    A class to save a :class:`otio.schema.Track` of kind ``otio.schema.TrackKind.Video``
    in ShotGrid.

    It gathers information about the track and its clips and creates or updates the
    corresponding ShotGrid Entities.
    """
    # The CutItem schema in ShotGrid, per ShotGrid site. Make it a class variable to get it only once.
    _cut_item_schema = {}

    def __init__(self, sg):
        """
        SGCutTrackWriter constructor.

        :param sg: A ShotGrid API session instance.
        """
        self._sg = sg
        # Local storages by name.
        self._local_storages = {}

    @property
    def cut_item_schema(self):
        """
        Return the Cut Item schema for the current SG site.

        :returns: The Cut Item Schema.
        """
        if not self._cut_item_schema.get(self._sg.base_url):
            self._cut_item_schema[self._sg.base_url] = self._sg.schema_field_read("CutItem")
        return self._cut_item_schema[self._sg.base_url]

    def write_to(self, entity_type, entity_id, video_track, input_media=None, sg_user=None, description=""):
        """
        Gather information about a Cut, its Cut Items and their linked Shots and create
        or update Entities accordingly in SG.

        When writing to SG, The Entity provided (type and ID) can be:
        - The Cut itself
        - The Project
        - Any Entity to link the Cut against (e.g. Sequence, Reel...)

        :param str entity_type: A SG Entity type.
        :param int entity_id: A SG Entity ID.
        :param video_track: An OTIO Video Track or a CutTrack.
        :param str input_media: An optional input media. If provided, a Version will be created for the Cut.
        :param sg_user: An optional SG User which will be registered when creating/updating Entities.
        :param description: An optional description for the Cut.
        """
        cut_track = video_track
        sg_track_data = video_track.metadata.get("sg")
        if sg_track_data and sg_track_data["type"] != "Cut":
            raise ValueError(
                "Invalid {} SG data for a {}".format(sg_track_data["type"], "Cut")
            )
        # Convert to a CutTrack if one was not provided.
        if not isinstance(cut_track, CutTrack):
            # We need to give the track a parent so time transforms from the Clip
            # to the track are correctly evaluated.
            stack = otio.schema.Stack()
            cut_track = CutTrack.from_track(video_track)
            stack.append(cut_track)

        sg_project, sg_cut, sg_linked_entity = self._get_cut_entities(
            entity_type, entity_id
        )
        input_media_version = None
        input_media_pf = None
        if input_media:
            input_media_version, input_media_pf = self._create_input_media_version(
                input_media, cut_track.name, sg_project, sg_linked_entity, sg_user
            )
        sg_cut = self._write_cut(
            video_track, cut_track, sg_project, sg_cut, sg_linked_entity, input_media_version, sg_user, description
        )
        sg_shots = self._write_shots(
            cut_track,
            sg_project,
            sg_linked_entity,
            sg_user
        )
        if SGSettings().create_missing_versions:
            self._write_versions(cut_track, sg_project, sg_linked_entity, input_media_pf, sg_user)
        self._write_cut_items(video_track, cut_track, sg_project, sg_cut, sg_linked_entity, sg_shots, sg_user)

    def _write_cut(
        self,
        video_track,
        cut_track,
        sg_project,
        sg_cut,
        sg_linked_entity,
        sg_version=None,
        sg_user=None,
        description=""
    ):
        """
        Gather information about a SG Cut given a video track, and create or update
        the corresponding Cut in SG.

        Add metadata to the OTIO video Track about the SG Cut.

        :param video_track: An OTIO Video Track.
        :param cut_track: An instance of :class:`CutTrack`.
        :param sg_project: The SG Project to write the Cut to.
        :param sg_cut: If provided, the SG Cut to update.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param sg_media_version: If provided, the SG Version to link to the Cut.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :param str description: An optional description for the Cut.
        :returns: The SG Cut entity created.
        """
        sg_cut_data = self._get_sg_cut_payload(cut_track, sg_version, sg_user, description)
        if sg_cut:
            # Update existing Cut
            logger.info("Updating Cut %s (ID %s)..." % (sg_cut["code"], sg_cut["id"]))
            logger.debug("Cut update payload %s" % sg_cut_data)
            sg_cut = self._sg.update(
                sg_cut["type"],
                sg_cut["id"],
                sg_cut_data,
            )
            video_track.metadata["sg"] = sg_cut
        else:
            revision_number = 1
            previous_cut = self._sg.find_one(
                "Cut",
                [
                    ["code", "is", cut_track.name],
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
            logger.info("Creating Cut %s..." % sg_cut_data["code"])
            logger.debug("Cut create payload %s" % sg_cut_data)
            sg_cut = self._sg.create(
                "Cut",
                sg_cut_data,
            )
            # Update the original track with the result
            logger.info("Updating %s SG metadata with %s" % (video_track.name, sg_cut))
            video_track.metadata["sg"] = sg_cut
        return sg_cut

    def _get_sg_cut_payload(self, cut_track, sg_version=None, sg_user=None, description=""):
        """
        Gather information about a SG Cut given a CutTrack.

        :param cut_track: An instance of :class:`CutTrack`.
        :param sg_version: If provided, the SG Version to link to the Cut.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :param str description: An optional description for the Cut.
        :returns: A dictionary with the SG Cut payload.
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
        if sg_version:
            cut_payload["version"] = {
                "type": sg_version["type"],
                "id": sg_version["id"],
                "code": sg_version["code"],
            }
        if sg_user:
            cut_payload["created_by"] = sg_user
            cut_payload["updated_by"] = sg_user
        if description:
            cut_payload["description"] = description
        return cut_payload

    def _write_cut_items(self, video_track, cut_track, sg_project, sg_cut, sg_linked_entity, sg_shots, sg_user):
        """
        Gather information about the Cut Items given a CutTrack, and create or update the Cut Items in SG
        accordingly.

        Add metadata to the OTIO Clips in the Track about the SG Cut Items.

        :param video_track: An OTIO Video Track.
        :param cut_track: An instance of :class:`CutTrack`.
        :param sg_project: The SG Project to write the Cut to.
        :param sg_cut: If provided, the SG Cut to update.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param sg_shots: A list of SG Shots.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :returns: The SG Cut Items.
        """
        shots_by_name = {x["code"]: x for x in sg_shots}
        shots_by_id = {x["id"]: x for x in sg_shots}
        sg_cut_items_data = []
        cut_item_clips = []

        # Loop over clips from the cut_track
        # Keep references to original clips and their index in the cut_track
        video_clips = list(video_track.each_clip())
        for i, clip in enumerate(cut_track.each_clip()):
            if not isinstance(clip, CutClip):
                continue
            # Get the SG Shot for this clip
            sg_shot = shots_by_name.get(clip.shot_name)
            sg_version = clip.media_reference.metadata.get("sg")
            # Add the Version metadata to the OTIO Clip
            if sg_version:
                video_clips[i].metadata["sg"] = sg_version
                logger.debug("Updating %s SG Version metadata with %s" % (
                    clip.name, sg_version
                ))
            sg_data = self.get_sg_cut_item_payload(clip, sg_shot=sg_shot, sg_version=sg_version, sg_user=sg_user)
            sg_cut_items_data.append(sg_data)

            cut_item_clips.append(video_clips[i])
        batch_data = []
        linked_entity = sg_linked_entity or sg_project
        for item_index, sg_cut_item_data in enumerate(sg_cut_items_data):
            sg_cut_item_data["cut"] = sg_cut
            sg_cut_item_data["project"] = sg_project
            sg_cut_item_data["cut_order"] = item_index + 1
            if (
                _ABSOLUTE_CUT_ORDER_FIELD in self.cut_item_schema
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
                    logger.info("Updating Cut Item %s (ID %s)..." % (sg_cut_item["code"], sg_cut_item["id"]))
                    batch_data.append({
                        "request_type": "update",
                        "entity_type": "CutItem",
                        "entity_id": sg_cut_item["id"],
                        "data": sg_cut_item_data
                    })
                else:
                    logger.info("Creating Cut Item %s..." % sg_cut_item_data["code"])
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
        sg_cut_items = []
        if batch_data:
            res = self._sg.batch(batch_data)
            for i, sg_cut_item in enumerate(res):
                # Set the Shot code we don't get back from the batch request
                if sg_cut_item.get("shot"):
                    sg_cut_item["shot"]["code"] = shots_by_id[sg_cut_item["shot"]["id"]]["code"]
                cut_item_clips[i].metadata["sg"] = sg_cut_item
                sg_cut_items.append(sg_cut_item)
                logger.debug("Updating %s SG metadata with %s" % (
                    clip.name, sg_cut_item)
                )
        return sg_cut_items

    def get_sg_cut_item_payload(self, cut_clip, sg_shot=None, sg_version=None, sg_user=None):
        """
        Get a SG CutItem payload for a given :class:`sg_otio.CutClip` instance.

        An absolute cut order can be set on CutItems if the `sg_absolute_cut_order`
        integer field was added to the SG CutItem schema. This absolute cut order
        is meant to be the cut order of the CutItem in the Project and is based on
        a cut order value set on the Entity (Reel, Sequence, etc...) the Cut is
        imported against. The absolute cut order is then:
        `1000 * entity cut order + edit cut order`.

        :param cut_clip: A :class:`sg_otio.CutClip` instance.
        :param sg_shot: An optional SG Shot to use for the CutItem.
        :param sg_version: An optional SG Version to use for the CutItem.
        :param sg_user: An optional user to provide when creating/updating Cut Items in SG.
        :returns: A dictionary with the CutItem payload.
        :raises ValueError: If no SG payload can be generated for this Clip.
        """
        description = ""
        cut_item_payload = {
            "code": cut_clip.cut_item_name,
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
            cut_item_payload["shot"] = {
                "type": sg_shot["type"],
                "id": sg_shot["id"],
                "code": sg_shot["code"],
            }
        if sg_version:
            cut_item_payload["version"] = {
                "type": sg_version["type"],
                "id": sg_version["id"],
                "code": sg_version["code"],
            }
        if sg_user:
            cut_item_payload["created_by"] = sg_user
            cut_item_payload["updated_by"] = sg_user

        if cut_clip.has_effects:
            description = "%s\nEffects: %s" % (
                description,
                self.effects_str
            )
        if _EFFECTS_FIELD in self.cut_item_schema:
            cut_item_payload[_EFFECTS_FIELD] = cut_clip.has_effects

        if cut_clip.has_retime:
            description = "%s\nRetime: %s" % (description, self.retime_str)
        if _RETIME_FIELD in self.cut_item_schema:
            cut_item_payload[_RETIME_FIELD] = cut_clip.has_retime

        cut_item_payload["description"] = description
        return cut_item_payload

    def _write_versions(self, cut_track, sg_project, sg_linked_entity, cut_published_file=None, sg_user=None):
        """
        For Clips which have a Media Reference, create a Version and a Published file for each one.

        :param cut_track: An instance of :class:`CutTrack`.
        :param sg_project: The SG Project to write the Cut to.
        :param sg_cut: If provided, the SG Cut to update.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param cut_published_file: If provided, the Cut's Published File.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :returns: A list of SG Versions, if any.
        """
        clips_with_media_refs = []
        clips_version_names = []
        for i, clip in enumerate(cut_track.each_clip()):
            # Only treat clips with a Media Reference.
            if clip.media_reference.is_missing_reference:
                logger.debug(
                    "Clip %s has no Media Reference, skipping Version creation" % clip.name
                )
                continue
            # Only treat clips that have an available range.
            if not clip.media_reference.available_range:
                logger.warning(
                    "Clip %s has a Media Reference %s with no available range, skipping Version creation." % (
                        clip.name, clip.media_reference
                    ))
                continue
            media_reference_path = clip.media_reference.target_url
            # Premiere XMLs start with file://localhost followed by an absolute path.
            media_reference_path = media_reference_path.replace("file://localhost", "")
            # EDLs start with file:// followed by an absolute path.
            media_reference_path = media_reference_path.replace("file://", "")
            if not os.path.exists(media_reference_path):
                logger.warning(
                    "Clip %s has a Media Reference %s not found locally, skipping Version creation." % (
                        clip.name, clip.media_reference
                    ))
                continue
            # Make sure that the clip's media reference has a proper computed name.
            version_name = compute_clip_version_name(clip, i + 1)
            clips_version_names.append(version_name)
            clip.media_reference.name = version_name
            clips_with_media_refs.append(clip)
        # Skip the creation of Versions if they already exist in SG.
        existing_sg_versions = self._sg.find(
            "Version",
            [["code", "in", clips_version_names]],
            ["code"]
        )
        sg_version_codes = [version["code"] for version in existing_sg_versions]

        date = datetime.datetime.now()
        versions_path_template = SGSettings().versions_path_template
        linked_entity = sg_linked_entity or sg_project
        local_storage = self._retrieve_local_storage()
        published_file_type = "mov"
        sg_published_file_type = self._sg.find_one(
            "PublishedFileType",
            [["code", "is", published_file_type]]
        )
        if not sg_published_file_type:
            logger.info("Creating %s PublishedFileType..." % published_file_type)
            sg_published_file_type = self._sg.create(
                "PublishedFileType",
                {"code": published_file_type}
            )
        data = {
            "PROJECT": sg_project["name"],
            "CUT_TITLE": cut_track.name,
            "LINK": linked_entity.get("code") or linked_entity.get("name") or "",
            "HH": date.strftime("%H"),
            "DD": date.strftime("%d"),
            "MM": date.strftime("%m"),
            "YY": date.strftime("%y"),
            "YYYY": date.strftime("%Y"),
        }
        # Store versions data by code since it will be useful when
        # creating the PublishedFiles and their dependencies.
        versions_data = {}
        for clip in clips_with_media_refs:
            if clip.media_reference.name in sg_version_codes:
                logger.debug("Clip %s has already a Version %s in SG. Skipping Creation" % (
                    clip.name, clip.media_reference.name
                ))
                continue
            # If there's no shot, we'll use the linked_entity or the project as
            # a Version link.
            # Note that this means that if {SHOT} is used in the template,
            # formatting will fail.
            sg_shot = clip.metadata.get("sg", {}).get("shot")
            version_name = clip.media_reference.name
            logger.info("Creating Version %s for clip %s..." % (version_name, clip.name))
            data["SHOT"] = sg_shot
            version_relative_path = versions_path_template.format(**data)
            version_path = os.path.join(local_storage["path"], version_relative_path)
            version_file_path = get_available_filename(version_path, version_name, "mov")
            version_relative_file_path = os.path.join(
                version_relative_path,
                os.path.basename(version_file_path)
            )
            if not os.path.exists(version_path):
                os.makedirs(version_path)
            # Copy the file to the right path
            media_reference_path = clip.media_reference.target_url
            # Premiere XMLs start with file://localhost followed by an absolute path.
            media_reference_path = media_reference_path.replace("file://localhost", "")
            # EDLs start with file:// followed by an absolute path.
            media_reference_path = media_reference_path.replace("file://", "")
            shutil.copyfile(
                media_reference_path,
                version_file_path
            )
            # Replace the media reference with the proper file path.
            clip.media_reference.target_url = "file://%s" % version_file_path
            # The first frame and the last frame depend on the cut in and the media's available range.
            # This is because the media can be shorter or longer than the cut in and out.
            first_frame_offset = clip.available_range().start_time - clip.visible_range().start_time
            first_frame = clip.cut_in + first_frame_offset
            last_frame = first_frame + clip.available_range().duration
            # The Version always starts at head_in + head_in_duration.
            version_data = {
                "code": version_name,
                "project": sg_project,
                "sg_first_frame": first_frame.to_frames(),
                "sg_last_frame": last_frame.to_frames(),
                # If no shot is provided, link the Version to the linked entity.
                "entity": sg_shot or linked_entity,
                "sg_path_to_movie": version_file_path
            }

            if sg_user:
                version_data["created_by"] = sg_user
                version_data["updated_by"] = sg_user
            # Get rid of double slashes and replace backslashes by forward slashes.
            # SG doesn't seem to accept backslashes when creating
            # PublishedFiles with relative paths to local storage
            version_relative_file_path = os.path.normpath(version_relative_file_path)
            version_relative_file_path = version_relative_file_path.replace("\\", "/")
            publish_path = {
                "relative_path": version_relative_file_path,
                "local_storage": local_storage,
                "local_path": version_file_path
            }
            published_file_data = {
                "code": version_name,
                "name": version_name,
                "project": sg_project,
                "entity": sg_shot,
                "path": publish_path,
                "published_file_type": sg_published_file_type,
                "version_number": 1,
                "path_cache": version_relative_file_path,
                "version": None,  # Will be set after the Version is created
            }
            if sg_user:
                published_file_data["created_by"] = sg_user
                published_file_data["updated_by"] = sg_user
            published_file_dependency_data = None
            if cut_published_file:
                published_file_dependency_data = {
                    "published_file": None,  # Will be set after the PublishedFile is created
                    "dependent_published_file": {
                        "type": "PublishedFile",
                        "id": cut_published_file["id"],
                    }
                }
            # Since multiple Versions can have the same code, differentiate them
            # by code, and sg_path_to_movie.
            versions_data[
                (version_data["code"], version_data["sg_path_to_movie"])
            ] = {
                "version": version_data,
                "published_file": published_file_data,
                "published_file_dependency": published_file_dependency_data,
                "version_file_path": version_file_path,
            }
        # Create the Versions and PublishedFiles and their dependencies,
        # and upload the movies for each Version.
        if versions_data:
            versions_batch_data = [
                {
                    "request_type": "create",
                    "entity_type": "Version",
                    "data": vdata["version"],
                } for vdata in versions_data.values()
            ]
            sg_versions = self._sg.batch(versions_batch_data)
            # Update the versions_data with the newly created versions.
            for sg_version in sg_versions:
                version_data = versions_data[
                    (sg_version["code"], sg_version["sg_path_to_movie"])
                ]
                version_data["version"] = sg_version
                version_data["published_file"]["version"] = sg_version
                # Also update the clip's media_reference metadata with the sg_version.
                for clip in clips_with_media_refs:
                    clip_path = clip.media_reference.target_url.replace("file://", "")
                    if (
                            clip.media_reference.name == sg_version["code"]
                            and clip_path == sg_version["sg_path_to_movie"]
                    ):
                        clip.media_reference.metadata["sg"] = sg_version
                        break

            # Create the PublishedFiles.
            published_files_batch_data = [
                {
                    "request_type": "create",
                    "entity_type": "PublishedFile",
                    "data": vdata["published_file"]
                } for vdata in versions_data.values()
            ]
            sg_published_files = self._sg.batch(published_files_batch_data)
            # Update the versions_data with the newly created PublishedFiles.
            for sg_published_file in sg_published_files:
                version_data = next(
                    version_data for version_data in versions_data.values()
                    if version_data["version"]["id"] == sg_published_file["version"]["id"]
                )
                version_data["published_file"] = sg_published_file
                if version_data["published_file_dependency"]:
                    version_data["published_file_dependency"]["published_file"] = sg_published_file
            # Create the PublishedFileDependencies.
            published_file_dependencies_batch_data = [
                {
                    "request_type": "create",
                    "entity_type": "PublishedFileDependency",
                    "data": vdata["published_file_dependency"]
                } for vdata in versions_data.values() if vdata["published_file_dependency"]
            ]
            if published_file_dependencies_batch_data:
                self._sg.batch(published_file_dependencies_batch_data)
            # Upload a movie for each Version.
            versions = []
            movies = []
            for vdata in versions_data.values():
                versions.append(vdata["version"])
                movies.append(vdata["version_file_path"])
            media_uploader = MediaUploader(self._sg, versions, movies)
            media_uploader.upload_versions()
        return [vdata["version"] for vdata in versions_data.values()]

    def _write_shots(self, cut_track, sg_project, sg_linked_entity, sg_user=None):
        """
        Gather information about SG Shots given a CutTrack, and create or update
        them accordingly in SG.

        :param cut_track: An instance of :class:`CutTrack`.
        :param sg_project: The SG Project to write the Cut to.
        :param sg_cut: If provided, the SG Cut to update.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :returns: A list of SG Shot Entities.
        """
        # If there are no shot names for the track, we can't do anything.
        if not cut_track.shot_names:
            return []
        sg_batch_data = []
        sg_shots = []
        existing_shots = self._sg.find(
            "Shot",
            [["project", "is", sg_project], ["code", "in", cut_track.shot_names]],
            ["code"]
        )
        existing_shots_by_name = {shot["code"]: shot for shot in existing_shots}
        for shot in cut_track.shots:
            if shot.name not in existing_shots_by_name.keys():
                logger.info("Creating Shot %s..." % shot.name)
                shot_payload = self._get_shot_payload(shot, sg_project, sg_linked_entity, sg_user)
                sg_batch_data.append({
                    "request_type": "create",
                    "entity_type": "Shot",
                    "data": shot_payload
                })
            else:
                # TODO: Logic for omitted/reinstated shots
                logger.info("Updating Shot %s..." % shot.name)
                sg_shot = existing_shots_by_name[shot.name]
                shot_payload = self._get_shot_payload(shot, sg_project, sg_linked_entity, sg_user)
                sg_batch_data.append({
                    "request_type": "update",
                    "entity_type": "Shot",
                    "entity_id": sg_shot["id"],
                    "data": shot_payload
                })

        if sg_batch_data:
            sg_shots = self._sg.batch(sg_batch_data)
        return sg_shots

    def _get_shot_payload(self, shot, sg_project, sg_linked_entity, sg_user=None):
        """
        Get a SG Shot payload for a given :class:`sg_otio.Shot` instance.

        :param shot: A :class:`sg_otio.Shot` instance.
        :param sg_project: The SG Project to write the Shot to.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param sg_user: An optional user to provide when creating/updating Shots in SG.
        :returns: A dictionary with the Shot payload.
        """
        sg_linked_entity = sg_linked_entity or sg_project
        # TODO: deal with smart fields and shot_cut_fields_prefix
        sfg = SGShotFieldsConfig(self._sg, sg_linked_entity["type"], use_smart_fields=False, shot_cut_fields_prefix=None)
        shot_payload = {
            "project": sg_project,
            "code": shot.name,
            sfg.head_in: shot.head_in.to_frames(),
            sfg.cut_in: shot.cut_in.to_frames(),
            sfg.cut_out: shot.cut_out.to_frames(),
            sfg.tail_out: shot.tail_out.to_frames(),
            sfg.cut_duration: shot.duration.to_frames(),
            sfg.cut_order: shot.index
        }
        if sg_user:
            shot_payload["created_by"] = sg_user
            shot_payload["updated_by"] = sg_user
        if sfg.working_duration:
            shot_payload[sfg.working_duration] = shot.working_duration.to_frames()
        if sfg.head_out:
            shot_payload[sfg.head_out] = shot.head_out.to_frames()
        if sfg.tail_in:
            shot_payload[sfg.tail_in] = shot.tail_in.to_frames()
        if sfg.tail_duration:
            shot_payload[sfg.tail_duration] = shot.tail_duration.to_frames()
        # TODO: Add setting for flagging retimes and effects?
        if True:
            shot_payload[sfg.has_effects] = shot.has_effects
            shot_payload[sfg.has_retime] = shot.has_retime
        if sfg.absolute_cut_order:
            # TODO: maybe create shot fields config before so that
            #       we can get the field without an extra query?
            sg_entity = self._sg.find_one(
                sg_linked_entity["type"],
                [["id", "is", sg_linked_entity["id"]]],
                [sfg.absolute_cut_order]
            )
            entity_cut_order = sg_entity.get(sfg.absolute_cut_order)
            if entity_cut_order:
                absolute_cut_order = 1000 * entity_cut_order + shot.index
                shot_payload[sfg.absolute_cut_order] = absolute_cut_order
        if sfg.shot_link_field and sg_linked_entity:
            shot_payload[sfg.shot_link_field] = sg_linked_entity
        return shot_payload

    def _get_cut_entities(self, entity_type, entity_id):
        """
        Get the Cut, Project and linked Entity which will be used to create or update
        the Cut, Shots and CutItems in SG.

        When writing to SG, The Entity provided (type and ID) can be:
        - The Cut itself
        - The Project
        - Any Entity to link the Cut against (e.g. Sequence, Reel...)

        Find these entities and return them.

        :param str entity_type: A SG Entity Type.
        :param int entity_id: A SG Entity ID.
        :returns: A tuple (project, sg_cut, sg_linked_entity). The Cut and linked Entity
                  can be ``None``.
        """
        sg_cut = None
        sg_project = None
        sg_linked_entity = None
        # Retrieve the target entity
        if entity_type == "Cut":
            sg_cut = self._sg.find_one(
                entity_type,
                [["id", "is", entity_id]],
                ["project", "code"]
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
                ["name"]
            )
            if not sg_project:
                raise ValueError(
                    "Unable to retrieve a %s with the id %s" % (entity_type, entity_id)
                )
        else:
            sg_linked_entity = self._sg.find_one(
                entity_type,
                [["id", "is", entity_id]],
                ["project", "code"]
            )
            if not sg_linked_entity:
                raise ValueError(
                    "Unable to retrieve a %s with the id %s" % (entity_type, entity_id)
                )
            sg_project = sg_linked_entity["project"]
        if not sg_project:
            raise ValueError("Unable to retrieve a Project from %s %s")
        return sg_project, sg_cut, sg_linked_entity

    def _retrieve_local_storage(self):
        """
        Retrieve a Local Storage path given its name.

        :raises ValueError: If LocalStorages can't be retrieved.
        :raises RuntimeError: If the platform is not supported.
        :returns: A SG Local Storage entity.
        """
        local_storage_name = SGSettings().local_storage_name
        if not self._local_storages.get(local_storage_name):
            path_field = "%s_path" % get_platform_name()
            local_storage = self._sg.find_one(
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
            self._local_storages[local_storage_name] = local_storage
        return self._local_storages[local_storage_name]

    def _create_input_media_version(self, input_media, track_name, sg_project, sg_linked_entity, sg_user=None):
        """
        Creates a Version and a Published File for an input media
        representing the whole Timeline.

        :param input_media: The path to the input media.
        :param str track_name: The track name.
        :param sg_project: A SG Project.
        :param sg_linked_entity: A SG Entity or ``None``.
        :param sg_user: A SG User or ``None``.
        :returns: A tuple of (SG Version, SG PublishedFile).
        """
        linked_entity = sg_linked_entity or sg_project
        local_storage = self._retrieve_local_storage()
        # Create the Version
        file_name, file_extension = os.path.splitext(os.path.basename(input_media))
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
            "project": sg_project,
            "code": track_name,
            "entity": linked_entity,
            "description": "Base media layer imported with Cut: %s" % track_name,
            "sg_first_frame": 1,
            "sg_movie_has_slate": False,
            "sg_path_to_movie": input_media,
        }
        if sg_user:
            version_payload["created_by"] = sg_user
            version_payload["updated_by"] = sg_user
        logger.info("Creating Version/Published File %s for Cut..." % version_payload["code"])
        version = self._sg.create("Version", version_payload)
        # Create the Published File
        # Check if we can publish it with a local file path instead of a URL
        if local_storage and input_media.startswith(local_storage["path"]):
            relative_path = input_media[len(local_storage["path"]):]
            # Get rid of double slashes and replace backslashes by forward slashes.
            # SG doesn't seem to accept backslashes when creating
            # PublishedFiles with relative paths to local storage
            relative_path = os.path.normpath(relative_path)
            relative_path = relative_path.replace("\\", "/")
            publish_path = {
                "relative_path": relative_path,
                "local_storage": local_storage
            }
        else:
            publish_path = {
                "url": pathlib.Path(os.path.abspath(input_media)).as_uri(),
                "name": file_name,
            }
        published_file_payload = {
            "code": file_name,
            "project": sg_project,
            "entity": linked_entity,
            "path": publish_path,
            "published_file_type": published_file_type,
            "version_number": 1,
            "version": version
        }
        if sg_user:
            published_file_payload["created_by"] = sg_user
            published_file_payload["updated_by"] = sg_user
        published_file = self._sg.create("PublishedFile", published_file_payload)

        # Upload media to the version.
        logger.debug("Uploading movie %s..." % os.path.basename(input_media))
        self._sg.upload(
            "Version",
            version["id"],
            input_media,
            "sg_uploaded_movie"
        )
        return version, published_file