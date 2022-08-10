# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging
from six.moves.urllib import parse

import opentimelineio as otio
import shotgun_api3

from sg_otio.constants import _CUT_ITEM_FIELDS, _CUT_FIELDS
from sg_otio.constants import _PUBLISHED_FILE_FIELDS, _VERSION_FIELDS
from sg_otio.sg_cut_track_writer import SGCutTrackWriter
from sg_otio.utils import get_platform_name, add_publish_file_media_reference_to_clip, add_version_media_reference_to_clip

logger = logging.getLogger(__name__)


def parse_sg_url(url):
    """
    Parse a SG url, extract the SG site url, credentials and other information.

    The url is a query url which must have the form:
    `https://<SG site>/<SG Entity type>?session_token=<session token>&id=<SG Entity id>`

    .. note:: A session token can be retrieved from a connected SG handle with the
    :meth:`~shotgun_api3.Shotgun.get_session_token()` method.

    :param str url: A SG query url.
    :returns: A SG site, SG Entity type, SG Entity id, session_token tuple.
    """
    parsed = parse.urlparse(url)
    params = parse.parse_qs(parsed.query)
    sg_site = parsed._replace(path="", params="", query="", fragment="").geturl()
    # Todo: check for existence of params
    session_token = params["session_token"][0]
    entity_type = parsed.path[1:]
    entity_id = int(params["id"][0])
    return sg_site, entity_type, entity_id, session_token


