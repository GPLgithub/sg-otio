# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging
import re

import opentimelineio as otio
import six
from opentimelineio.opentime import RationalTime

logger = logging.getLogger(__name__)


class ExtendedClip(otio.schema.Clip):
    """
    A class that extends the Clip class with additional fields.
    """
    # The CutItem schema in ShotGrid. Make it a class variable to get it only once.
    _cut_item_schema = None

    def __init__(
        self,
        name,
        source_range,
        index=1,
        media_reference=None,
        metadata=None,
        effects=None,
        markers=None,
        head_in=1001,
        head_in_duration=8,
        tail_out_duration=8,
        use_clip_names_for_shot_names=False,
        clip_name_shot_regexp=None,
        log_level=logging.INFO,
    ):
        """
        Construct a :class:`ExtendedClip` instance.

        :param str name: The name of the clip.
        :param source_range: A :class:`otio.opentime.TimeRange` instance,
                             the source range of the clip.
        :param int index: The index of the clip in the track.
        :param media_reference: A :class:`otio.schema.MediaReference` instance.
        :param metadata: A dictionary of metadata.
        :param effects: A list of :class:`otio.schema.Effect` instances.
        :param markers: A list of :class:`otio.schema.Marker` instances.
        :param int head_in: The head in point of the clip.
        :param int head_in_duration: The duration of the head in.
        :param int tail_out_duration: The duration of the tail out.
        :param bool use_clip_names_for_shot_names: If True, and a shot name was not found,
                                                   use the clip name as the shot name.
        :param str clip_name_shot_regexp: A regular expression to use to find the shot name.
        :param int log_level: The logging level to use.
        """
        super(ExtendedClip, self).__init__(
            name=name,
            source_range=source_range,
            media_reference=media_reference,
            metadata=metadata,
        )
        logger.setLevel(log_level)
        # If the clip has a reel name, override its name.
        if self.metadata.get("cmx_3600", {}).get("reel"):
            self.name = self.metadata["cmx_3600"]["reel"]
        self._frame_rate = self.duration().rate
        self._index = index
        self._head_in = RationalTime(head_in, self._frame_rate)
        self._head_in_duration = RationalTime(head_in_duration, self._frame_rate)
        self._tail_out_duration = RationalTime(tail_out_duration, self._frame_rate)
        self._use_clip_names_for_shot_names = use_clip_names_for_shot_names
        self._clip_name_shot_regexp = clip_name_shot_regexp
        self._shot_name = None
        self.effect = self._relevant_timing_effect(effects)
        self._markers = markers or []
        self._compute_shot_name()

    @classmethod
    def from_clip(
            cls,
            clip,
            index=1,
            head_in=1001,
            head_in_duration=8,
            tail_out_duration=8,
            use_clip_names_for_shot_names=False,
            clip_name_shot_regexp=None,
            log_level=logging.INFO,
    ):
        """
        Convenience method to create a :class:`ExtendedClip` instance from a
        :class:`otio.schema.Clip` instance.

        :param clip: A :class:`otio.schema.Clip` instance.
        :param int index: The index of the clip in the track.
        :param int head_in: The head in point of the clip.
        :param int head_in_duration: The duration of the head in.
        :param int tail_out_duration: The duration of the tail out.
        :param bool use_clip_names_for_shot_names: If True, and a shot name was not found,
                                                   use the clip name as the shot name.
        :param str clip_name_shot_regexp: A regular expression to use to find the shot name.
        :param int log_level: The logging level to use.
        :returns: A :class:`ExtendedClip` instance.
        """
        return ExtendedClip(
            name=clip.name,
            source_range=clip.source_range,
            index=index,
            media_reference=clip.media_reference,
            metadata=clip.metadata,
            effects=clip.effects,
            markers=clip.markers,
            head_in=head_in,
            head_in_duration=head_in_duration,
            tail_out_duration=tail_out_duration,
            use_clip_names_for_shot_names=use_clip_names_for_shot_names,
            clip_name_shot_regexp=clip_name_shot_regexp,
            log_level=log_level,
        )

    @property
    def effect(self):
        """
        Return the effect. We only support one effect per clip, and it must be either a
        :class:`otio.schema.LinearTimeWarp` or a :class:`otio.schema.FreezeFrame`.
        """
        return self._effect

    @effect.setter
    def effect(self, value):
        """
        Set the effect.
        """
        self._effect = value

    @staticmethod
    def _supported_timing_effects(effects):
        """
        We only support LinearTimeWarp and FreezeFrame effects for now (same as cmx_3600).

        :param effects: A list of :class:`otio.schema.Effect` instances.
        :returns: A list of supported :class:`otio.schema.Effect` instances.
        """
        effects = effects or []
        supported_effects = [
            fx for fx in effects
            if isinstance(fx, otio.schema.LinearTimeWarp)
        ]
        if supported_effects != effects:
            for effect in effects:
                if effect not in supported_effects:
                    logger.warning(
                        "Unsupported effect %s will be ignored" % effect
                    )
        return supported_effects

    @staticmethod
    def _relevant_timing_effect(effects):
        """
        Return the relevant timing effects for the given clip.
        :param effects: A list of :class:`otio.schema.Effect` instances.
        :returns: An effect or ``None``.
        """
        # check to see if there is more than one timing effect
        effects = ExtendedClip._supported_timing_effects(effects)
        timing_effect = None
        if effects:
            timing_effect = effects[0]
        if len(effects) > 1:
            logger.warning(
                "Only one timing effect / clip. is supported. Ignoring %s" % (
                    ", ".join(effects[1:])
                )
            )
        return timing_effect

    @property
    def markers(self):
        """
        Return the markers.
        """
        return self._markers

    @markers.setter
    def markers(self, value):
        """
        Set the markers.
        """
        self._markers = value

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
        Return the duration of the cut item, taking into account the transitions
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
        Return the source in of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        return self.visible_range().start_time

    @property
    def source_out(self):
        """
        Return the source out of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        return self.source_in + self.visible_duration

    @property
    def cut_in(self):
        """
        Return the cut in time of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        cut_in = RationalTime(0, self._frame_rate) + self._head_in + self._head_in_duration
        return cut_in

    @property
    def cut_out(self):
        """
        Return the cut out time of the clip. It's exclusive.

        :returns: A :class:`RationalTime` instance.
        """
        return self.cut_in + self.visible_duration - RationalTime(1, self._frame_rate)

    @property
    def record_in(self):
        """
        Return the record in time of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        transformed_time_range = self.transformed_time_range(
            self.visible_range(), self.parent().parent()
        )
        return transformed_time_range.start_time

    @property
    def record_out(self):
        """
        Return the record out time of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        # Does not take into account retime effects like self.visible_duration does.
        return self.record_in + self.visible_range().duration

    @property
    def edit_in(self):
        """
        Return the edit in time of the clip.
        :returns: A :class:`RationalTime` instance.
        """
        edit_in = self.transformed_time_range(self.visible_range(), self.parent()).start_time
        # We add one frame here
        edit_in += RationalTime(1, self._frame_rate)
        return edit_in

    @property
    def edit_out(self):
        """
        Return the edit out time of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        return self.transformed_time_range(self.visible_range(), self.parent()).end_time_exclusive()

    @property
    def head_in(self):
        """
        Return head in value, from the Shot or from the clip information.

        :returns: A :class:`RationalTime` instance.
        """
        return self.cut_in - self._head_in_duration

    @property
    def tail_out(self):
        """
        Return tail out value.

        :returns: A :class:`RationalTime` instance.
        """
        return self.cut_out + self._tail_out_duration

    @property
    def head_in_duration(self):
        """
        Returns the head in duration.

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
    def tail_out_duration(self):
        """
        Returns the tail out duration.

        :returns: A :class:`RationalTime` instance.
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
    def transition_before(self):
        """
        Returns the transition before, if any.

        :returns: A class :class:`otio.schema.Transition` instance or ``None``.
        """
        prev, _ = self.parent().neighbors_of(self)
        if prev and isinstance(prev, otio.schema.Transition):
            return prev

    @property
    def transition_after(self):
        """
        Returns the transition after, if any.

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
        effects_str = ""
        if self.transition_before:
            effects_str += "Before: %s (%s frames)\n" % (
                self.transition_before.transition_type,
                self.transition_before.in_offset.to_frames()
            )
        if self.transition_after:
            effects_str += "After: %s (%s frames)\n" % (
                self.transition_after.transition_type,
                self.transition_after.out_offset.to_frames()
            )
        return effects_str

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
        return True if self.effect else False

    def _compute_shot_name(self):
        r"""
        Processes the clip to find information about the shot name

        The Shot name can be found in the following places, in order of preference:
        - SG metadata about the Cut Item, if it has a shot field.
        - A :class:`otio.schema.Marker`, in an EDL it would be
          * LOC: 00:00:02:19 YELLOW  053_CSC_0750_PC01_V0001 997 // 8-8 Match to edit,
          which otio would convert to a marker with name "name='053_CSC_0750_PC01_V0001 997 // 8-8 Match to edit".
          We would only consider the first part of the name, split by " ".
        - In an EDL "pure" comment, e.g. "* COMMENT : 053_CSC_0750_PC01_V0001"
        - In an EDL comment, e.g. "* 053_CSC_0750_PC01_V0001"
        - The reel name.

        The reel name is only used if `_use_clip_names_for_shot_names` is True.
        If a `_clip_name_shot_regexp` is set, it will be used to extract the shot name from the reel name.
        """
        if self.metadata.get("sg", {}).get("shot"):
            self.shot_name = self.metadata["sg"]["shot"]["name"]
            return
        if self.markers:
            self.shot_name = self.markers[0].name.split()[0]
            return
        comment_match = None
        if self.metadata.get("cmx_3600") and self.metadata["cmx_3600"].get("comments"):
            comments = self.metadata["cmx_3600"]["comments"]
            if comments:
                pure_comment_regexp = r"\*?(\s*COMMENT\s*:)?\s*([a-z0-9A-Z_-]+)$"
                pure_comment_match = None
                for comment in comments:
                    m = re.match(pure_comment_regexp, comment)
                    if m:
                        if m.group(1):
                            # Priority is given to matches from line beginning with
                            # * COMMENT
                            pure_comment_match = m.group(2)
                        # If we already matched one, no need to rematch
                        elif not comment_match:
                            comment_match = m.group(2)
                    if pure_comment_match:
                        comment_match = pure_comment_match
                        break
        if comment_match:
            self.shot_name = comment_match
            return
        if not self._use_clip_names_for_shot_names:
            self.shot_name = None
            return
        if self._use_clip_names_for_shot_names:
            if not self._clip_name_shot_regexp:
                self.shot_name = self.name
                return
            # Support both pre-compiled regexp and strings
            regexp = self._clip_name_shot_regexp
            if isinstance(self._clip_name_shot_regexp, str):
                regexp = re.compile(self._clip_name_shot_regexp)
            m = regexp.search(
                self.name
            )
            if m:
                # If we have capturing groups, use the first one
                # otherwise use the whole match.
                if len(m.groups()):
                    self.shot_name = m.group(1)
                else:
                    self.shot_name = m.group()
