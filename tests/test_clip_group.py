# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import unittest

import opentimelineio as otio
from sg_otio.clip_group import ClipGroup
from sg_otio.sg_settings import SGSettings


class TestClipGroup(unittest.TestCase):

    def setUp(self):
        """
        Setup the tests suite.
        """
        sg_settings = SGSettings()
        sg_settings.reset_to_defaults()

    def test_shot_clips(self):
        """
        Test that when loading a timeline, it detects the shots belonging to the tracks,
        and that the shots have the proper clips in them.
        """
        edl = """
            TITLE:   CUT_CREATE_TEST

            001  clip_1 V     C        01:00:01:00 01:00:10:00 01:00:00:00 01:00:09:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
            002  clip_2 V     C        01:00:02:00 01:00:05:00 01:00:09:00 01:00:12:00
            * FROM CLIP NAME: shot_002_v001
            * COMMENT: shot_002
            003  clip_3 V     C        01:00:00:00 01:00:04:00 01:00:12:00 01:00:16:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
            004  clip_4 V     C        01:00:00:00 01:00:01:00 01:00:16:00 01:00:17:00
            * FROM CLIP NAME: shot_002_v001
            * COMMENT: shot_002
            005  clip_5 V     C        01:00:00:00 01:00:01:00 01:00:17:00 01:00:18:00
            * FROM CLIP NAME: shot_003_v001
            * COMMENT: shot_003
        """

        edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        track = edl_timeline.tracks[0]
        shot_groups = ClipGroup.groups_from_track(track)
        self.assertEqual(set(shot_groups.keys()), {"shot_001", "shot_002", "shot_003"})
        shot_001_clips = shot_groups["shot_001"].clips
        self.assertEqual({clip.name for clip in shot_001_clips}, {"clip_1", "clip_3"})
        shot_002_clips = shot_groups["shot_002"].clips
        self.assertEqual({clip.name for clip in shot_002_clips}, {"clip_2", "clip_4"})
        shot_003_clips = shot_groups["shot_003"].clips
        self.assertEqual({clip.name for clip in shot_003_clips}, {"clip_5"})

    def test_group_values(self):
        """
        Test that the group values provided are correct.
        """
        edl = """
            TITLE:   CUT_CREATE_TEST

            001  clip_1 V     C        01:00:01:00 01:00:10:00 01:00:00:00 01:00:09:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
            002  clip_2 V     C        01:00:02:00 01:00:05:00 01:00:09:00 01:00:12:00
            * FROM CLIP NAME: shot_002_v001
            * COMMENT: shot_002
            003  clip_3 V     C        01:00:00:00 01:00:04:00 01:00:12:00 01:00:16:00
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
            edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
            track = edl_timeline.tracks[0]
            shot_groups = ClipGroup.groups_from_track(track)

            shot = shot_groups["shot_001"]
            self.assertEqual(shot.name, "shot_001")
            self.assertEqual(shot.index, 3)  # first clip is the last starting at 01:00:00:00
            self.assertEqual(shot.cut_in.to_frames(), head_in + head_in_duration)
            self.assertEqual(shot.cut_out.to_frames(), head_in + head_in_duration + 10 * 24 - 1)
            self.assertEqual(shot.head_in.to_frames(), head_in)
            self.assertEqual(shot.head_out.to_frames(), head_in + head_in_duration - 1)
            self.assertEqual(shot.tail_in.to_frames(), head_in + head_in_duration + 10 * 24)
            self.assertEqual(
                shot.tail_out.to_frames(),
                head_in + head_in_duration + 10 * 24 + tail_out_duration - 1
            )
            self.assertEqual(shot.tail_duration.to_frames(), tail_out_duration)
            self.assertTrue(not shot.has_effects)
            self.assertTrue(not shot.has_retime)
            self.assertEqual(shot.duration.to_frames(), 10 * 24)
            self.assertEqual(shot.working_duration.to_frames(), head_in_duration + 10 * 24 + tail_out_duration - 1)


if __name__ == '__main__':
    unittest.main()
