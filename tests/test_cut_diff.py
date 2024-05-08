# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import copy
import csv
import logging
import os
import tempfile
import shotgun_api3

from sg_otio.cut_clip import SGCutClip
from .python.sg_test import SGBaseTest

import opentimelineio as otio
from opentimelineio.opentime import TimeRange, RationalTime

from sg_otio.track_diff import SGTrackDiff
from sg_otio.cut_diff import SGCutDiff
from sg_otio.utils import get_read_url, get_write_url
from sg_otio.constants import _DIFF_TYPES, _ALT_SHOT_FIELDS
from sg_otio.constants import _TC2FRAME_ABSOLUTE_MODE, _TC2FRAME_AUTOMATIC_MODE, _TC2FRAME_RELATIVE_MODE
from sg_otio.sg_settings import SGSettings, SGShotFieldsConfig


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
        """
        Called before each test.
        """
        super(TestCutDiff, self).setUp()
        self._sg_entities_to_delete = []
        sg_settings = SGSettings()
        sg_settings.reset_to_defaults()

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

    def _add_sg_cut_data(self):
        """
        """
        # SG is case insensitive but mockun is case sensitive so better to
        # keep everything lower case.
        self.sg_sequences = [{
            "code": "seq_6666",
            "project": self.mock_project,
            "type": "Sequence",
            "id": 6666,
        }, {
            "code": "seq_6667",
            "project": self.mock_project,
            "type": "Sequence",
            "id": 6667,
        }]
        self.add_to_sg_mock_db(self.sg_sequences)
        self._sg_entities_to_delete.extend(self.sg_sequences)
        self.sg_shots = [{
            "code": "shot_6666",
            "project": self.mock_project,
            "type": "Shot",
            "sg_sequence": self.sg_sequences[0],
            "id": 6666,
            "sg_status_list": None,
        }, {
            "code": "shot_6667",
            "project": self.mock_project,
            "type": "Shot",
            "sg_sequence": self.sg_sequences[0],
            "id": 6667,
            "sg_status_list": None,
        }, {
            "code": "shot_6668",
            "project": self.mock_project,
            "type": "Shot",
            "sg_sequence": self.sg_sequences[0],
            "id": 6668,
            "sg_status_list": None,
        }, {
            "code": "shot_6669",
            "project": self.mock_project,
            "type": "Shot",
            "sg_sequence": self.sg_sequences[0],
            "id": 6669,
            "sg_status_list": None,
        }]
        self.add_to_sg_mock_db(self.sg_shots)
        self._sg_entities_to_delete.extend(self.sg_shots)

        self.sg_cuts = [{
            "code": "cut_6666",
            "project": self.mock_project,
            "type": "Cut",
            "entity": self.sg_sequences[0],
            "id": 6666,
            "fps": 24.0,
        }, {
            "code": "cut_6667",
            "project": self.mock_project,
            "type": "Cut",
            "entity": self.sg_sequences[0],
            "id": 6667,
            "fps": 24.0,
        }]
        self.add_to_sg_mock_db(self.sg_cuts)
        self._sg_entities_to_delete.extend(self.sg_cuts)
        self.sg_cut_items = [{
            "timecode_cut_item_out_text": "01:00:08:00",
            "cut": self.sg_cuts[0],
            "shot": self.sg_shots[0],
            "cut_item_duration": 192,
            "cut_item_in": 1008,
            "cut_order": 1,
            "timecode_cut_item_in_text": "01:00:00:00",
            "version": None,
            "cut_item_out": 1199,
            "type": "CutItem",
            "id": 54,
            "code": "Item 54",
            "timecode_edit_in_text": "07:00:00:00",
            "timecode_edit_out_text": "07:00:08:00",
        }, {
            "timecode_cut_item_out_text": "00:00:05:00",
            "cut": self.sg_cuts[0],
            "shot": self.sg_shots[1],
            "cut_item_duration": 111,
            "cut_item_in": 1008,
            "cut_order": 2,
            "timecode_cut_item_in_text": "00:00:00:09",
            "version": None,
            "cut_item_out": 1118,
            "type": "CutItem",
            "id": 53,
            "code": "Item 53",
            "timecode_edit_in_text": "07:00:08:00",
            "timecode_edit_out_text": "07:00:12:15",
        }, {
            "timecode_cut_item_out_text": "00:00:06:10",
            "cut": self.sg_cuts[0],
            "shot": self.sg_shots[2],
            "cut_item_duration": 145,
            "cut_item_in": 1008,
            "cut_order": 3,
            "timecode_cut_item_in_text": "00:00:00:09",
            "version": None,
            "cut_item_out": 1152,
            "type": "CutItem",
            "id": 52,
            "code": "Item 52",
            "timecode_edit_in_text": "07:00:12:15",
            "timecode_edit_out_text": "07:00:18:16",
        }, {
            "timecode_cut_item_out_text": "00:00:07:16",
            "cut": self.sg_cuts[0],
            "shot": self.sg_shots[3],
            "cut_item_duration": 175,
            "cut_item_in": 1008,
            "cut_order": 4,
            "timecode_cut_item_in_text": "00:00:00:09",
            "version": None,
            "cut_item_out": 1182,
            "type": "CutItem",
            "id": 58,
            "code": "Item 58",
            "timecode_edit_in_text": "07:00:18:16",
            "timecode_edit_out_text": "07:00:25:23",
        }, {
            "timecode_cut_item_out_text": "00:00:06:10",
            "cut": self.sg_cuts[1],
            "shot": self.sg_shots[2],
            "cut_item_duration": 149,
            "cut_item_in": 1004,
            "cut_order": 1,
            "timecode_cut_item_in_text": "00:00:00:05",
            "version": None,
            "cut_item_out": 1152,
            "type": "CutItem",
            "id": 59,
            "code": "Item 59",
            "timecode_edit_in_text": "07:00:12:11",
            "timecode_edit_out_text": "07:00:18:16",
        }, {
            "timecode_cut_item_out_text": "00:00:07:20",
            "cut": self.sg_cuts[1],
            "shot": self.sg_shots[3],
            "cut_item_duration": 179,
            "cut_item_in": 1008,
            "cut_order": 2,
            "timecode_cut_item_in_text": "00:00:00:09",
            "version": None,
            "cut_item_out": 1186,
            "type": "CutItem",
            "id": 60,
            "code": "Item 60",
            "timecode_edit_in_text": "07:00:18:16",
            "timecode_edit_out_text": "07:00:26:03",
        }]
        self.add_to_sg_mock_db(self.sg_cut_items)
        self._sg_entities_to_delete.extend(self.sg_cut_items)

    @staticmethod
    def _mock_compute_clip_shot_name(clip):
        """
        Override compute clip shot name to get a unique shot name per clip.
        """
        return "shot_%d" % (6665 + list(clip.parent().find_clips()).index(clip) + 1)

    def _get_track_diff(self, new_track, old_track=None, mock_compute_clip_shot_name=None, sg_entity=None):
        """
        Create a track diff altering the shot names so that there's

        :param new_track: A :class:`opentimelineio.schema.Track` instance.
        :param old_track: An optional :class:`opentimelineio.schema.Track` instance
                          read from SG.
        :returns: A :class:`SGTrackDiff` instance.
        """
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            if mock_compute_clip_shot_name:
                with mock.patch("sg_otio.track_diff.compute_clip_shot_name", wraps=mock_compute_clip_shot_name):
                    with mock.patch("sg_otio.cut_clip.compute_clip_shot_name", wraps=mock_compute_clip_shot_name):
                        return SGTrackDiff(self.mock_sg, self.mock_project, new_track, old_track, sg_entity)
            else:
                return SGTrackDiff(self.mock_sg, self.mock_project, new_track, old_track, sg_entity)

    def tearDown(self):
        """
        Called inconditionally after each test.
        """
        super(TestCutDiff, self).tearDown()
        for sg_entity in self._sg_entities_to_delete:
            logger.debug("Deleting %s %s" % (sg_entity["type"], sg_entity["id"]))
            self.mock_sg.delete(sg_entity["type"], sg_entity["id"])
        self._sg_entities_to_delete = []

    def test_cut_diff(self):
        """
        Test various SGCutDiff behaviors
        """
        clip = otio.schema.Clip(
            name="test_clip",
            source_range=TimeRange(
                RationalTime(10, 24),
                RationalTime(10, 24),  # duration, 10 frames.
            ),
        )
        # Omitted Clips need to be linked to a SG CutItem
        with self.assertRaisesRegex(
            ValueError,
            "Omitted Clips need to be linked to a SG CutItem"
        ):
            cut_diff = SGCutDiff(
                clip=clip,
                index=1,
                sg_shot=None,
                as_omitted=True,
            )

        cut_diff = SGCutDiff(
            clip=clip,
            index=1,
            sg_shot=None,
        )
        # We can only compare to Clips linked to a SG CutItem
        with self.assertRaisesRegex(
            ValueError,
            "Old clips for SGCutDiff must be coming from a SG Cut Item"
        ):
            cut_diff.old_clip = cut_diff

        old_clip = otio.schema.Clip(
            name="test_clip",
            source_range=TimeRange(
                RationalTime(10, 24),
                RationalTime(10, 24),  # duration, 10 frames.
            ),
        )

        sg_shots = [{
            "type": "Shot",
            "code": "Fake shot 1",
            "sg_status_list": None,
            "project": self.mock_project,
            "id": 1
        }, {
            "type": "Shot",
            "code": "Fake shot 2",
            "sg_status_list": None,
            "project": self.mock_project,
            "id": 2
        }]

        old_clip.metadata["sg"] = {
            "type": "CutItem",
            "id": -1,
            "cut_item_in": 1009,
            "cut_item_out": 1018,
            "cut_order": 1,
            "timecode_cut_item_in_text": "%s" % RationalTime(110, 24).to_timecode(),
            "shot": sg_shots[0],
            "code": "test_clip",
        }
        cut_diff.old_clip = SGCutClip(
            clip=old_clip,
            index=1,
            sg_shot=None,
        )
        cut_diff.sg_shot = sg_shots[1]
        cut_diff.old_clip = SGCutClip(
            clip=old_clip,
            index=1,
            sg_shot=sg_shots[1],
        )
        # Shot mismatches should raise an error
        with self.assertRaisesRegex(
            ValueError,
            "Shot mismatch between current clip and old one 2 vs 1"
        ):
            cut_diff.old_clip = SGCutClip(
                clip=old_clip,
                index=1,
                sg_shot=sg_shots[0],
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
        self._sg_entities_to_delete = sg_shots
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

    def test_old_clip_for_shot(self):
        """
        Test that old_clip_for_shot retrieves the right clip.
        """
        self._add_sg_cut_data()

        def get_clip_list():
            prev_clip_list = []
            for i in range(2):
                clip = otio.schema.Clip(
                    name="test_clip_%d" % i,
                    source_range=TimeRange(
                        RationalTime(10, 24),
                        RationalTime(10, 24),  # duration, 10 frames.
                    ),
                    metadata={"sg": self.sg_cut_items[i]}
                )
                cut_clip = SGCutClip(clip, self.sg_shots[i], i + 1)
                prev_clip_list.append(cut_clip)
            return prev_clip_list
        clip = otio.schema.Clip(
            name="test_clip",
            source_range=TimeRange(
                RationalTime(10, 24),
                RationalTime(10, 24),  # duration, 10 frames.
            ),
        )
        # Test that if another_clip is not in prev_clip_list, it returns None
        another_clip = SGCutClip(clip, self.sg_shots[3], 4)
        prev_clip_list = get_clip_list()
        old_clip = SGTrackDiff.old_clip_for_shot(another_clip, prev_clip_list, self.sg_shots[3])
        self.assertIsNone(old_clip)
        # Test that if we provide the wrong Shot, it returns None
        prev_clip_list = get_clip_list()
        old_clip = SGTrackDiff.old_clip_for_shot(prev_clip_list[0], prev_clip_list, self.sg_shots[3])
        self.assertIsNone(old_clip)
        # If we provide the exact same clip and the right Shot, we have a match.
        prev_clip_list = get_clip_list()
        first_clip = prev_clip_list[0]
        old_clip = SGTrackDiff.old_clip_for_shot(first_clip, prev_clip_list, self.sg_shots[0])
        self.assertEqual(old_clip, first_clip)
        # Even if we provide a bogus Version it still matches properly.
        prev_clip_list = get_clip_list()
        first_clip = prev_clip_list[0]
        old_clip = SGTrackDiff.old_clip_for_shot(
            first_clip,
            prev_clip_list,
            self.sg_shots[0],
            {"type": "Version", "id": -1}
        )
        self.assertEqual(old_clip, first_clip)

        # If we provide the right Version for two identical clips, it matches the one with the matching Version.
        fake_version = {"type": "Version", "id": 1}
        prev_clip_list = get_clip_list()
        first_clip = prev_clip_list[0]
        another_clip = copy.deepcopy(first_clip)
        another_clip.media_reference.metadata["sg"] = {"version": fake_version}
        prev_clip_list.insert(0, another_clip)
        old_clip = SGTrackDiff.old_clip_for_shot(first_clip, prev_clip_list, self.sg_shots[0], fake_version)
        self.assertEqual(old_clip, another_clip)

        # If there are two matching clips, it will depend on the matching score (index, tc_in, tc_out)
        # Different index
        clip_list = get_clip_list()
        first_clip = clip_list[0]
        first_clip_copy = copy.deepcopy(first_clip)
        clip_list.insert(0, first_clip_copy)
        first_clip._index = 2
        old_clip = SGTrackDiff.old_clip_for_shot(first_clip_copy, clip_list, self.sg_shots[0])
        self.assertEqual(old_clip, first_clip_copy)

        # Different tc_in
        clip_list = get_clip_list()
        first_clip = clip_list[0]
        first_clip_copy = copy.deepcopy(first_clip)
        first_clip._clip.source_range = TimeRange(RationalTime(5, 24), RationalTime(5, 24))
        clip_list.append(first_clip_copy)
        old_clip = SGTrackDiff.old_clip_for_shot(first_clip_copy, clip_list, self.sg_shots[0])
        self.assertEqual(old_clip, first_clip_copy)

        # Different tc out
        clip_list = get_clip_list()
        first_clip = clip_list[0]
        first_clip_copy = copy.deepcopy(first_clip)
        first_clip._clip.source_range = TimeRange(RationalTime(10, 24), RationalTime(5, 24))
        clip_list.append(first_clip_copy)
        old_clip = SGTrackDiff.old_clip_for_shot(first_clip_copy, clip_list, self.sg_shots[0])
        self.assertEqual(old_clip, first_clip_copy)

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
        # Shots are created by the SG writer, check them
        sg_shots = self.mock_sg.find("Shot", [], ["code"])
        self.assertEqual(len(sg_shots), 2)
        self._sg_entities_to_delete = sg_shots
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
                self.assertEqual(cut_diff.reasons, [])
                self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.NO_CHANGE)
                self.assertFalse(cut_diff.rescan_needed)

    def test_all_new(self):
        """
        Check we're able to detect the right changes.
        """
        # Test a tracks without shot names
        track = otio.schema.Track()
        for i in range(10):
            clip = otio.schema.Clip(
                name="test_clip_%d" % i,
                source_range=TimeRange(
                    RationalTime(i * 10, 24),
                    RationalTime(10, 24),  # duration, 10 frames.
                ),
            )
            track.append(clip)
        track_diff = SGTrackDiff(
            self.mock_sg,
            self.mock_project,
            new_track=track,
        )
        # Each clip should have its own group
        self.assertEqual(len(list(track_diff)), len(track))
        for name, clip_group in track_diff.items():
            self.assertTrue(name)
            self.assertIsNone(clip_group.sg_shot)
            self.assertIsNone(clip_group.name)
            for clip in clip_group.clips:
                self.assertIsNone(clip.sg_shot)
                self.assertIsNone(clip.old_clip)
                self.assertIsNone(clip.old_cut_in)
                self.assertIsNone(clip.old_cut_out)
                self.assertIsNone(clip.old_visible_duration)
                self.assertEqual(clip.diff_type, _DIFF_TYPES.NO_LINK)

        # Add some markers to the Clips to provide Shot names
        for i, clip in enumerate(track):
            clip.markers.append(
                otio.schema.Marker("marker_shot_%03d XXX" % (i % 2))
            )
        track_diff = SGTrackDiff(
            self.mock_sg,
            self.mock_project,
            new_track=track,
        )
        self.assertEqual(sorted(list(track_diff)), ["marker_shot_000", "marker_shot_001"])
        for shot_name, clip_group in track_diff.items():
            for clip in clip_group.clips:
                self.assertIsNone(clip.sg_shot)
                self.assertIsNone(clip.old_clip)
                self.assertIsNone(clip.old_cut_in)
                self.assertIsNone(clip.old_cut_out)
                self.assertIsNone(clip.old_visible_duration)
                self.assertTrue(clip.repeated)
                # No Shot so all NEW
                self.assertEqual(clip.diff_type, _DIFF_TYPES.NEW)

    def test_shot_mismatches(self):
        """
        Check we're able to detect the right changes.
        """
        # Test a tracks without shot names
        track = otio.schema.Track()
        for i in range(10):
            clip = otio.schema.Clip(
                name="test_clip_%d" % i,
                source_range=TimeRange(
                    RationalTime(i * 10, 24),
                    RationalTime(10, 24),  # duration, 10 frames.
                ),
            )
            clip.markers.append(
                otio.schema.Marker("marker_shot_%03d XXX" % (i % 2))
            )
            track.append(clip)

        old_track = copy.deepcopy(track)
        # Without sg metada for the old track an error should be raised.
        with self.assertRaises(ValueError) as cm:
            track_diff = SGTrackDiff(
                self.mock_sg,
                self.mock_project,
                new_track=track,
                old_track=old_track,
            )
        # Should have choked on the track not being linked to a Cut
        self.assertEqual(
            "%s" % cm.exception,
            "Invalid track  not linked to a SG Cut"
        )
        old_track.metadata["sg"] = {
            "type": "Cut",
            "id": -1,
            "code": "Faked Cut",
            "project": {"type": "Project", "id": -1}
        }
        # It should choke on invalid project
        with self.assertRaises(ValueError) as cm:
            track_diff = SGTrackDiff(
                self.mock_sg,
                self.mock_project,
                new_track=track,
                old_track=old_track,
            )
        self.assertEqual(
            "%s" % cm.exception,
            "Can't compare Cuts from different SG Projects"
        )

        old_track.metadata["sg"] = {
            "type": "Cut",
            "id": -1,
            "code": "Faked Cut",
            "project": self.mock_project
        }
        # It should choke now on invalid clips
        with self.assertRaises(ValueError) as cm:
            track_diff = SGTrackDiff(
                self.mock_sg,
                self.mock_project,
                new_track=track,
                old_track=old_track,
            )
        # Should have choked on the first clip
        self.assertEqual(
            "%s" % cm.exception,
            "Invalid clip %s not linked to a SG CutItem" % old_track[0].name
        )
        sg_shots = [
            {"type": "Shot", "code": "old_shot_001", "project": self.mock_project, "id": 1},
            {"type": "Shot", "code": "old_shot_002", "project": self.mock_project, "id": 2}
        ]
        self.add_to_sg_mock_db(sg_shots)
        self._sg_entities_to_delete = sg_shots
        for i, clip in enumerate(old_track.find_clips()):
            clip.metadata["sg"] = {
                "type": "CutItem",
                "id": -1,
                "cut_item_in": 1009,
                "cut_item_out": 1018,  # inclusive, ten frames
                "cut_order": i + 1,
                "timecode_cut_item_in_text": "%s" % RationalTime(i * 10, 24).to_timecode(),
                "shot": sg_shots[i % 2]
            }
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            track_diff = SGTrackDiff(
                self.mock_sg,
                self.mock_project,
                new_track=track,
                old_track=old_track,
            )
        self.assertEqual(
            sorted(list(track_diff)),
            ["marker_shot_000", "marker_shot_001", "old_shot_001", "old_shot_002"]
        )
        for shot_name, clip_group in track_diff.items():
            if shot_name.startswith("old"):
                # Omitted Shot
                for clip in clip_group.clips:
                    self.assertIsNotNone(clip.sg_shot)
                    self.assertIsNone(clip.current_clip)
                    self.assertIsNotNone(clip.old_clip)
                    self.assertEqual(clip.cut_in, clip.old_cut_in)
                    self.assertFalse(clip.effect)
                    self.assertEqual(clip.visible_duration.to_frames(), 10)
                    self.assertEqual(clip.visible_duration, clip.old_visible_duration)
                    self.assertEqual(clip.cut_out, clip.old_cut_out)
                    self.assertTrue(clip.repeated)
                    self.assertFalse(clip.rescan_needed)
                    # No Shot so all ommitted
                    self.assertEqual(clip.diff_type, _DIFF_TYPES.OMITTED_IN_CUT)
            else:
                # new Shot
                for clip in clip_group.clips:
                    self.assertIsNone(clip.sg_shot)
                    self.assertIsNone(clip.old_clip)
                    self.assertIsNone(clip.old_cut_in)
                    self.assertIsNone(clip.old_cut_out)
                    self.assertIsNone(clip.old_visible_duration)
                    self.assertTrue(clip.repeated)
                    # No Shot so all NEW
                    self.assertEqual(clip.diff_type, _DIFF_TYPES.NEW)

    def test_shot_matches(self):
        """
        Check we're able to detect the right changes.
        """
        # Test a tracks without shot names
        track = otio.schema.Track()
        for i in range(10):
            # Make the clips contiguous for two Shots
            clip = otio.schema.Clip(
                name="test_clip_%d" % i,
                source_range=TimeRange(
                    RationalTime((i // 2) * 10, 24),
                    RationalTime(10, 24),  # duration, 10 frames.
                ),
            )
            clip.markers.append(
                otio.schema.Marker("marker_shot_%03d XXX" % (i % 2))
            )
            track.append(clip)

        old_track = copy.deepcopy(track)
        old_track.metadata["sg"] = {
            "type": "Cut",
            "id": -1,
            "code": "Faked Cut",
            "project": self.mock_project,
        }
        sg_shots = [
            {"type": "Shot", "code": "marker_shot_000", "project": self.mock_project, "id": 1},
            {"type": "Shot", "code": "marker_shot_001", "project": self.mock_project, "id": 2}
        ]
        self.add_to_sg_mock_db(sg_shots)
        self._sg_entities_to_delete = sg_shots
        for i, clip in enumerate(old_track.find_clips()):
            clip.metadata["sg"] = {
                "type": "CutItem",
                "id": -1,
                "cut_item_in": 1009 + (i // 2) * 10,
                "cut_item_out": 1009 + (i // 2) * 10 + 10 - 1,
                "cut_order": i + 1,
                "timecode_cut_item_in_text": "%s" % RationalTime((i // 2) * 10, 24).to_timecode(),
                "shot": sg_shots[i % 2],
                "code": "test_clip_%d" % i,
            }
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            track_diff = SGTrackDiff(
                self.mock_sg,
                self.mock_project,
                new_track=track,
                old_track=old_track,
            )
        self.assertEqual(
            sorted(list(track_diff)),
            ["marker_shot_000", "marker_shot_001"]
        )
        for shot_name, clip_group in track_diff.items():
            self.assertIsNotNone(clip_group.sg_shot)
            for clip in clip_group.clips:
                logger.info("Checking %s" % clip.name)
                self.assertIsNotNone(clip.sg_shot)
                self.assertIsNotNone(clip.current_clip)
                self.assertIsNotNone(clip.old_clip)
                # Two different clips
                self.assertNotEqual(clip.current_clip, clip.old_clip)
                self.assertEqual(clip.current_clip.name, clip.old_clip.name)
                self.assertEqual(clip.cut_in, clip.old_cut_in)
                self.assertFalse(clip.effect)
                self.assertEqual(clip.visible_duration.to_frames(), 10)
                self.assertEqual(clip.visible_duration, clip.old_visible_duration)
                self.assertEqual(clip.cut_out, clip.old_cut_out)
                self.assertTrue(clip.repeated)
                self.assertFalse(clip.rescan_needed)
                # No changes
                self.assertEqual(clip.diff_type, _DIFF_TYPES.NO_CHANGE)
        # Remove the second entries for the two Shots in the new Cut
        logger.info("Deleting %s" % track[3].name)
        del track[2]
        logger.info("Deleting %s" % track[3].name)
        del track[2]
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            track_diff = SGTrackDiff(
                self.mock_sg,
                self.mock_project,
                new_track=track,
                old_track=old_track,
            )
        for shot_name, clip_group in track_diff.items():
            self.assertIsNotNone(clip_group.sg_shot)
            for clip in clip_group.clips:
                logger.info("Checking %s" % clip.name)
                if clip.name in ["test_clip_2", "test_clip_3"]:
                    self.assertIsNone(clip.current_clip)
                    self.assertEqual(clip.diff_type, _DIFF_TYPES.OMITTED_IN_CUT)
                else:
                    self.assertIsNotNone(clip.current_clip)
                    self.assertIsNotNone(clip.old_clip)
                    self.assertEqual(clip.cut_in, clip.old_cut_in)
                    self.assertEqual(clip.diff_type, _DIFF_TYPES.NO_CHANGE)
                    self.assertEqual(clip.current_clip.name, clip.old_clip.name)
                    self.assertEqual(clip.cut_in, clip.old_cut_in)
                    self.assertFalse(clip.effect)
                    self.assertEqual(clip.visible_duration.to_frames(), 10)
                    self.assertEqual(clip.visible_duration, clip.old_visible_duration)
                    self.assertEqual(clip.cut_out, clip.old_cut_out)
                    self.assertTrue(clip.repeated)
                    self.assertFalse(clip.rescan_needed)
        # Remove first and last entries in the new track and check how this
        # affects groups values
        logger.info("Deleting %s" % track[0].name)
        del track[0]
        logger.info("Deleting %s" % track[0].name)
        del track[0]
        logger.info("Deleting %s" % track[-1].name)
        del track[-1]
        logger.info("Deleting %s" % track[-1].name)
        del track[-1]
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            track_diff = SGTrackDiff(
                self.mock_sg,
                self.mock_project,
                new_track=track,
                old_track=old_track,
            )
        for shot_name, clip_group in track_diff.items():
            self.assertIsNotNone(clip_group.sg_shot)
            # We removed the two first entries for each group
            self.assertEqual(clip_group.source_in.to_frames(), 20)
            # We only have left two 10 frames clips for each Shot.
            # The source out is an exclusive value
            self.assertEqual(clip_group.source_out.to_frames(), 40)
            # Should match what is still left
            self.assertEqual(clip_group.cut_in.to_frames(), 1029)
            self.assertEqual(clip_group.cut_out.to_frames(), 1048)
            for clip in clip_group.clips:
                logger.info("Checking %s" % clip.name)
                if clip.name in [
                    "test_clip_0", "test_clip_1",
                    "test_clip_2", "test_clip_3",
                    "test_clip_8", "test_clip_9",
                ]:
                    self.assertIsNone(clip.current_clip)
                    self.assertEqual(clip.diff_type, _DIFF_TYPES.OMITTED_IN_CUT)
                else:
                    self.assertEqual(clip.cut_in, clip.old_cut_in)
                    self.assertEqual(clip.cut_out, clip.old_cut_out)
                    self.assertEqual(clip.diff_type, _DIFF_TYPES.NO_CHANGE)

    def test_cut_differences(self):
        """
        Check we're able to detect the right changes.
        """
        clip = otio.schema.Clip(
            name="test_clip",
            source_range=TimeRange(
                RationalTime(110, 24),
                RationalTime(10, 24),  # duration, 10 frames.
            ),
        )
        clip.markers.append(
            otio.schema.Marker("marker_shot")
        )
        sg_shot = {
            "type": "Shot",
            "code": "marker_shot",
            "sg_status_list": None,
            "project": self.mock_project,
            "id": 1
        }
        self.add_to_sg_mock_db(sg_shot)
        self._sg_entities_to_delete = [sg_shot]
        cut_diff = SGCutDiff(
            clip=clip, index=1, sg_shot=sg_shot,
        )
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.NEW_IN_CUT)
        sg_settings = SGSettings()
        sg_shot["sg_status_list"] = sg_settings.shot_omit_status
        self.assertIsNotNone(cut_diff.sg_shot_status)
        cut_diff.compute_head_tail_values()
        cut_diff._check_and_set_changes()
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.REINSTATED)
        old_clip = otio.schema.Clip(
            name="test_clip",
            source_range=TimeRange(
                RationalTime(110, 24),
                RationalTime(10, 24),  # duration, 10 frames.
            ),
        )
        old_clip.metadata["sg"] = {
            "type": "CutItem",
            "id": -1,
            "cut_item_in": 1009,
            "cut_item_out": 1018,
            "cut_order": 1,
            "timecode_cut_item_in_text": "%s" % RationalTime(110, 24).to_timecode(),
            "shot": sg_shot,
            "code": "test_clip",
        }
        cut_diff.old_clip = SGCutDiff(
            clip=old_clip,
            index=1,
            sg_shot=sg_shot,
        )
        cut_diff.compute_head_tail_values()
        cut_diff._check_and_set_changes()
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.REINSTATED)
        sg_shot["sg_status_list"] = {
            "code": "notomitted",
            "id": -1,
        }
        cut_diff.compute_head_tail_values()
        cut_diff._check_and_set_changes()
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.NO_CHANGE)
        clip.source_range = TimeRange(
            RationalTime(110, 24),
            RationalTime(20, 24),  # duration, 20 frames.
        )
        cut_diff.compute_head_tail_values()
        cut_diff._check_and_set_changes()
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.CUT_CHANGE)
        self.assertEqual(cut_diff.reasons, ["Tail trimmed 10 frs"])
        clip.source_range = TimeRange(
            RationalTime(100, 24),
            RationalTime(20, 24),  # duration, 20 frames.
        )
        cut_diff.compute_head_tail_values()
        cut_diff._check_and_set_changes()
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.CUT_CHANGE)
        self.assertEqual(cut_diff.reasons, ["Head trimmed 10 frs"])
        clip.source_range = TimeRange(
            RationalTime(111, 24),
            RationalTime(8, 24),  # duration, 8 frames.
        )
        cut_diff.compute_head_tail_values()
        cut_diff._check_and_set_changes()
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.CUT_CHANGE)
        self.assertEqual(cut_diff.reasons, ["Head extended 1 frs", "Tail extended 1 frs"])

        # Check rescan are correctly detected.
        # So far values coming from the Shot should be None
        self.assertIsNone(cut_diff.sg_shot_head_in)
        self.assertIsNone(cut_diff.old_head_duration)
        self.assertIsNone(cut_diff.sg_shot_tail_out)
        self.assertIsNone(cut_diff.old_tail_duration)

        sg_shot["sg_head_in"] = 1001
        sg_shot["sg_tail_out"] = 1026
        self.assertEqual(cut_diff.sg_shot_head_in, 1001)
        cut_diff.compute_head_tail_values()
        cut_diff._check_and_set_changes()
        self.assertEqual(cut_diff.head_in.to_frames(), 1001)
        self.assertEqual(cut_diff.cut_in.to_frames(), 1010)
        self.assertEqual(cut_diff.head_duration.to_frames(), 9)
        self.assertEqual(cut_diff.old_cut_in.to_frames(), 1009)
        self.assertEqual(cut_diff.old_head_duration.to_frames(), 8)
        self.assertEqual(cut_diff.old_tail_duration.to_frames(), 8)
        # Within handles
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.CUT_CHANGE)

        # Cut in one frame before registered head in.
        clip.source_range = TimeRange(
            RationalTime(101, 24),  # one frame before head in
            RationalTime(10, 24),  # duration, 10 frames.
        )
        cut_diff.compute_head_tail_values()
        cut_diff._check_and_set_changes()
        self.assertEqual(cut_diff.sg_shot_head_in, 1001)
        self.assertEqual(cut_diff.cut_in.to_frames(), 1000)
        self.assertEqual(cut_diff.head_duration.to_frames(), -1)
        self.assertEqual(cut_diff.old_cut_in.to_frames(), 1009)
        self.assertEqual(cut_diff.old_head_duration.to_frames(), 8)
        self.assertEqual(cut_diff.old_tail_duration.to_frames(), 8)
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.RESCAN)

        # Same cut in, cut out after registered handles.
        clip.source_range = TimeRange(
            RationalTime(110, 24),
            RationalTime(19, 24),  # duration, 19 frames, one frame after tail out.
        )
        cut_diff.compute_head_tail_values()
        cut_diff._check_and_set_changes()
        self.assertEqual(cut_diff.sg_shot_tail_out, 1026)
        self.assertEqual(cut_diff.tail_out.to_frames(), 1026)
        self.assertEqual(cut_diff.cut_in.to_frames(), 1009)
        self.assertEqual(cut_diff.cut_out.to_frames(), 1009 + 19 - 1)
        self.assertEqual(cut_diff.tail_duration.to_frames(), - 1)
        self.assertEqual(cut_diff.old_cut_in.to_frames(), 1009)
        self.assertEqual(cut_diff.old_head_duration.to_frames(), 8)
        self.assertEqual(cut_diff.old_tail_duration.to_frames(), 8)
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.RESCAN)

        # Both cut in and cut out out of handle margins.
        clip.source_range = TimeRange(
            RationalTime(101, 24),  # one frame before head in
            RationalTime(28, 24),  # duration, 28 frames, one frame after tail out.
        )
        cut_diff.compute_head_tail_values()
        cut_diff._check_and_set_changes()
        self.assertEqual(cut_diff.sg_shot_head_in, 1001)
        self.assertEqual(cut_diff.cut_in.to_frames(), 1000)
        self.assertEqual(cut_diff.head_duration.to_frames(), -1)
        self.assertEqual(cut_diff.sg_shot_tail_out, 1026)
        self.assertEqual(cut_diff.tail_out.to_frames(), 1026)  # Retrieved from the Shot
        self.assertEqual(cut_diff.cut_in.to_frames(), 1000)
        self.assertEqual(cut_diff.cut_out.to_frames(), 1000 + 28 - 1)
        self.assertEqual(cut_diff.tail_duration.to_frames(), - 1)
        self.assertEqual(cut_diff.old_cut_in.to_frames(), 1009)
        self.assertEqual(cut_diff.old_head_duration.to_frames(), 8)
        self.assertEqual(cut_diff.old_tail_duration.to_frames(), 8)
        self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.RESCAN)

    def test_report(self):
        """
        Test generating a diff report.
        """
        settings = SGSettings()
        settings.default_head_in = 1000
        settings.default_head_duration = 8
        settings.default_tail_duration = 8
        self._add_sg_cut_data()
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            mock_cut_url = get_read_url(
                self.mock_sg.base_url,
                self.sg_cuts[0]["id"],
                self._SESSION_TOKEN
            )
            # Read it back from SG.
            timeline_from_sg = otio.adapters.read_from_file(mock_cut_url, adapter_name="ShotGrid")
            sg_track = timeline_from_sg.tracks[0]
            mock_cut_url2 = get_read_url(
                self.mock_sg.base_url,
                self.sg_cuts[1]["id"],
                self._SESSION_TOKEN
            )
            # Read it back from SG.
            timeline_from_sg2 = otio.adapters.read_from_file(mock_cut_url2, adapter_name="ShotGrid")
            sg_track2 = timeline_from_sg2.tracks[0]

        # Compare the existing Cut to itself.
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            track_diff = SGTrackDiff(
                self.mock_sg,
                self.mock_project,
                new_track=sg_track,
                old_track=sg_track,
            )
        # Check that the common container for the Cut was correctly detected
        self.assertIsNotNone(track_diff._sg_entity)
        self.assertEqual(track_diff._sg_shot_link_field_name, "sg_sequence")
        self.assertEqual(track_diff._sg_entity["id"], self.sg_sequences[0]["id"])
        self.assertEqual(track_diff._sg_entity["type"], self.sg_sequences[0]["type"])
        # Since we're comparing to existing tracks, their name should be mentioned
        # in the title.
        self.assertEqual(
            track_diff.get_summary_title("This is a Test"),
            "This is a Test Cut Summary changes between cut_6666 and cut_6666"
        )
        self.assertEqual(track_diff.count_for_type(_DIFF_TYPES.NO_CHANGE), 4)

        for shot_name, clip_group in track_diff.items():
            for clip in clip_group.clips:
                self.assertIsNotNone(clip.sg_shot)
                self.assertEqual(clip.diff_type, _DIFF_TYPES.NO_CHANGE)
        diffs = [x for x in track_diff.diffs_for_type(_DIFF_TYPES.NO_CHANGE, just_earliest=False)]
        self.assertEqual(
            len(diffs),
            4,  # 4 Cut Items for the Cut
        )
        for diff_type, items in track_diff.get_diffs_by_change_type().items():
            self.assertEqual(items, [])
        report = track_diff.get_report("This is a Test", [])
        self.assertEqual(
            report,
            (
                "This is a Test Cut Summary changes between cut_6666 and cut_6666",
                "\n\nLinks: \n\nThe changes in This is a Test are as follows:\n\n0 New Shots\n\n\n0 Omitted Shots\n\n\n0 Reinstated Shot\n\n\n0 Cut Changes\n\n\n0 Rescan Needed\n\n\n"
            )
        )
        # Test csv report
        _, csv_path = tempfile.mkstemp(suffix=".csv")
        track_diff.write_csv_report(csv_path, "This is a Test", [mock_cut_url])
        # If newline='' is not specified, newlines embedded inside quoted fields will not be interpreted correctly,
        # and on platforms that use \r\n linendings on write an extra \r will be added.
        # It should always be safe to specify newline='', since the csv module does its own (universal) newline handling.
        # see: https://docs.python.org/3/library/csv.html#id4
        with open(csv_path, newline="") as csvfile:
            reader = csv.reader(csvfile)
            in_edits_rows = False
            edits_rows_count = 0
            checks = 0
            for row in reader:
                if not in_edits_rows:
                    if row[0] == "To:":
                        self.assertEqual(row[1], sg_track.name)
                        checks += 1
                    elif row[0] == "From:":
                        self.assertEqual(row[1], sg_track.name)
                        checks += 1
                    elif row[0] == "Total Run Time [fr]:":
                        self.assertEqual(row[1], "%s" % sg_track.duration().to_frames())
                        checks += 1
                    elif row[0] == "Total Run Time [tc]:":
                        self.assertEqual(row[1], "%s" % sg_track.duration().to_timecode())
                        checks += 1
                    elif row[0] == "Total Count:":
                        self.assertEqual(row[1], "4")
                        checks += 1
                    elif row[0] == "Links:":
                        self.assertEqual(row[1], mock_cut_url)
                        checks += 1
                    elif row[0] == "Cut Order":  # Header for edit rows
                        self.assertEqual(checks, 6)
                        in_edits_rows = True
                else:
                    self.assertEqual(row[0], "%s" % self.sg_cut_items[edits_rows_count]["cut_order"])
                    self.assertEqual(row[1], _DIFF_TYPES.NO_CHANGE.name)
                    self.assertEqual(row[2], "%s" % self.sg_cut_items[edits_rows_count]["shot"]["code"])
                    self.assertEqual(row[3], "%s" % self.sg_cut_items[edits_rows_count]["cut_item_duration"])
                    self.assertEqual(row[4], "%s" % self.sg_cut_items[edits_rows_count]["cut_item_in"])
                    self.assertEqual(row[5], "%s" % self.sg_cut_items[edits_rows_count]["cut_item_out"])
                    edits_rows_count += 1
                logger.debug(row)
            self.assertEqual(edits_rows_count, 4)
        os.remove(csv_path)
        # Compare to Cut from EDL
        path = os.path.join(
            self.resources_dir,
            "edls",
            "R7v26.0_Turnover001_WiP_VFX__1_.edl"
        )
        timeline_from_edl = otio.adapters.read_from_file(path)
        new_track = timeline_from_edl.tracks[0]
        track_diff = self._get_track_diff(new_track, sg_track, self._mock_compute_clip_shot_name)
        self.assertEqual(len(new_track), track_diff.active_count)
        # 4 shots exist in the DB, from shot_6666 to shot_6669
        self.assertEqual(track_diff.count_for_type(_DIFF_TYPES.NEW), 28)
        self.assertEqual(track_diff.count_for_type(_DIFF_TYPES.NO_CHANGE), 4)
        report = track_diff.get_report("This is a Test", [])
        self.assertEqual(
            report,
            (
                "Sequence Cut Summary changes on This is a Test",
                (
                    "\n\nLinks: \n\nThe changes in This is a Test are as follows:\n\n"
                    "28 New Shots\n%s\n\n"
                    "0 Omitted Shots\n\n\n"
                    "0 Reinstated Shot\n\n\n"
                    "0 Cut Changes\n\n\n"
                    "0 Rescan Needed\n\n\n"
                ) % "\n".join(["shot_%d" % (6670 + i) for i in range(28)])
            )
        )
        # Test csv report
        _, csv_path = tempfile.mkstemp(suffix=".csv")
        new_track.name = "Howdy.edl"
        track_diff.write_csv_report(csv_path, "This is a Test", [])
        with open(csv_path, newline='') as csvfile:
            reader = csv.reader(csvfile)
            in_edits_rows = False
            edits_rows_count = 0
            checks = 0
            for row in reader:
                if not in_edits_rows:
                    if row[0] == "To:":
                        self.assertEqual(row[1], "Howdy.edl")
                        checks += 1
                    elif row[0] == "From:":
                        self.assertEqual(row[1], sg_track.name)
                        checks += 1
                    elif row[0] == "Total Run Time [fr]:":
                        self.assertEqual(row[1], "%s (%s)" % (new_track.duration().to_frames(), sg_track.duration().to_frames()))
                        checks += 1
                    elif row[0] == "Total Run Time [tc]:":
                        self.assertEqual(row[1], "%s (%s)" % (new_track.duration().to_timecode(), sg_track.duration().to_timecode()))
                        checks += 1
                    elif row[0] == "Total Count:":
                        self.assertEqual(row[1], "32 (4)")
                        checks += 1
                    elif row[0] == "Cut Order":  # Header for edit rows
                        self.assertEqual(checks, 5)
                        in_edits_rows = True
                else:
                    if edits_rows_count < 4:
                        # Identical values between the EDL and the SG Cut
                        self.assertEqual(row[0], "%s" % self.sg_cut_items[edits_rows_count]["cut_order"])
                        self.assertEqual(row[1], _DIFF_TYPES.NO_CHANGE.name)
                        self.assertEqual(row[2], "%s" % self.sg_cut_items[edits_rows_count]["shot"]["code"])
                        self.assertEqual(row[3], "%s" % self.sg_cut_items[edits_rows_count]["cut_item_duration"])
                        self.assertEqual(row[4], "%s" % self.sg_cut_items[edits_rows_count]["cut_item_in"])
                        self.assertEqual(row[5], "%s" % self.sg_cut_items[edits_rows_count]["cut_item_out"])
                    else:
                        clip = new_track[edits_rows_count]
                        # New edits
                        self.assertEqual(row[0], "%s" % (edits_rows_count + 1))
                        self.assertEqual(row[1], _DIFF_TYPES.NEW.name)
                        self.assertEqual(row[2], "%s" % self._mock_compute_clip_shot_name(clip))
                        self.assertEqual(row[3], "%s" % clip.duration().to_frames())
                        self.assertEqual(row[4], "%s" % (settings.default_head_in + settings.default_head_duration))
                        self.assertEqual(row[5], "%s" % (
                            settings.default_head_in + settings.default_head_duration + clip.duration().to_frames() - 1)
                        )
                    edits_rows_count += 1
                logger.debug(row)
            self.assertEqual(edits_rows_count, 32)
        os.remove(csv_path)

        # Compare the two SG Cuts where some items are missing and
        # in and out differs for the two remaining items
        track_diff = self._get_track_diff(sg_track2, sg_track)
        self.assertEqual(len(sg_track2), track_diff.active_count)
        self.assertEqual(len(sg_track2), 2)
        # Only 2 items kept
        self.assertEqual(track_diff.count_for_type(_DIFF_TYPES.OMITTED), 2)
        self.assertEqual(track_diff.count_for_type(_DIFF_TYPES.NO_CHANGE), 0)
        self.assertEqual(track_diff.count_for_type(_DIFF_TYPES.CUT_CHANGE), 2)
        report = track_diff.get_report("This is a Test", [])
        self.assertEqual(
            report,
            (
                "This is a Test Cut Summary changes between cut_6667 and cut_6666",
                (
                    "\n\nLinks: \n\nThe changes in This is a Test are as follows:\n\n"
                    "0 New Shots\n\n\n"
                    "2 Omitted Shots\n%s\n\n"
                    "0 Reinstated Shot\n\n\n"
                    "2 Cut Changes\n%s\n\n"
                    "0 Rescan Needed\n\n\n"
                ) % (
                    "\n".join([self.sg_shots[0]["code"], self.sg_shots[1]["code"]]),
                    "\n".join(["Item 59", "Item 60"]),  # For some reasons Shot names are not used...
                )
            )
        )
        _, csv_path = tempfile.mkstemp(suffix=".csv")
        track_diff.write_csv_report(csv_path, "This is a Test", [mock_cut_url])
        with open(csv_path, newline="") as csvfile:
            reader = csv.reader(csvfile)
            in_edits_rows = False
            edits_rows_count = 0
            checks = 0
            for row in reader:
                if not in_edits_rows:
                    if row[0] == "To:":
                        self.assertEqual(row[1], sg_track2.name)
                        checks += 1
                    elif row[0] == "From:":
                        self.assertEqual(row[1], sg_track.name)
                        checks += 1
                    elif row[0] == "Total Run Time [fr]:":
                        self.assertEqual(row[1], "%s (%s)" % (sg_track2.duration().to_frames(), sg_track.duration().to_frames()))
                        checks += 1
                    elif row[0] == "Total Run Time [tc]:":
                        self.assertEqual(row[1], "%s (%s)" % (sg_track2.duration().to_timecode(), sg_track.duration().to_timecode()))
                        checks += 1
                    elif row[0] == "Total Count:":
                        self.assertEqual(row[1], "2 (4)")
                        checks += 1
                    elif row[0] == "Links:":
                        self.assertEqual(row[1], mock_cut_url)
                        checks += 1
                    elif row[0] == "Cut Order":  # Header for edit rows
                        self.assertEqual(checks, 6)
                        in_edits_rows = True
                else:
                    # We one line for cut change, then one line for
                    # the omitted entry
                    if edits_rows_count % 2:
                        old_item = self.sg_cut_items[edits_rows_count // 2]
                        self.assertEqual(row[0], "%s" % (
                            old_item["cut_order"]
                        ))
                        self.assertEqual(row[1], _DIFF_TYPES.OMITTED.name)
                        self.assertEqual(row[2], "%s" % old_item["shot"]["code"])
                        self.assertEqual(row[3], "%s" % old_item["cut_item_duration"])
                        self.assertEqual(row[4], "%s" % old_item["cut_item_in"])
                        self.assertEqual(row[5], "%s" % old_item["cut_item_out"])
                    else:
                        # New cut items start after 4 first old cut items
                        # and two first old items are omitted.
                        item = self.sg_cut_items[edits_rows_count // 2 + 4]
                        old_item = self.sg_cut_items[edits_rows_count // 2 + 2]
                        self.assertEqual(row[0], "%s (%s)" % (
                            item["cut_order"],
                            old_item["cut_order"]
                        ))
                        self.assertEqual(row[1], _DIFF_TYPES.CUT_CHANGE.name)
                        self.assertEqual(row[2], "%s" % item["shot"]["code"])
                        self.assertEqual(row[3], "%s (%s)" % (item["cut_item_duration"], old_item["cut_item_duration"]))
                        if item["cut_item_in"] != old_item["cut_item_in"]:
                            self.assertEqual(row[4], "%s (%s)" % (item["cut_item_in"], old_item["cut_item_in"]))
                        else:
                            self.assertEqual(row[4], "%s" % item["cut_item_in"])
                        if item["cut_item_out"] != old_item["cut_item_out"]:
                            self.assertEqual(row[5], "%s (%s)" % (item["cut_item_out"], old_item["cut_item_out"]))
                        else:
                            self.assertEqual(row[5], "%s" % item["cut_item_out"])
                    edits_rows_count += 1
                logger.debug(row)
            self.assertEqual(edits_rows_count, 4)  # 2 cut changes, 2 omitted edits
        os.remove(csv_path)

        SGSettings().shot_cut_fields_prefix = "myprecious"

        timeline_from_edl = otio.adapters.read_from_file(path)
        new_track = timeline_from_edl.tracks[0]
        # Check that using custom Shot cut fields is handled
        # Validation should fail
        with self.assertRaisesRegex(
            ValueError,
            "Following SG Shot fields are missing",
        ):
            self._get_track_diff(new_track, sg_track, self._mock_compute_clip_shot_name)
        # Bypass validation and check the fields are passed through
        with mock.patch.object(SGShotFieldsConfig, "validate_shot_cut_fields_prefix"):
            track_diff = self._get_track_diff(new_track, sg_track, self._mock_compute_clip_shot_name)
            self.assertEqual(track_diff.count_for_type(_DIFF_TYPES.NO_CHANGE), 4)
            self.assertEqual(track_diff.count_for_type(_DIFF_TYPES.NEW), 28)
            self.assertEqual(len(new_track), track_diff.active_count)

            # Check the custom fields were queried
            expected = [x % "myprecious" for x in _ALT_SHOT_FIELDS]
            for cut_diff in track_diff.diffs_for_type(_DIFF_TYPES.NO_CHANGE):
                self.assertTrue(
                    all([x in cut_diff.sg_shot for x in expected])
                )
            # Check summary CutDiff iteration and Shot values
            for i, (shot_name, clip_group) in enumerate(track_diff.items()):
                self.assertEqual(len(clip_group), 1)
                cut_diff = clip_group[0]
                if i < 4:
                    sg_shot = clip_group.sg_shot
                    self.assertEqual(sg_shot["id"], self.sg_shots[i]["id"])
                    self.assertTrue("sg_myprecious_cut_out" in sg_shot)
                    self.assertTrue("sg_myprecious_status_list" in sg_shot)
                    self.assertTrue("sg_myprecious_working_duration" in sg_shot)
                    self.assertTrue("sg_myprecious_head_in" in sg_shot)
                    self.assertTrue("sg_myprecious_cut_duration" in sg_shot)
                    self.assertTrue("sg_myprecious_cut_order" in sg_shot)
                    self.assertTrue("sg_myprecious_tail_out" in sg_shot)
                    self.assertTrue("sg_myprecious_cut_in" in sg_shot)
                    self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.NO_CHANGE)
                    self.assertEqual(clip_group.index, i + 1)
                    self.assertEqual(clip_group.head_in.to_frames(), self.sg_cut_items[i]["cut_item_in"] - 8)
                    self.assertEqual(clip_group.cut_in.to_frames(), self.sg_cut_items[i]["cut_item_in"])
                    self.assertEqual(clip_group.cut_out.to_frames(), self.sg_cut_items[i]["cut_item_out"])
                    self.assertEqual(clip_group.tail_out.to_frames(), self.sg_cut_items[i]["cut_item_out"] + 8)
                else:
                    self.assertIsNone(clip_group.sg_shot)
                    self.assertEqual(cut_diff.diff_type, _DIFF_TYPES.NEW)

    def test_timecode_frame_mapping_modes(self):
        """
        Test the different mapping modes.
        """
        self._add_sg_cut_data()
        SGSettings().timecode_in_to_frame_mapping_mode = _TC2FRAME_AUTOMATIC_MODE
        path = os.path.join(
            self.resources_dir,
            "edls",
            "R7v26.0_Turnover001_WiP_VFX__1_.edl"
        )

        timeline_from_edl = otio.adapters.read_from_file(path)
        new_track = timeline_from_edl.tracks[0]
        track_diff = self._get_track_diff(new_track, mock_compute_clip_shot_name=self._mock_compute_clip_shot_name)
        self.assertEqual(len(new_track), track_diff.active_count)
        for cut_diff in track_diff.diffs_for_type(_DIFF_TYPES.NEW):
            self.assertEqual(1009, cut_diff.cut_in.to_frames())

        SGSettings().timecode_in_to_frame_mapping_mode = _TC2FRAME_RELATIVE_MODE
        SGSettings().timecode_in_to_frame_relative_mapping = (
            "00:00:00:10",  # 10 frames
            100,
        )
        track_diff = self._get_track_diff(new_track, mock_compute_clip_shot_name=self._mock_compute_clip_shot_name)
        self.assertEqual(len(new_track), track_diff.active_count)
        for cut_diff in track_diff.diffs_for_type(_DIFF_TYPES.NEW):
            self.assertEqual(
                cut_diff.source_in.to_frames() - 10 + 100,
                cut_diff.cut_in.to_frames()
            )
        SGSettings().timecode_in_to_frame_mapping_mode = _TC2FRAME_ABSOLUTE_MODE
        track_diff = self._get_track_diff(new_track, mock_compute_clip_shot_name=self._mock_compute_clip_shot_name)
        self.assertEqual(len(new_track), track_diff.active_count)
        for cut_diff in track_diff.diffs_for_type(_DIFF_TYPES.NEW):
            self.assertEqual(
                cut_diff.source_in.to_frames(),
                cut_diff.cut_in.to_frames()
            )

    def test_sg_version(self):
        """
        Test SG Version retrieval
        """
        self._add_sg_cut_data()
        cut_item = self.sg_cut_items[0]
        old_clip = otio.schema.Clip(
            name="test_clip",
            source_range=otio.opentime.range_from_start_end_time(
                otio.opentime.from_timecode(cut_item["timecode_cut_item_in_text"], 24),
                otio.opentime.from_timecode(cut_item["timecode_cut_item_out_text"], 24)
            )
        )
        old_clip.metadata["sg"] = cut_item
        old_cut_clip = SGCutClip(
            old_clip,
            index=1,
            sg_shot=self.sg_shots[0],
        )
        self.assertIsNone(old_cut_clip.sg_version)
        self.assertIsNone(old_cut_clip.sg_version_name)
        clip = otio.schema.Clip(
            name="test_clip",
            source_range=otio.opentime.range_from_start_end_time(
                otio.opentime.from_timecode(cut_item["timecode_cut_item_in_text"], 24),
                otio.opentime.from_timecode(cut_item["timecode_cut_item_out_text"], 24)
            )
        )
        # If no old clip, the SG Version is retrieved from the current clip
        cut_diff = SGCutDiff(
            clip=clip,
            index=1,
            sg_shot=self.sg_shots[0],
        )
        # Add some dummy media reference
        clip.media_reference = otio.schema.ExternalReference()
        clip.media_reference.name = "Dummy"
        self.assertIsNone(cut_diff.sg_version)
        self.assertIsNone(cut_diff.sg_version_name)
        # Add some SG meta data to the media reference
        clip.media_reference.metadata["sg"] = {
            "type": "PublishedFile",
            "id": -1,
            # Version matching the clip name
            "version": {
                "type": "Version",
                "id": -1,
                # Set a different name for test purpose: in practice the Version name
                # will always match the clip name.
                "code": "FAKE %s" % clip.name
            }
        }
        self.assertEqual(cut_diff.sg_version["id"], -1)
        self.assertEqual(cut_diff.sg_version_name, cut_diff.sg_version["code"])
        # Add an old clip to the diff, that shouldn't change anything
        cut_diff.old_clip = old_cut_clip
        self.assertEqual(cut_diff.sg_version["id"], -1)
        self.assertEqual(cut_diff.sg_version_name, cut_diff.sg_version["code"])
        # If we remove the SG Version meta data on the current clip, nothing
        # should be found
        del clip.media_reference.metadata["sg"]
        self.assertIsNone(cut_diff.sg_version)
        self.assertIsNone(cut_diff.sg_version_name)
        # If we add SG Version meta data to the old clip, it should be used
        old_clip.media_reference = otio.schema.ExternalReference()
        old_clip.media_reference.name = "Old Dummy"
        old_clip.media_reference.metadata["sg"] = {
            "type": "PublishedFile",
            "id": -1,
            # Version matching the clip name
            "version": {
                "type": "Version",
                "id": -2,
                # Set a different name for test purpose: in practice the Version name
                # will always match the clip name.
                "code": "OLD FAKE %s" % clip.name
            }
        }
        self.assertEqual(cut_diff.sg_version["id"], -2)
        self.assertTrue(cut_diff.sg_version_name.startswith("OLD"))
        self.assertEqual(cut_diff.sg_version_name, cut_diff.sg_version["code"])
        # Put back the current SG Version meta data, it should be used.
        clip.media_reference.metadata["sg"] = {
            "type": "PublishedFile",
            "id": -1,
            # Version matching the clip name
            "version": {
                "type": "Version",
                "id": -1,
                # Set a different name for test purpose: in practice the Version name
                # will always match the clip name.
                "code": "FAKE %s" % clip.name
            }
        }
        self.assertEqual(cut_diff.sg_version["id"], -1)
        self.assertTrue(cut_diff.sg_version_name.startswith("FAKE"))
        self.assertEqual(cut_diff.sg_version_name, cut_diff.sg_version["code"])
        # Check Cut Diff whith just an old clip value
        cut_diff = SGCutDiff(
            clip=old_clip,
            index=1,
            sg_shot=self.sg_shots[0],
            as_omitted=True,
        )
        self.assertEqual(cut_diff.sg_version["id"], -2)
        self.assertTrue(cut_diff.sg_version_name.startswith("OLD"))
        self.assertEqual(cut_diff.sg_version_name, cut_diff.sg_version["code"])
        del old_clip.media_reference.metadata["sg"]
        self.assertIsNone(cut_diff.sg_version)
        self.assertIsNone(cut_diff.sg_version_name)

    def test_sg_link(self):
        """
        Test defining the SG link for TrackDiffs
        """
        self._add_sg_cut_data()
        # Compare to Cut from EDL
        path = os.path.join(
            self.resources_dir,
            "edls",
            "R7v26.0_Turnover001_WiP_VFX__1_.edl"
        )
        timeline_from_edl = otio.adapters.read_from_file(path)
        edl_track = timeline_from_edl.tracks[0]
        # No previous Cut information, no explicit SG Entity
        # the Project should be used.
        track_diff = self._get_track_diff(
            edl_track,
            None,
            self._mock_compute_clip_shot_name,
            sg_entity=None
        )
        self.assertEqual(track_diff.sg_link, self.mock_project)
        # We can explicitly set the Project if we want
        track_diff = self._get_track_diff(
            edl_track,
            None,
            self._mock_compute_clip_shot_name,
            sg_entity=self.mock_project
        )
        self.assertEqual(track_diff.sg_link, self.mock_project)
        track_diff = self._get_track_diff(
            edl_track,
            None,
            self._mock_compute_clip_shot_name,
            sg_entity=self.sg_sequences[0]
        )
        self.assertEqual(track_diff.sg_link, self.sg_sequences[0])
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            mock_cut_url = get_read_url(
                self.mock_sg.base_url,
                self.sg_cuts[0]["id"],
                self._SESSION_TOKEN
            )
            # Read it back from SG.
            timeline_from_sg = otio.adapters.read_from_file(mock_cut_url, adapter_name="ShotGrid")
            sg_track = timeline_from_sg.tracks[0]
        # The SG link should be retrieved from the SG Cut track
        track_diff = self._get_track_diff(
            sg_track,
            None,
            self._mock_compute_clip_shot_name,
            sg_entity=None
        )
        self.assertEqual(track_diff.sg_link["type"], self.sg_sequences[0]["type"])
        self.assertEqual(track_diff.sg_link["id"], self.sg_sequences[0]["id"])
        # Using the expected SG link shouldn't cause problem
        track_diff = self._get_track_diff(
            sg_track,
            None,
            self._mock_compute_clip_shot_name,
            sg_entity=self.sg_sequences[0],
        )
        self.assertEqual(track_diff.sg_link["type"], self.sg_sequences[0]["type"])
        self.assertEqual(track_diff.sg_link["id"], self.sg_sequences[0]["id"])
        # Using an unexpected SG link should raise an Exception
        with self.assertRaisesRegex(
            ValueError,
            r"Invalid explicit SG Entity .* not matching existing link"
        ):
            track_diff = self._get_track_diff(
                sg_track,
                None,
                self._mock_compute_clip_shot_name,
                sg_entity=self.sg_sequences[1],
            )
        # Using an unexpected SG Project should raise an Exception
        with self.assertRaisesRegex(
            ValueError,
            r"Invalid explicit SG Entity .* different from SG Project"
        ):
            track_diff = self._get_track_diff(
                sg_track,
                None,
                self._mock_compute_clip_shot_name,
                sg_entity={"type": "Project", "id": 1234456},
            )
        # The SG link should be retrieved from the SG Cut track
        track_diff = self._get_track_diff(
            edl_track,
            sg_track,
            self._mock_compute_clip_shot_name,
            sg_entity=None
        )
        self.assertEqual(track_diff.sg_link["type"], self.sg_sequences[0]["type"])
        self.assertEqual(track_diff.sg_link["id"], self.sg_sequences[0]["id"])
        # Using the expected SG link shouldn't cause problem
        track_diff = self._get_track_diff(
            sg_track,
            None,
            self._mock_compute_clip_shot_name,
            sg_entity=self.sg_sequences[0],
        )
        self.assertEqual(track_diff.sg_link["type"], self.sg_sequences[0]["type"])
        self.assertEqual(track_diff.sg_link["id"], self.sg_sequences[0]["id"])
        # If the previous Cut was linked to the Project, we should get it back
        sg_track.metadata["sg"]["entity"] = self.mock_project
        track_diff = self._get_track_diff(
            edl_track,
            sg_track,
            self._mock_compute_clip_shot_name,
            sg_entity=None
        )
        self.assertEqual(track_diff.sg_link, self.mock_project)
        # If the previous Cut was linked to the Project, we should be able to refine
        # the link with an Entity in the same Project
        sg_track.metadata["sg"]["entity"] = self.mock_project
        track_diff = self._get_track_diff(
            edl_track,
            sg_track,
            self._mock_compute_clip_shot_name,
            sg_entity=self.sg_sequences[1],
        )
        self.assertEqual(track_diff.sg_link, self.sg_sequences[1])

    def test_no_link(self):
        """
        """
        SGSettings().timecode_in_to_frame_mapping_mode = _TC2FRAME_AUTOMATIC_MODE
        path = os.path.join(
            self.resources_dir,
            "media_cutter.edl"
        )
        timeline_from_edl = otio.adapters.read_from_file(path)
        edl_track = timeline_from_edl.tracks[0]
        track_diff = self._get_track_diff(
            edl_track,
            None,
            None,  # Do not provide Shot names
            sg_entity=None
        )
        # Each clip should get its individual group, even if it does not
        # provide a Shot name.
        self.assertEqual(len(track_diff._diffs_by_shots), len(edl_track))
        for shot_key, cut_group in track_diff.items():
            # A dedicated key should be set
            self.assertTrue(shot_key)
            # But Shot related information should be empty
            self.assertIsNone(cut_group.sg_shot)
            self.assertIsNone(cut_group.name)
            for cut_diff in cut_group.clips:
                self.assertIsNone(cut_diff.sg_shot)
                self.assertFalse(cut_diff.repeated)
                self.assertEqual(cut_diff.head_in.to_frames(), 1001)
                self.assertEqual(cut_diff.head_duration.to_frames(), 8)
                self.assertEqual(cut_diff.cut_in.to_frames(), 1009)
                self.assertIsNone(cut_diff.shot_name)
