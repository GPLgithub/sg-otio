# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging
import six
from six.moves.urllib import parse

import opentimelineio as otio
import shotgun_api3
from opentimelineio.opentime import RationalTime

from sg_otio.constants import _CUT_ITEM_FIELDS, _CUT_FIELDS
from sg_otio.cut_track import CutTrack
from sg_otio.cut_clip import CutClip

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
    sg_cut = None
    sg_project = None
    sg_linked_entity = None
    sg = shotgun_api3.Shotgun(sg_site, session_token=session_token)
    if entity_type == "Cut":
        sg_cut = sg.find_one(
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
        sg_project = sg.find_one(
            entity_type,
            [["id", "is", entity_id]],
        )
        if not sg_project:
            raise ValueError(
                "Unable to retrieve a %s with the id %s" % (entity_type, entity_id)
            )
    else:
        sg_linked_entity = sg.find_one(
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
    cut_track = video_track
    sg_track_data = video_track.metadata.get("sg")
    if sg_track_data and sg_track_data["type"] != "Cut":
        raise ValueError(
            "Invalid {} SG data for a {}".format(sg_track_data["type"], "Cut")
        )
    # Convert to a CutTrack if one was not provided.
    if not isinstance(cut_track, CutTrack):
        cut_track = CutTrack.from_track(video_track)
        sg_track_data = cut_track.sg_payload

    sg_cut_items = []
    cut_item_clips = []
    # Loop over clips from the cut_track in case we did a conversion to get
    # SG data.
    # Keep references to original clips
    video_clips = list(video_track.each_clip())
    for i, clip in enumerate(cut_track.each_clip()):
        sg_data = clip.metadata.get("sg")
        if not sg_data:
            if isinstance(clip, CutClip):
                sg_data = clip.sg_payload
            else:
                logger.info("Not treating %s without SG data" % clip)
                continue
        if sg_data["type"] != "CutItem":
            logger.info("Not treating %s not linked to a SG CutItem" % clip)
            continue
        sg_cut_items.append(sg_data)
        # Make sure we keep a reference to the original clip to able to set
        # SG metadata.
        cut_item_clips.append(video_clips[i])
    sg_cut_data = {}
    # Collect and sanitize SG data
    # TODO: do it for real, this is just a proof of concept
    for k, v in sg_track_data.items():
        if k in ["type", "id"]:
            continue
        if isinstance(v, otio._otio.AnyDictionary):
            sg_cut_data[k] = dict(v)
        else:
            for integer_type in six.integer_types:
                if isinstance(v, integer_type):
                    sg_cut_data[k] = int(v)
                    break
            else:
                sg_cut_data[k] = v
        if k == "fps":
            sg_cut_data[k] = float(v)

    if sg_cut:  # Update existing Cut
        sg.update(
            sg_cut["type"],
            sg_cut["id"],
            sg_cut_data,
        )
    else:
        revision_number = 1
        previous_cut = sg.find_one(
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
        sg_cut_data["description"] = "Blah"
        sg_cut = sg.create(
            "Cut",
            sg_cut_data,
        )
        # Update the track with the result
        logger.info("Updating %s SG metadata with %s" % (video_track, sg_cut))
        video_track.metadata["sg"] = sg_cut
    batch_data = []
    for item_index, sg_cut_item in enumerate(sg_cut_items):
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
            else:
                for integer_type in six.integer_types:
                    if isinstance(v, integer_type):
                        sg_cut_item_data[k] = int(v)
                        break
                else:
                    sg_cut_item_data[k] = v
            if k == "fps":
                sg_cut_item_data[k] = float(v)
        sg_cut_item_data["cut"] = sg_cut
        sg_cut_item_data["project"] = sg_project
        sg_cut_item_data["cut_order"] = item_index + 1
        # Check if we should update an existing CutItem of create a new one
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
        res = sg.batch(batch_data)
        # Update the clips SG metadata
        for i, sg_cut_item in enumerate(res):
            cut_item_clips[i].metadata["sg"] = sg_cut_item
            logger.info("Updating %s SG metadata with %s" % (cut_item_clips[i], sg_cut_item))

    # TODO: deal with CutItems, Versions, Shots, etc...
