# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging

import opentimelineio as otio
import six
from opentimelineio.opentime import RationalTime

from .sg_settings import SGSettings
from .utils import compute_clip_shot_name

logger = logging.getLogger(__name__)
logger.setLevel(SGSettings().log_level)


class CutClip(otio.schema.Clip):
    """
    A Clip in the context of a Cut.
    """

    def __init__(
        self,
        index=1,
        effects=None,
        markers=None,
        *args,
        **kwargs
    ):
        """
        Construct a :class:`CutClip` instance.

        :param int index: The index of the clip in the track.
        :param effects: A list of :class:`otio.schema.Effect` instances.
        :param markers: A list of :class:`otio.schema.Marker` instances.
        """
        super(CutClip, self).__init__(*args, **kwargs)
        # TODO: check what we should grab from the SG metadata, if any.
        # If the clip has a reel name, override its name.
        if self.metadata.get("cmx_3600", {}).get("reel"):
            self.name = self.metadata["cmx_3600"]["reel"]
        self._frame_rate = self.duration().rate
        self._index = index
        sg_settings = SGSettings()
        self._head_in = RationalTime(sg_settings.default_head_in, self._frame_rate)
        self._head_in_duration = RationalTime(sg_settings.default_head_in_duration, self._frame_rate)
        self._tail_out_duration = RationalTime(sg_settings.default_tail_out_duration, self._frame_rate)
        self._shot_name = None
        self.effect = self._relevant_timing_effect(effects or [])
        self._markers = markers or []
        self.shot_name = compute_clip_shot_name(self)
        self._unique_name = self.name

    @classmethod
    def from_clip(
        cls,
        clip,
        index=1,
    ):
        """
        Convenience method to create a :class:`CutClip` instance from a
        :class:`otio.schema.Clip` instance.

        :param clip: A :class:`otio.schema.Clip` instance.
        :param int index: The index of the clip in the track.
        :returns: A :class:`CutClip` instance.
        """
        return cls(
            name=clip.name,
            source_range=clip.source_range,
            index=index,
            media_reference=clip.media_reference,
            metadata=clip.metadata,
            effects=clip.effects,
            markers=clip.markers,
        )

    @property
    def effect(self):
        """
        Return the effect.
        """
        return self._effect

    @effect.setter
    def effect(self, value):
        """
        Set the effect for the clip.

        We only support one effect per clip, and it must be either a
        :class:`otio.schema.LinearTimeWarp` or a :class:`otio.schema.FreezeFrame`.
        """
        self._effect = value

    @staticmethod
    def _is_timing_effect_supported(effect):
        """
        Check if the effect is supported, return ``True`` if it is.

        We only support LinearTimeWarp and FreezeFrame effects for now (same as cmx_3600).

        :param effect: A :class:`otio.schema.Effect` instance.
        :returns: A bool.
        """
        if isinstance(effect, otio.schema.LinearTimeWarp):
            return True
        return False

    @staticmethod
    def _relevant_timing_effect(effects):
        """
        Return the relevant timing effect for the given clip.

        We only support one effect per clip, and it must be either a
        :class:`otio.schema.LinearTimeWarp` or a :class:`otio.schema.FreezeFrame`.

        :param effects: A list of :class:`otio.schema.Effect` instances.
        :returns: An effect or ``None``.
        """
        # check to see if there is more than one timing effect
        supported_effects = []
        for effect in effects:
            if CutClip._is_timing_effect_supported(effect):
                supported_effects.append(effect)
            else:
                logger.warning(
                    "Unsupported effect %s will be ignored" % effect
                )
        timing_effect = None
        if supported_effects:
            timing_effect = effects[0]
        if len(supported_effects) > 1:
            logger.warning(
                "Only one timing effect / clip. is supported. Ignoring %s" % (
                    ", ".join(supported_effects[1:])
                )
            )
        return timing_effect

    @property
    def markers(self):
        """
        Return the markers.

        :returns: A list of :class:`otio.schema.Marker` instances.
        """
        return self._markers

    @markers.setter
    def markers(self, value):
        """
        Set the markers.

        :param value: A list of :class:`otio.schema.Marker` instances.
        """
        self._markers = value

    @property
    def unique_name(self):
        """
        Return a unique name.

        The only difference with the clip name is that this name is unique in the track, i.e.
        if two clips have the same name foo, their cut item names will be foo and foo_001

        :returns: A string.
        """
        return self._unique_name

    @unique_name.setter
    def unique_name(self, value):
        """
        Set a unique name.

        The only difference with the clip name is that this name is unique in the track, i.e.
        if two clips have the same name foo, their cut item names will be foo and foo_001

        :param value: A string.
        """
        self._unique_name = value

    @property
    def shot_name(self):
        """
        Return the name of the shot.

        :returns: A str or ``None``.
        """
        return self._shot_name

    @shot_name.setter
    def shot_name(self, value):
        """
        Set the name of the shot.

        :param value: A str or ``None``.
        """
        self._shot_name = value
        if self._shot_name:
            # Make sure the shot name is not unicode.
            self._shot_name = six.ensure_str(self._shot_name)

    @property
    def visible_duration(self):
        """
        Return the duration of the clip, taking into account the transitions
        and the effects.

        :returns: A :class:`RationalTime` instance.
        """
        duration = self.visible_range().duration
        if self.effect:
            if isinstance(self.effect, otio.schema.LinearTimeWarp):
                duration_value = duration.value * self.effect.time_scalar
            elif isinstance(self.effect, otio.schema.FreezeFrame):
                duration_value = duration.value + RationalTime(1, self._frame_rate)
            duration = RationalTime(duration_value, self._frame_rate)
        return duration

    @property
    def index(self):
        """
        Return the index of the clip in the track.

        :returns: An int.
        """
        return self._index

    @property
    def source_in(self):
        """
        Return the source in of the clip, which is the source start time of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        return self.visible_range().start_time

    @property
    def source_out(self):
        """
        Return the source out of the clip, which is the source end time of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        return self.source_in + self.visible_duration

    @property
    def media_cut_in(self):
        """
        Return the media cut in of the clip.

        It is an arbitrary time.

        :returns: A :class:`RationalTime` instance.
        """
        return self._head_in + self._head_in_duration

    @property
    def media_cut_out(self):
        """
        Return the media cut out of the clip.

        It is an arbitrary time.
        :returns: A :class:`RationalTime` instance.
        """
        if not self.media_reference.is_missing_reference and self.media_reference.available_range:
            return self.media_cut_in + self.available_range().duration - RationalTime(1, self._frame_rate)
        else:
            return self.media_cut_in + self.visible_duration - RationalTime(1, self._frame_rate)

    @property
    def cut_in(self):
        """
        Return the cut in time of the clip.

        The cut_in is an arbitrary start time of the clip,
        taking into account any handles.

        It also has to take into account if there's a media reference in the clip.
        If it has one, and it has an available range, take it into account comparing it to the visible range
        of the clip.

        For example, if a clip visible range starts at frame 5, and the media reference starts
        at frame 0, it means that the media cut_in has to start 5 frames after the clip's cut_in

        :returns: A :class:`RationalTime` instance.
        """
        cut_in = self._head_in + self._head_in_duration
        if not self.media_reference.is_missing_reference and self.media_reference.available_range:
            cut_in_offset = self.visible_range().start_time - self.media_reference.available_range.start_time
            cut_in += cut_in_offset
        return cut_in

    @property
    def cut_out(self):
        """
        Return the cut out time of the clip. It's exclusive.

        The cut_out is an arbitrary end time of the clip,
        taking into account any handles.

        :returns: A :class:`RationalTime` instance.
        """
        return self.cut_in + self.visible_duration - RationalTime(1, self._frame_rate)

    @property
    def record_in(self):
        """
        Return the record in time of the clip.

        It is the time the clip starts in the track, taking into account
        when a track starts.

        For example, if the track starts at 01:00:00:00, and the relative
        time the clip starts in the track is 00:00:01:00, then the record_in
        is 01:00:01:00.

        :returns: A :class:`RationalTime` instance.
        """
        # We use visible_range wich adds adjacents transitions ranges to the Clip
        # trimmed_range
        # https://opentimelineio.readthedocs.io/en/latest/tutorials/time-ranges.html#clip-visible-range
        # We need to evaluate the time in the parent of our parent track to get
        # the track source_range applied as an offset to our values.
        transformed_time_range = self.transformed_time_range(
            self.visible_range(), self.parent().parent(),
        )
        return transformed_time_range.start_time

    @property
    def record_out(self):
        """
        Return the record out time of the clip.

        It is the time the clip ends in the track, taking into account
        when a track starts.

        For example, if the track starts at 01:00:00:00, and the relative
        time the clip ends in the track is 00:00:01:00, then the record_out
        is 01:00:01:00.

        :returns: A :class:`RationalTime` instance.
        """
        # We use visible_range wich adds adjacents transitions ranges to the Clip
        # trimmed_range
        # https://opentimelineio.readthedocs.io/en/latest/tutorials/time-ranges.html#clip-visible-range
        return self.record_in + self.visible_range().duration

    @property
    def edit_in(self):
        """
        Return the edit in time of the clip.

        It is the relative time the clip starts in the track, i.e. the time
        when the clip starts in the track if the track starts at 00:00:00:00.

        :returns: A :class:`RationalTime` instance.
        """
        edit_in = self.transformed_time_range(self.visible_range(), self.parent()).start_time
        # We add one frame here, because the edit in starts at frame 1 for the first clip,
        # not frame 0.
        edit_in += RationalTime(1, self._frame_rate)
        return edit_in

    @property
    def edit_out(self):
        """
        Return the edit out time of the clip.

        It is the relative time the clip ends in the track, i.e. the time
        when the clip ends in the track if the track starts at 00:00:00:00.

        :returns: A :class:`RationalTime` instance.
        """
        return self.transformed_time_range(self.visible_range(), self.parent()).end_time_exclusive()

    @property
    def head_in(self):
        """
        Return head in value.

        This is an arbitrary start time of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        return self._head_in

    @property
    def head_out(self):
        """
        Return head out value.

        It is an arbitrary time, which corresponds to
        head_in + head_in_duration - 1 (one frame before cut_in).

        :returns: A :class:`RationalTime` instance.
        """
        return self.head_in + self.head_in_duration - RationalTime(1, self._frame_rate)

    @property
    def head_in_duration(self):
        """
        Return the head in duration.

        It is an arbitrary duration corresponding to the handles from the head_in to the cut_in.

        :returns: A :class:`RationalTime` instance.
        """
        return self._head_in_duration

    @head_in_duration.setter
    def head_in_duration(self, value):
        """
        Sets the head in duration.

        :param value: A :class:`RationalTime` instance.
        """
        self._head_in_duration = value

    @property
    def tail_in(self):
        """
        Returns the tail in value.

        It is an arbitrary value which corresponds to when the out handles of the clip start.

        :returns: A :class:`RationalTime` instance.
        """
        return self.cut_out + RationalTime(1, self._frame_rate)

    @property
    def tail_out(self):
        """
        Return tail out value.

        It is an arbitrary time, which corresponds to when the clip ends, after its out handles.

        It is equal to cut_out + tail_out_duration

        :returns: A :class:`RationalTime` instance.
        """
        return self.cut_out + self._tail_out_duration

    @property
    def tail_out_duration(self):
        """
        Return the tail out duration.

        It is an arbitrary time, corresponding to the out handles from the cut_out to the tail_out.
        """
        return self._tail_out_duration

    @tail_out_duration.setter
    def tail_out_duration(self, value):
        """
        Sets the tail out duration.

        :param value: A :class:`RationalTime` instance.
        """
        self._tail_out_duration = value

    @property
    def working_duration(self):
        """
        Return the working duration.

        It is the duration of the clip including handles.
        It takes into account transitions and effects, like :meth:`visible_duration`.

        :returns: A :class:`RationalTime` instance.
        """
        return self.tail_out - self.head_in

    @property
    def transition_before(self):
        """
        Returns the transition before this Clip, if any.

        :returns: A class :class:`otio.schema.Transition` instance or ``None``.
        """
        prev, _ = self.parent().neighbors_of(self)
        if prev and isinstance(prev, otio.schema.Transition):
            return prev

    @property
    def transition_after(self):
        """
        Returns the transition after this Clip, if any.

        :returns: A class :class:`otio.schema.Transition` instance or ``None``.
        """
        _, next = self.parent().neighbors_of(self)
        if next and isinstance(next, otio.schema.Transition):
            return next

    @property
    def effects_str(self):
        """
        Return a string with the effects of the clip, if any.

        :returns: A string.
        """
        effects = []
        if self.transition_before:
            effects.append("Before: %s (%s frames)" % (
                self.transition_before.transition_type,
                self.transition_before.in_offset.to_frames()
            ))
        if self.transition_after:
            effects.append("After: %s (%s frames)" % (
                self.transition_after.transition_type,
                self.transition_after.out_offset.to_frames()
            ))
        return "\n".join(effects)

    @property
    def has_effects(self):
        """
        Returns whether or not the clip has effects.

        :returns: A bool.
        """
        if self.transition_before or self.transition_after:
            return True
        return False

    @property
    def retime_str(self):
        """
        Returns a string with retime information, if any.

        :returns: A string.
        """

        if self.effect:
            return "%s (time scalar: %s)" % (self.effect.effect_name, self.effect.time_scalar)
        return ""

    @property
    def has_retime(self):
        """
        Returns whether or not the clip has retime information.

        :returns: A bool.
        """
        return bool(self.effect)
