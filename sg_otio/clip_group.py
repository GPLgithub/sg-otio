# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
from opentimelineio.opentime import RationalTime


class ClipGroup(object):
    """
    A class representing group of clips in an OTIO timeline.

    Clips can be grouped together when they reference the same source. For example, if multiple clips
    in a timeline represent the same shot, they can be grouped together, and some information about them
    can be inferred, like the source_in and source_out for all the clips in the shot (i.e. the earliest
    start time and the latest end time of all clips).
    """

    def __init__(self, name, clips):
        """
        Initializes a new instance of the :class:`ClipGroup` class.

        .. note:: Ideally this should derive from a :class:`otio.schema.Stack`
                  but :class:`CutClip` code has a strong assumption that everything
                  is in a single Track, right under a Timeline.
                  Also, some adapters like cmx_3600 don't really support anything
                  else than simple composition.

        :param str name: The name of the group.
        :param clips: A list of :class:`otio.schema.Clip` instances.
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
        if clips:
            self.add_clips(clips)

    @property
    def clips(self):
        """
        Returns the clips that are part of the group.

        :returns: A list of :class:`otio.schema.Clip` instances.
        """
        # Don't return the original list, because it might be modified.
        return list(self._clips)

    def add_clip(self, clip):
        """
        Adds a clip to the group.

        Recompute the clip group values, since they might have changed,
        because the group values cover the range of all clips in the group.

        :param clip: A :class:`otio.schema.Clip` instance.
        """
        self.add_clips([clip])

    def add_clips(self, clips):
        """
        Adds clips to the group.

        Recompute the clip group values, since they might have changed,
        because the group values cover the range of all clips in the group.

        :param clips: A list of :class:`otio.schema.Clip` instances.
        :raises ValueError: If the clips do not have the same frame rate
        """
        if not self._frame_rate:
            self._frame_rate = clips[0].duration().rate
        for clip in clips:
            if clip.duration().rate != self._frame_rate:
                raise ValueError(
                    "Clips must have the same frame rate. Clip: %s frame rate %s, group frame rate: %s" % (
                        clip.name, clip.duration().rate, self._frame_rate
                    )
                )
        self._clips.extend(clips)
        self._compute_group_values(clips)

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
        for clip in clips:
            if self._index is None or clip.index < self._index:
                self._index = clip.index
            if self._source_in is None or clip.source_in < self._source_in:
                self._source_in = clip.source_in
            if self._head_in is None or clip.head_in < self._head_in:
                self._head_in = clip.head_in
            if self._head_out is None or clip.head_out < self._head_out:
                self._head_out = clip.head_out
            if self._cut_in is None or clip.cut_in < self._cut_in:
                self._cut_in = clip.cut_in
            if self._source_out is None or clip.source_out > self._source_out:
                self._source_out = clip.source_out
            if self._cut_out is None or clip.cut_out > self._cut_out:
                self._cut_out = clip.cut_out
            if self._tail_in is None or clip.tail_in > self._tail_in:
                self._tail_in = clip.tail_in
            if self._tail_out is None or clip.tail_out > self._tail_out:
                self._tail_out = clip.tail_out
            if not self._has_effects and clip.has_effects:
                self._has_effects = True
            if not self._has_retime and clip.has_retime:
                self._has_retime = True

        # Adjust the head_in_duration and tail_out_duration of all clips in the group
        for clip in self.clips:
            clip.head_in_duration = clip.source_in - self.source_in + self.head_duration
            clip.tail_out_duration = self.source_out - clip.source_out + self.tail_duration

    @property
    def index(self):
        """
        Returns the index of the group, i.e. the smallest index of all clips in the Track.

        Since the group values cover the range of all clips,
        the index of the group is the smallest index of the group's clips.

        ..seealso:: :attr:`sg_otio.CutClip.index`

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

        ..seealso:: :attr:`sg_otio.ExtendedClip.head_out`

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
