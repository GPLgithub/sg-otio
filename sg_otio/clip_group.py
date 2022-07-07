# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
from opentimelineio.opentime import RationalTime

from .cut_clip import SGCutClip
from .utils import compute_clip_shot_name


class ClipGroup(object):
    """
    A class representing group of clips in an OTIO timeline.

    Clips can be grouped together when they reference the same source. For example,
    if multiple clips in a timeline represent the same shot, (e.g. for flashback effects)

    A single "media item" is associated with all the entries in the same group.
    All frame values are relative to the earliest entry head in value.
        --------------------------
        |       instance 1       |
        --------------------------
        ^   --------------------
        |   |   instance 2     |
            --------------------
        |  ---------------------------------
           |      instance 3               |
        |  ---------------------------------
                                           ^
        |                                  |
        ------------------------------------
        |  media covering all instances    |
        ------------------------------------
    """

    def __init__(self, name, clips=None, sg_shot=None):
        """
        Initializes a new instance of the :class:`ClipGroup` class.

        :param str name: The name of the group.
        :param clips: A list of :class:`sg_otio.SGCutClip` instances.
        """
        super(ClipGroup, self).__init__()
        self.name = name
        self._clips = []
        self._index = None
        self._source_in = None
        self._source_out = None
        self._head_in = None
        self._head_out = None
        self._cut_in = None
        self._cut_out = None
        self._tail_in = None
        self._tail_out = None
        self._has_effects = False
        self._has_retime = False
        self._frame_rate = None
        self._earliest_clip = None
        self._last_clip = None
        if clips:
            self.add_clips(clips)
        self.sg_shot = sg_shot

    @property
    def clips(self):
        """
        Returns the clips that are part of the group.

        :returns: A list of :class:`otio.schema.Clip` instances.
        """
        # Don't return the original list, because it might be modified.
        for clip in self._clips:
            yield(clip)
        #return list(self._clips)

    def add_clip(self, clip):
        """
        Adds a clip to the group.

        Recompute the clip group values, since they might have changed,
        because the group values cover the range of all clips in the group.

        :param clip: A :class:`otio.schema.Clip` instance.
        """
        if not self._frame_rate:
            self._frame_rate = clip.duration().rate
        if clip.duration().rate != self._frame_rate:
            raise ValueError(
                "Clips must have the same frame rate. Clip: %s frame rate %s, group frame rate: %s" % (
                    clip.name, clip.duration().rate, self._frame_rate
                )
            )
        clip.sg_shot = self.sg_shot
        if self._earliest_clip is None or clip.source_in < self._earliest_clip.source_in:
            self._earliest_clip = clip
        if self._last_clip is None or clip.source_out > self._last_clip.source_out:
            self._last_clip = clip
        if not self._has_effects and clip.has_effects:
            self._has_effects = True
        if not self._has_retime and clip.has_retime:
            self._has_retime = True
        self._clips.append(clip)
        self._compute_group_values(self._clips)

    def add_clips(self, clips):
        """
        Adds clips to the group.

        Recompute the clip group values, since they might have changed,
        because the group values cover the range of all clips in the group.

        :param clips: A list of :class:`otio.schema.Clip` instances.
        :raises ValueError: If the clips do not have the same frame rate
        """
        for clip in clips:
            self.add_clip(clip)

    def _compute_group_values(self, clips):
        """
        Computes the group values given a list of clips.

        Since the group values have to cover the range of all clips,
        when clips are added to the group, the group values need to be
        recomputed.

        Also, the head_in_duration and tail_out_duration of all clips in the group
        must be adjusted to make sure that their values are correct, and reflect
        the whole range of the group.

        :param clips: A list of :class:`otio.schema.Clip` instances.
        """
        if not self._clips:
            return
        # Get some values from the first and last clips
        self._index = self._earliest_clip.index
        self._source_in = self._earliest_clip.source_in
        head_in, head_duration, _ = self._earliest_clip.get_head_tail_values()

        self._source_out = self._last_clip.source_out
        _, _, tail_duration = self._last_clip.get_head_tail_values()

        # Adjust the head_in_duration and tail_out_duration of all clips in the group
        for clip in self.clips:
            clip.head_in = head_in
            clip.head_in_duration = clip.source_in - self.source_in + head_duration
            clip.tail_out_duration = self.source_out - clip.source_out + tail_duration

        # Get other values from first and last clips now that they have been set.
        self._head_in = self._earliest_clip.head_in
        self._head_out = self._earliest_clip.head_out
        self._cut_in = self._earliest_clip.cut_in
        self._cut_out = self._last_clip.cut_out
        self._tail_in = self._last_clip.tail_in
        self._tail_out = self._last_clip.tail_out

    @property
    def sg_shot(self):
        """
        Return the SG Shot associated with this ClipGroup.

        :retruns: A dictionary or ``None``.
        """
        return self._sg_shot

    @sg_shot.setter
    def sg_shot(self, value):
        """
        Set the SG Shot associated with this ClipGroup.

        Propagate it to contained clips.

        :param value: A SG Shot dictionary or ``None``.
        """
        self._sg_shot = value
        for clip in self.clips:
            clip.sg_shot = self._sg_shot
        self._compute_group_values(self._clips)

    @property
    def index(self):
        """
        Returns the index of the group, i.e. the smallest index of all clips in the Track.

        Since the group values cover the range of all clips,
        the index of the group is the smallest index of the group's clips.

        ..seealso:: :attr:`sg_otio.SGCutClip.index`

        :returns: An integer.
        """
        return self._index

    @property
    def source_in(self):
        """
        Returns the source_in of the group.

        Since the group values cover the range of all clips,
        the source_in of the group is the smallest source_in of the group's clips.

        ..seealso:: :attr:`sg_otio.ExtendedClip.source_in`

        :returns: A :class:`otio.schema.TimeRange` instance.
        """
        return self._source_in

    @property
    def source_out(self):
        """
        Returns the source_out of the group.

        Since the group values cover the range of all clips,
        the source_out of the group is the largest source_out of the group's clips.

        ..seealso:: :attr:`sg_otio.ExtendedClip.source_out`

        :returns: A :class:`otio.schema.TimeRange` instance.
        """
        return self._source_out

    @property
    def cut_in(self):
        """
        Returns cut_in of the group.

        Since the group values cover the range of all clips,
        the cut_in of the group is the smallest cut_in of the group's clips.

        ..seealso:: :attr:`sg_otio.ExtendedClip.cut_in`

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._cut_in

    @property
    def cut_out(self):
        """
        Returns the cut_out of the group.

        Since the group values cover the range of all clips,
        the cut_out of the group is the largest cut_out of the group's clips.

        ..seealso:: :attr:`sg_otio.ExtendedClip.cut_out`

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._cut_out

    @property
    def head_in(self):
        """
        Returns the head_in of the group.

        Since the group values cover the range of all clips,
        the head_in of the group is the smallest head_in of the group's clips.

        ..seealso:: :attr:`sg_otio.ExtendedClip.head_in`

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._head_in

    @property
    def head_out(self):
        """
        Returns the head out of the group.

        Since the group values cover the range of all clips,
        the head_out of the group is the largest head_out of the group's clips.

        ..seealso:: :attr:`sg_otio.SGCutClip.head_out`

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._head_out

    @property
    def head_duration(self):
        """
        Returns the head duration of the group.

        Since the group values cover the range of all clips,
        The head duration is the difference between the largest head_out of the group's clips
        and the smallest head_in of the group's clips.

        ..seealso:: :attr:`sg_otio.ExtendedClip.head_in`
        ..seealso:: :attr:`sg_otio.ExtendedClip.head_out`

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self.head_out - self.head_in + RationalTime(1, self._frame_rate)

    @property
    def tail_in(self):
        """
        Returns the tail in of the group.

        Since the group values cover the range of all clips,
        The tail in is the largest tail_in of the group's clips.

        ..seealso:: :attr:`sg_otio.ExtendedClip.tail_in`

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._tail_in

    @property
    def tail_out(self):
        """
        Returns the tail out of the group.

        Since the group values cover the range of all clips,
        The tail out is the largest tail_out of the group's clips.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._tail_out

    @property
    def tail_duration(self):
        """
        Returns the tail duration of the group.

        Since the group values cover the range of all clips,
        The tail duration is the difference between the largest tail_out of the group's clips
        and the smallest tail_in of the group's clips.

        ..seealso:: :attr:`sg_otio.ExtendedClip.tail_in`
        ..seealso:: :attr:`sg_otio.ExtendedClip.tail_out`

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self.tail_out - self.tail_in + RationalTime(1, self._frame_rate)

    @property
    def has_effects(self):
        """
        Returns ``True`` if the shot has at least one clip with effects.

        :returns: A boolean.
        """
        return self._has_effects

    @property
    def has_retime(self):
        """
        Returns ``True`` if the shot has at least one clip with retime.

        :returns: A boolean.
        """
        return self._has_retime

    @property
    def duration(self):
        """
        Returns the duration of the group, taking into account transitions
        and effects.

        Since the group values cover the range of all clips,
        The visible duration is the difference between the largest cut_out of the group's clips
        and the smallest cut_in of the group's clips.

        ..seealso:: :attr:`sg_otio.ExtendedClip.visible_duration`
        ..seealso:: :attr:`sg_otio.ExtendedClip.cut_in`
        ..seealso:: :attr:`sg_otio.ExtendedClip.cut_out`

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self.cut_out - self.cut_in + RationalTime(1, self._frame_rate)

    @property
    def working_duration(self):
        """
        Returns the working duration of the group.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self.tail_out - self.head_in

    @staticmethod
    def groups_from_track(video_track):
        """
        Convenience method to generate :class:`ClipGroup` from a video track.

        :param video_track: A class:`otio.schema.Track` instance.
        :returns: A dictionary where keys are shot names and values :class:`ClipGroup`
                  instances.
        """
        shots_by_name = {}
        for i, clip in enumerate(video_track.each_clip()):
            shot_name = compute_clip_shot_name(clip)
            # Store a tuple with the clip index and the clip
            if shot_name not in shots_by_name:
                shots_by_name[shot_name] = ClipGroup(shot_name)
            shots_by_name[shot_name].add_clip(
                SGCutClip(clip, index=i + 1, sg_shot=None)
            )
        return shots_by_name
