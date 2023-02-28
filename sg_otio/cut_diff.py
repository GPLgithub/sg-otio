# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging

from opentimelineio.opentime import RationalTime

from .cut_clip import SGCutClip
from .constants import _DIFF_TYPES
from .sg_settings import SGSettings

logger = logging.getLogger(__name__)


class SGCutDiff(SGCutClip):
    """
    A class representing a difference between two Cuts.

    The difference is set with two clips, the current one and the old one.
    A SGCutDiff always have at least a current clip or an old clip, and can
    have both if the current clip was matched to an old one.
    """
    def __init__(self, as_omitted=False, repeated=False, *args, **kwargs):
        """
        Instantiate a new :class:`SGCutDiff`.

        If `as_omitted` is set to ``True``, this instance represents and old
        Clip without any counterpart in the new Cut.
        """
        self._as_omitted = as_omitted
        self._old_clip = None
        self._repeated = repeated
        self._diff_type = _DIFF_TYPES.NO_CHANGE
        self._cut_changes_reasons = []
        super(SGCutDiff, self).__init__(*args, **kwargs)
        # Omitted clips should be linked to SG Cut Items.
        if self._as_omitted and not self.sg_cut_item:
            raise ValueError("Omitted Clips need to be linked to a SG CutItem")
        self._check_and_set_changes()

    @SGCutClip.group.setter
    def group(self, value):
        """
        Set the :class:`ClipGroup` this Clip is in.

        Override base implementation setter to update the diff type if the group is set.

        :param value: :class:`ClipGroup` instance.
        """
        old = self.group
        # See: https://docs.python.org/2/library/functions.html#property
        SGCutClip.group.fset(self, value)
        if old != value:
            self._check_and_set_changes()

    @SGCutClip.sg_shot.setter
    def sg_shot(self, value):
        """
        Set the SG Shot value associated with this Clip.

        Recompute head_in, head_duration and tail_duration,
        which depend on the SG Shot.

        :param value: A SG Shot dictionary.
        :raises ValueError: For invalid values.
        """
        old = self.sg_shot
        # See: https://docs.python.org/2/library/functions.html#property
        SGCutClip.sg_shot.fset(self, value)
        if old != value:
            self._check_and_set_changes()

    @property
    def sg_version(self):
        """
        Return the SG Version associated with this SGCutDiff, if any.

        :returns: A dictionary or ``None``.
        """
        # Check the current clip
        sg_version = super(SGCutDiff, self).sg_version
        if sg_version:
            return sg_version
        # Check the old clip
        if self._old_clip:
            return self._old_clip.sg_version
        return None

    @property
    def current_clip(self):
        """
        Return the current Clip for this SGCutDiff, if any.

        :returns: A :class:`SGCutClip` or ``None``.
        """
        if self._as_omitted:
            return None
        return self

    @property
    def old_clip(self):
        """
        Return the old Clip for this SGCutDiff, if any.

        :returns: A :class:`SGCutClip` or ``None``.
        """
        if self._as_omitted:
            return self  # Note: we could rather return None here.
        return self._old_clip

    @old_clip.setter
    def old_clip(self, value):
        """
        Set the old Clip for this SGCutDiff.

        :param value: A :class:`SGCutClip`.
        :raises ValueError: For invalid values.
        """
        if self._as_omitted:
            raise ValueError(
                "Setting the old clip for an omitted SGCutDiff is not allowed."
            )
        if value:
            if not value.sg_cut_item:
                raise ValueError(
                    "Old clips for SGCutDiff must be coming from a SG Cut Item"
                )
            if self.sg_shot:
                if value.sg_shot and value.sg_shot["id"] != self.sg_shot["id"]:
                    raise ValueError(
                        "Shot mismatch between current clip and old one %s vs %s" % (
                            self.sg_shot["id"], value.sg_shot["id"]
                        )
                    )
        self._old_clip = value
        self._check_and_set_changes()

    @property
    def old_cut_in(self):
        """
        Return the Cut in value for the old Clip, if any.

        :returns: A :class:`RationalTime` instance or ``None``.
        """
        old_clip = self.old_clip
        if old_clip:
            value = old_clip.metadata.get("sg", {}).get("cut_item_in")
            if value is not None:
                return RationalTime(value, old_clip.frame_rate)
        return None

    @property
    def old_cut_out(self):
        """
        Return the Cut out value for the old Clip, if any.

        :returns: A :class:`RationalTime` instance or ``None``.
        """
        old_clip = self.old_clip
        if old_clip:
            value = old_clip.metadata.get("sg", {}).get("cut_item_out")
            if value is not None:
                return RationalTime(value, old_clip.frame_rate)
        return None

    @property
    def old_index(self):
        """
        Return the Cut index value for the old Clip, if any.

        :returns: An integer or ``None``.
        """
        old_clip = self.old_clip
        if old_clip:
            return old_clip.index
        return None

    @property
    def old_visible_duration(self):
        """
        Return the Cut duration value for the old Clip, if any.

        :returns: A :class:`RationalTime` instance or ``None``.
        """
        old_clip = self.old_clip
        if old_clip:
            return old_clip.visible_duration
        return None

    @property
    def old_head_duration(self):
        """
        Return the head duration for the old Clip, or None.

        :returns: A :class:`RationalTime` instance or ``None``.
        """
        sg_shot_head_in = self.sg_shot_head_in
        if sg_shot_head_in is None:
            return None
        old_cut_in = self.old_cut_in
        if old_cut_in is None:
            return None
        return old_cut_in - RationalTime(sg_shot_head_in, self._frame_rate)

    @property
    def old_tail_duration(self):
        """
        Return the tail duration for the old Clip, or None.

        :returns: A :class:`RationalTime` instance or ``None``.
        """
        sg_shot_tail_out = self.sg_shot_tail_out
        if sg_shot_tail_out is None:
            return None
        old_cut_out = self.old_cut_out
        if old_cut_out is None:
            return None
        return RationalTime(sg_shot_tail_out, self._frame_rate) - old_cut_out

    @property
    def cut_in(self):
        """
        Return the cut in time of the clip.

        Override base implementation to take into account the previous Cut
        entry, if any.

        :returns: A :class:`RationalTime` instance.
        """
        if self.old_clip:
            cut_in = self.old_cut_in
            source_in = self.old_clip.source_in
            if cut_in is not None and source_in is not None:
                # Calculate the cut offset
                offset = self.source_in - source_in
                # Just apply the offset to the old cut in
                return cut_in + offset
        return super(SGCutDiff, self).cut_in

    @property
    def head_duration(self):
        """
        Return the head duration.

        Override base implementation to take into account the previous Cut
        cut in value, if any.

        :returns: A :class:`RationalTime` instance.
        """
        if self.current_clip:
            cut_in = self.cut_in
            head_in = self.head_in
            # head_out would be cut_in -1, so head_duration would be:
            # cut_in -1 - head_in + 1, we use a simplified formula below
            return cut_in - head_in
        return super(SGCutDiff, self).head_duration

    @head_duration.setter
    def head_duration(self, value):
        """
        Sets the head handle duration.

        Needed because we override the corresponding property.

        :param value: A :class:`RationalTime` instance.
        """
        self._head_duration = value

    @property
    def tail_out(self):
        """
        Return tail out value.

        This is the very last frame number for this clip, including handles.

        Override base implementation to take into account the previous value
        set on the Shot, if any.

        :returns: A :class:`RationalTime` instance.
        """
        if self.sg_shot_tail_out is not None:
            return RationalTime(self.sg_shot_tail_out, self._frame_rate)
        return super(SGCutDiff, self).tail_out

    @property
    def tail_duration(self):
        """
        Return the tail handle duration.

        Override base implementation to take into account the previous value
        set on the Shot, if any.

        :returns: A :class:`RationalTime` instance.
        """
        if self.current_clip:
            cut_out = self.cut_out
            tail_out = self.sg_shot_tail_out
            if tail_out is not None:
                return RationalTime(tail_out, self._frame_rate) - cut_out
        return super(SGCutDiff, self).tail_duration

    @tail_duration.setter
    def tail_duration(self, value):
        """
        Sets the tail handle duration.

        Needed because we override the corresponding property.

        :param value: A :class:`RationalTime` instance.
        """
        self._tail_duration = value

    @property
    def diff_type(self):
        """
        Return the SGCutDiff type of this cut difference

        :returns: A _DIFF_TYPES
        """
        return self._diff_type

    @property
    def reasons(self):
        """
        Return a list of reasons strings for this Cut difference.

        Return an empty list for any diff type which is not
        a CUT_CHANGE or a RESCAN.

        :returns: A possibly empty list of strings
        """
        return self._cut_changes_reasons

    @property
    def interpreted_diff_type(self):
        """
        Some difference types are grouped under a common type to deal with repeated
        Shots. Invididual entries can be flagged as NEW_IN_CUT or OMITTED_IN_CUT.

        - If all entries for a given Shot are OMITTED_IN_CUT, then the Shot is
        OMITTED, and this is the returned type. Otherwise it is just a CUT_CHANGE.

        - NEW_IN_CUT is different, even if all entries for a Shot are NEW_IN_CUT,
        if a Shot exists it is not NEW. Individual entries will be set to NEW if
        the Shot does not exist in Shotgun.

        Other cases fall back to the actual diff type.

        :returns: A _DIFF_TYPES
        """
        if self.diff_type in [_DIFF_TYPES.NEW_IN_CUT, _DIFF_TYPES.OMITTED_IN_CUT]:
            return _DIFF_TYPES.CUT_CHANGE

        # Please note that a loop is potentially done over all siblings, so this
        # must be used with care as it can be inefficient
        if self.diff_type == _DIFF_TYPES.OMITTED_IN_CUT and self.repeated:
            # Check if all our siblings are omitted_in_cut as well
            for sibling in self.group.clips:
                if sibling != _DIFF_TYPES.OMITTED_IN_CUT:
                    break
            else:
                return _DIFF_TYPES.OMITTED

        # Fall back to reality!
        return self.diff_type

    @property
    def rescan_needed(self):
        """
        Return True if this SGCutDiff implies a rescan.

        :returns: ``True`` if a rescan is needed, ``False`` otherwise
        """
        return self._diff_type == _DIFF_TYPES.RESCAN

    @property
    def repeated(self):
        """
        Return ``True`` if multiple Clips are associated with the same Shot in
        the current Cut.

        :returns: A boolean.
        """
        return self._repeated

    @repeated.setter
    def repeated(self, value):
        """
        Set this SGCutDiff as repeated.

        :param value: A boolean.
        """
        if value != self._repeated:
            self._repeated = value
            # Cut in/out values are affected by repeated changes
            self._check_and_set_changes()

    def summary(self):
        """
        Return a summary for this SGCutDiff instance as a tuple with :
        Shot details, Cut item details, Version details and New cut details

        :returns: A tuple with four entries, where each entry is a potentially empty string.
        """
        shot_details = ""
        if self.sg_shot:
            shot_details = (
                "Name : %s, Status : %s, Head In : %s, Cut In : %s, Cut Out : %s, "
                "Tail Out : %s, Cut Order : %s" % (
                    self.sg_shot["code"],
                    self.sg_shot_status,
                    self.sg_shot_head_in,
                    self.sg_shot_cut_in,
                    self.sg_shot_cut_out,
                    self.sg_shot_tail_out,
                    self.sg_shot_cut_order,
                )
            )
        old_details = ""
        if self.old_clip:
            old_details = self.old_clip.source_info
        version_details = ""
        sg_version = self.sg_version
        if sg_version:
            version_details = "%s, link %s %s" % (
                sg_version["code"],
                sg_version["entity"]["type"] if sg_version["entity"] else "None",
                sg_version["entity.Shot.code"] if sg_version["entity.Shot.code"] else "",
            )
        new_details = ""
        if not self._as_omitted:
            new_details = self.source_info
        return shot_details, old_details, version_details, new_details

    def _check_and_set_changes(self):
        """
        Set the cut difference type for this cut difference.
        """
        self._diff_type = _DIFF_TYPES.NO_CHANGE
        self._cut_changes_reasons = []

        # The type of difference we are dealing with.
        if not self.shot_name:
            self._diff_type = _DIFF_TYPES.NO_LINK
            return

        if not self.sg_shot:
            self._diff_type = _DIFF_TYPES.NEW
            return

        # No current clip
        if self._as_omitted:
            if not self.repeated:
                self._diff_type = _DIFF_TYPES.OMITTED
            else:
                self._diff_type = _DIFF_TYPES.OMITTED_IN_CUT
            return

        # We have both a Shot and a current clip.
        if self.sg_shot_status and self.sg_shot_status in SGSettings().reinstate_shot_if_status_is:
            self._diff_type = _DIFF_TYPES.REINSTATED
            return

        # This clip hasn't appeared in previous Cuts.
        if not self._old_clip:
            self._diff_type = _DIFF_TYPES.NEW_IN_CUT
            return

        # Check if we have a difference.
        # If any of the previous values are not set, then assume they all changed
        # (initial import)
        if (
            self.old_index is None
            or self.old_cut_in is None
            or self.old_cut_out is None
            or self.old_visible_duration is None
        ):
            self._diff_type = _DIFF_TYPES.CUT_CHANGE
            return

        # Note: leaving this in here in case we decide to switch back to an old
        # behavior where index changes would be flagged as changes.
        # if self.index != self.old_index:
        #     self._diff_type = _DIFF_TYPES.CUT_CHANGE
        #     self._cut_changes_reasons.append(
        #         "Cut order changed from %d to %d" % (self.old_index, self.index))

        self._check_and_set_rescan()

    def _check_and_set_rescan(self):
        """
        Check if a rescan is needed and set the cut difference type accordingly.

        This method should only be called if new Cut values are available.

        .. note:: This is currently based on Shot values and is not very reliable
                  since Shot values can be unset or manually set to any value
                  regardless of imported Cuts.
        """
        # Note: the head_in and tail_out values are actually the values
        # set on the Shot (if set). So these values can't be used to check for
        # changes.
        # Please note as well that if the head in and/or tail out values are changed
        # on the Shot and the Cut which was previously imported is imported again
        # some entries might be flagged as "Need rescan", even if there are no
        # cut changes.
        if (
            self.sg_shot_head_in is not None  # Report rescan only if value is set on the Shot
            and self.head_duration is not None
            and self.head_duration.to_frames() < 0
        ):
            self._diff_type = _DIFF_TYPES.RESCAN

        if (
            self.sg_shot_tail_out is not None  # Report rescan only if value is set on the Shot
            and self.tail_duration is not None
            and self.tail_duration.to_frames() < 0
        ):
            self._diff_type = _DIFF_TYPES.RESCAN

        # We use cut in and cut out values which accurately report changes since
        # they are not based on Shot values.
        if (
            self.old_cut_in is not None
            and self.cut_in is not None
            and self.old_cut_in != self.cut_in
        ):
            if self._diff_type != _DIFF_TYPES.RESCAN:
                self._diff_type = _DIFF_TYPES.CUT_CHANGE
            diff = (self.cut_in - self.old_cut_in).to_frames()
            if diff > 0:
                self._cut_changes_reasons.append("Head extended %d frs" % diff)
            else:
                self._cut_changes_reasons.append("Head trimmed %d frs" % -diff)

        if (
            self.old_cut_out is not None
            and self.cut_out is not None
            and self.old_cut_out != self.cut_out
        ):
            if self._diff_type != _DIFF_TYPES.RESCAN:
                self._diff_type = _DIFF_TYPES.CUT_CHANGE
            diff = (self.cut_out - self.old_cut_out).to_frames()
            if diff > 0:
                self._cut_changes_reasons.append("Tail trimmed %d frs" % diff)
            else:
                self._cut_changes_reasons.append("Tail extended %d frs" % -diff)
