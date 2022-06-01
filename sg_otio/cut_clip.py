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

from .constants import DEFAULT_HEAD_IN, DEFAULT_HEAD_IN_DURATION, DEFAULT_TAIL_OUT_DURATION

logger = logging.getLogger(__name__)


class CutClip(otio.schema.Clip):
    """
    A Clip in the context of a Cut.
    """

    def __init__(
        self,
        index=1,
        effects=None,
        markers=None,
        head_in=DEFAULT_HEAD_IN,
        head_in_duration=DEFAULT_HEAD_IN_DURATION,
        tail_out_duration=DEFAULT_TAIL_OUT_DURATION,
        use_clip_names_for_shot_names=False,
        clip_name_shot_regexp=None,
        log_level=logging.INFO,
        *args,
        **kwargs
    ):
        """
        Construct a :class:`CutClip` instance.

        :param int index: The index of the clip in the track.
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
        super(CutClip, self).__init__(*args, **kwargs)
        logger.setLevel(log_level)
        # TODO: check what we should grab from the SG metadata, if any.
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
        self.effect = self._relevant_timing_effect(effects or [])
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
        Convenience method to create a :class:`CutClip` instance from a
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
    def cut_in(self):
        """
        Return the cut in time of the clip.

        The cut_in is an arbitrary start time of the clip,
        taking into account any handles.

        :returns: A :class:`RationalTime` instance.
        """
        cut_in = self._head_in + self._head_in_duration
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
        transformed_time_range = self.transformed_time_range(
            self.visible_range(), self.parent().parent()
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
        # Does not take into account retime effects like self.visible_duration does.
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
        # We add one frame here, because the edit in is exclusive.
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

    def _compute_shot_name(self):
        r"""
        Processes the clip to find information about the shot name

        The ClipGroup name can be found in the following places, in order of preference:
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
        if self.metadata.get("sg", {}).get("shot.Shot.code"):
            self.shot_name = self.metadata["sg"]["shot.Shot.code"]
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

    @property
    def sg_payload(self):
        """
        Get a SG CutItem payload for a given :class:`otio.schema.Clip` instance.

        An absolute cut order can be set on CutItems if the `sg_absolute_cut_order`
        integer field was added to the SG CutItem schema. This absolute cut order
        is meant to be the cut order of the CutItem in the Project and is based on
        a cut order value set on the Entity (Reel, Sequence, etc...) the Cut is
        imported against. The absolute cut order is then:
        `1000 * entity cut order + edit cut order`.

        :returns: A dictionary with the CutItem payload.
        :raises ValueError: If no SG payload can be generated for this Clip
        """
        cut_track = self.parent()
        if not cut_track:
            raise ValueError(
                "SG payload can only be generated for a Clip in a Track"
            )
        sg_cut = cut_track.metadata.get("sg")
        if not sg_cut:
            raise ValueError(
                "Track %s does not have SG metadata" % cut_track
            )
        description = ""
        cut_item_payload = {
            "type": "CutItem",
            "project": sg_cut.get("project"),
            "code": self.name,
            "cut": sg_cut,
            "cut_order": self._clip_index,
            "timecode_cut_item_in_text": self.source_in.to_timecode(),
            "timecode_cut_item_out_text": self.source_out.to_timecode(),
            "timecode_edit_in_text": self.edit_in().to_timecode(),
            "timecode_edit_out_text": self.edit_out().to_timecode(),
            "cut_item_in": self.cut_in.to_frames(),
            "cut_item_out": self.cut_out.to_frames(),
            "edit_in": self.edit_in(absolute=False).to_frames(),
            "edit_out": self.edit_out(absolute=False).to_frames(),
            "cut_item_duration": self.duration.to_frames(),
            # TODO: Add support for Linking/Creating Versions + Published Files
            # "version": cut_diff.sg_version,

        }
#        if self._sg_shot:
#            cut_item_payload["shot"] = self._sg_shot
#        if self._user:
#            cut_item_payload["created_by"] = self._user
#            cut_item_payload["updated_by"] = self._user
#
        if self.has_effects:
            description = "%s\nEffects: %s" % (
                description,
                self.effects_str
            )

#        if _EFFECTS_FIELD in self._cut_item_schema:
#            cut_item_payload[_EFFECTS_FIELD] = self.has_effects
#
#        if self.has_retime:
#            description = "%s\nRetime: %s" % (description, self.retime_str)
#        if _RETIME_FIELD in self._cut_item_schema:
#            cut_item_payload[_RETIME_FIELD] = self.has_retime
#
        cut_item_payload["description"] = description
#        linked_entity = self._sg_cut["entity"]
#        if (
#                _ABSOLUTE_CUT_ORDER_FIELD in self._cut_item_schema
#                and linked_entity.get(_ENTITY_CUT_ORDER_FIELD)
#        ):
#            cut_item_payload[_ABSOLUTE_CUT_ORDER_FIELD] = 1000 * linked_entity[
#                _ENTITY_CUT_ORDER_FIELD] + self._clip_index
        return cut_item_payload
