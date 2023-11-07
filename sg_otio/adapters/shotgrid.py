# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging
from urllib import parse

import opentimelineio as otio
import shotgun_api3

from sg_otio.sg_cut_track_writer import SGCutTrackWriter
from sg_otio.sg_cut_reader import SGCutReader

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
    return SGCutReader(sg).read(cut_id)


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
