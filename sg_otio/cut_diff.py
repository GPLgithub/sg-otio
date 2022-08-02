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
        super(SGCutDiff, self).__init__(*args, **kwargs)
        self._old_clip = None
        self._repeated = repeated
        self._diff_type = _DIFF_TYPES.NO_CHANGE
        self._as_omitted = as_omitted
        self._cut_changes_reasons = []
        self._check_and_set_changes()

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
        self._old_clip = value
        self._check_and_set_changes()

    @property
    def old_cut_in(self):
        """
        Return the Cut in value for the old Clip, if any.

        :returns: A :class:`RationalTime` instance or ``None``.
        """
        if self._as_omitted:
            old_clip = self
        else:
            old_clip = self._old_clip
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
        if self._as_omitted:
            old_clip = self
        else:
            old_clip = self._old_clip
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
        if self._as_omitted:
            return self.index
        if self._old_clip:
            return self._old_clip.index
        return None

    @property
    def old_visible_duration(self):
        """
        Return the Cut duration value for the old Clip, if any.

        :returns: A :class:`RationalTime` instance or ``None``.
        """
        if self._as_omitted:
            return self.visible_duration
        if self._old_clip:
            return self._old_clip.visible_duration
        return None

    @property
    def cut_in(self):
        """
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
        if self.sg_shot_status and self.sg_shot_status.get("code"):
            # TODO: check if matching by short code is right? #9320
            if self.sg_shot_status["code"] in SGSettings().shot_omitted_statuses:
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
        if(
            self.sg_shot_head_in is not None  # Report rescan only if value is set on the Shot
            and self.head_in_duration is not None
            and self.head_in_duration.to_frames() < 0
        ):
            self._diff_type = _DIFF_TYPES.RESCAN

        if(
            self.sg_shot_tail_out is not None  # Report rescan only if value is set on the Shot
            and self.tail_out_duration is not None
            and self.tail_out_duration.to_frames() < 0
        ):
            self._diff_type = _DIFF_TYPES.RESCAN

        # We use cut in and cut out values which accurately report changes since
        # they are not based on Shot values.
        if(
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

        if(
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
