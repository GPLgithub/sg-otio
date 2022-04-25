# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import unittest

import opentimelineio as otio

from sg_otio.constants import _ENTITY_CUT_ORDER_FIELD
from sg_otio.constants import _RETIME_FIELD, _EFFECTS_FIELD, _ABSOLUTE_CUT_ORDER_FIELD
from sg_otio.sg_cut_item import SGCutItem

try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock


class SGCutItemTest(unittest.TestCase):
    """
    Test the SGCutItem class. Even though some of the logic depends on SG, avoid using mockgun
    to be able to run these tests without any connection to SG (for the schema).
    """

    def test_cut_items_values(self):
        """
        Test cut item values for simple cut items (no transitions, gaps, no values from SG).
        """
        # We start from an EDL since it's easier to see what each value from the clip item
        # is supposed to be.
        edl = """
            001  ABC0100 V     C        00:00:00:00 00:00:01:00 01:00:00:00 01:00:01:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001

            002  ABC0200 V     C        00:00:01:00 00:00:02:00 01:00:01:00 01:00:02:00
            * FROM CLIP NAME: shot_002_v001
            * COMMENT: shot_002
        """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        track = timeline.tracks[0]
        # Test for the first clip
        first_clip = list(track.each_clip())[0]
        cut_item = SGCutItem(
            sg=mock.MagicMock(),
            sg_cut=None,
            clip=first_clip,
            clip_index=1,
            track_start=-track.source_range.start_time,
            shot_fields_config=None,
        )
        self.assertEqual(cut_item.name, "ABC0100")
        self.assertEqual(cut_item.shot_name, "shot_001")
        self.assertEqual(cut_item.duration, first_clip.duration())
        self.assertEqual(cut_item.clip_index, 1)
        # Assertions with timecodes since this is what will be saved to SG
        self.assertEqual(cut_item.source_in.to_timecode(), "00:00:00:00")
        self.assertEqual(cut_item.source_out.to_timecode(), "00:00:01:00")
        # Cut in should be head_in + head_in_duration
        self.assertEqual(cut_item.cut_in.to_frames(), 1001 + 8)
        # Cut out should be cut in + duration - 1
        self.assertEqual(cut_item.cut_out.to_frames(), 1001 + 8 + cut_item.duration.to_frames() - 1)
        # Assertions with timecodes since this is what will be saved to SG
        self.assertEqual(cut_item.edit_in().to_timecode(), "01:00:00:00")
        self.assertEqual(cut_item.edit_out().to_timecode(), "01:00:01:00")
        # Assertions with frames since this is what will be saved to SG
        self.assertEqual(cut_item.edit_in(absolute=False).to_frames(), 1)
        self.assertEqual(cut_item.edit_out(absolute=False).to_frames(), 24)
        self.assertEqual(cut_item.head_in.to_frames(), 1001)
        self.assertEqual(cut_item.tail_out.to_frames(), cut_item.cut_out.to_frames() + 8)
        self.assertEqual(cut_item.head_in_duration.to_frames(), 8)
        self.assertEqual(cut_item.tail_out_duration.to_frames(), 8)
        # Is VFX Shot depends on the fact if a SG Shot was set or not
        self.assertTrue(not cut_item.is_vfx_shot)
        cut_item.sg_shot = {"foo": "bar"}
        self.assertTrue(cut_item.is_vfx_shot)
        self.assertTrue(not cut_item.has_effects)
        self.assertTrue(not cut_item.has_retime)

        # Test for the second clip. This is important specially for edit_in/out information
        # so we will limit the tests to cut in/out and edit in/out
        second_clip = list(track.each_clip())[1]
        cut_item = SGCutItem(
            sg=mock.MagicMock(),
            sg_cut=None,
            clip=second_clip,
            clip_index=2,
            track_start=-track.source_range.start_time,
            shot_fields_config=None,
        )
        # Cut in should be head_in + head_in_duration
        self.assertEqual(cut_item.cut_in.to_frames(), 1001 + 8)
        # Cut out should be cut in + duration - 1
        self.assertEqual(cut_item.cut_out.to_frames(), 1001 + 8 + cut_item.duration.to_frames() - 1)
        # Assertions with timecodes since this is what will be saved to SG
        self.assertEqual(cut_item.edit_in().to_timecode(), "01:00:01:00")
        self.assertEqual(cut_item.edit_out().to_timecode(), "01:00:02:00")
        # Assertions with frames since this is what will be saved to SG
        self.assertEqual(cut_item.edit_in(absolute=False).to_frames(), 25)
        self.assertEqual(cut_item.edit_out(absolute=False).to_frames(), 48)

    def test_cut_items_values_with_transitions(self):
        """
        Check that when there are transitions, the cut item values are correct
        """
        # Create a track with a transition between shot_001 and shot_002
        # Note that the cmx_3600 adapter has a bug when the last clip is just after a transition,
        # and creates a gap instead of a clip, that's why we add the shot_003 clip.
        edl = """
            TITLE:   OTIO_TEST
            FCM: NON-DROP FRAME

            001  ABC0100 V     C        01:00:00:00 01:00:01:00 01:00:00:00 01:00:01:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001

            002  ABC0200 V     C        01:00:01:00 01:00:01:00 01:00:01:00 01:00:01:00
            * COMMENT: shot_002

            002  ABC0200 V     D    024 01:00:01:00 01:00:02:00 01:00:01:00 01:00:02:00
            * FROM CLIP NAME: shot_001_v001
            * TO CLIP NAME: shot_002_v001

            003  ABC0300 V     C        00:00:05:00 00:00:15:00 01:00:02:00 01:00:12:00
            * FROM CLIP NAME: shot_003_v001
            * COMMENT: shot_003
        """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        track = timeline.tracks[0]
        # Test for the first clip
        first_clip = list(track.each_child())[0]
        transition = list(track.each_child())[1]
        cut_item = SGCutItem(
            sg=mock.MagicMock(),
            sg_cut=None,
            clip=first_clip,
            clip_index=1,
            track_start=-track.source_range.start_time,
            shot_fields_config=None,
            # Note that it's the responsibility of sg_cut when setting the cut_items to add
            # the proper transitions.
            transition_after=transition,
        )
        # What we'd like to check is that the transition's in_offset has correctly been
        # added to some of the values of the first clip
        self.assertEqual(cut_item.duration, first_clip.duration() + transition.in_offset)
        # Test with timecodes since this is what will be saved to SG
        self.assertEqual(cut_item.source_in.to_timecode(), "01:00:00:00")
        # Note that it's the same source out as in the EDL, but with the transition time in it
        self.assertEqual(cut_item.source_out.to_timecode(), "01:00:02:00")
        self.assertEqual(cut_item.cut_in.to_frames(), 1001 + 8)
        self.assertEqual(
            cut_item.cut_out.to_frames(),
            # Note that we explicitly add the clip duration and the transition in offset,
            # which is actually the cut item's duration, but just so that it's more obvious
            # how the cut out is calculated.
            1001 + 8 + first_clip.duration().to_frames() - 1 + transition.in_offset.to_frames()
        )
        self.assertEqual(cut_item.edit_in().to_timecode(), "01:00:00:00")
        # Note that edit out takes the transition into account.
        self.assertEqual(cut_item.edit_out().to_timecode(), "01:00:02:00")
        self.assertEqual(cut_item.edit_in(absolute=False).to_frames(), 1)
        # Note that edit out takes the transition into account.
        self.assertEqual(cut_item.edit_out(absolute=False).to_frames(), 24 + 24)
        self.assertTrue(cut_item.has_effects)
        self.assertEqual(cut_item.effects_str, "After: SMPTE_Dissolve (12 frames)\n")

        # Test for the second clip
        second_clip = list(track.each_child())[2]
        cut_item = SGCutItem(
            sg=mock.MagicMock(),
            sg_cut=None,
            clip=second_clip,
            clip_index=1,
            track_start=-track.source_range.start_time,
            shot_fields_config=None,
            # Note that it's the responsibility of sg_cut when setting the cut_items to add
            # the proper transitions.
            transition_before=transition,
        )
        self.assertEqual(second_clip.duration().to_frames(), 12)
        self.assertEqual(cut_item.duration, second_clip.duration() + transition.in_offset)
        # Test with timecodes since this is what will be saved to SG
        self.assertEqual(cut_item.source_in.to_timecode(), "01:00:01:00")
        # Note that it's the same source out as in the EDL, but with the transition time in it
        self.assertEqual(cut_item.source_out.to_timecode(), "01:00:02:00")
        self.assertEqual(cut_item.cut_in.to_frames(), 1001 + 8)
        self.assertEqual(
            cut_item.cut_out.to_frames(),
            # Note that we explicitly add the clip duration and the transition in offset,
            # which is actually the cut item's duration, but just so that it's more obvious
            # how the cut out is calculated.
            1001 + 8 + second_clip.duration().to_frames() - 1 + transition.in_offset.to_frames()
        )
        self.assertEqual(cut_item.edit_in().to_timecode(), "01:00:01:00")
        # Note that edit out takes the transition into account.
        self.assertEqual(cut_item.edit_out().to_timecode(), "01:00:02:00")
        self.assertEqual(cut_item.edit_in(absolute=False).to_frames(), 25)
        # Note that edit out takes the transition into account.
        self.assertEqual(cut_item.edit_out(absolute=False).to_frames(), 25 + 12 + 12 - 1)
        self.assertTrue(cut_item.has_effects)
        self.assertEqual(cut_item.effects_str, "Before: SMPTE_Dissolve (12 frames)\n")

    def test_cut_item_retime(self):
        """
        Test that a cut item from a clip that has retime effects takes them into account.
        """
        edl = """
        005  foo V     C        00:00:43:09 00:00:45:22 01:08:10:07 01:08:11:14 
        M2   foo       048.0                00:00:43:09
        """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        track = timeline.tracks[0]
        cut_item = SGCutItem(
            sg=mock.MagicMock(),
            sg_cut=None,
            clip=list(track.each_child())[0],
            clip_index=1,
            track_start=-track.source_range.start_time,
            shot_fields_config=None,
        )
        self.assertTrue(cut_item.has_retime)
        self.assertEqual(cut_item.retime_str, "LinearTimeWarp")

    def test_cut_items_payload(self):
        """
        Test that the Cut Items payload is correct.
        """
        edl = """
                    001  ABC0100 V     C        00:00:00:00 00:00:01:00 01:00:00:00 01:00:01:00
                    * FROM CLIP NAME: shot_001_v001
                    * COMMENT: shot_001

                    002  ABC0200 V     C        00:00:01:00 00:00:02:00 01:00:01:00 01:00:02:00
                    * FROM CLIP NAME: shot_002_v001
                    * COMMENT: shot_002
                """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        track = timeline.tracks[0]
        # Let's create a dummy schema and a dummy cut.
        SGCutItem._cut_item_schema = {
            _EFFECTS_FIELD: None,
            _RETIME_FIELD: None,
            _ABSOLUTE_CUT_ORDER_FIELD: None
        }
        sg_cut = {
            "project": {"name": "foo"},
            "entity": {"name": "bar", _ENTITY_CUT_ORDER_FIELD: 2},
        }
        # Test for the first clip
        first_clip = list(track.each_clip())[0]
        cut_item = SGCutItem(
            sg=mock.MagicMock(),
            sg_cut=sg_cut,
            clip=first_clip,
            clip_index=1,
            track_start=-track.source_range.start_time,
            shot_fields_config=None,
        )
        payload = {
            "project": {"name": "foo"},
            "code": "ABC0100",
            "cut": {"project": {"name": "foo"}, "entity": {"name": "bar", "sg_cut_order": 2}},
            "cut_order": 1,
            "timecode_cut_item_in_text": "00:00:00:00",
            "timecode_cut_item_out_text": "00:00:01:00",
            "timecode_edit_in_text": "01:00:00:00",
            "timecode_edit_out_text": "01:00:01:00",
            "cut_item_in": 1009,
            "cut_item_out": 1032,
            "edit_in": 1,
            "edit_out": 24,
            "cut_item_duration": 24,
            "sg_effects": False,
            "sg_respeed": False,
            "description": "",
            "sg_absolute_cut_order": 2001
        }
        self.assertEqual(cut_item.payload, payload)

        # Test for the second clip
        second_clip = list(track.each_clip())[1]
        cut_item = SGCutItem(
            sg=mock.MagicMock(),
            sg_cut=sg_cut,
            clip=second_clip,
            clip_index=2,
            track_start=-track.source_range.start_time,
            shot_fields_config=None,
        )
        payload = {
            "project": {"name": "foo"},
            "code": "ABC0200",
            "cut": {"project": {"name": "foo"}, "entity": {"name": "bar", "sg_cut_order": 2}},
            "cut_order": 2,
            "timecode_cut_item_in_text": "00:00:01:00",
            "timecode_cut_item_out_text": "00:00:02:00",
            "timecode_edit_in_text": "01:00:01:00",
            "timecode_edit_out_text": "01:00:02:00",
            "cut_item_in": 1009,
            "cut_item_out": 1032,
            "edit_in": 25,
            "edit_out": 48,
            "cut_item_duration": 24,
            "sg_effects": False,
            "sg_respeed": False,
            "description": "",
            "sg_absolute_cut_order": 2002,
        }
        self.assertEqual(cut_item.payload, payload)


if __name__ == "__main__":
    unittest.main()
