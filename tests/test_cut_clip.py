# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#

import unittest

import opentimelineio as otio
from opentimelineio.opentime import TimeRange, RationalTime

from sg_otio.cut_clip import CutClip
from sg_otio.cut_track import CutTrack
from sg_otio.sg_settings import SGSettings
from sg_otio.utils import compute_clip_shot_name


class TestCutClip(unittest.TestCase):

    def setUp(self):
        """
        Setup the tests suite.
        """
        sg_settings = SGSettings()
        sg_settings.reset_to_defaults()

    def test_no_shared_pointers(self):
        """
        Test that when we create a CutClip from an OTIO clip,
        we don't have shared pointers between the two.
        """
        clip = otio.schema.Clip(name="foo")
        # The media_reference is a good case to show no shared pointers.
        clip.media_reference = otio.schema.ExternalReference(
            target_url="https://example.com/foo.mp4",
            available_range=otio.opentime.TimeRange(
                otio.opentime.RationalTime(0, 24),
                otio.opentime.RationalTime(5, 24)
            )
        )
        clip.media_reference.metadata["foo"] = "bar"
        cut_clip = CutClip.from_clip(clip)
        self.assertFalse(cut_clip.media_reference.is_missing_reference)
        self.assertEqual(cut_clip.media_reference.metadata, {"foo": "bar"})
        # Now let's change the cut_clip and make sure the original clip does not
        # change
        cut_clip.name = "bar"
        cut_clip.media_reference = otio.schema.MissingReference()
        cut_clip.media_reference.metadata["bar"] = "baz"
        self.assertEqual(clip.name, "foo")
        self.assertFalse(clip.media_reference.is_missing_reference)
        self.assertEqual(clip.media_reference.target_url, "https://example.com/foo.mp4")
        self.assertEqual(clip.media_reference.metadata, {"foo": "bar"})

    def test_clip_name(self):
        """
        Test that the name does come from the reel name if available,
        otherwise it defaults to the clip name.
        """
        clip = CutClip(
            name="test_clip",
            source_range=TimeRange(
                RationalTime(0, 24),
                RationalTime(0, 24),
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
        edl_clip = list(timeline.tracks[0].each_clip())[0]
        clip = CutClip.from_clip(edl_clip)
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
        """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        edl_clip = list(timeline.tracks[0].each_clip())[0]
        # Set use reel names to True to see it does not affect the outcome.
        sg_settings = SGSettings()
        sg_settings.use_clip_names_for_shot_names = True
        clip = CutClip.from_clip(
            edl_clip
        )
        # Locators and comments present, locator is used.
        self.assertEqual(clip.shot_name, "shot_001")

        # Let's remove the locator. Comment starting with COMMENT: is used.
        clip.markers = []
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
        # set non_default head_in, head_in_duration, tail_out_duration
        # to show that the results are still consistent.
        sg_settings = SGSettings()
        sg_settings.default_head_in = 555
        sg_settings.default_head_in_duration = 10
        sg_settings.default_tail_out_duration = 20
        edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        timeline = CutTrack.from_timeline(
            edl_timeline,
        )
        clips = list(timeline.tracks[0].each_clip())
        self.assertEqual(len(clips), 2)
        clip_1 = clips[0]
        # There's a retime, so the clip is actually 2 * 0.5 seconds long.
        self.assertEqual(clip_1.duration().to_frames(), 24)
        self.assertEqual(clip_1.visible_duration.to_frames(), 48)
        self.assertEqual(clip_1.source_in.to_timecode(), "01:00:00:00")
        self.assertEqual(clip_1.source_out.to_timecode(), "01:00:02:00")
        self.assertEqual(clip_1.cut_in.to_frames(), sg_settings.default_head_in + sg_settings.default_head_in_duration)
        self.assertEqual(clip_1.cut_out.to_frames(), clip_1.cut_in.to_frames() + 48 - 1)
        self.assertEqual(clip_1.record_in.to_timecode(), "02:00:00:00")
        self.assertEqual(clip_1.record_out.to_timecode(), "02:00:01:00")
        self.assertEqual(clip_1.edit_in.to_frames(), 1)
        self.assertEqual(clip_1.edit_out.to_frames(), 24)
        self.assertTrue(clip_1.has_retime)
        self.assertEqual(clip_1.retime_str, "LinearTimeWarp (time scalar: 2.0)")
        self.assertTrue(not clip_1.has_effects)
        self.assertEqual(clip_1.effects_str, "")

        clip_2 = clips[1]
        self.assertEqual(clip_2.duration().to_frames(), 24)
        self.assertEqual(clip_2.visible_duration.to_frames(), 24)
        self.assertEqual(clip_2.source_in.to_timecode(), "00:00:00:00")
        self.assertEqual(clip_2.source_out.to_timecode(), "00:00:01:00")
        self.assertEqual(clip_2.cut_in.to_frames(), sg_settings.default_head_in + sg_settings.default_head_in_duration)
        self.assertEqual(clip_2.cut_out.to_frames(), clip_2.cut_in.to_frames() + 24 - 1)
        self.assertEqual(clip_2.record_in.to_timecode(), "02:00:01:00")
        self.assertEqual(clip_2.record_out.to_timecode(), "02:00:02:00")
        self.assertEqual(clip_2.edit_in.to_frames(), 25)
        self.assertEqual(clip_2.edit_out.to_frames(), 48)
        self.assertTrue(not clip_2.has_retime)
        self.assertEqual(clip_2.retime_str, "")

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
        # set non_default head_in, head_in_duration, tail_out_duration
        # to show that the results are still consistent.
        sg_settings = SGSettings()
        sg_settings.use_clip_names_for_shot_names = False
        sg_settings.default_head_in = 555
        sg_settings.default_head_in_duration = 10
        sg_settings.default_tail_out_duration = 20
        edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        timeline = CutTrack.from_timeline(
            edl_timeline,
        )
        clips = list(timeline.tracks[0].each_clip())
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
        self.assertEqual(clip_1.cut_in.to_frames(), sg_settings.default_head_in + sg_settings.default_head_in_duration)
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
        self.assertEqual(clip_2.cut_in.to_frames(), sg_settings.default_head_in + sg_settings.default_head_in_duration)
        self.assertEqual(clip_2.cut_out.to_frames(), clip_2.cut_in.to_frames() + 24 - 1)
        self.assertEqual(clip_2.record_in.to_timecode(), "01:00:01:00")
        self.assertEqual(clip_2.record_out.to_timecode(), "01:00:02:00")
        # Note it starts at 25, whereas previous clip ended at 48.
        self.assertEqual(clip_2.edit_in.to_frames(), 25)
        self.assertEqual(clip_2.edit_out.to_frames(), 48)
        self.assertTrue(clip_2.has_effects)
        self.assertEqual(clip_2.effects_str, "Before: SMPTE_Dissolve (0 frames)")

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
        # set multiple head_in, head_in_duration, tail_out_duration
        # to show that the results are still consistent.
        values = [
            [1001, 8, 8],
            [555, 10, 20],
            [666, 25, 50],
        ]
        sg_settings = SGSettings()
        for head_in, head_in_duration, tail_out_duration in values:
            sg_settings.default_head_in = head_in
            sg_settings.default_head_in_duration = head_in_duration
            sg_settings.default_tail_out_duration = tail_out_duration
            edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600", rate=30)
            timeline = CutTrack.from_timeline(
                edl_timeline,
            )
            track = timeline.tracks[0]
            # All we care about is to make sure that head_in_duration and tail_out_duration have been set in such
            # a way that cut_in - head_in_duration = head_in and cut_out + tail_out_duration = tail_out
            # The rest of the values are already tested in the other tests.
            # The duration of the source used is 10 seconds.
            tail_out = RationalTime(head_in + head_in_duration + 10 * 30 + tail_out_duration - 1, 30)
            for clip in track.shot_clips("shot_001"):
                self.assertEqual(
                    clip.cut_in - clip.head_in_duration,
                    clip.head_in,
                )
                self.assertEqual(clip.cut_out + clip.tail_out_duration, tail_out)


if __name__ == '__main__':
    unittest.main()
