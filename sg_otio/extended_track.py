# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import copy
import logging

import opentimelineio as otio

from .clip_group import ClipGroup
from .constants import DEFAULT_HEAD_IN, DEFAULT_HEAD_IN_DURATION, DEFAULT_TAIL_OUT_DURATION
from .extended_clip import ExtendedClip

logger = logging.getLogger(__name__)


class ExtendedTrack(otio.schema.Track):
    """
    An extended :class:`otio.schema.Track` handling clips with :class:`ExtendedClip` instances.

    It is a subclass of :class:`otio.schema.Track` with the following additions:
    - :class:`ExtendedClip` instances are added to the track, which have more attributes.
    - Names of clips are unique.
    - Clips are grouped by their shot, using :class:`ClipGroup` instances.
    """
    def __init__(self, log_level=logging.INFO, *args, **kwargs):
        """
        Initialize an :class:`ExtendedTrack` instance.

        :param log_level: The log level to use.
        """
        super(ExtendedTrack, self).__init__(*args, **kwargs)
        logger.setLevel(log_level)
        # Check if Clips have duplicate names and if they have, make sure their names are unique.
        clip_names = [clip.name for clip in self.each_clip()]
        seen_names = set()
        duplicate_names = []
        for clip_name in clip_names:
            if clip_name not in seen_names:
                seen_names.add(clip_name)
            else:
                duplicate_names.append(clip_name)
        if duplicate_names:
            for duplicate_name in duplicate_names:
                clip_name_index = 1
                for clip in self.each_clip():
                    if clip.name == duplicate_name:
                        clip.name = "%s_%03d" % (clip.name, clip_name_index)
                        clip_name_index += 1

        # Set the :class:`ClipGroup` objects for this track.
        self._shots_by_name = {}
        for clip in self.each_clip():
            if clip.shot_name not in self._shots_by_name:
                self._shots_by_name[clip.shot_name] = ClipGroup(clip.shot_name, [clip])
            else:
                self._shots_by_name[clip.shot_name].add_clip(clip)

    @classmethod
    def from_track(
        cls,
        track,
        clip_class=ExtendedClip,
        head_in=DEFAULT_HEAD_IN,
        head_in_duration=DEFAULT_HEAD_IN_DURATION,
        tail_out_duration=DEFAULT_TAIL_OUT_DURATION,
        use_clip_names_for_shot_names=False,
        clip_name_shot_regexp=None,
        log_level=logging.INFO,
    ):
        """
        Convenience method to create a :class:`ExtendedTrack` from a :class:`otio.schema.Track`

        :param track: The track to convert.
        :param int head_in: The default head in time of clips.
        :param int head_in_duration: The default head in duration of clips.
        :param int tail_out_duration: The default tail out duration of clips.
        :param bool use_clip_names_for_shot_names: If ``True``, clip names can be used as shot names.
        :param clip_name_shot_regexp: If given, and use_clip_names_for_shot_names is ``True``,
                                      use this regexp to find the shot name from the clip name.
        :param log_level: The log level to use.
        :returns: A :class:`ExtendedTrack` instance
        :raises ValueError: If the track is not a :class:`otio.schema.Track`
                            of kind :class:`otio.schema.TrackKind.Video`.
        """
        if not isinstance(track, otio.schema.Track) and not track.kind == otio.schema.TrackKind.Video:
            raise ValueError("Track %s must be an OTIO video track" % track)

        children = []
        clip_index = 1

        for child in track.each_child():
            if isinstance(child, otio.schema.Clip):
                clip = clip_class.from_clip(
                    child,
                    index=clip_index,
                    head_in=head_in,
                    head_in_duration=head_in_duration,
                    tail_out_duration=tail_out_duration,
                    use_clip_names_for_shot_names=use_clip_names_for_shot_names,
                    clip_name_shot_regexp=clip_name_shot_regexp,
                    log_level=log_level,
                )
                clip_index += 1
                children.append(clip)
            else:
                children.append(copy.deepcopy(child))

        return cls(
            name=track.name,
            metadata=track.metadata,
            children=children,
            source_range=track.source_range,
            log_level=log_level,
        )

    @property
    def shots(self):
        """
        Returns the :class:`ClipGroup` instances of the track.

        ..note:: some clips might not have information to be able to link them to a shot,
        in which case the :class:`ClipGroup` does exist, but its name is ``None``.

        :returns: A list of :class:`ClipGroup` instances.
        """
        return list(self._shots_by_name.values())

    @property
    def shot_names(self):
        """
        Returns the names of the shots of the track.

        There can be a shot named ``None`` if some clips don't have information
        to be able to link them to a shot.

        :returns: A list of shot names.
        """
        return list(self._shots_by_name.keys())

    @property
    def shots_by_name(self):
        """
        Returns a dictionary of shots, keyed by their name.

        :returns: A dictionary.
        """
        return self._shots_by_name

    def shot_clips(self, shot_name):
        """
        Return the clips that belong to a given shot.

        :param shot: A str, the shot name, or ``None``.
        :returns: A list of :class:`ExtendedClip` instances.
        :raises ValueError: If the shot is unknown.
        """
        shot = self._shots_by_name.get(shot_name)
        if not shot:
            raise ValueError("ClipGroup %s not found" % shot_name)
        return shot.clips