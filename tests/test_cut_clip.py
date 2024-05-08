# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import os
import unittest

import opentimelineio as otio
from opentimelineio.opentime import TimeRange, RationalTime

from sg_otio.cut_clip import SGCutClip
from sg_otio.clip_group import ClipGroup
from sg_otio.sg_settings import SGSettings
from sg_otio.utils import compute_clip_shot_name
from sg_otio.constants import _TC2FRAME_ABSOLUTE_MODE, _TC2FRAME_AUTOMATIC_MODE, _TC2FRAME_RELATIVE_MODE


class TestCutClip(unittest.TestCase):

    def setUp(self):
        """
        Setup the tests suite.
        """
        sg_settings = SGSettings()
        sg_settings.reset_to_defaults()
        self._edls_dir = os.path.join(os.path.dirname(__file__), "resources", "edls")

    def test_clip_name(self):
        """
        Test that the name does come from the reel name if available,
        otherwise it defaults to the clip name.
        """
        clip = SGCutClip(
            otio.schema.Clip(
                name="test_clip",
                source_range=TimeRange(
                    RationalTime(0, 24),
                    RationalTime(0, 24),
                )
            )
        )
        self.assertEqual(clip.name, "test_clip")
        edl = """
            TITLE:   OTIO_TEST
            FCM: NON-DROP FRAME

            001  clip_reel_name V     C        00:00:00:00 00:00:01:00 01:00:00:00 01:00:01:00
            * FROM CLIP NAME: clip_name
         """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        edl_clip = list(timeline.tracks[0].find_clips())[0]
        clip = SGCutClip(edl_clip)
        self.assertEqual(clip.name, "clip_reel_name")

    def test_shot_name(self):
        """
        Test that the shot name is properly extracted in different scenarios.
        """
        edl = """
            001  reel_name V     C        00:00:00:00 00:00:01:00 01:00:00:00 01:00:01:00
            * LOC: 01:00:00:12 YELLOW  shot_001
            * FROM CLIP NAME: clip_1
            * COMMENT: shot_002
            * shot_003
            002  reel_name V     C        00:00:00:00 00:00:01:00 01:00:01:00 01:00:02:00
            * FROM CLIP NAME: clip_1
            * COMMENT: shot_002
            * shot_003
            003  reel_name V     C        00:00:00:00 00:00:01:00 01:00:02:00 01:00:03:00
            * LOC: 01:00:00:12 YELLOW
            004  reel_name V     C        00:00:00:00 00:00:01:00 01:00:03:00 01:00:04:00
            * LOC: 01:00:00:12 YELLOW
            * LOC: 01:00:00:12 YELLOW  shot_004
        """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        edl_clip = list(timeline.tracks[0].find_clips())[0]
        # Set use reel names to True to see it does not affect the outcome.
        sg_settings = SGSettings()
        sg_settings.use_clip_names_for_shot_names = True
        clip = SGCutClip(
            edl_clip
        )
        # Locators and comments present, locator is used.
        self.assertEqual(clip.shot_name, "shot_001")

        # Without a locator. Comment starting with COMMENT: is used.
        edl_clip = list(timeline.tracks[0].find_clips())[1]
        clip = SGCutClip(
            edl_clip
        )
        clip._shot_name = compute_clip_shot_name(clip)
        self.assertEqual(clip.shot_name, "shot_002")

        # Remove the comment starting with COMMENT:. The bare comment is used.
        clip.metadata["cmx_3600"]["comments"].remove("COMMENT: shot_002")
        clip._shot_name = compute_clip_shot_name(clip)
        self.assertEqual(clip.shot_name, "shot_003")

        # Remove the comments. We set use_clip_names_for_shot_names to True,
        # so we should get the reel name.
        clip.metadata["cmx_3600"]["comments"] = []
        clip._shot_name = compute_clip_shot_name(clip)
        self.assertEqual(clip.shot_name, "reel_name")

        # Set use_clip_names_for_shot_names to False, so we should get None.
        sg_settings.use_clip_names_for_shot_names = False
        clip._shot_name = compute_clip_shot_name(clip)
        self.assertEqual(clip.shot_name, None)

        # Using reel names and a regex, the regex is used to find the first matching group.
        sg_settings.use_clip_names_for_shot_names = True
        sg_settings.clip_name_shot_regexp = r"(\w+)_(\w+)"
        clip._shot_name = compute_clip_shot_name(clip)
        self.assertEqual(clip.shot_name, "reel")

        # If there is some SG meta data and a Shot code it should be used
        clip.metadata["sg"] = {
            "type": "CutItem",
            "id": 123456,
            "shot": {"code": "shot_from_SG"}
        }
        clip._shot_name = compute_clip_shot_name(clip)
        self.assertEqual(clip.shot_name, "shot_from_SG")

        # A locator with an empty name.
        sg_settings.use_clip_names_for_shot_names = False
        edl_clip = list(timeline.tracks[0].find_clips())[2]
        clip = SGCutClip(
            edl_clip
        )
        clip._shot_name = compute_clip_shot_name(clip)
        self.assertIsNone(clip.shot_name)

        # Two locators, the first one has an empty name, the second one has a name.
        edl_clip = list(timeline.tracks[0].find_clips())[3]
        clip = SGCutClip(
            edl_clip
        )
        clip._shot_name = compute_clip_shot_name(clip)
        self.assertEqual(clip.shot_name, "shot_004")

    def test_clip_values(self):
        """
        Test that the clip values are correct.
        """
        edl = """
            TITLE:   OTIO_TEST
            FCM: NON-DROP FRAME

            001  reel_1 V     C        01:00:00:00 01:00:02:00 02:00:00:00 02:00:01:00
            M2   reel_1       048.0    01:00:00:00
            * FROM CLIP NAME: clip_1
            * COMMENT: shot_001

            002  reel_2 V     C        00:00:00:00 00:00:01:00 02:00:01:00 02:00:02:00
            * FROM CLIP NAME: clip_1
            * COMMENT: shot_002
        """
        # set non_default head_in, head_duration, tail_duration
        # to show that the results are still consistent.
        sg_settings = SGSettings()
        sg_settings.default_head_in = 555
        sg_settings.default_head_duration = 10
        sg_settings.default_tail_duration = 20
        edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        video_track = edl_timeline.tracks[0]
        clips = [SGCutClip(c, index=i + 1) for i, c in enumerate(video_track.find_clips())]
        self.assertEqual(len(clips), 2)
        clip_1 = clips[0]
        # There's a retime, so the clip is actually 2 * 0.5 seconds long.
        self.assertEqual(clip_1.duration().to_frames(), 24)
        self.assertEqual(clip_1.visible_duration.to_frames(), 48)
        self.assertEqual(clip_1.source_in.to_timecode(), "01:00:00:00")
        self.assertEqual(clip_1.source_out.to_timecode(), "01:00:02:00")
        self.assertEqual(clip_1.cut_in.to_frames(), sg_settings.default_head_in + sg_settings.default_head_duration)
        self.assertEqual(clip_1.cut_out.to_frames(), clip_1.cut_in.to_frames() + 48 - 1)
        self.assertEqual(clip_1.record_in.to_timecode(), "02:00:00:00")
        self.assertEqual(clip_1.record_out.to_timecode(), "02:00:01:00")
        self.assertEqual(clip_1.edit_in.to_frames(), 1)
        self.assertEqual(clip_1.edit_out.to_frames(), 24)
        self.assertTrue(clip_1.has_retime)
        self.assertEqual(clip_1.retime_str, "LinearTimeWarp (time scalar: 2.0)")
        self.assertTrue(not clip_1.has_effects)
        self.assertEqual(clip_1.effects_str, "")
        self.assertRegex(
            clip_1.source_info,
            r"001\s+reel_1\s+V\s+C\s+01:00:00:00 01:00:02:00 02:00:00:00 02:00:01:00"
        )

        clip_2 = clips[1]
        self.assertEqual(clip_2.duration().to_frames(), 24)
        self.assertEqual(clip_2.visible_duration.to_frames(), 24)
        self.assertEqual(clip_2.source_in.to_timecode(), "00:00:00:00")
        self.assertEqual(clip_2.source_out.to_timecode(), "00:00:01:00")
        self.assertEqual(clip_2.cut_in.to_frames(), sg_settings.default_head_in + sg_settings.default_head_duration)
        self.assertEqual(clip_2.cut_out.to_frames(), clip_2.cut_in.to_frames() + 24 - 1)
        self.assertEqual(clip_2.record_in.to_timecode(), "02:00:01:00")
        self.assertEqual(clip_2.record_out.to_timecode(), "02:00:02:00")
        self.assertEqual(clip_2.edit_in.to_frames(), 25)
        self.assertEqual(clip_2.edit_out.to_frames(), 48)
        self.assertTrue(not clip_2.has_retime)
        self.assertEqual(clip_2.retime_str, "")
        self.assertRegex(
            clip_2.source_info,
            r"002\s+reel_2\s+V\s+C\s+00:00:00:00 00:00:01:00 02:00:01:00 02:00:02:00"
        )

    def test_clip_values_with_transitions(self):
        """
        Test that the clip values for clips before/after transitions are correct.
        :return:
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
        # set non_default head_in, head_duration, tail_duration
        # to show that the results are still consistent.
        sg_settings = SGSettings()
        sg_settings.timecode_in_to_frame_mapping = _TC2FRAME_AUTOMATIC_MODE
        sg_settings.use_clip_names_for_shot_names = False
        sg_settings.default_head_in = 555
        sg_settings.default_head_duration = 10
        sg_settings.default_tail_duration = 20
        edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        video_track = edl_timeline.tracks[0]
        clips = [SGCutClip(c) for c in video_track.find_clips()]
        self.assertEqual(len(clips), 3)
        for clip in clips:
            self.assertIsNotNone(clip.shot_name)
        clip_1 = clips[0]
        # The normal duration is 24 frames
        self.assertEqual(clip_1.duration().to_frames(), 24)
        # The visible duration takes into account the whole duration of the transition
        self.assertEqual(clip_1.visible_duration.to_frames(), 48)
        # All out values take into account the transition time
        self.assertEqual(clip_1.source_in.to_timecode(), "01:00:00:00")
        self.assertEqual(clip_1.source_out.to_timecode(), "01:00:02:00")
        self.assertEqual(clip_1.cut_in.to_frames(), sg_settings.default_head_in + sg_settings.default_head_duration)
        self.assertEqual(clip_1.cut_out.to_frames(), clip_1.cut_in.to_frames() + 48 - 1)
        self.assertEqual(clip_1.record_in.to_timecode(), "01:00:00:00")
        self.assertEqual(clip_1.record_out.to_timecode(), "01:00:02:00")
        self.assertEqual(clip_1.edit_in.to_frames(), 1)
        self.assertEqual(clip_1.edit_out.to_frames(), 48)
        self.assertTrue(clip_1.has_effects)
        self.assertEqual(clip_1.effects_str, "After: SMPTE_Dissolve (24 frames)")
        self.assertEqual(clip_1.shot_name, "shot_001")
        # This is the transition clip. It has a duration of 1 second.
        clip_2 = clips[1]
        # The duration is the whole duration of the transition
        self.assertEqual(clip_2.duration().to_frames(), 24)
        # The visible duration takes into account the whole duration of the transition
        self.assertEqual(clip_2.visible_duration.to_frames(), 24)
        self.assertEqual(clip_2.source_in.to_timecode(), "01:00:01:00")
        self.assertEqual(clip_2.source_out.to_timecode(), "01:00:02:00")
        self.assertEqual(clip_2.cut_in.to_frames(), sg_settings.default_head_in + sg_settings.default_head_duration)
        self.assertEqual(clip_2.cut_out.to_frames(), clip_2.cut_in.to_frames() + 24 - 1)
        self.assertEqual(clip_2.record_in.to_timecode(), "01:00:01:00")
        self.assertEqual(clip_2.record_out.to_timecode(), "01:00:02:00")
        # Note it starts at 25, whereas previous clip ended at 48.
        self.assertEqual(clip_2.edit_in.to_frames(), 25)
        self.assertEqual(clip_2.edit_out.to_frames(), 48)
        self.assertTrue(clip_2.has_effects)
        self.assertEqual(clip_2.effects_str, "Before: SMPTE_Dissolve (0 frames)")

    def test_clip_values_with_transitions_from_file(self):
        """
        Test that transitions are properly computed from an example EDL file.
        """
        edl_filepath = os.path.join(self._edls_dir, "raphe_temp1_rfe_R01_v01_TRANSITIONS.edl")
        edl_timeline = otio.adapters.read_from_file(edl_filepath, adapter_name="cmx_3600")
        video_track = edl_timeline.tracks[0]
        clip = list(video_track.find_clips())[1]
        cut_clip = SGCutClip(clip)
        self.assertEqual(cut_clip.source_in.to_timecode(), "00:59:59:09")
        self.assertEqual(cut_clip.source_out.to_timecode(), "01:00:05:15")
        self.assertEqual(cut_clip.record_in.to_timecode(), "01:00:07:23")
        self.assertEqual(cut_clip.record_out.to_timecode(), "01:00:14:05")
        # The normal duration is 120 frames
        self.assertEqual(cut_clip.duration().to_frames(), 120)
        # The visible duration takes into account the whole duration of the transition
        self.assertEqual(cut_clip.visible_duration.to_frames(), 150)
        self.assertTrue(cut_clip.has_effects)
        self.assertEqual(cut_clip.effects_str, "Before: SMPTE_Dissolve (0 frames)\nAfter: SMPTE_Dissolve (30 frames)")

    def test_repeated_shots(self):
        """
        Test that when a shot has more than one clip, the clip values
        are correct.
        """
        edl = """
            TITLE:   CUT_CREATE_TEST

            001  ABC0100 V     C        01:00:01:00 01:00:10:00 01:00:00:00 01:00:09:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
            002  ABC0200 V     C        01:00:02:00 01:00:05:00 01:00:09:00 01:00:12:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
            003  ABC0200 V     C        01:00:00:00 01:00:04:00 01:00:12:00 01:00:16:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
        """
        # set multiple head_in, head_duration, tail_duration
        # to show that the results are still consistent.
        values = [
            [1001, 8, 8],
            [555, 10, 20],
            [666, 25, 50],
        ]
        sg_settings = SGSettings()
        for head_in, head_duration, tail_duration in values:
            sg_settings.default_head_in = head_in
            sg_settings.default_head_duration = head_duration
            sg_settings.default_tail_duration = tail_duration
            edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600", rate=30)
            track = edl_timeline.tracks[0]
            clip_group = ClipGroup("shot_001")
            i = 1
            for clip in track.find_clips():
                clip_group.add_clip(SGCutClip(clip, index=i))
                i += 1
            self.assertEqual(clip_group.index, 3)  # First clip is the last starting at 01:00:00:00
            # All clips are considered parts of a single big clip, so head in
            # tail out values are identical for all clips, but the cut in and
            # cut out values differ, with different handle durations.
            tail_out = RationalTime(head_in + head_duration + 10 * 30 + tail_duration - 1, 30)
            for clip in clip_group.clips:
                self.assertEqual(clip.group, clip_group)
                self.assertEqual(clip.head_in.to_frames(), clip_group.head_in.to_frames())
                self.assertEqual(clip.tail_out.to_frames(), clip_group.tail_out.to_frames())
                self.assertEqual(
                    clip.cut_in - clip.head_duration,
                    clip.head_in,
                )
                self.assertEqual(clip.cut_out + clip.tail_duration, tail_out)

    def test_in_out_values(self):
        """
        Test we get the expected frame values depending on mapping mode
        """
        sg_settings = SGSettings()
        sg_settings.timecode_in_to_frame_mapping_mode = _TC2FRAME_AUTOMATIC_MODE
        clip = SGCutClip(
            otio.schema.Clip(
                name="test_clip",
                source_range=TimeRange(
                    RationalTime(0, 24),
                    RationalTime(10, 24),  # exclusive, 10 frames.
                )
            )
        )
        self.assertEqual(clip.head_in.to_frames(), sg_settings.default_head_in)
        self.assertEqual(clip.cut_in.to_frames(), sg_settings.default_head_in + sg_settings.default_head_duration)
        self.assertEqual(clip.cut_out.to_frames(), clip.cut_in.to_frames() + 10 - 1)
        self.assertEqual(clip.tail_in.to_frames(), clip.cut_out.to_frames() + 1)
        self.assertEqual(clip.tail_out.to_frames(), clip.tail_in.to_frames() + sg_settings.default_tail_duration - 1)
        # If a Shot is associated with the Clip, and it has a head_in value, it
        # is always used
        sg_shot = {
            "type": "Shot",
            "id": -1,
            "code": "Totally Faked",
            "sg_head_in": 123456,
            "sg_tail_out": 123466
        }
        clip.sg_shot = sg_shot
        self.assertEqual(clip.head_in.to_frames(), sg_shot["sg_head_in"])
        self.assertEqual(clip.tail_out.to_frames(), sg_shot["sg_tail_out"])

        sg_settings.timecode_in_to_frame_mapping_mode = _TC2FRAME_ABSOLUTE_MODE
        clip.sg_shot = None  # Unsetting the Shot forces a recompute
        # In absolute mode the source range is used directly
        self.assertEqual(clip.head_in.to_frames(), -8)
        self.assertEqual(clip.head_duration.to_frames(), sg_settings.default_head_duration)
        self.assertEqual(clip.cut_in.to_frames(), 0)
        self.assertEqual(clip.cut_out.to_frames(), 9)
        self.assertEqual(clip.tail_in.to_frames(), 9 + 1)
        self.assertEqual(clip.tail_out.to_frames(), clip.tail_in.to_frames() + sg_settings.default_tail_duration - 1)

        sg_settings.timecode_in_to_frame_mapping_mode = _TC2FRAME_RELATIVE_MODE
        sg_settings.timecode_in_to_frame_relative_mapping = ("00:00:00:00", 20000)
        clip.sg_shot = None  # Unsetting the Shot forces a recompute
        self.assertEqual(clip.compute_cut_in().to_frames(), 20000)
        self.assertEqual(clip.head_in.to_frames(), 20000 - 8)
        self.assertEqual(clip.head_duration.to_frames(), sg_settings.default_head_duration)
        self.assertEqual(clip.cut_in.to_frames(), 20000)
        self.assertEqual(clip.cut_out.to_frames(), 20000 + 9)
        self.assertEqual(clip.tail_in.to_frames(), 20000 + 9 + 1)
        self.assertEqual(clip.tail_out.to_frames(), clip.tail_in.to_frames() + sg_settings.default_tail_duration - 1)

        # Switch to AUTOMATIC mode, and make sure the values are recomputed
        # correctly. Do not set a cut item for now.
        sg_settings.timecode_in_to_frame_mapping_mode = _TC2FRAME_AUTOMATIC_MODE
        sg_settings.default_head_duration = 54
        sg_settings.default_head_in = 123
        clip.sg_shot = None  # Unsetting the Shot forces a recompute
        self.assertEqual(clip.head_in.to_frames(), clip.head_in.to_frames())
        self.assertEqual(clip.compute_cut_in().to_frames(), clip.head_in.to_frames() + sg_settings.default_head_duration)
        self.assertEqual(clip.head_duration.to_frames(), sg_settings.default_head_duration)
        self.assertEqual(clip.cut_in.to_frames(), clip.head_in.to_frames() + sg_settings.default_head_duration)
        self.assertEqual(clip.cut_out.to_frames(), clip.cut_in.to_frames() + clip.duration().to_frames() - 1)
        self.assertEqual(clip.tail_in.to_frames(), clip.cut_out.to_frames() + 1)
        self.assertEqual(clip.tail_out.to_frames(), clip.tail_in.to_frames() + sg_settings.default_tail_duration - 1)

        # Again in AUTOMATIC mode, but this time with an SG cut item
        # The value from it should be used as a base for an offset
        clip.metadata["sg"] = {
            "type": "CutItem",
            "id": -1,
            "code": "Totally Faked",
            "cut_item_in": 3002,
            "timecode_cut_item_in_text": "00:00:00:02",
        }
        clip.sg_shot = None  # Unsetting the Shot forces a recompute
        # The clip timecode in is "00:00:00:00", so the cut in will be 3002 - 2
        self.assertEqual(clip.compute_cut_in().to_frames(), 3000)
        # The head in should be the default head in
        self.assertEqual(clip.head_in.to_frames(), sg_settings.default_head_in)
        self.assertEqual(clip.head_duration, clip.cut_in - clip.head_in)
        self.assertEqual(clip.cut_in.to_frames(), 3000)
        self.assertEqual(clip.cut_out.to_frames(), 3000 + 9)
        self.assertEqual(clip.tail_in.to_frames(), 3000 + 9 + 1)
        self.assertEqual(clip.tail_out.to_frames(), clip.tail_in.to_frames() + sg_settings.default_tail_duration - 1)

    def test_sg_values(self):
        """
        Test retrieving various SG properties
        """
        clip = SGCutClip(
            otio.schema.Clip(
                name="test_clip",
                source_range=TimeRange(
                    RationalTime(0, 24),
                    RationalTime(10, 24),  # exclusive, 10 frames.
                )
            )
        )
        self.assertIsNone(clip.sg_shot)
        self.assertIsNone(clip.sg_cut_item)
        clip.sg_shot = {
            "type": "Shot",
            "id": -1,
            "code": "Totally Faked",
            "sg_head_in": 123456,
            "sg_tail_out": 123466
        }
        self.assertIsNotNone(clip.sg_shot)
        self.assertEqual(clip.sg_shot["id"], -1)
        self.assertEqual(clip.sg_shot["code"], "Totally Faked")
        self.assertIsNone(clip.sg_cut_item)
        clip.metadata["sg"] = {
            "type": "CutItem",
            "id": -1,
            "code": "Totally Faked Cut Item",
            "cut_item_in": 3002,
            "timecode_cut_item_in_text": "00:00:00:02",
        }
        self.assertEqual(clip.sg_shot["code"], "Totally Faked")
        self.assertIsNotNone(clip.sg_cut_item)
        self.assertEqual(clip.sg_cut_item["code"], "Totally Faked Cut Item")
        clip.sg_shot = None
        self.assertIsNone(clip.sg_shot)
        self.assertIsNotNone(clip.sg_cut_item)
        self.assertEqual(clip.sg_cut_item["code"], "Totally Faked Cut Item")


if __name__ == '__main__':
    unittest.main()
