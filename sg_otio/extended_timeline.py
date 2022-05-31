# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging

import opentimelineio as otio

from .constants import DEFAULT_HEAD_IN, DEFAULT_HEAD_IN_DURATION, DEFAULT_TAIL_OUT_DURATION
from .cut_track import CutTrack
from .cut_clip import CutClip

logger = logging.getLogger(__name__)


def extended_timeline(
    timeline,
    track_class=CutTrack,
    clip_class=CutClip,
    head_in=DEFAULT_HEAD_IN,
    head_in_duration=DEFAULT_HEAD_IN_DURATION,
    tail_out_duration=DEFAULT_TAIL_OUT_DURATION,
    use_clip_names_for_shot_names=False,
    clip_name_shot_regexp=None,
    log_level=logging.INFO,
):
    """
    Copy a Timeline and convert its video tracks from :class:`otio.schema.Track` to
    :class:`sg_otio.CutTrack`.

    :param timeline: The :class:`otio.schema.Timeline` to convert.
    :param track_class: The class to use for the tracks, e.g. :class:`sg_otio.CutTrack`.
    :param int head_in: The default head in time of clips.
    :param int head_in_duration: The default head in duration of clips.
    :param int tail_out_duration: The default tail out duration of clips.
    :param bool use_clip_names_for_shot_names: If ``True``, clip names can be used as shot names.
    :param clip_name_shot_regexp: If given, and use_clip_names_for_shot_names is ``True``,
                                  use this regexp to find the shot name from the clip name.
    :param log_level: The log level to use.
    :returns: A :class:`otio.schema.Timeline` instance.
    """
    audio_tracks = timeline.audio_tracks()
    video_tracks = timeline.video_tracks()
    if len(video_tracks) > 1:
        logger.warning("Only one video track is supported, using the first one.")
        # We could flatten the timeline here by using otio.core.flatten_stack(input_otio.video_tracks())
        # But we lose information, for example the track source_range becomes ``None``
    video_tracks[0] = track_class.from_track(
        video_tracks[0],
        clip_class=clip_class,
        head_in=head_in,
        head_in_duration=head_in_duration,
        tail_out_duration=tail_out_duration,
        use_clip_names_for_shot_names=use_clip_names_for_shot_names,
        clip_name_shot_regexp=clip_name_shot_regexp,
        log_level=log_level,
    )

    return otio.schema.Timeline(
        name=timeline.name,
        tracks=audio_tracks + video_tracks,
        metadata=timeline.metadata,
        global_start_time=timeline.global_start_time,
    )
