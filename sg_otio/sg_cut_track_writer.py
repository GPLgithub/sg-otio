# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import datetime
import logging
import os
import shutil

import opentimelineio as otio
from opentimelineio.opentime import RationalTime

from .clip_group import ClipGroup
from .constants import _EFFECTS_FIELD, _RETIME_FIELD
from .constants import _ENTITY_CUT_ORDER_FIELD, _ABSOLUTE_CUT_ORDER_FIELD
from .constants import _REINSTATE_FROM_PREVIOUS_STATUS
from .media_uploader import MediaUploader
from .sg_settings import SGShotFieldsConfig, SGSettings
from .utils import get_available_filename, get_local_storage_relative_path
from .utils import get_platform_name, get_path_from_target_url
from .track_diff import SGTrackDiff

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

    def write_to(
        self,
        entity_type,
        entity_id,
        video_track,
        input_media=None,
        sg_user=None,
        description="",
        previous_track=None,
        update_shots=True,
        input_file=None,
    ):
        """
        Gather information about a Cut, its Cut Items and their linked Shots and create
        or update Entities accordingly in SG.

        When writing to SG, The Entity provided (type and ID) can be:
        - The Cut itself
        - The Project
        - Any Entity to link the Cut against (e.g. Sequence, Reel...)

        If an input file is provided, it is uploaded as a Published File to the
        SG Cut.

        :param str entity_type: A SG Entity type.
        :param int entity_id: A SG Entity ID.
        :param video_track: An OTIO Video Track.
        :param str input_media: An optional input media. If provided, a Version will be created for the Cut.
        :param sg_user: An optional SG User which will be registered when creating/updating Entities.
        :param description: An optional description for the Cut.
        :param previous_track: An optional OTIO Video Track read from SG to compare
                               the current Track to.
        :param bool update_shots: Whether or not existing SG Shots should be updated.
                                  New SG Shots are always created.
        :param str input_file: Optional input source file for the Cut.
        """
        sg_track_data = video_track.metadata.get("sg")
        if sg_track_data and sg_track_data["type"] != "Cut":
            raise ValueError(
                "Invalid {} SG data for a {}".format(sg_track_data["type"], "Cut")
            )
        sg_project, sg_cut, sg_linked_entity = self._get_cut_entities(
            entity_type, entity_id
        )
        # Retrieve the existing Shots for the clips
        sfg = SGShotFieldsConfig(
            self._sg,
            sg_linked_entity["type"] if sg_linked_entity else None,
        )
        if previous_track:
            track_diff = SGTrackDiff(
                self._sg,
                sg_project,
                new_track=video_track,
                old_track=previous_track,
            )
            clips_by_shots = track_diff.diffs_by_shots
        else:
            clips_by_shots = ClipGroup.groups_from_track(video_track)

            # Grab Shots and enforce unique cut item names
            shot_names = []
            seen_names = []
            duplicate_names = {}
            for shot_key, clip_group in clips_by_shots.items():
                if shot_key:
                    shot_names.append(shot_key)
                for clip in clip_group.clips:
                    if clip.name not in seen_names:
                        seen_names.append(clip.name)
                    else:
                        if clip.name not in duplicate_names:
                            duplicate_names[clip.name] = []
                        duplicate_names[clip.name].append(clip)

            for name, clips in duplicate_names.items():
                clip_name_index = 1
                for clip in clips:
                    clip.cut_item_name = "%s_%03d" % (clip.name, clip_name_index)
                    clip_name_index += 1

            if shot_names:
                # find is case insensitive so we can use our
                # lowered case shot keys.
                sg_shots = self._sg.find(
                    "Shot",
                    [["project", "is", sg_project], ["code", "in", shot_names]],
                    sfg.all
                )
                # Apply retrieved Shots to ClipGroups
                for sg_shot in sg_shots:
                    shot_name = sg_shot["code"]
                    # clips_by_shots has the lowercased name as key.
                    clips_by_shots[shot_name.lower()].sg_shot = sg_shot

        sg_cut, sg_cut_version, sg_cut_pf = self.write_cut(
            video_track,
            sg_project,
            sg_cut=sg_cut,
            sg_linked_entity=sg_linked_entity,
            cut_media=input_media,
            sg_user=sg_user,
            description=description
        )
        # Upload input file to the Cut record and keep going if it fails.
        if input_file:
            try:
                self._sg.upload(
                    sg_cut["type"],
                    sg_cut["id"],
                    input_file,
                    "attachments"
                )
            except Exception as e:
                logger.warning(
                    "Couldn't upload %s into SG: %s" % (
                        input_file, e
                    )
                )

        sg_shots = self.write_shots(
            clips_by_shots,
            sg_project,
            sg_linked_entity,
            sg_user,
            update_shots=update_shots,
        )
        if SGSettings().create_missing_versions:
            self._write_versions(
                video_track.name,
                clips_by_shots,
                sg_project,
                sg_linked_entity,
                sg_cut_pf,
                sg_user
            )
        self.write_cut_items(
            clips_by_shots,
            sg_project,
            sg_cut,
            sg_linked_entity,
            sg_shots,
            sg_user
        )

    def write_cut(
        self,
        video_track,
        sg_project,
        sg_cut=None,
        sg_linked_entity=None,
        sg_user=None,
        cut_media=None,
        description="",
    ):
        """
        Gather information about a SG Cut given a video track, and create or update
        the corresponding Cut in SG.

        Add metadata to the OTIO video Track about the SG Cut.

        :param video_track: An OTIO Video Track.
        :param sg_project: The SG Project to write the Cut to.
        :param sg_cut: If provided, the SG Cut to update.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param sg_version: If provided, the SG Version to link to the Cut.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :param input_media: The path to the input media.
        :param str description: An optional description for the Cut.
        :returns: A tuple with the SG Cut entity created, a SG Version and a PublishedFile
                  set to ``None`` if no cut media was provided.
        """

        sg_cut_version = None
        sg_cut_pf = None
        if cut_media:
            sg_cut_version, sg_cut_pf = self._create_input_media_version(
                cut_media, video_track.name, sg_project, sg_linked_entity, sg_user
            )
        sg_cut = self._write_cut(
            video_track, sg_project, sg_cut, sg_linked_entity, sg_cut_version, sg_user, description
        )
        return sg_cut, sg_cut_version, sg_cut_pf

    def _write_cut(
        self,
        video_track,
        sg_project,
        sg_cut=None,
        sg_linked_entity=None,
        sg_version=None,
        sg_user=None,
        description=""
    ):
        """
        Gather information about a SG Cut given a video track, and create or update
        the corresponding Cut in SG.

        Add metadata to the OTIO video Track about the SG Cut.

        :param video_track: An OTIO Video Track.
        :param sg_project: The SG Project to write the Cut to.
        :param sg_cut: If provided, the SG Cut to update.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param sg_version: If provided, the SG Version to link to the Cut.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :param str description: An optional description for the Cut.
        :returns: The SG Cut entity created.
        """
        sg_cut_data = self._get_sg_cut_payload(video_track, sg_version, sg_user, description)
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
            logger.info("Creating Cut %s..." % sg_cut_data["code"])
            logger.debug("Cut create payload %s" % sg_cut_data)
            sg_cut = self._sg.create(
                "Cut",
                sg_cut_data,
            )
            # Update the original track with the result
            logger.debug("Updating %s SG metadata with %s" % (video_track.name, sg_cut))
            video_track.metadata["sg"] = sg_cut
        return sg_cut

    def _get_sg_cut_payload(self, video_track, sg_version=None, sg_user=None, description=""):
        """
        Gather information about a SG Cut given a Track.

        :param video_track: An OTIO Video Track.
        :param sg_version: If provided, the SG Version to link to the Cut.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :param str description: An optional description for the Cut.
        :returns: A dictionary with the SG Cut payload.
        """
        # If the track starts at 00:00:00:00, for some reason it does not have a source range.
        if video_track.source_range:
            # The source range is set with a negative offset to use it as an
            # offset when computing clips record times.
            track_start = -video_track.source_range.start_time
        else:
            track_start = RationalTime(0, video_track.duration().rate)
        track_end = track_start + video_track.duration()
        cut_payload = {
            "code": video_track.name or "New Cut %s" % datetime.date.today(),
            "fps": video_track.duration().rate,
            "timecode_start_text": track_start.to_timecode(),
            "timecode_end_text": track_end.to_timecode(),
            "duration": video_track.duration().to_frames(),
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

    def write_cut_items(self, clips_by_shots, sg_project, sg_cut, sg_linked_entity, sg_shots, sg_user):
        """
        Create or update Cut Items in SG for the given clips.

        Add metadata to the OTIO Clips in the Track about the SG Cut Items.

        :param clips_by_shots: A dictionary where keys are Shot names and values
                               instances of :class:`ClipGroup`.
        :param sg_project: The SG Project to write the Cut to.
        :param sg_cut: If provided, the SG Cut to update.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param sg_shots: A list of SG Shots.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :returns: The SG Cut Items.
        """
        shots_by_id = {x["id"]: x for x in sg_shots}
        sg_cut_items_data = []
        cut_item_clips = []

        # Loop over all clips
        for shot_key, clip_group in clips_by_shots.items():
            if clip_group.sg_shot_is_omitted:
                logger.info("Skipping omitted Shot %s" % shot_key)
                continue
            for clip in clip_group.clips:
                logger.debug("Getting payload for %s %s %s %s %s" % (
                    clip.name, clip.head_in, clip.cut_in, clip.cut_out, clip.tail_out
                ))
                # TODO: check if the medata is updated if we created Versions
                sg_version = clip.sg_version
                sg_data = self.get_sg_cut_item_payload(
                    clip,
                    sg_shot=clip.sg_shot,
                    sg_version=sg_version,
                    sg_user=sg_user
                )
                sg_cut_items_data.append(sg_data)
                cut_item_clips.append(clip)

        batch_data = []
        linked_entity = sg_linked_entity or sg_project
        for cut_item_clip, sg_cut_item_data in zip(cut_item_clips, sg_cut_items_data):
            sg_cut_item_data["cut"] = sg_cut
            sg_cut_item_data["project"] = sg_project
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
            sg_cut_item = cut_item_clip.metadata.get("sg") or {}
            if sg_cut_item.get("id"):
                # Check if the CutItem is linked to the Cut we updated or created.
                # If not, create a new CutItem.
                if sg_cut_item.get("cut") and sg_cut_item["cut"].get("id") == sg_cut["id"]:
                    logger.info("Updating Cut Item %s (ID %s)..." % (sg_cut_item["code"], sg_cut_item["id"]))
                    logger.debug("with %s..." % sg_cut_item_data)
                    batch_data.append({
                        "request_type": "update",
                        "entity_type": "CutItem",
                        "entity_id": sg_cut_item["id"],
                        "data": sg_cut_item_data
                    })
                else:
                    logger.info("Creating Cut Item %s..." % sg_cut_item_data["code"])
                    logger.debug("with %s..." % sg_cut_item_data)
                    batch_data.append({
                        "request_type": "create",
                        "entity_type": "CutItem",
                        "data": sg_cut_item_data
                    })
            else:
                logger.info("Creating Cut Item %s..." % sg_cut_item_data["code"])
                logger.debug("with %s..." % sg_cut_item_data)
                batch_data.append({
                    "request_type": "create",
                    "entity_type": "CutItem",
                    "data": sg_cut_item_data
                })
        sg_cut_items = []
        if batch_data:
            res = self._sg.batch(batch_data)
            for cut_item_clip, sg_cut_item in zip(cut_item_clips, res):
                # Set the Shot code we don't get back from the batch request
                if sg_cut_item.get("shot"):
                    sg_cut_item["shot"]["code"] = shots_by_id[sg_cut_item["shot"]["id"]]["code"]
                cut_item_clip.metadata["sg"] = sg_cut_item
                sg_cut_items.append(sg_cut_item)
                logger.debug("Updating %s SG metadata with %s" % (
                    cut_item_clip.name, sg_cut_item)
                )
        return sg_cut_items

    def get_sg_cut_item_payload(self, cut_clip, sg_shot=None, sg_version=None, sg_user=None):
        """
        Get a SG CutItem payload for a given :class:`sg_otio.SGCutClip` instance.

        An absolute cut order can be set on CutItems if the `sg_absolute_cut_order`
        integer field was added to the SG CutItem schema. This absolute cut order
        is meant to be the cut order of the CutItem in the Project and is based on
        a cut order value set on the Entity (Reel, Sequence, etc...) the Cut is
        imported against. The absolute cut order is then:
        `1000 * entity cut order + edit cut order`.

        :param cut_clip: A :class:`sg_otio.SGCutClip` instance.
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
            "cut_order": cut_clip.index
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
                "code": sg_version.get("code") or sg_version.get("name") or None,
            }
        if sg_user:
            cut_item_payload["created_by"] = sg_user
            cut_item_payload["updated_by"] = sg_user

        if cut_clip.has_effects:
            description = "%s\nEffects: %s" % (
                description,
                cut_clip.effects_str
            )
        if _EFFECTS_FIELD in self.cut_item_schema:
            cut_item_payload[_EFFECTS_FIELD] = cut_clip.has_effects

        if cut_clip.has_retime:
            description = "%s\nRetime: %s" % (description, cut_clip.retime_str)
        if _RETIME_FIELD in self.cut_item_schema:
            cut_item_payload[_RETIME_FIELD] = cut_clip.has_retime

        cut_item_payload["description"] = description
        return cut_item_payload

    def _write_versions(self, cut_title, clips_by_shots, sg_project, sg_linked_entity, cut_published_file=None, sg_user=None):
        """
        For Clips which have a Media Reference, create a Version and a Published file for each one.

        :param str cut_title: A name for the Cut.
        :param clips_by_shots: A dictionary where keys are Shot names and values
                               instances of :class:`ClipGroup`.
        :param sg_project: The SG Project to write the Cut to.
        :param sg_cut: If provided, the SG Cut to update.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param cut_published_file: If provided, the Cut's Published File.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :returns: A list of SG Versions, if any.
        """
        clips_with_media_refs = []
        clips_version_names = []
        all_clips = []
        for _, clip_group in clips_by_shots.items():
            all_clips.extend(clip_group.clips)
        for clip in all_clips:
            # Only treat clips with a Media Reference.
            if clip.media_reference.is_missing_reference:
                logger.debug(
                    "Clip %s has no Media Reference, skipping Version creation" % clip.name
                )
                continue
            # Only treat clips which have Media References with no SG metadata.
            sg_metadata = clip.media_reference.metadata.get("sg")
            if sg_metadata and sg_metadata.get("version.Version.id"):
                if sg_metadata.get("id"):
                    logger.debug(
                        "Clip %s is already linked to Published File %s (ID: %s)"
                        " and Version %s (ID %s), skipping Version creation" % (
                            clip.name,
                            sg_metadata["code"],
                            sg_metadata["id"],
                            sg_metadata["version.Version.code"],
                            sg_metadata["version.Version.id"]
                        )
                    )
                else:
                    logger.debug(
                        "Clip %s is already linked to Version %s (ID %s), "
                        "skipping Version creation" % (
                            clip.name,
                            sg_metadata["version.Version.code"],
                            sg_metadata["version.Version.id"]
                        )
                    )
                continue
            # Only treat clips that have an available range.
            if not clip.media_reference.available_range:
                logger.debug(
                    "Clip %s has a Media Reference %s with no available range, skipping Version creation." % (
                        clip.name, clip.media_reference
                    ))
                continue
            media_reference_path = get_path_from_target_url(clip.media_reference.target_url)
            if not os.path.exists(media_reference_path):
                logger.debug(
                    "Clip %s has a Media Reference %s not found locally, skipping Version creation." % (
                        clip.name, clip.media_reference
                    ))
                continue
            # Make sure that the clip's media reference has a proper computed name.
            version_name = clip.compute_clip_version_name()
            clips_version_names.append(version_name)
            clip.media_reference.name = version_name
            clips_with_media_refs.append(clip)
        if not clips_with_media_refs:
            return []
        # Skip the creation of Versions if they already exist in SG.
        existing_sg_versions = self._sg.find(
            "Version",
            [["code", "in", clips_version_names], ["project", "is", sg_project]],
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
            "CUT_TITLE": cut_title,
            "LINK": linked_entity.get("code") or linked_entity.get("name") or "",
            "HH": date.strftime("%H"),
            "DD": date.strftime("%d"),
            "MM": date.strftime("%m"),
            "YY": date.strftime("%y"),
            "YYYY": date.strftime("%Y"),
        }
        # Store versions data by code and path to movie since it will be useful when
        # creating the PublishedFiles and their dependencies.
        versions_data = {}
        for clip in clips_with_media_refs:
            if clip.media_reference.name in sg_version_codes:
                logger.debug("Clip %s has already a Version %s in SG. Skipping Creation" % (
                    clip.name, clip.media_reference.name
                ))
                continue
            # If there's no Shot, we'll use the linked_entity or the project as
            # a Version link.
            # Note that this means that if {SHOT} is used in the template,
            # formatting will fail.
            sg_shot = clip.sg_shot
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
            media_reference_path = get_path_from_target_url(clip.media_reference.target_url)
            shutil.copyfile(
                media_reference_path,
                version_file_path
            )
            # Replace the media reference with the proper file path for both the clip and the video clip.
            clip.media_reference.target_url = "file://%s" % version_file_path
            # The first frame and the last frame depend on the cut in and the media's available range,
            # because we apply a cut in offset based on the head in and the head duration.
            first_frame = clip.available_range().start_time + clip.cut_in - clip.visible_range().start_time
            last_frame = first_frame + clip.available_range().duration
            # Last frame is inclusive, meaning that if first frame is 1 and last frame is 2,
            # the duration is 2.
            last_frame -= otio.opentime.RationalTime(1, first_frame.rate)
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
                "project": sg_project,
                # If no Shot is provided, link the Version to the linked Entity.
                "entity": sg_shot or linked_entity,
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
            # Update the versions_data with the newly created Versions.
            for sg_version in sg_versions:
                version_data = versions_data[
                    (sg_version["code"], sg_version["sg_path_to_movie"])
                ]
                version_data["version"] = sg_version
                version_data["published_file"]["version"] = sg_version

            # Create the Published Files.
            published_files_batch_data = [
                {
                    "request_type": "create",
                    "entity_type": "PublishedFile",
                    "data": vdata["published_file"]
                } for vdata in versions_data.values()
            ]
            sg_published_files = self._sg.batch(published_files_batch_data)
            # Update the versions_data with the newly created Published Files.
            for sg_published_file in sg_published_files:
                version_data = next(
                    version_data for version_data in versions_data.values()
                    if version_data["version"]["id"] == sg_published_file["version"]["id"]
                )
                version_data["published_file"] = sg_published_file
                if version_data["published_file_dependency"]:
                    version_data["published_file_dependency"]["published_file"] = sg_published_file
                # Also update the clip's media_reference metadata with the Published File.
                sg_version = version_data["version"]
                for clip in clips_with_media_refs:
                    clip_path = clip.media_reference.target_url.replace("file://", "")
                    if (
                            clip.media_reference.name == sg_version["code"]
                            and clip_path == sg_version["sg_path_to_movie"]
                    ):
                        logger.debug("Updating %s SG Published File metadata with %s" % (
                            clip.name, sg_published_file
                        ))
                        clip.media_reference.metadata["sg"] = sg_published_file
                        clip.media_reference.metadata["sg"]["version"] = sg_version
                        break
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
            # Upload a movie for each Version, in parallel.
            versions = []
            movies = []
            for vdata in versions_data.values():
                versions.append(vdata["version"])
                movies.append(vdata["version_file_path"])
            media_uploader = MediaUploader(self._sg, versions, movies)
            media_uploader.upload_versions()
        return [vdata["version"] for vdata in versions_data.values()]

    def write_shots(self, clips_by_shots, sg_project, sg_linked_entity, sg_user=None, update_shots=True):
        """
        Create or update SG Shots for the given clips.

        :param clips_by_shots: A dictionary where keys are Shot names and values
                               instances of :class:`ClipGroup`.
        :param sg_project: The SG Project to write the Cut to.
        :param sg_cut: If provided, the SG Cut to update.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param sg_user: An optional user to provide when creating/updating Entities in SG.
        :param bool update_shots: Whether or not existing SG Shots should be updated.
                                  New SG Shots are always created.
        :returns: A list of SG Shot Entities.
        """
        sg_batch_data = []
        sg_shots = []
        for shot_key, clip_group in clips_by_shots.items():
            # The shot key might be _no_shot_name, so we need to check the clip group name too.
            if not shot_key or not clip_group.name:
                continue
            if not clip_group.sg_shot:
                logger.info("Creating Shot %s..." % clip_group.name)
                shot_payload = self._get_shot_payload(
                    clip_group,
                    sg_project,
                    sg_linked_entity,
                    sg_user,
                )
                sg_batch_data.append({
                    "request_type": "create",
                    "entity_type": "Shot",
                    "data": shot_payload
                })
            elif update_shots:
                logger.info("Updating Shot %s..." % clip_group.name)
                sg_shot = clip_group.sg_shot
                shot_payload = self._get_shot_payload(
                    clip_group,
                    sg_project,
                    sg_linked_entity,
                    sg_user
                )
                if shot_payload:
                    sg_batch_data.append({
                        "request_type": "update",
                        "entity_type": "Shot",
                        "entity_id": sg_shot["id"],
                        "data": shot_payload
                    })
                else:
                    logger.info(
                        "No update to perform for Shot %s..." % clip_group.name
                    )

        if sg_batch_data:
            sg_shots = self._sg.batch(sg_batch_data)
            # Update the clips Shots
            for sg_shot in sg_shots:
                # clips_by_shots has the lowercased name as key.
                clip_group = clips_by_shots[sg_shot["code"].lower()]
                if not clip_group.sg_shot:
                    clip_group.sg_shot = sg_shot
                else:
                    # Only update with values which were updated in case it
                    # was a partial update.
                    for k in sg_shot.keys():
                        clip_group.sg_shot[k] = sg_shot[k]

        return sg_shots

    def _get_shot_payload(self, clip_group, sg_project, sg_linked_entity, sg_user=None):
        """
        Get a SG Shot payload for a given :class:`sg_otio.ClipGroup` instance.

        :param clip_group: A :class:`sg_otio.ClipGroup` instance.
        :param sg_project: The SG Project to write the Shot to.
        :param sg_linked_entity: If provided, the Entity the Cut will be linked to.
        :param sg_user: An optional user to provide when creating/updating Shots in SG.
        :returns: A dictionary with the Shot payload.
        """
        sg_linked_entity = sg_linked_entity or sg_project
        sfg = SGShotFieldsConfig(self._sg, sg_linked_entity["type"])
        if clip_group.sg_shot_is_omitted:
            # Just update the status of the Shot.
            omit_status = SGSettings().shot_omit_status
            if omit_status:
                return {
                    "code": clip_group.name,
                    sfg.status: omit_status
                }
            return None

        # Set the status even if we don't change it to get it
        # back in SG batch result.
        if clip_group.sg_shot:
            shot_status = clip_group.sg_shot.get(sfg.status)
        else:
            shot_status = None

        shot_payload = {
            "project": sg_project,
            "code": clip_group.name,
            sfg.head_in: clip_group.head_in.to_frames(),
            sfg.cut_in: clip_group.cut_in.to_frames(),
            sfg.cut_out: clip_group.cut_out.to_frames(),
            sfg.tail_out: clip_group.tail_out.to_frames(),
            sfg.cut_duration: clip_group.duration.to_frames(),
            sfg.cut_order: clip_group.index,
            sfg.status: shot_status,
        }
        if sg_user and not clip_group.sg_shot:  # Only settable on create
            shot_payload["created_by"] = sg_user
            shot_payload["updated_by"] = sg_user
        if sfg.working_duration:
            shot_payload[sfg.working_duration] = clip_group.working_duration.to_frames()
        if sfg.head_duration:
            shot_payload[sfg.head_duration] = self.head_duration.to_frames()
        if sfg.head_out:
            shot_payload[sfg.head_out] = clip_group.head_out.to_frames()
        if sfg.tail_in:
            shot_payload[sfg.tail_in] = clip_group.tail_in.to_frames()
        if sfg.tail_duration:
            shot_payload[sfg.tail_duration] = clip_group.tail_duration.to_frames()
        # TODO: Add setting for flagging retimes and effects?
        if True:
            shot_payload[sfg.has_effects] = clip_group.has_effects
            shot_payload[sfg.has_retime] = clip_group.has_retime
        if sfg.absolute_cut_order and sg_linked_entity.get(sfg.absolute_cut_order):
            entity_cut_order = sg_linked_entity[sfg.absolute_cut_order]
            absolute_cut_order = 1000 * entity_cut_order + clip_group.index
            shot_payload[sfg.absolute_cut_order] = absolute_cut_order
        if sfg.shot_link_field and sg_linked_entity:
            shot_payload[sfg.shot_link_field] = sg_linked_entity

        if clip_group.sg_shot_is_reinstated:
            reinstate_status = None
            settings = SGSettings()
            shot_reinstate_status = settings.shot_reinstate_status
            shot_reinstate_status_default = settings.shot_reinstate_status_default
            if shot_reinstate_status == _REINSTATE_FROM_PREVIOUS_STATUS:
                # Find the most recent status change event log entry where the
                # project and linked Shot code match the current project/shot
                filters = [
                    ["project", "is", sg_project],
                    ["event_type", "is", "Shotgun_Shot_Change"],
                    ["attribute_name", "is", sfg.status],
                    ["entity.Shot.id", "is", clip_group.sg_shot["id"]]
                ]
                fields = ["meta"]
                event_log = self._sg.find_one(
                    "EventLogEntry",
                    filters,
                    fields,
                    order=[
                        {"field_name": "created_at", "direction": "desc"}
                    ]
                )
                # Set the reinstate status value to the value previous to the
                # event log entry
                if event_log:
                    reinstate_status = event_log["meta"]["old_value"]
                elif shot_reinstate_status_default:
                    # Use the default status if we didn't find a previous status
                    reinstate_status = shot_reinstate_status_default
            elif shot_reinstate_status:
                # Just use the status as is.
                reinstate_status = shot_reinstate_status
            if reinstate_status:
                # We set it only if we found a status to set.
                shot_payload[sfg.status] = reinstate_status
            else:
                logger.warning(
                    "Shot %s reinstated but no status to set found, leaving to current value %s" % (
                        shot_payload["code"], shot_payload[sfg.status]
                    )
                )

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
        sg_linked_entity = None
        # Retrieve the target entity
        if entity_type == "Cut":
            sg_cut = self._sg.find_one(
                entity_type,
                [["id", "is", entity_id]],
                ["project", "code", "entity"]
            )
            if not sg_cut:
                raise ValueError(
                    "Unable to retrieve a %s with the id %s" % (entity_type, entity_id)
                )
            sg_project = sg_cut["project"]
            sg_linked_entity = sg_cut["entity"]
            # We might need the absolute cut order of the linked entity later, it's better
            # to retrieve it now.
            if sg_linked_entity:
                sfg = SGShotFieldsConfig(
                    self._sg,
                    sg_linked_entity["type"],
                )
                if sfg.absolute_cut_order:
                    sg_linked_entity = self._sg.find_one(
                        sg_linked_entity["type"],
                        [["id", "is", sg_linked_entity["id"]]],
                        ["project", "code", sfg.absolute_cut_order]
                    )
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
                # We might need the absolute cut order of the linked entity later, it's better
                # to retrieve it now. We should normally get the field from sfg.absolute_cut_order,
                # but to get the Shot Fields Config, we need the linked entity, so to query it properly,
                # we'd need to retrieve the linked entity twice.
                # Instead, we just get the field from the constant instead, if it doesn't exist, it'll just
                # not be present in the payload.
                ["project", "code", _ABSOLUTE_CUT_ORDER_FIELD]
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
        # Get the extension without '.' to use as a Published File Type
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
        relative_path = get_local_storage_relative_path(local_storage, input_media)
        if relative_path:
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

        # Upload media to the Version.
        logger.debug("Uploading movie %s..." % os.path.basename(input_media))
        self._sg.upload(
            "Version",
            version["id"],
            input_media,
            "sg_uploaded_movie"
        )
        return version, published_file
