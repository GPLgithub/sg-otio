# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging
import shotgun_api3

from .python.sg_test import SGBaseTest

import opentimelineio as otio
from sg_otio.track_diff import SGTrackDiff
from sg_otio.utils import get_read_url, get_write_url
from sg_otio.constants import _DIFF_TYPES


try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock

logger = logging.getLogger(__name__)


class TestCutDiff(SGBaseTest):
    """
    Test related to computing differences between two Cuts
    """
    def setUp(self):
        super(TestCutDiff, self).setUp()
        self.mock_sequence = {
            "project": self.mock_project,
            "type": "Sequence",
            "code": "SEQ01",
            "id": 2,
            "sg_cut_order": 2
        }
        self.add_to_sg_mock_db(self.mock_sequence)
        self._SG_SEQ_URL = get_write_url(
            self.mock_sg.base_url,
            "Sequence",
            self.mock_sequence["id"],
            self._SESSION_TOKEN
        )

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
                self.assertIsNone(cut_diff.old_clip)
                self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.NEW)

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
                    self.assertIsNone(cut_diff.old_clip)
                    self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.NEW_IN_CUT)
                    if shot_name == "shot_001":
                        self.assertTrue(cut_diff.repeated)
                    else:
                        self.assertFalse(cut_diff.repeated)

        finally:
            for sg_shot in sg_shots:
                self.mock_sg.delete(sg_shot["type"], sg_shot["id"])

    def test_same_cut(self):
        """
        Test saving a Cut to SG and comparing it to itself.
        """
        edl = """
            TITLE:   CUT_DIFF_TEST

            001  clip_1 V     C        01:00:01:00 01:00:10:00 01:00:00:00 01:00:09:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: test_same_cut_shot_001
            002  clip_2 V     C        01:00:02:00 01:00:05:00 01:00:09:00 01:00:12:00
            * FROM CLIP NAME: shot_002_v001
            * COMMENT: test_same_cut_shot_002
            003  clip_3 V     C        01:00:00:00 01:00:04:00 01:00:12:00 01:00:16:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: test_same_cut_SHOT_001
        """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        track = timeline.tracks[0]
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            otio.adapters.write_to_file(timeline, self._SG_SEQ_URL, "ShotGrid")
            mock_cut_url = get_read_url(
                self.mock_sg.base_url,
                track.metadata["sg"]["id"],
                self._SESSION_TOKEN
            )
            # Read it back from SG.
            timeline_from_sg = otio.adapters.read_from_file(mock_cut_url, adapter_name="ShotGrid")
            sg_track = timeline_from_sg.tracks[0]
            clip = sg_track[0]
            self.assertEqual(clip.metadata["sg"]["cut_item_in"], 1033)
            clip = sg_track[1]
            self.assertEqual(clip.metadata["sg"]["cut_item_in"], 1009)
            clip = sg_track[2]
            self.assertEqual(clip.metadata["sg"]["cut_item_in"], 1009)
        # Shots are created by the SG writer, check them
        sg_shots = self.mock_sg.find("Shot", [], ["code"])
        self.assertEqual(len(sg_shots), 2)
        for sg_shot in sg_shots:
            self.assertIn("test_same_cut_shot", sg_shot["code"])

        # Read back the EDL in a fresh timeline
        edl_timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        edl_track = edl_timeline.tracks[0]
        track_diff = SGTrackDiff(
            self.mock_sg,
            self.mock_project,
            new_track=edl_track,
            old_track=sg_track
        )
        for shot_name, cut_group in track_diff.items():
            for cut_diff in cut_group.clips:
                self.assertIsNotNone(cut_diff.sg_shot)
                self.assertIsNotNone(cut_diff.current_clip)
                self.assertIsNotNone(cut_diff.old_clip)
                self.assertEqual(
                    cut_diff.current_clip.index, cut_diff.old_clip.index
                )
                self.assertEqual(
                    cut_diff.cut_in, cut_diff.old_cut_in
                )
                self.assertEqual(
                    cut_diff.cut_out, cut_diff.old_cut_out
                )
                logger.info(cut_diff.reasons)
                self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.NO_CHANGE)
                self.assertFalse(cut_diff.rescan_needed)
