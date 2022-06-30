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
from .cut_clip import CutClip
from .sg_settings import SGSettings

logger = logging.getLogger(__name__)
logger.setLevel(SGSettings().log_level)


class CutTrack(otio.schema.Track):
    """
    A :class:`otio.schema.Track` in the context of a Cut.

    It is a subclass of :class:`otio.schema.Track` with the following additions:
    - :class:`CutClip` instances are added to the track, which have more attributes.
    - Names of clips are unique.
    - Clips are grouped by their shot, using :class:`ClipGroup` instances.
    """
    def __init__(self, *args, **kwargs):
        """
        Initialize an :class:`CutTrack` instance.
        """
        # Must be kept first, before adding any attributes
        super(CutTrack, self).__init__(*args, **kwargs)
        # Check if Clips have duplicate names and if they have, make sure their cut item names are unique.
        clip_names = [clip.unique_name for clip in self.each_clip()]
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
                    if clip.unique_name == duplicate_name:
                        clip.unique_name = "%s_%03d" % (clip.unique_name, clip_name_index)
                        clip_name_index += 1

        # Set the :class:`ClipGroup` objects for this track.
        self._shots_by_name = {}

# for n, item in enumerate(track):
#        previous_item = track[n - 1] if n > 0 else None
#        next_item = track[n + 1] if n + 1 < len(track) else None
#        if not isinstance(item, schema.Transition):
#            # find out if this item has any neighboring transition
#            if isinstance(previous_item, schema.Transition):
#                if previous_item.out_offset.value:
#                    transition_offsets[0] = previous_item.in_offset
#                else:
#                    transition_offsets[0] = None
#            if isinstance(next_item, schema.Transition):
#                if next_item.in_offset.value:
#                    transition_offsets[1] = next_item.out_offset
#                else:
#                    transition_offsets[1] = None

        # Note: there is an assumption here that all clips are CutClips
        for clip in self.each_clip():
            if clip.shot_name not in self._shots_by_name:
                self._shots_by_name[clip.shot_name] = ClipGroup(clip.shot_name, [clip])
            else:
                self._shots_by_name[clip.shot_name].add_clip(clip)

    @classmethod
    def from_timeline(
        cls,
        timeline,
    ):
        """
        Convenience method to Copy a Timeline and convert its video track
        from :class:`otio.schema.Track` to a :class:`sg_otio.CutTrack`.

        :param timeline: The :class:`otio.schema.Timeline` to convert.
        :returns: A :class:`otio.schema.Timeline` instance.
        """
        # We need to deepcopy the timeline, because the different elements
        # already have parents and otio will complain.
        audio_tracks = copy.deepcopy(timeline.audio_tracks())
        video_tracks = copy.deepcopy(timeline.video_tracks())
        if video_tracks:
            if len(video_tracks) > 1:
                logger.warning("Only one video track is supported, using the first one.")
                # We could flatten the timeline here by using otio.core.flatten_stack(input_otio.video_tracks())
                # But we lose information, for example the track source_range becomes ``None``
            video_tracks[0] = cls.from_track(
                video_tracks[0],
            )

        return otio.schema.Timeline(
            name=timeline.name,
            tracks=audio_tracks + video_tracks,
            metadata=timeline.metadata,
            global_start_time=timeline.global_start_time,
        )

    @classmethod
    def from_track(
        cls,
        track,
    ):
        """
        Convenience method to create a :class:`CutTrack` from a :class:`otio.schema.Track`

        :param track: The track to convert.
        :returns: A :class:`CutTrack` instance
        :raises ValueError: If the track is not a :class:`otio.schema.Track`
                            of kind :class:`otio.schema.TrackKind.Video`.
        """
        if not isinstance(track, otio.schema.Track) and not track.kind == otio.schema.TrackKind.Video:
            raise ValueError("Track %s must be an OTIO video track" % track)

        children = []
        clip_index = 1

        for child in track.each_child():
            if isinstance(child, otio.schema.Clip):
                clip = CutClip.from_clip(
                    child,
                    index=clip_index,
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
        )

    @property
    def shots(self):
        """
        Returns the :class:`ClipGroup` instances of the track.

        :returns: A list of :class:`ClipGroup` instances.
        """
        return [v for k, v in self._shots_by_name.items() if k is not None]

    @property
    def shot_names(self):
        """
        Returns the names of the shots of the track.

        :returns: A list of shot names.
        """
        return [k for k in self._shots_by_name.keys() if k is not None]

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
        :returns: A list of :class:`CutClip` instances.
        :raises ValueError: If the shot is unknown.
        """
        shot = self._shots_by_name.get(shot_name)
        if not shot:
            raise ValueError("ClipGroup %s not found" % shot_name)
        return shot.clips
