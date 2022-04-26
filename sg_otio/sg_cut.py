# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging
import os
import sys
from collections import defaultdict
from pprint import pformat

import opentimelineio as otio
from opentimelineio.opentime import RationalTime

# Relative imports don't work with the way OTIO loads adapters.
from .constants import _ENTITY_CUT_ORDER_FIELD
from .sg_cut_item import SGCutItem
from .sg_shot import SGShotFieldsConfig

try:
    # For Python 3.4 or later
    import pathlib
except ImportError:
    # fallback to library in required packages
    import pathlib2 as pathlib

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class SGCut(object):
    """
    A class to represent a :class:`otio.schema.Track` of kind ``otio.schema.TrackKind.Video`` in Shotgrid.

    - The video track is represented as a SG Cut.
    - If an input media is provided, it can be used to create a SG Version and a Published File for the SG Cut.
    - The Clips and Gaps are represented as SG Cut Items.
    - Shots can be created/updated based on the Clips information.

    There are methods to create all these entities, namely :meth:`create_sg_cut`, :meth:`create_sg_cut_items`.
    """

    def __init__(
            self,
            track,
            sg,
            entity_type,
            project,
            linked_entity,
            user=None,
            description=None,
            input_media=None,
            local_storage_name=None,
            shot_regexp=None,
            use_smart_fields=False,
            shot_cut_fields_prefix=None,
            head_in=1001,
            head_in_duration=8,
            tail_out_duration=8,
            flag_retimes_and_effects=True,
            log_level=logging.INFO
    ):
        """
        SGCut constructor.

        :param track: An :class:`otio.schema.Track` instance of kind ``otio.schema.TrackKind.Video``.
        :param sg: A ShotGrid API session instance.
        :param entity_type: A string.
        :param project: A SG Project entity.
        :param linked_entity: A SG dictionary of the Entity to link the Cut to.
        :param user: An optional SG User entity.
        :param description: An optional description.
        :param input_media: An optional path to a media file of the Timeline.
        :param local_storage_name: If provided, the local storage where files will be published to.
        :param shot_regexp: A regular expression to extract extra information from the
                            clip comments.
        :param bool use_smart_fields: Whether or not ShotGrid Shot cut smart fields
                                      should be used.
        :param str shot_cut_fields_prefix: If set, use custom Shot cut fields based
                                           on the given prefix.
        :param int head_in: Default head in, in frames.
        :param int head_in_duration: Default head in duration, in frames.
        :param int tail_out_duration: Default tail out duration, in frames.
        :param bool flag_retimes_and_effects: Whether or not to flag retimes and effects.
        """
        logger.setLevel(log_level)
        self._track = track
        self._sg = sg
        self._entity_type = entity_type
        self._project = project
        self._linked_entity = self._sg.find_one(
            linked_entity["type"],
            [["project", "is", self._project]],
            # We ask for various 'name' fields used by SG Entities, only
            # the existing one will be returned, others will be ignored.
            [
                "code",
                "name",
                "title",
                _ENTITY_CUT_ORDER_FIELD,
            ]
        )
        if not self._linked_entity:
            raise ValueError("Entity %s could not be found in project %s" % (
                linked_entity, self._project
            ))
        self._user = user
        self._description = description
        self._input_media = input_media
        self._local_storage = None
        if local_storage_name:
            try:
                self._local_storage = self._retrieve_local_storage(self._sg, local_storage_name)
            except (ValueError, RuntimeError) as e:
                logger.warning(e, exc_info=True)
        self._shot_regexp = shot_regexp
        self._use_smart_fields = use_smart_fields
        self._shot_cut_fields_prefix = shot_cut_fields_prefix
        self._head_in = head_in
        self._head_in_duration = head_in_duration
        self._tail_out_duration = tail_out_duration
        self._flag_retimes_and_effects = flag_retimes_and_effects
        self._sg_cut = None
        self._cut_items_by_shot = defaultdict(list)
        self._shot_fields_config = SGShotFieldsConfig(
            self._sg,
            self._linked_entity["type"],
            self._use_smart_fields,
            self._shot_cut_fields_prefix
        )
        # Will set the cut items by shot, without a link to a SG Cut.
        # The sg_cut will be updated once it is created.
        self._set_cut_items()

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

    def create_sg_cut(self):
        """
        Writes information from :class:`otio.schema.Track` instance to
        ShotGrid and returns the SG Cut dictionary.

        It will create a SG Cut, and if an input media is provided, it will
        also create a SG Version and a SG Published File.

        :param input_otio: An :class:`otio.schema.Timeline` instance of kind :class:`otio.schema.TrackKind.video`.
        :returns: The SG Cut dictionary.
        :raises ValueError: If provided, if the input media is not a valid file.
        """
        input_media_version = None
        if self._input_media:
            if not os.path.isfile(self._input_media):
                raise ValueError("Input media %s is not a file" % self._input_media)
            input_media_version, input_media_published_file = self._create_input_media_version()
        self._sg_cut = self._create_sg_cut(input_media_version)
        logger.debug("Created Cut:\n%s" % pformat(self._sg_cut))
        # Set the sg cut on all cut items
        for cut_items in self._cut_items_by_shot.values():
            for cut_item in cut_items:
                cut_item.sg_cut = self._sg_cut
        return self._sg_cut

    def create_sg_cut_items(self):
        """
        Creates SG CutItems from the :class:`otio.schema.Clip` and :class:`otio.schema.Gap` instances
        of the video track.

        The Shots linked to the SGCutItems will be created if they don't exist, and updated if they do.

        Since SG does not support playing or representing :class:`otio.schema.Transition` instances,
        when a transition is found between two clips, its in_offset will be considered as part of the
        first clip, and its out_offset will be considered as part of the second clip.

        :returns: A list of tuples (SG Shot, list of SG CutItems).
        """
        self._create_or_update_sg_shots()
        self._create_sg_cut_items()
        result = []
        logger.debug("Created Cut Items, by Shot:")
        for shot_code, cut_items in self._cut_items_by_shot.items():
            sg_shot = cut_items[0].sg_shot
            sg_cut_items = [ci.sg_cut_item for ci in cut_items]
            logger.debug("Shot:%s" % pformat(sg_shot))
            logger.debug("Cut Items:")
            for sg_cut_item in sg_cut_items:
                logger.debug("%s" % pformat(sg_cut_item))
            result.append((sg_shot, sg_cut_items))
        return result

    def _create_sg_cut(self, input_media_version=None):
        """
        Creates a SG Cut given an input OTIO timeline.

        :param input_media_version: A SG Version entity for the input media, if any.
        """
        cut_name = self._track.name
        revision_number = 1
        previous_cut = self._sg.find_one(
            "Cut",
            [
                ["code", "is", cut_name],
                ["entity", "is", self._linked_entity],
            ],
            ["revision_number"],
            order=[{"field_name": "revision_number", "direction": "desc"}]
        )
        if previous_cut:
            revision_number = (previous_cut.get("revision_number") or 0) + 1
        # If the track starts at 00:00:00:00, for some reason it does not have a source range.
        if self._track.source_range:
            track_start = (-self._track.source_range.start_time)
        else:
            track_start = RationalTime(0, self._track.duration().rate).to_timecode()
        track_end = track_start + self._track.duration()
        cut_payload = {
            "project": self._project,
            "code": cut_name,
            "entity": self._linked_entity,
            "fps": self._track.duration().rate,
            "timecode_start_text": track_start.to_timecode(),
            "timecode_end_text": track_end.to_timecode(),
            "duration": self._track.duration().to_frames(),
            "revision_number": revision_number,
        }
        if self._user:
            cut_payload["created_by"] = self._user
            cut_payload["updated_by"] = self._user
        if self._description:
            cut_payload["description"] = self._description
        if input_media_version:
            cut_payload["version"] = input_media_version
        return self._sg.create("Cut", cut_payload)

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

    def _set_cut_items(self):
        """
        Set the :class:`SGCutItems` instances for the timeline.

        The created SGCutItems are stored by shot name in self._cut_items_by_shot.

        In a video track, there can be Clips, Transitions and Gaps.
        In SG, transitions are not supported, so when there is a Transition with
        an in_offset and an out_offset, the in_offset is considered part of the previous Clip,
        and the out_offset is considered part of the next Clip.

        Gaps can be represented as Cut Items, Transitions won't be.
        """
        if self._track.source_range:
            track_start = -self._track.source_range.start_time
        else:
            # For some reason a track that starts at 00:00:00:00 doesn't have a source_range
            track_start = RationalTime(0, self._track.duration().rate)
        clip_index = 0
        # Keep a list of all the cut items we create so that we can add transitions to them if needed.
        cut_items = []
        for track_index, track_elt in enumerate(self._track.each_child()):
            if isinstance(track_elt, otio.schema.Clip) or isinstance(track_elt, otio.schema.Gap):
                cut_item = SGCutItem(
                    sg=self._sg,
                    sg_cut=self._sg_cut,
                    clip=track_elt,
                    clip_index=clip_index + 1,
                    track_start=track_start,
                    shot_fields_config=self._shot_fields_config,
                    head_in=self._head_in,
                    head_in_duration=self._head_in_duration,
                    tail_out_duration=self._tail_out_duration,
                    shot_regexp=self._shot_regexp,
                    user=self._user,
                )
                # If a transition_after was added to the previous clip,
                # it means it's the transition_before of this clip.
                if clip_index > 0 and cut_items[clip_index - 1].transition_after:
                    cut_item.transition_before = cut_items[clip_index - 1].transition_after
                cut_items.append(cut_item)
                # Note that the shot name can be None, for a gap for example.
                self._cut_items_by_shot[cut_item.shot_name].append(cut_item)
                clip_index += 1
            elif isinstance(track_elt, otio.schema.Transition):
                # A transition can only be between two clips.
                # The clip before the transition was created at index clip_index.
                cut_items[clip_index].transition_after = track_elt

        # Check if SGCutItems have duplicate names, and if they have, make sure their names are unique.
        cut_item_names = [cut_item.name for cut_item in cut_items]
        seen_names = set()
        duplicate_names = [x for x in cut_item_names if x in seen_names or seen_names.add(x)]
        if duplicate_names:
            for duplicate_name in duplicate_names:
                index = 1
                for cut_item in cut_items:
                    if cut_item.name == duplicate_name:
                        cut_item.name = "%s_%03d" % (cut_item.name, index)
                        index += 1

        # For cases where multiple SGCutItems belong to the same Shot,
        # head_in_duration and tail_out_duration must be adjusted, so that all the SGCutItems
        # have the same duration.
        for shot_name, cut_items in self._cut_items_by_shot.items():
            if len(cut_items) > 1:
                min_source_in = min(cut_item.source_in for cut_item in cut_items)
                max_source_out = max(cut_item.source_out for cut_item in cut_items)
                for cut_item in cut_items:
                    if cut_item.source_in > min_source_in:
                        cut_item.head_in_duration += cut_item.source_in - min_source_in
                    if cut_item.source_out < max_source_out:
                        cut_item.tail_out_duration += max_source_out - cut_item.source_out
        # Link cut items to existing Shots in SG.
        self._set_cut_items_shots()

    def _set_cut_items_shots(self):
        """
        Set the SG Shots of the SGCutItems, if they exist in SG.
        """
        shot_names = [shot_name for shot_name in self._cut_items_by_shot.keys() if shot_name]
        # Get existing shots from SG
        shots = self._sg.find(
            "Shot",
            [
                ["code", "in", shot_names],
                ["project", "is", self._project]
            ],
            self._shot_fields_config.all
        )
        shots_by_code = dict((shot["code"], shot) for shot in shots)
        # Link existing shots to their cut items
        for cut_items in self._cut_items_by_shot.values():
            for cut_item in cut_items:
                if cut_item.shot_name in shots_by_code.keys():
                    cut_item.sg_shot = shots_by_code[cut_item.shot_name]

    def _create_or_update_sg_shots(self):
        """
        Create or update SG Shots based on the SGCutItems information.
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
