# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging
import re
import six

import opentimelineio as otio
from opentimelineio.opentime import RationalTime

from .constants import _EFFECTS_FIELD, _RETIME_FIELD, _ABSOLUTE_CUT_ORDER_FIELD
from .constants import _ENTITY_CUT_ORDER_FIELD

logger = logging.getLogger(__name__)


class SGCutItem(object):
    """
    Get information from a :class:`otio.schema.Clip` instance and use it to compute field
    values for a SG CutItem.

    The method :meth:`SGCutItem.payload` will get all the information necessary to create
    a SG CutItem and return it as a dictionary.

    For example, if the clip is the second clip from this EDL:
    001  ABC0100 V     C        00:00:00:00 00:00:01:00 01:00:00:00 01:00:01:00
    * FROM CLIP NAME: shot_001_v001
    * COMMENT: shot_001

    002  ABC0200 V     C        00:00:01:00 00:00:02:00 01:00:01:00 01:00:02:00
    * FROM CLIP NAME: shot_002_v001
    * COMMENT: shot_002

    And if we have defined that the fps is 30, head in is 1001 and the head/tail duration is 8

    - The name of the CutItem is ABC0100. If there's another clip with the same name,
      it is ABC0100_001
    - The name of the linked Shot is shot_001 if not shot_regexp has been defined.
      If there's a regexp, see :meth:`SGCutItem_process_clip` for more details.
    - The name of the linked Version is shot_002_v001 if no shot_regexp has been defined.
    - The Cut in timecode is 00:00:01:00
    - The Cut out timecode is 00:00:02:00
    - The Cut in frame is 1009 (1001 + 8)
    - The Cut out frame is 1038 (1001 + 8 + 30 - 1)
    - The Edit in timecode is 01:00:01:00
    - The Edit out timecode is 01:00:02:00
    - The Edit in frame is 31 (first clip is from 1 to 30)
    - The Edit out frame is 60
    - The duration is 30

    Note that if a clip has transitions before or after, this will affect some of these values
    (e.g. duration, cut in/out timecodes, edit in/out timecodes and frames).
    This is because SG has no notion of transitions, so we have to take them into account in the CutItem as
    if they were part of the clip.
    """
    # The CutItem schema in ShotGrid. Make it a class variable to get it only once.
    _cut_item_schema = None

    def __init__(
            self,
            sg,
            sg_cut,
            clip,
            clip_index,
            track_start,
            shot_fields_config,
            head_in=1001,
            head_in_duration=8,
            tail_out_duration=8,
            shot_regexp=None,
            user=None,
            transition_before=None,
            transition_after=None,
    ):
        """
        Construct a :class:`SGCutItem` instance.

        :param sg: The :class:`ShotGrid` instance.
        :param sg_cut: The SG Cut to create the CutItems for.
        :param clip: The :class:`otio.schema.Clip` instance.
        :param int clip_index: The index of the clip in the track.
        :param track_start: A :class:`otio.opentime.RationalTime` instance,
                            the start time of the track.
        :param shot_fields_config: A :class:`SGShotFieldsConfig` instance.
        :param int head_in: A :class:`RationalTime` instance, default head in.
        :param int head_in_duration: A :class:`RationalTime` instance, head in duration.
        :param int tail_out_duration: A :class:`RationalTime` instance, tail out duration.
        :param user: An optional SG User entity.
        :param transition_before: An optional :class:`otio.schema.Transition` instance that comes before the clip.
        :param transition_after: An optional :class:`otio.schema.Transition` instance that comes after the clip.
        """
        self._sg = sg
        self._sg_cut = sg_cut
        self._clip = clip
        self._frame_rate = clip.duration().rate
        self._clip_index = clip_index
        self._track_start = track_start
        self._shot_fields_config = shot_fields_config
        self._head_in = RationalTime(head_in, self._frame_rate)
        self._head_in_duration = RationalTime(head_in_duration, self._frame_rate)
        self._tail_out_duration = RationalTime(tail_out_duration, self._frame_rate)
        self._shot_regexp = shot_regexp
        if not self._cut_item_schema:
            self._cut_item_schema = self._sg.schema_field_read("CutItem")
        self._shot_name = None
        self._type = None
        self._format = None
        self._version_name = None
        self.sg_shot = None
        self._sg_cut_item = None
        self._user = user
        self._name = None
        self._transition_before = transition_before
        self._transition_after = transition_after
        self._process_clip()

    @property
    def name(self):
        """
        Return the cut item name.

        :returns: A str.
        """
        if not self._name:
            if isinstance(self._clip, otio.schema.Clip):
                # We prefer the reel name over the clip name.
                if self._clip.metadata.get("cmx_3600", {}).get("reel"):
                    self._name = self._clip.metadata["cmx_3600"]["reel"]
                else:
                    self._name = self._clip.name
            else:
                self._name = "Gap %03d" % self._clip_index
        return self._name

    @name.setter
    def name(self, value):
        """
        Set the cut item name.

        :param value: A str.
        """
        self._name = value

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
        # Make sure the shot name is not unicode.
        self._shot_name = six.ensure_str(value)

    @property
    def sg_cut(self):
        """
        Return the ShotGrid cut entity.

        :returns: A SG Cut dict or ``None``.
        """
        return self._sg_cut

    @sg_cut.setter
    def sg_cut(self, value):
        """
        Set the ShotGrid cut entity.

        :param value: A SG Cut dict or ``None``.
        """
        self._sg_cut = value

    @property
    def sg_shot(self):
        """
        Return the SG Shot of this CutItem.

        :returns: A SG Shot dict or ``None``.
        """
        return self._sg_shot

    @sg_shot.setter
    def sg_shot(self, value):
        """
        Set the SG Shot of this SGCutItem.

        :param value: A SG Shot dict or ``None``.
        """
        self._sg_shot = value

    @property
    def sg_cut_item(self):
        """
        Return the SG CutItem.

        :returns: A SG CutItem dict or ``None``.
        """
        return self._sg_cut_item

    @sg_cut_item.setter
    def sg_cut_item(self, value):
        """
        Set the SG CutItem.

        :param value: A SG CutItem dict or ``None``.
        """
        self._sg_cut_item = value

    @property
    def duration(self):
        """
        Return the duration of the cut item, taking into account the transitions.

        :returns: A :class:`RationalTime` instance.
        """
        duration = self._clip.duration()
        if self.transition_before:
            duration += self.transition_before.in_offset
        if self.transition_after:
            duration += self.transition_after.out_offset
        return duration

    @property
    def transition_before(self):
        """
        Get the :class:`otio.schema.Transition` that comes before this clip, if any.

        :returns: A :class:`otio.schema.Transition` or ``None``.
        """
        return self._transition_before

    @transition_before.setter
    def transition_before(self, value):
        """
        Set the :class:`otio.schema.Transition` that comes before this clip.

        :param value: A :class:`otio.schema.Transition` or ``None``.
        """
        self._transition_before = value

    @property
    def transition_after(self):
        """
        Get the :class:`otio.schema.Transition` that comes after this clip, if any.

        :returns: A :class:`otio.schema.Transition` or ``None``.
        """
        return self._transition_after

    @transition_after.setter
    def transition_after(self, value):
        """
        Set the :class:`otio.schema.Transition` that comes after this clip.

        :param value: A :class:`otio.schema.Transition` or ``None``.
        """
        self._transition_after = value

    @property
    def clip_index(self):
        """
        Return the index of the clip in the track.

        :returns: An int.
        """
        return self._clip_index

    @property
    def source_in(self):
        """
        Return the source in of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        source_in = self._clip.source_range.start_time
        if self.transition_before:
            source_in -= self.transition_before.in_offset
        return source_in

    @property
    def source_out(self):
        """
        Return the source out of the clip.

        :returns: A :class:`RationalTime` instance.
        """
        source_out = self._clip.source_range.end_time_exclusive()
        if self.transition_after:
            source_out += self.transition_after.out_offset
        return source_out

    @property
    def cut_in(self):
        """
        Return the cut in time of the clip.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        cut_in = RationalTime(0, self.duration.rate) + self._head_in + self._head_in_duration
        return cut_in

    @property
    def cut_out(self):
        """
        Return the cut out time of the clip.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self.cut_in + self.duration - RationalTime(1, self._frame_rate)

    def edit_in(self, absolute=True):
        """
        Return the edit in time of the clip.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        edit_in = self._clip.range_in_parent().start_time
        if absolute:
            edit_in += self._track_start
        else:
            edit_in += RationalTime(1, self._frame_rate)
        if self.transition_before:
            edit_in -= self.transition_before.in_offset
        return edit_in

    def edit_out(self, absolute=True):
        """
        Return the edit out time of the clip.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        edit_out = self._clip.range_in_parent().end_time_exclusive()
        if absolute:
            edit_out += self._track_start
        if self.transition_after:
            edit_out += self.transition_after.out_offset
        return edit_out

    @property
    def head_in(self):
        """
        Return head in value, from the Shot or from the clip information.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        # If we have an SG Shot, return it.
        if self.sg_shot:
            head_in_field = self._shot_fields_config.head_in
            if self._shot_fields_config.use_smart_fields:
                head_in_field = "smart_%s" % head_in_field
            head_in = self.sg_shot.get(head_in_field)
            if head_in:
                return RationalTime(head_in, self._frame_rate)
        # Otherwise, return the default.
        return self.cut_in - self._head_in_duration

    @property
    def tail_out(self):
        """
        Return tail out value.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        # If we have an SG Shot, return it.
        if self.sg_shot:
            tail_out_field = self._shot_fields_config.tail_out
            if self._shot_fields_config.use_smart_fields:
                tail_out_field = "smart_%s" % tail_out_field
            tail_out = self.sg_shot.get(tail_out_field)
            if tail_out:
                return RationalTime(tail_out, self._frame_rate)
        # Otherwise, return the default.
        return self.cut_out + self._tail_out_duration

    @property
    def head_in_duration(self):
        """
        Returns the head in duration.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._head_in_duration

    @head_in_duration.setter
    def head_in_duration(self, value):
        """
        Sets the head in duration.

        :param value: A :class:`otio.opentime.RationalTime` instance.
        """
        self._head_in_duration = value

    @property
    def tail_out_duration(self):
        """
        Returns the tail out duration.

        :returns: A :class:`otio.opentime.RationalTime` instance.
        """
        return self._tail_out_duration

    @tail_out_duration.setter
    def tail_out_duration(self, value):
        """
        Sets the tail out duration.

        :param value: A :class:`otio.opentime.RationalTime` instance.
        """
        self._tail_out_duration = value

    @property
    def is_vfx_shot(self):
        """
        Return ``True`` if this item is linked to a VFX Shot

        :returns: ``True`` if linked to a VFX Shot, ``False`` otherwise.
        """
        # Non vfx Shots are not handled in SG by our current clients so, for the
        # time being, just check if the item is linked to a Shot.
        # If not, then this is not a VFX Shot entry.
        if self.sg_shot:
            # Later we might want to do additional checks on the linked Shot
            return True
        return False

    @property
    def effects_str(self):
        """
        Return a string with the effects of the clip, if any.

        :returns: A string or ``None``.
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

        :returns: A string or ``None``.
        """

        if self._clip.effects:
            return ", ".join([effect.effect_name for effect in self._clip.effects])
        return None

    @property
    def has_retime(self):
        """
        Returns whether or not the clip has retime information.

        :returns: A bool.
        """
        return True if self._clip.effects else False

    @property
    def payload(self):
        """
        Get a SG CutItem payload for a given :class:`otio.schema.Clip` instance.

        An absolute cut order can be set on CutItems if the `sg_absolute_cut_order`
        integer field was added to the SG CutItem schema. This absolute cut order
        is meant to be the cut order of the CutItem in the Project and is based on
        a cut order value set on the Entity (Reel, Sequence, etc...) the Cut is
        imported against. The absolute cut order is then:
        `1000 * entity cut order + edit cut order`.

        :returns: A dictionary with the CutItem payload.
        """

        description = ""
        cut_item_payload = {
            "project": self._sg_cut.get("project"),
            "code": self.name,
            "cut": self._sg_cut,
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
        if self._sg_shot:
            cut_item_payload["shot"] = self._sg_shot
        if self._user:
            cut_item_payload["created_by"] = self._user
            cut_item_payload["updated_by"] = self._user

        if self.has_effects:
            description = "%s\nEffects: %s" % (
                description,
                self.effects_str
            )
        if _EFFECTS_FIELD in self._cut_item_schema:
            cut_item_payload[_EFFECTS_FIELD] = self.has_effects

        if self.has_retime:
            description = "%s\nRetime: %s" % (description, self.retime_str)
        if _RETIME_FIELD in self._cut_item_schema:
            cut_item_payload[_RETIME_FIELD] = self.has_retime

        cut_item_payload["description"] = description
        linked_entity = self._sg_cut["entity"]
        if (
                _ABSOLUTE_CUT_ORDER_FIELD in self._cut_item_schema
                and linked_entity.get(_ENTITY_CUT_ORDER_FIELD)
        ):
            cut_item_payload[_ABSOLUTE_CUT_ORDER_FIELD] = 1000 * linked_entity[
                _ENTITY_CUT_ORDER_FIELD] + self._clip_index
        return cut_item_payload

    def _process_clip(self):
        r"""
        Processes the clip to find information about the shot name, and potentially
        type, format and version name.

        The Shot name can be found in the following places, in order of preference:
        - SG metadata about the Cut Item, if it has a shot field.
        - A :class:`otio.schema.Marker`, in an EDL it would be
          * LOC: 00:00:02:19 YELLOW  053_CSC_0750_PC01_V0001 997 // 8-8 Match to edit,
          which otio would convert to a marker with name "name='053_CSC_0750_PC01_V0001 997 // 8-8 Match to edit".
          We would only consider the first part of the name, split by " ".
        - In an EDL "pure" comment, e.g. "* COMMENT : 053_CSC_0750_PC01_V0001"
        - In an EDL comment, e.g. "* 053_CSC_0750_PC01_V0001"

        If a shot regular expression is given, it will be used to extract extra information
        from the edit name.

        - a shot name
        - a type
        - a format
        - a version name

        Typical values for the regular expression would be as simple as a single group
        to extract the shot name, e.g. ``^(\w+)_.+$``
        or more advanced regular expression with named groups to extract additional
        information, e.g. ``(?P<shot_name>\w+)_(?P<type>\w\w\d\d)_(?P<version>[V,v]\d+)$``
        """
        if self._clip.metadata.get("sg", {}).get("shot"):
            self.shot_name = self._clip.metadata["sg"]["shot"]["name"]
            return
        if self._clip.markers:
            self.shot_name = self._clip.markers[0].name.split()[0]
            return
        comment_match = None
        if self._clip.metadata.get("cmx_3600") and self._clip.metadata["cmx_3600"].get("comments"):
            comments = self._clip.metadata["cmx_3600"]["comments"]
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
        if not comment_match:
            return
        if not self._shot_regexp:
            self.shot_name = comment_match
            return
        # Support pre-compiled regexp or strings
        if isinstance(self._shot_regexp, str):
            regexp = re.compile(self._shot_regexp)
        else:
            regexp = self._shot_regexp
        logger.debug("Parsing %s with %s" % (comment_match, str(regexp)))
        m = regexp.search(comment_match)
        if m:
            logger.debug("Matched groups: %s" % str(m.groups()))
            if regexp.groups == 1:  # Only one capturing group, use it for the shot name
                self._shot_name = m.group(1)
            else:
                grid = regexp.groupindex
                if "shot_name" not in grid:
                    raise ValueError(
                        "No \"shot_name\" named group in regular expression %s" % regexp.pattern)
                self.shot_name = m.group("shot_name")
                if "type" in grid:
                    self.type = m.group("type")
                if "format" in grid:
                    self._format = m.group("format")
                if "version" in grid:
                    self._version_name = m.group("version")
