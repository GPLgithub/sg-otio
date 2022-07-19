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
