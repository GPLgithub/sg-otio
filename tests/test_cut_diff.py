# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

from .python.sg_test import SGBaseTest

import opentimelineio as otio
from sg_otio.track_diff import SGTrackDiff


class TestCutDiff(SGBaseTest):
    """
    Test related to computing differences between two Cuts
    """

    def test_loading_edl(self):
        """
        Test loading an EDL
        """
        edl = """
            TITLE:   CUT_DIFF_TEST

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
        edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        track = edl_timeline.tracks[0]
        track_diff = SGTrackDiff(
            self.mock_sg,
            self.mock_project,
            new_track=track,
        )
        # Three clips
        self.assertEqual(len(track_diff), 3)
        # Check Shot names
        self.assertEqual([x for x in track_diff], ["shot_001", "shot_002"])
        # No Shot in SG
        for shot_name, cut_group in track_diff.items():
            self.assertIsNone(cut_group.sg_shot)
            for cut_diff in cut_group.clips:
                self.assertEqual(cut_diff.sg_shot, cut_group.sg_shot)

        sg_shots = [
            {"type": "Shot", "code": "shot_001", "project": self.mock_project, "id": 1},
            {"type": "Shot", "code": "shot_002", "project": self.mock_project, "id": 2}
        ]
        by_name = {
            "shot_001": sg_shots[0],
            "shot_002": sg_shots[1],
        }
        self.add_to_sg_mock_db(sg_shots)
        try:
            track_diff = SGTrackDiff(
                self.mock_sg,
                self.mock_project,
                new_track=track,
            )
            for shot_name, cut_group in track_diff.items():
                self.assertEqual(cut_group.sg_shot["id"], by_name[shot_name]["id"])
                self.assertEqual(cut_group.sg_shot["type"], by_name[shot_name]["type"])
                for cut_diff in cut_group.clips:
                    self.assertEqual(cut_diff.sg_shot, cut_group.sg_shot)

        finally:
            for sg_shot in sg_shots:
                self.mock_sg.delete(sg_shot["type"], sg_shot["id"])
