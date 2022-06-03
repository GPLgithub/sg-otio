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
from sg_otio.sg_cut_track_writer import SGCutTrackWriter
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def parse_sg_url(url):
    """
    Parse a SG url, extract the SG site url, credentials and other informations.

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

    The retrieved SG entities are stored in the items metadata.

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
            start_time=otio.opentime.from_timecode(cut_item["timecode_cut_item_in_text"], cut["fps"]),
            duration=otio.opentime.from_timecode(cut_item["timecode_cut_item_out_text"], cut["fps"])
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
    `https://<SG site>/<SG Entity type>?session_token=<session token>&id=<SG Entity id>`

    The Entity type can either be:
    - A Cut, in that case the Cut with the given id will be updated.
    - A Project, a new Cut will be created, linked to this Project.
    - An arbitrary Entity type, e.g. a Sequence, a new Cut will be created, linked
      to the Entity.

    :param input_otio: An :class:`otio.schema.Timeline` instance.
    :param str filepath: A query URL.
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
        description="Generated from sg-otio"
    )
    return
