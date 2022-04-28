# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import copy
from collections import defaultdict

import opentimelineio as otio
from .extended_clip import ExtendedClip
from .shot import Shot


class ExtendedTrack(otio.schema.Track):
    """
    A track where :class:`otio.schema.Clip` objects are replaced with :class:`ExtendedClip` objects,
    and with knowledge about shots, and clips in each shot.
    """
    def __init__(self, *args, **kwargs):
        super(ExtendedTrack, self).__init__(*args, **kwargs)
        # Check if Clips have duplicate names and if they have, make sure their names are unique.
        clip_names = [clip.name for clip in self.each_clip()]
        seen_names = set()
        duplicate_names = [
            clip_name for clip_name in clip_names if clip_name in seen_names or seen_names.add(clip_name)
        ]
        if duplicate_names:
            for duplicate_name in duplicate_names:
                index = 1
                for clip in self.each_clip():
                    if clip.name == duplicate_name:
                        clip.name = "%s_%03d" % (clip.name, index)
                        index += 1

        # Set the :class:`Shot` objects for this track.
        clips_by_shot_name = defaultdict(list)
        self._shots_by_name = {}
        for clip in self.each_clip():
            # Note that some clips might not have information to be able to link them to a shot,
            # in which case the shot is ``None``.
            clips_by_shot_name[clip.shot_name].append(clip)
        for shot_name, clips in clips_by_shot_name.items():
            self._shots_by_name[shot_name] = Shot(shot_name, clips)

        # For cases where multiple clips belong to the same shot,
        # head_in_duration and tail_out_duration must be adjusted, so that all the clips
        # in the shot have the same head_in and tail_out.
        for shot in self._shots_by_name.values():
            if len(shot.clips) > 1:
                min_source_in = min([clip.source_in for clip in shot.clips])
                max_source_out = max([clip.source_out for clip in shot.clips])
                for clip in shot.clips:
                    if clip.source_in > min_source_in:
                        clip.head_in_duration += clip.source_in - min_source_in
                    if clip.source_out < max_source_out:
                        clip.tail_out_duration += max_source_out - clip.source_out

    @classmethod
    def from_track(
            cls,
            track,
            clip_class=ExtendedClip,
            head_in=1001,
            head_in_duration=8,
            tail_out_duration=8,
            use_clip_names_for_shot_names=False,
            clip_name_shot_regexp=None,
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
        :returns: A :class:`ExtendedTrack` instance.
        """
        if not isinstance(track, otio.schema.Track) and not track.kind == otio.schema.TrackKind.Video:
            raise ValueError("Track %s must be an OTIO video track" % track)

        children = []
        clip_index = 1

        for child in track.each_child():
            if isinstance(child, otio.schema.Transition):
                children.append(copy.deepcopy(child))
            elif isinstance(child, otio.schema.Clip):
                clip = clip_class.from_clip(
                    child,
                    index=clip_index,
                    head_in=head_in,
                    head_in_duration=head_in_duration,
                    tail_out_duration=tail_out_duration,
                    use_clip_names_for_shot_names=use_clip_names_for_shot_names,
                    clip_name_shot_regexp=clip_name_shot_regexp
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
        Returns the :class:`Shot` instances of the track.

        ..note:: some clips might not have information to be able to link them to a shot,
        in which case the shot is ``None``.

        :returns: A list of :class:`Shot` instances.
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

        :param str shot: The shot name.
        :returns: A list of :class:`ExtendedClip` instances.
        :raises ValueError: If the shot does not exist.
        """
        shot = self._shots_by_name.get(shot_name)
        if not shot:
            raise ValueError("Shot %s not found" % shot_name)
        return shot.clips
