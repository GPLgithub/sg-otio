# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
from opentimelineio.opentime import RationalTime


class Shot(object):
    """
    A class representing a shot in an OTIO timeline.
    All the clips that have the same shot name are considered to be part of the same shot.

    It allows to access the clips that are part of the shot
    """

    def __init__(self, name, clips):
        self.name = name
        self._clips = clips
        self._index = None
        self._head_in = None
        self._cut_in = None
        self._cut_out = None
        self._tail_out = None
        self._has_effects = False
        self._has_retime = False
        # All clips should have the same frame rate.
        self._frame_rate = clips[0].duration().rate
        self._compute_shot_values()

    @property
    def clips(self):
        """
        Returns the clips that are part of the shot.

        :returns: A list of :class:`ExtendedClip` instances.
        """
        return self._clips

    def _compute_shot_values(self):
        """
        Computes the shot values given the clips values.
        """
        for clip in self.clips:
            if self._index is None or clip.index < self._index:
                self._index = clip.index
            if self._head_in is None or clip.head_in < self._head_in:
                self._head_in = clip.head_in
            if self._cut_in is None or clip.cut_in < self._cut_in:
                self._cut_in = clip.cut_in
            if self._cut_out is None or clip.cut_out > self._cut_out:
                self._cut_out = clip.cut_out
            if self._tail_out is None or clip.tail_out > self._tail_out:
                self._tail_out = clip.tail_out
            if not self._has_effects and clip.has_effects:
                self._has_effects = True
            if not self._has_retime and clip.has_retime:
                self._has_retime = True

    @property
    def index(self):
        """
        Returns the smallest index of the shot's clips.

        :returns: An integer.
        """
        return self._index

    @property
    def cut_in(self):
        """
        Returns the smallest cut_in of the shot's clips.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._cut_in

    @property
    def cut_out(self):
        """
        Returns the largest cut_out of the shot's clips.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._cut_out

    @property
    def head_in(self):
        """
        Returns the smallest head_in of the shot's clips.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._head_in

    @property
    def head_out(self):
        """
        Returns the head out of the shot.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self.cut_in - RationalTime(1, self._frame_rate)

    @property
    def head_duration(self):
        """
        Returns the head duration of the shot.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self.head_out - self.head_in + RationalTime(1, self._frame_rate)

    @property
    def tail_in(self):
        """
        Returns the tail in of the shot.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self.cut_out + RationalTime(1, self._frame_rate)

    @property
    def tail_out(self):
        """
        Returns the largest tail_out of the shot's clips.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._tail_out

    @property
    def tail_duration(self):
        """
        Returns the tail duration of the shot.

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
        Returns the duration of the shot.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self.cut_out - self.cut_in + RationalTime(1, self._frame_rate)

    @property
    def working_duration(self):
        """
        Returns the working duration of the shot.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self.tail_out - self.head_in
