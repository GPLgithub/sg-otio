# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging

import opentimelineio as otio
from opentimelineio.opentime import RationalTime

from .constants import _TC2FRAME_ABSOLUTE_MODE, _TC2FRAME_AUTOMATIC_MODE, _TC2FRAME_RELATIVE_MODE
from .sg_settings import SGShotFieldsConfig, SGSettings
from .utils import compute_clip_shot_name, compute_clip_version_name

logger = logging.getLogger(__name__)


class SGCutClip(object):
    """
    A Clip in the context of a SG Cut.

    SGCutClips can be grouped together in a :class:`ClipGroup` instance if they
    represent the same source, typically a Shot. In this case, their Cut values
    are adjusted to represent parts of the same source.
    """

    def __init__(
        self,
        clip,
        sg_shot=None,
        index=1,
        *args,
        **kwargs
    ):
        """
        Construct a :class:`SGCutClip` instance.

        :param clip: A :class:`otio.schema.Clip` instance.
        :param sg_shot: A SG Shot dictionary.
        :param int index: The index of the clip in its track.
        """
        super(SGCutClip, self).__init__(*args, **kwargs)
        self._clip = clip
        self._clip_group = None
        self._shot_name = None
        self._sg_shot = None
        self.effect = self._relevant_timing_effect(clip.effects or [])
        # TODO: check what we should grab from the SG metadata, if any.
        # If the clip has a reel name, override its name.
        self._name = self._clip.name
        if self._clip.metadata.get("sg", {}).get("code"):
            self._name = self._clip.metadata["sg"]["code"]
        elif self._clip.metadata.get("cmx_3600", {}).get("reel"):
            self._name = self._clip.metadata["cmx_3600"]["reel"]
        self._frame_rate = self._clip.duration().rate
        self._index = index
        self._cut_item_name = self.name
        # Set the Shot, this will set the Shot name as well, if available.
        self.sg_shot = sg_shot
        if not self._shot_name:
            self._shot_name = compute_clip_shot_name(self._clip)
        self.compute_head_tail_values()

    @property
    def clip(self):
        """
        Return the linked Clip.

        :returns: A :class:`otio.schema.Clip` instance.
        """
        return self._clip

    @property
    def frame_rate(self):
        """
        Return the linked Clip frame rate.

        :returns: A float.
        """
        return self._frame_rate

    @property
    def media_reference(self):
        """
        Return the media reference of the linked Clip.

        :returns: A :class:`otio.MediaReference` instance.
        """
        return self._clip.media_reference

    def duration(self):
        """
        Return the duration of the linked Clip.

        :returns: A :class:`RationalTime` instance.
        """
        return self._clip.duration()

    def available_range(self):
        """
        Return the available range of the linked Clip.

        :returns: A :class:`otio.opentime.TimeRange` instance.
        """
        return self._clip.available_range()

    def visible_range(self):
        """
        Return the visible range of the linked Clip.

        :returns: A :class:`otio.opentime.TimeRange` instance.
        """
        return self._clip.visible_range()

    @property
    def name(self):
        """
        Return this SGCutClip name.

        :returns: A string or ``None``.
        """
        return self._name

    @name.setter
    def name(self, value):
        """
        Set this SGCutClip name.

        :param value: A string or ``None``.
        """
        self._name = value

    @property
    def metadata(self):
        """
        Return the metadata of the linked Clip.

        :returns: A dictionary.
        """
        return self._clip.metadata

    @property
    def group(self):
        """
        Return the :class:`ClipGroup` this Clip is in, if any.

        :returns: A :class:`ClipGroup` or ``None``.
        """
        return self._clip_group

    @group.setter
    def group(self, value):
        """
        Set the :class:`ClipGroup` this Clip is in.

        :param value: :class:`ClipGroup` instance.
        """
        self._clip_group = value
        if self._clip_group is not None:  # Can't use just if self._clip_group: empty groups evaluate to False
            self.shot_name = self._clip_group.name
            # Note: the Shot name might be modified by setting the SG Shot if
            # it is set and has a code key.
            self.sg_shot = self._clip_group.sg_shot
        else:
            # Recompute values only if we don't have a clip group.
            # Otherwise we assume that values are maintained by the group.
            self.compute_head_tail_values()

    @property
    def sg_shot(self):
        """
        Return the SG Shot associated with this Clip, if any.

        :returns: A dictionary or ``None``.
        """
        return self._sg_shot

    @sg_shot.setter
    def sg_shot(self, value):
        """
        Set the SG Shot value associated with this Clip.

        Recompute head_in, head_duration and tail_duration,
        which depend on the SG Shot.

        :param value: A SG Shot dictionary.
        :raises ValueError: For invalid values.
        """
        if self._clip_group is not None:  # Can't use just if self._clip_group: empty groups evaluate to False
            if value:
                if (
                    not self._clip_group.sg_shot
                    or self._clip_group.sg_shot["id"] != value["id"]
                    or self._clip_group.sg_shot["type"] != value["type"]
                ):
                    raise ValueError(
                        "Can't change the SG Shot value controlled by %s" % self._clip_group
                    )
            elif self._clip_group.sg_shot:
                raise ValueError(
                    "Can't change the SG Shot value controlled by %s" % self._clip_group
                )

        self._sg_shot = value
        if self._sg_shot and self._sg_shot.get("code"):
            self.shot_name = self._sg_shot["code"]
        # If the Clip is part of a group, assume that the values are set by
        # the group
        if self._clip_group is None:  # Can't use just if self._clip_group: empty groups evaluate to False
            self.compute_head_tail_values()

    @property
    def sg_cut_item(self):
        """
        Return the SG CutItem associated with this Clip, if any.

        :returns: A dictionary or ``None``.
        """
        return self.metadata.get("sg")

    @property
    def cut_item_name(self):
        """
        Return the cut item name.

        It can be different from the Clip name if for example
        uniqueness of names needs to be enforced in a Cut.

        :returns: A string.
        """
        return self._cut_item_name

    @cut_item_name.setter
    def cut_item_name(self, value):
        """
        Set a cut item name.

        It can be different from the Clip name if for example
        uniqueness of names needs to be enforced in a Cut.

        :param value: A string.
        """
        self._cut_item_name = value

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
            if SGCutClip._is_timing_effect_supported(effect):
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
        return self._clip.markers

    @property
    def shot_name(self):
        """
        Return the name of the Shot.

        :returns: A string or ``None``.
        """
        return self._shot_name

    @shot_name.setter
    def shot_name(self, value):
        """
        Set the name of the Shot.

        :param value: A string or ``None``.
        """
        self._shot_name = value

    @property
    def visible_duration(self):
        """
        Return the duration of the clip, taking into account the transitions
        and the effects.

        :returns: A :class:`RationalTime` instance.
        """
        duration = self._clip.visible_range().duration
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
        return self._clip.visible_range().start_time

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

        The cut_in is the source_in converted to a frame number for image sequences.
        It represents the first frame in the image sequence for this clip, without
        handles.

        :returns: A :class:`RationalTime` instance.
        """
        return self._head_in + self._head_duration

    @property
    def cut_out(self):
        """
        Return the cut out time of the clip.

        The cut_out is the source_out, minus one frame, converted to a frame number
        for image sequences.
        It represents the last frame in the image sequence for this clip, without
        handles.

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
        # We use visible_range which adds adjacent transitions ranges to the Clip
        # trimmed_range
        # https://opentimelineio.readthedocs.io/en/latest/tutorials/time-ranges.html#clip-visible-range
        # We need to evaluate the time in the parent of our parent track to get
        # the track source_range applied as an offset to our values.
        transformed_time_range = self._clip.transformed_time_range(
            self._clip.visible_range(), self._clip.parent().parent(),
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
        edit_in = self._clip.transformed_time_range(
            self._clip.visible_range(),
            self._clip.parent()
        ).start_time
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
        # The edit out is inclusive but since we start numbering at 1, we use
        # the exclusive end time which adds 1 frame for us.
        return self._clip.transformed_time_range(
            self._clip.visible_range(),
            self._clip.parent()
        ).end_time_exclusive()

    @property
    def head_in(self):
        """
        Return head in value.

        This is the very first frame number for this clip, including handles.

        :returns: A :class:`RationalTime` instance.
        """
        return self._head_in

    @head_in.setter
    def head_in(self, value):
        """
        Set the head in value.

        :param value: A :class:`RationalTime` instance.
        """
        self._head_in = value

    @property
    def head_out(self):
        """
        Return head out value.

        This is the last frame number for this clip head handle.

        :returns: A :class:`RationalTime` instance.
        """
        return self.head_in + self.head_duration - RationalTime(1, self._frame_rate)

    @property
    def head_duration(self):
        """
        Return the head handle duration.

        :returns: A :class:`RationalTime` instance.
        """
        return self._head_duration

    @head_duration.setter
    def head_duration(self, value):
        """
        Sets the head handle duration.

        :param value: A :class:`RationalTime` instance.
        """
        self._head_duration = value

    @property
    def tail_in(self):
        """
        Returns the tail in value.

        This is the first frame number for this clip tail handle.

        :returns: A :class:`RationalTime` instance.
        """
        return self.cut_out + RationalTime(1, self._frame_rate)

    @property
    def tail_out(self):
        """
        Return tail out value.

        This is the very last frame number for this clip, including handles.

        :returns: A :class:`RationalTime` instance.
        """
        return self.cut_out + self._tail_duration

    @property
    def tail_duration(self):
        """
        Return the tail handle duration.

        :returns: A :class:`RationalTime` instance.
        """
        return self._tail_duration

    @tail_duration.setter
    def tail_duration(self, value):
        """
        Sets the tail handle duration.

        :param value: A :class:`RationalTime` instance.
        """
        self._tail_duration = value

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
        prev, _ = self._clip.parent().neighbors_of(self._clip)
        if prev and isinstance(prev, otio.schema.Transition):
            return prev

    @property
    def transition_after(self):
        """
        Returns the transition after this Clip, if any.

        :returns: A class :class:`otio.schema.Transition` instance or ``None``.
        """
        _, next = self._clip.parent().neighbors_of(self._clip)
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

    @property
    def sg_shot_head_in(self):
        """
        Return the head in from the SG Shot, if any.

        :returns: An integer or ``None``.
        """
        if self.sg_shot:
            # If we have SG Shot we use its head in value if it is set.
            config = SGShotFieldsConfig(
                None, None
            )
            head_in_field = config.head_in
            return self.sg_shot.get(head_in_field)
        return None

    @property
    def sg_shot_tail_out(self):
        """
        Return the tail out from the SG Shot, if any.

        :returns: An integer or ``None``.
        """
        if self.sg_shot:
            # If we have SG Shot we use its tail out value if it is set.
            config = SGShotFieldsConfig(
                None, None
            )
            tail_out_field = config.tail_out
            return self.sg_shot.get(tail_out_field)
        return None

    @property
    def sg_shot_cut_in(self):
        """
        Return the cut in from the SG Shot, if any.

        :returns: An integer or None
        """
        if self.sg_shot:
            # If we have SG Shot we use its cut in value if it is set.
            config = SGShotFieldsConfig(
                None, None
            )
            cut_in_field = config.cut_in
            return self.sg_shot.get(cut_in_field)
        return None

    @property
    def sg_shot_cut_out(self):
        """
        Return the cut out from the SG Shot, if any.

        :returns: An integer or None
        """
        if self.sg_shot:
            # If we have SG Shot we use its cut out value if it is set.
            config = SGShotFieldsConfig(
                None, None
            )
            cut_out_field = config.cut_out
            return self.sg_shot.get(cut_out_field)
        return None

    @property
    def sg_shot_cut_order(self):
        """
        Return the cut order from the SG Shot, if any.

        :returns: An integer or None
        """
        if self.sg_shot:
            # If we have SG Shot we use its cut out value if it is set.
            config = SGShotFieldsConfig(
                None, None
            )
            cut_order_field = config.cut_order
            return self.sg_shot.get(cut_order_field)
        return None

    @property
    def sg_shot_status(self):
        """
        Return the status value from associated SG Shot, or None

        :returns: An integer or None
        """
        if self.sg_shot:
            config = SGShotFieldsConfig(
                None, None
            )
            status_field = config.status
            return self.sg_shot.get(status_field)
        return None

    def compute_head_tail_values(self):
        """
        Compute and set the head and tail values for this clip.
        """
        self._head_in, self._head_duration, self._tail_duration = self.get_head_tail_values()

    def get_head_tail_values(self):
        """
        Compute head and tail values for this clip.

        :returns: A head in, head duration, tail duration tuple of :class:`RationalTime`.
        """
        sg_settings = SGSettings()
        sg_shot_head_in = self.sg_shot_head_in
        cut_in = self.compute_cut_in()
        if sg_shot_head_in is None:
            head_duration = RationalTime(sg_settings.default_head_duration, self._frame_rate)
            if sg_settings.timecode_in_to_frame_mapping_mode == _TC2FRAME_AUTOMATIC_MODE:
                head_in = RationalTime(sg_settings.default_head_in, self._frame_rate)
                head_duration = cut_in - head_in
            else:
                head_in = cut_in - head_duration
        else:
            head_in = RationalTime(sg_shot_head_in, self._frame_rate)
            head_duration = cut_in - head_in

        cut_out = cut_in + self.visible_duration - RationalTime(1, self._frame_rate)
        sg_shot_tail_out = self.sg_shot_tail_out
        if sg_shot_tail_out is None:
            tail_duration = RationalTime(sg_settings.default_tail_duration, self._frame_rate)
        else:
            tail_out = RationalTime(sg_shot_tail_out, self._frame_rate)
            # tail_in would be cut_out + 1, so tail_duration would be
            # tail_out - (cut_out + 1) -1, we use a simplified formula below
            tail_duration = tail_out - cut_out

        return (
            head_in,
            head_duration,
            tail_duration,
        )

    def compute_cut_in(self):
        """
        Retrieve a cut in value for this Clip.

        The value can be retrieved as an offset to a previous import, or computed.

        :returns: A :class:`RationalTime`.
        """
        sg_cut_item = self.sg_cut_item
        if sg_cut_item:
            cut_item_in = sg_cut_item.get("cut_item_in")
            cut_item_source_in = sg_cut_item.get("timecode_cut_item_in_text")
            if cut_item_in is not None and cut_item_source_in is not None:
                # Calculate the cut offset
                offset = self.source_in - otio.opentime.from_timecode(cut_item_source_in, self._frame_rate)
                # Just apply the offset to the old cut in
                return RationalTime(cut_item_in, self._frame_rate) + offset

        sg_settings = SGSettings()
        timecode_in_to_frame_mapping_mode = sg_settings.timecode_in_to_frame_mapping_mode

        if timecode_in_to_frame_mapping_mode == _TC2FRAME_ABSOLUTE_MODE:
            return self.source_in

        if timecode_in_to_frame_mapping_mode == _TC2FRAME_RELATIVE_MODE:
            tc_base, frame = sg_settings.timecode_in_to_frame_relative_mapping
            tc_base = otio.opentime.from_timecode(tc_base, self._frame_rate)
            return self.source_in - tc_base + RationalTime(frame, self._frame_rate)

        # Automatic mode
        head_in = self.sg_shot_head_in
        if head_in is None:
            head_in = sg_settings.default_head_in
        return RationalTime(head_in + sg_settings.default_head_duration, self._frame_rate)

    @property
    def sg_version(self):
        """
        Return the SG Version associated with this Clip, if any.

        :returns: A dictionary or ``None``.
        """
        sg_version = self.media_reference.metadata.get("sg", {}).get("version")
        return sg_version

    @property
    def sg_version_name(self):
        """
        Return the name of SG Version associated with this Clip, if any.

        :returns: A string or ``None``.
        """

        sg_version = self.sg_version
        if sg_version:
            return sg_version["code"]
        return None

    @property
    def source_info(self):
        """
        Return a string representation of the source for this :class:`CutClip`.

        :returns: A string.
        """
        sg_cut_item = self.sg_cut_item
        if sg_cut_item:
            fps = sg_cut_item["cut.Cut.fps"]
            tc_in = otio.opentime.from_timecode(sg_cut_item["timecode_cut_item_in_text"], fps).to_frames()
            tc_out = otio.opentime.from_timecode(sg_cut_item["timecode_cut_item_out_text"], fps).to_frames()
            return (
                "Cut Order %s, TC in %s, TC out %s, Cut In %s, Cut Out %s, Cut Duration %s" % (
                    sg_cut_item["cut_order"],
                    tc_in,
                    tc_out,
                    sg_cut_item["cut_item_in"],
                    sg_cut_item["cut_item_out"],
                    sg_cut_item["cut_item_duration"]
                )
            )

        if self._clip.metadata.get("cmx_3600"):
            return "%03d %s %s %s %s %s %s %s" % (
                self.index,
                self.name,
                "V",
                "C",
                self.source_in.to_timecode(),
                self.source_out.to_timecode(),
                self.record_in.to_timecode(),
                self.record_out.to_timecode(),
            )
        # TODO: refine to something readable and useful
        return "%s" % self._clip

    def compute_clip_version_name(self):
        """
        Compute a Version name for this clip.

        :returns: A string.
        """
        return compute_clip_version_name(
            self,
            self.index,
            shot_name=self.shot_name,
            cut_item_name=self.cut_item_name,
        )
