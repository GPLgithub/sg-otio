# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging
from six.moves.urllib import parse

import opentimelineio as otio
import shotgun_api3
from opentimelineio.opentime import RationalTime

from sg_otio.constants import _CUT_ITEM_FIELDS, _CUT_FIELDS

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def parse_sg_url(url):
    """
    Parse a SG url, extract the SG site url, credentials and other informations.

    The url is a query url which must have the form:
    `https://<SG site>/<SG Entity type>?script=<my script>&api_key=<script key>&id=<SG Entity id>`

    :param str url: A SG query url.
    :returns: A SG site, SG Entity type, SG Entity id, script name, script key tuple.
    """
    parsed = parse.urlparse(url)
    params = parse.parse_qs(parsed.query)
    sg_site = parsed._replace(path="", params="", query="", fragment="").geturl()
    # Todo: check for existence of params
    script_name = params["script"][0]
    api_key = params["api_key"][0]
    entity_type = parsed.path[1:]
    entity_id = int(params["id"][0])
    return sg_site, entity_type, entity_id, script_name, api_key


def read_from_file(filepath):
    """
    Reads information from a Cut in ShotGrid and returns a
    :class:`otio.schema.Timeline` instance.

    The retrieved SG entities are stored in the items metadata.

    This is the standard method for adapters to implement.
    .. seealso:: https://opentimelineio.readthedocs.io/en/latest/tutorials/write-an-adapter.html#required-functions

    The filepath is a query url which have the form:
    `https://<SG site>/<SG Entity type>?script=<my script>&api_key=<script key>&id=<SG Entity id>`

    :param str filepath: A query URL.
    :returns: A :class:`otio.schema.Timeline` instance.
    :raises ValueError: For unsupported SG Entity types.
    """
    sg_site, entity_type, cut_id, script_name, api_key = parse_sg_url(filepath)
    if entity_type != "Cut":
        raise ValueError("Only Cut Entities are supported.")
    sg = shotgun_api3.Shotgun(sg_site, script_name, api_key)

    cut = sg.find_one(
        "Cut",
        [["id", "is", cut_id]],
        _CUT_FIELDS
    )
    if not cut:
        raise ValueError("No Cut found with ID {}".format(cut_id))
    # TODO: check if we should just return a track or a timeline?
    timeline = otio.schema.Timeline(name=cut["code"])
    track = otio.schema.Track(name=cut["code"])
    track.metadata["sg"] = cut
    # TODO: check what should be done if these values are not set
    if cut["timecode_end_text"] and cut["timecode_start_text"]:
        track.source_range = otio.opentime.range_from_start_end_time(
            -otio.opentime.from_timecode(cut["timecode_end_text"], cut["fps"]),
            -otio.opentime.from_timecode(cut["timecode_start_text"], cut["fps"]),
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
    for cut_item in cut_items:
        clip = otio.schema.Clip()
        # Not sure if there is a better way to allow writing to EDL and getting the right
        # Reel name without having this dependency to the CMX adapter.
        clip.metadata["cmx_3600"] = {"reel": cut_item["code"]}
        clip.metadata["sg"] = cut_item
        if cut_item["version"]:
            clip.name = cut_item["version"]["name"]
        else:
            clip.name = cut_item["code"]
#        if cut_item["shot"]:
#            clip.metadata["sg"]["shot"] = cut_item.pop("shot")
#        if cut_item["version"]:
#            clip.name = cut_item["version"]["name"]
#            clip.metadata["sg"]["version"] = cut_item.pop("version")
#        else:
#            clip.name = cut_item["code"]
#        clip.metadata["sg"]["cut_item"] = cut_item
        clip.source_range = otio.opentime.TimeRange(
            start_time=RationalTime(cut_item["cut_item_in"], cut["fps"]),
            duration=RationalTime(cut_item["cut_item_duration"], cut["fps"])
        )
        # TODO: Add media reference for Version. This would require some logic to get them either
        #       from the uploaded media, but the AWS links expire after a while, or from the
        #       Published Files, which would require some logic on how to choose them.
        #       If we want available ranges, we also need to either rely on some Version fields,
        #       or use ffprobe to get the available ranges.
        track.append(clip)
    return timeline


def write_to_file(input_otio, filepath):
    """
    Write the given timeline to SG.

    The filepath is a query url which have the form:
    `https://<SG site>/<SG Entity type>?script=<my script>&api_key=<script key>&id=<SG Entity id>`

    :param input_otio: An :class:`otio.schema.Timeline` instance.
    :param str filepath: A query URL.
    :raises ValueError: For unsupported SG Entity types.
    """
    if not isinstance(input_otio, otio.schema.Timeline) and not isinstance(input_otio, otio.schema.Track):
        raise ValueError("Only OTIO Timelines and Video Tracks are supported.")
    if isinstance(input_otio, otio.schema.Track) and input_otio.kind != otio.schema.TrackKind.Video:
        raise ValueError("Only OTIO Video Tracks are supported.")
    sg_site, entity_type, entity_id, script_name, api_key = parse_sg_url(filepath)
    if entity_type != "Cut":
        raise ValueError("Only the following entity types are supported: {}".format(
            ", ".join(["Cut"])
        ))
    sg = shotgun_api3.Shotgun(sg_site, script_name, api_key)
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
    sg_data = video_track.metadata.get("sg")
    if not sg_data:
        raise ValueError("No SG data found for {}".format(video_track))
    if sg_data["type"] != entity_type:
        raise ValueError("Invalid {} SG data for a {}".format(sg_data["type"], entity_type))
    sg_cut = sg_data
    sg_project = sg_cut["project"]
    # sg_cut_link = sg_cut.get("entity") or sg_project
    sg_cut_items = []
    for clip in video_track.each_clip():
        sg_data = clip.metadata.get("sg")
        if not sg_data:
            logger.info("Not treating %s without SG data" % clip)
            continue
        if sg_data["type"] != "CutItem":
            logger.info("Not treating %s not linked to a SG CutItem" % clip)
            continue
        sg_cut_items.append(sg_data)
    sg_cut_data = {}
    # Collect and sanitize SG data
    # TODO: do it for real, this is just a proof of concept
    for k, v in sg_cut.items():
        if k in ["type", "id"]:
            continue
        if isinstance(v, otio._otio.AnyDictionary):
            sg_cut_data[k] = dict(v)
        elif isinstance(v, long):
            sg_cut_data[k] = int(v)
        else:
            sg_cut_data[k] = v
        if k == "fps":
            sg_cut_data[k] = float(v)

    if sg_cut.get("id"):  # Existing Cut, do an update?
        sg.update(
            sg_cut["type"],
            sg_cut["id"],
            sg_cut_data,
        )
    else:
        # Create a new Cut
        sg_cut = sg.create(
            sg_cut["type"],
            sg_cut_data,
        )
    # TODO: make sure the SG metadata is updated with the sg_cut
    batch_data = []
    for sg_cut_item in sg_cut_items:
        sg_cut_item["cut"] = sg_cut
        sg_cut_item["project"] = sg_project
        sg_cut_item_data = {}
        # Collect and sanitize SG data
        # TODO: do it for real, this is just a proof of concept
        for k, v in sg_cut_item.items():
            if k in ["type", "id", "cut_duration"]:  # cut_duration does not seem to be valid?
                continue
            if "." in k:
                continue
            if isinstance(v, otio._otio.AnyDictionary):
                sg_cut_item_data[k] = dict(v)
            elif isinstance(v, long):
                sg_cut_item_data[k] = int(v)
            else:
                sg_cut_item_data[k] = v
            if k == "fps":
                sg_cut_item_data[k] = float(v)
        if sg_cut_item.get("id"):
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
    if batch_data:
        res = sg.batch(batch_data)
        # TODO: update the SG metadata
    # TODO: deal with CutItems, Versions, Shots, etc...
    print(res)

# def write_to_string(
#     input_otio,
#     sg_url,
#     script_name,
#     api_key,
#     entity_type,
#     project,
#     link,
#     user=None,
#     description=None,
#     input_media=None,
#     local_storage_name=None,
#     shot_regexp=None,
#     use_smart_fields=False,
#     shot_cut_fields_prefix=None,
#     head_in=1001,
#     head_in_duration=8,
#     tail_out_duration=8,
#     flag_retimes_and_effects=True
# ):
#     """
#     Writes information from a :class:`otio.schema.Timeline` instance to
#     ShotGrid and returns a string.
#
#     This is the standard method for adapters to implement.
#     .. seealso:: https://opentimelineio.readthedocs.io/en/latest/tutorials/write-an-adapter.html#required-functions
#
#     :param input_otio: An :class:`otio.schema.Timeline` instance.
#     :param str sg_url: A SG site URL, e.g. "https://shotgrid.shotgunstudio.com".
#     :param str script_name: A SG script name.
#     :param str api_key: A SG API key.
#     :param str entity_type: An Entity type, e.g. Cut.
#     :param project: A SG Project entity.
#     :param link: A SG dictionary of the Entity to link the Cut to.
#     :param user: An optional SG User entity.
#     :param description: An optional description.
#     :param input_media: An optional path to a media file of the Timeline.
#     :param local_storage_name: If provided, the local storage where files will be published to.
#     :param shot_regexp: A regular expression to extract extra information from the
#                         clip comments.
#     :param bool use_smart_fields: Whether or not ShotGrid Shot cut smart fields
#                                       should be used.
#     :param str shot_cut_fields_prefix: If set, use custom Shot cut fields based
#                                        on the given prefix.
#     :param int head_in: Default head in frame number to use.
#     :param int head_in_duration: Default head in number of frames to use.
#     :param int tail_out_duration: Default tail out number of frames to use.
#     :param bool flag_retimes_and_effects: Whether or not to flag retimes and effects.
#     :returns: A string.
#     """
#     if not isinstance(input_otio, otio.schema.Timeline) and not isinstance(input_otio, otio.schema.Track):
#         raise ValueError("Only OTIO Timelines and Video Tracks are supported.")
#     if isinstance(input_otio, otio.schema.Track) and input_otio.kind != otio.schema.TrackKind.Video:
#         raise ValueError("Only OTIO Video Tracks are supported.")
#     if entity_type not in SG_SUPPORTED_ENTITY_TYPES:
#         raise ValueError("Only the following entity types are supported: {}".format(
#             ", ".join(SG_SUPPORTED_ENTITY_TYPES)
#         ))
#
#     sg = shotgun_api3.Shotgun(sg_url, script_name, api_key)
#     if entity_type == "Cut":
#         # OTIO suppports multiple video tracks, but ShotGrid cuts can only represent one.
#         if isinstance(input_otio, otio.schema.Timeline):
#             if len(input_otio.video_tracks()) > 1:
#                 logger.warning("Only one video track is supported, using the first one.")
#             # We could flatten the timeline here by using otio.core.flatten_stack(input_otio.video_tracks())
#             # But we lose information, for example the track source_range becomes ``None``
#             video_track = input_otio.video_tracks()[0]
#             # Change the track name to the timeline name.
#             video_track.name = input_otio.name
#         else:
#             video_track = input_otio
#         cut = SGCut(
#             video_track,
#             sg,
#             entity_type,
#             project,
#             link,
#             user,
#             description,
#             input_media,
#             local_storage_name,
#             shot_regexp,
#             use_smart_fields,
#             shot_cut_fields_prefix,
#             head_in,
#             head_in_duration,
#             tail_out_duration,
#             flag_retimes_and_effects
#         )
#         sg_cut = cut.create_sg_cut()
#         cut_items_by_shot = cut.create_sg_cut_items()
#         # TODO: Improve what's returned.
#         result = {
#             "sg_cut": sg_cut,
#             "sg_cut_items": cut_items_by_shot
#         }
#         return json.dumps(result)
