# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import unittest

import opentimelineio as otio
from opentimelineio.opentime import TimeRange, RationalTime

from sg_otio.clip_group import ClipGroup
from sg_otio.sg_settings import SGSettings
from sg_otio.track_diff import SGCutDiffGroup
from sg_otio.cut_diff import SGCutDiff
from sg_otio.constants import _DIFF_TYPES


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
            * COMMENT: SHOT_001
            002  clip_2 V     C        01:00:02:00 01:00:05:00 01:00:09:00 01:00:12:00
            * FROM CLIP NAME: shot_002_v001
            * COMMENT: shot_002
            003  clip_3 V     C        01:00:00:00 01:00:04:00 01:00:12:00 01:00:16:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
            004  clip_4 V     C        01:00:00:00 01:00:01:00 01:00:16:00 01:00:17:00
            * FROM CLIP NAME: shot_002_v001
            * COMMENT: SHOT_002
            005  clip_5 V     C        01:00:00:00 01:00:01:00 01:00:17:00 01:00:18:00
            * FROM CLIP NAME: shot_003_v001
            * COMMENT: shot_003
        """

        edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        track = edl_timeline.tracks[0]
        shot_groups = ClipGroup.groups_from_track(track)
        self.assertEqual(set(shot_groups.keys()), {"shot_001", "shot_002", "shot_003"})
        self.assertIsNone(shot_groups["shot_001"].sg_shot)
        self.assertEqual(shot_groups["shot_001"].name, "SHOT_001")  # First entry is upper case
        shot_001_clips = shot_groups["shot_001"].clips
        self.assertEqual({clip.name for clip in shot_001_clips}, {"clip_1", "clip_3"})
        self.assertEqual(shot_groups["shot_002"].name, "shot_002")  # First entry is lower case
        shot_002_clips = shot_groups["shot_002"].clips
        self.assertEqual({clip.name for clip in shot_002_clips}, {"clip_2", "clip_4"})
        self.assertEqual(shot_groups["shot_003"].name, "shot_003")  # Single entry is lower case
        shot_003_clips = shot_groups["shot_003"].clips
        self.assertEqual({clip.name for clip in shot_003_clips}, {"clip_5"})

        # Test setting Shots
        sg_shot = {
            "type": "Shot",
            "id": 1,
        }
        for clip in shot_groups["shot_001"].clips:
            self.assertEqual(clip.sg_shot, None)
            with self.assertRaises(ValueError) as cm:
                clip.sg_shot = sg_shot
            self.assertIn(
                "Can't change the SG Shot value controlled by",
                str(cm.exception)
            )
            # This shouldn't cause any problem
            clip.sg_shot = shot_groups["shot_001"].sg_shot
        shot_groups["shot_001"].sg_shot = sg_shot
        for clip in shot_groups["shot_001"].clips:
            self.assertEqual(clip.sg_shot, sg_shot)
            with self.assertRaises(ValueError) as cm:
                clip.sg_shot = None
            self.assertIn(
                "Can't change the SG Shot value controlled by",
                str(cm.exception)
            )
            with self.assertRaises(ValueError) as cm:
                clip.sg_shot = {"type": "Shot", "id": 10234}
            self.assertIn(
                "Can't change the SG Shot value controlled by",
                str(cm.exception)
            )
            # This shouldn't cause any problem
            clip.sg_shot = shot_groups["shot_001"].sg_shot

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
            * COMMENT: SHOT_001
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
            edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
            track = edl_timeline.tracks[0]
            shot_groups = ClipGroup.groups_from_track(track)

            shot = shot_groups["shot_001"]
            # The case is taken from the first entry
            self.assertEqual(shot.name, "shot_001")
            self.assertEqual(shot.index, 3)  # first clip is the last starting at 01:00:00:00
            self.assertEqual(shot.cut_in.to_frames(), head_in + head_duration)
            self.assertEqual(shot.cut_out.to_frames(), head_in + head_duration + 10 * 24 - 1)
            self.assertEqual(shot.head_in.to_frames(), head_in)
            self.assertEqual(shot.head_out.to_frames(), head_in + head_duration - 1)
            self.assertEqual(shot.tail_in.to_frames(), head_in + head_duration + 10 * 24)
            self.assertEqual(
                shot.tail_out.to_frames(),
                head_in + head_duration + 10 * 24 + tail_duration - 1
            )
            self.assertEqual(shot.tail_duration.to_frames(), tail_duration)
            self.assertTrue(not shot.has_effects)
            self.assertTrue(not shot.has_retime)
            self.assertEqual(shot.duration.to_frames(), 10 * 24)
            self.assertEqual(shot.working_duration.to_frames(), head_duration + 10 * 24 + tail_duration - 1)
            clips = list(shot.clips)
            self.assertEqual(len(clips), 2)
            self.assertEqual(clips[0].cut_in.to_frames(), head_in + head_duration + 24)
            self.assertEqual(clips[1].cut_in.to_frames(), head_in + head_duration)

    def test_diff_values(self):
        """
        Test SGCutDiff values when in a group.
        """
        cut_clips = []
        track = otio.schema.Track()
        for i in range(2):
            clip = otio.schema.Clip(
                name="test_clip_%d" % i,
                source_range=TimeRange(
                    RationalTime(10, 24),
                    RationalTime(10, 24),  # duration, 10 frames.
                ),
            )
            track.append(clip)
            cut_clips.append(SGCutDiff(clip=clip, index=i + 1))
        group = SGCutDiffGroup("totally_faked")
        group.add_clip(cut_clips[0])
        self.assertEqual(group.name, cut_clips[0].shot_name)
        self.assertEqual(cut_clips[0].diff_type, _DIFF_TYPES.NEW)
        sg_shot = {
            "type": "Shot",
            "id": 666,
            "code": "Evil Shot",
            "sg_status_list": {"code": "ip", "id": -1}
        }
        group.sg_shot = sg_shot
        self.assertEqual(cut_clips[0].sg_shot, sg_shot)
        self.assertEqual(cut_clips[0].shot_name, "Evil Shot")
        self.assertEqual(cut_clips[0].diff_type, _DIFF_TYPES.NEW_IN_CUT)

        self.assertEqual(cut_clips[1].diff_type, _DIFF_TYPES.NO_LINK)
        self.assertIsNone(cut_clips[1].shot_name)
        group.add_clip(cut_clips[1])
        self.assertEqual(cut_clips[1].sg_shot, sg_shot)
        self.assertEqual(cut_clips[1].shot_name, "Evil Shot")
        self.assertEqual(cut_clips[1].diff_type, _DIFF_TYPES.NEW_IN_CUT)


if __name__ == '__main__':
    unittest.main()
