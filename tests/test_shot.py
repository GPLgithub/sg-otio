# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#

import unittest

import opentimelineio as otio
from sg_otio import extended_timeline


class TestShot(unittest.TestCase):
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
            004  clip_5 V     C        01:00:00:00 01:00:01:00 01:00:17:00 01:00:18:00
            * FROM CLIP NAME: shot_003_v001
            * COMMENT: shot_003
        """

        edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        timeline = extended_timeline.from_timeline(
            edl_timeline
        )
        track = timeline.tracks[0]
        self.assertEqual(set(track.shot_names), {"shot_001", "shot_002", "shot_003"})
        shot_001_clips = track.shot_clips("shot_001")
        self.assertEqual({clip.name for clip in shot_001_clips}, {"clip_1", "clip_3"})
        shot_002_clips = track.shot_clips("shot_002")
        self.assertEqual({clip.name for clip in shot_002_clips}, {"clip_2", "clip_4"})
        shot_003_clips = track.shot_clips("shot_003")
        self.assertEqual({clip.name for clip in shot_003_clips}, {"clip_5"})

    def test_shot_values(self):
        """
        Test that the shot values provided are correct.
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
        for head_in, head_in_duration, tail_out_duration in values:
            edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
            timeline = extended_timeline.from_timeline(
                edl_timeline,
                head_in=head_in,
                head_in_duration=head_in_duration,
                tail_out_duration=tail_out_duration,
            )
            track = timeline.tracks[0]
            shot = track.shots_by_name["shot_001"]
            self.assertEqual(shot.name, "shot_001")
            self.assertEqual(shot.index, 1)
            self.assertEqual(shot.cut_in.to_frames(), head_in + head_in_duration)
            self.assertEqual(shot.cut_out.to_frames(), head_in + head_in_duration + 9 * 24 - 1)
            self.assertEqual(shot.head_in.to_frames(), head_in)
            self.assertEqual(shot.head_out.to_frames(), head_in + head_in_duration - 1)
            self.assertEqual(shot.tail_in.to_frames(), head_in + head_in_duration + 9 * 24)
            self.assertEqual(
                shot.tail_out.to_frames(),
                head_in + head_in_duration + 9 * 24 + tail_out_duration - 1
            )
            self.assertEqual(shot.tail_duration.to_frames(), tail_out_duration)
            self.assertTrue(not shot.has_effects)
            self.assertTrue(not shot.has_retime)
            self.assertEqual(shot.duration.to_frames(), 9 * 24)
            self.assertEqual(shot.working_duration.to_frames(), head_in_duration + 9 * 24 + tail_out_duration - 1)


if __name__ == '__main__':
    unittest.main()