def read_from_file(filepath):
    """
    Reads information from a Cut in ShotGrid and returns a
    :class:`otio.schema.Timeline` instance.

    The retrieved SG entities are stored in the items metadata:
    - At the Track level, track.metadata["sg"] is a SG Cut.
    - At the Clip level, clip.metadata["sg"] is a SG Cut Item.
    - At the Clip Media Reference level, clip.media_reference.metadata["sg"] is a SG Published File.
      Note that the Published File can have an ID of None with Version information instead, if the
      Clip could not be bound to a Published File.

    This is the standard method for adapters to implement.
    .. seealso:: https://opentimelineio.readthedocs.io/en/latest/tutorials/write-an-adapter.html#required-functions

    The filepath is a query url which have the form:
    `https://<SG site>/<SG Entity type>?script=<my script>&api_key=<script key>&id=<SG Entity id>`

    :param str filepath: A query URL.
    :returns: A :class:`otio.schema.Timeline` instance.
    :raises ValueError: For unsupported SG Entity types.
    """
    sg_site, entity_type, cut_id, session_token = parse_sg_url(filepath)
    if entity_type != "Cut":
        raise ValueError("Only Cut Entities are supported.")
    sg = shotgun_api3.Shotgun(sg_site, session_token=session_token)

    cut = sg.find_one(
        "Cut",
        [["id", "is", cut_id]],
        _CUT_FIELDS
    )
    if not cut:
        raise ValueError("No Cut found with ID {}".format(cut_id))
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
    cut_items = sg.find(
        "CutItem",
        [["cut", "is", cut]],
        # TODO: respeed and effects are just checkboxes on SG, and some information added to the description,
        #       so we can't really retrieve them and include them in the clips.
        _CUT_ITEM_FIELDS,
        order=[{"field_name": "cut_order", "direction": "asc"}]
    )
    if not cut_items:
        logger.warning("Couldn't retrieve any SG CutItem linked to Cut %s (%s)" % (cut["code"], cut["id"]))
    cut_item_version_ids = [cut_item["version"]["id"] for cut_item in cut_items if cut_item["version"]]
    published_files_by_version_id = {}
    versions_with_no_published_files_by_id = {}
    if cut_item_version_ids:
        # Find Published Files of type mov associated to the Version of the Cut Item.
        published_files = sg.find(
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
            versions_with_no_published_files = sg.find(
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
                raise ValueError("No edit_out found for cut_item %s" % prev_cut_item)
            # We start frame numbering at one
            # since timecode out is exclusive we just use it to not do 1 + value -1
            if cut_item["edit_in"]:
                edit_in = otio.opentime.from_frames(cut_item["edit_in"] - 1, cut["fps"])
            elif cut_item["timecode_edit_in_text"]:
                edit_in = otio.opentime.from_timecode(cut_item["timecode_edit_in_text"], cut["fps"])
            else:
                raise ValueError("No edit_in found for cut_item %s" % cut_item)
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
        # Check if there's an overlap of clips and flag it.
        if cut_item["shot"]:
            cut_item["shot"]["code"] = cut_item["shot.Shot.code"]
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
            add_publish_file_media_reference_to_clip(clip, published_file, platform_name, cut_item)
        elif cut_item_version_id in versions_with_no_published_files_by_id.keys():
            # Cut Item has no Published File, use its Version to create a Media Reference.
            # The SG Metadata is a Published File with ID None, and information about the Version
            # in version, and version.Version.XXX fields present in _PUBLISHED_FILE_FIELDS.
            version = versions_with_no_published_files_by_id[cut_item_version_id]
            # If there's no uploaded movie, we can't create a media reference.
            if version["sg_uploaded_movie"]:
                add_version_media_reference_to_clip(clip, version, cut_item)
        # If it was linked to a Version or a Published File, prefer that as the reel name.
        pf = clip.media_reference.metadata.get("sg")
        if pf:
            pf_name = pf["code"] or pf["version.Version.code"]
            clip.metadata["cmx_3600"]["reel"] = pf_name
        track.append(clip)
    return timeline


def write_to_file(input_otio, filepath, input_media=None, previous_track=None, input_file=None):
    """
    Write the given timeline to SG.

    The filepath is a query url which have the form:
    `https://<SG site>/<SG Entity type>?session_token=<session token>&id=<SG Entity id>`

    The Entity type can either be:
    - A Cut, in that case the Cut with the given id will be updated.
    - A Project, a new Cut will be created, linked to this Project.
    - An arbitrary Entity type, e.g. a Sequence, a new Cut will be created, linked
      to the Entity.

    If an input_media is provided, it will be used to create a Version and a Published File
    for the cut, and possibly Versions for individual clips.

    :param input_otio: A :class:`otio.schema.Timeline` instance
                       or
    :param str filepath: A query URL.
    :param str input_media: A path to a media file representing the video track, if any.
    :param previous_track: An optional :class:`otio.schema.Track` instance.
    :param str input_file: Optional input source file for the Cut.
    :raises ValueError: For unsupported SG Entity types.
    """
    if not isinstance(input_otio, otio.schema.Timeline) and not isinstance(input_otio, otio.schema.Track):
        raise ValueError("Only OTIO Timelines and Video Tracks are supported.")
    if isinstance(input_otio, otio.schema.Track) and input_otio.kind != otio.schema.TrackKind.Video:
        raise ValueError("Only OTIO Video Tracks are supported.")
    sg_site, entity_type, entity_id, session_token = parse_sg_url(filepath)
    # OTIO suppports multiple video tracks, but ShotGrid cuts can only represent one.
    if isinstance(input_otio, otio.schema.Timeline):
        if len(input_otio.video_tracks()) > 1:
            logger.warning("Only one video track is supported, using the first one.")
        # We could flatten the timeline here by using otio.core.flatten_stack(input_otio.video_tracks())
        # But we lose information, for example the track source_range becomes ``None``
        video_track = input_otio.video_tracks()[0]
        # Change the track name to the timeline name.
        video_track.name = input_otio.name
    else:
        video_track = input_otio

    sg = shotgun_api3.Shotgun(sg_site, session_token=session_token)
    sg_writer = SGCutTrackWriter(sg)
    sg_writer.write_to(
        entity_type,
        entity_id,
        video_track,
        description="Generated from sg-otio",
        input_media=input_media,
        previous_track=previous_track,
        input_file=input_file
    )
    return
