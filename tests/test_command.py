# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import csv
import logging
import os
import tempfile

import shotgun_api3

from .python.sg_test import SGBaseTest

import opentimelineio as otio

from sg_otio.command import SGOtioCommand
from sg_otio.sg_settings import SGSettings
from sg_otio.utils import get_write_url
from sg_otio.track_diff import SGTrackDiff


try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock

logger = logging.getLogger(__name__)


class TestCommand(SGBaseTest):
    """
    Test related to computing differences between two Cuts
    """
    def setUp(self):
        """
        Called before each test.
        """
        super(TestCommand, self).setUp()
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
        Add some SG data used by tests.
        """
        # SG is case insensitive but mockgun is case sensitive so better to
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
            "revision_number": 1,
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
        }]
        self.add_to_sg_mock_db(self.sg_cut_items)
        self._sg_entities_to_delete.extend(self.sg_cut_items)

    @staticmethod
    def _mock_compute_clip_shot_name(clip):
        """
        Override compute clip shot name to get a unique shot name per clip.
        """
        return "shot_%d" % (6665 + list(clip.parent().find_clips()).index(clip) + 1)

    def tearDown(self):
        """
        Called inconditionally after each test.
        """
        super(TestCommand, self).tearDown()
        for sg_entity in self._sg_entities_to_delete:
            logger.debug("Deleting %s %s" % (sg_entity["type"], sg_entity["id"]))
            self.mock_sg.delete(sg_entity["type"], sg_entity["id"])
        self._sg_entities_to_delete = []

    def test_commands(self):
        """
        Test commands.
        """
        self._add_sg_cut_data()
        command = SGOtioCommand(self.mock_sg)
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            with mock.patch("sg_otio.track_diff.compute_clip_shot_name", wraps=self._mock_compute_clip_shot_name):
                with mock.patch("sg_otio.cut_clip.compute_clip_shot_name", wraps=self._mock_compute_clip_shot_name):
                    _, path = tempfile.mkstemp(suffix=".otio")
                    # Check read command
                    command.read_from_sg(
                        sg_cut_id=self.sg_cuts[0]["id"],
                        file_path=path,
                    )
                    timeline = otio.adapters.read_from_file(path)
                    self.assertEqual(len(timeline.tracks), 1)
                    track = timeline.tracks[0]
                    self.assertIsNotNone(track.metadata.get("sg"))
                    sg_data = track.metadata["sg"]
                    self.assertEqual(sg_data["type"], "Cut")
                    self.assertEqual(sg_data["id"], self.sg_cuts[0]["id"])
                    self.assertEqual(len(track), len(self.sg_cut_items))
                    for i, clip in enumerate(track.find_clips()):
                        # Just check basic stuff
                        self.assertEqual(clip.name, self.sg_cut_items[i]["code"])
                        self.assertEqual(
                            clip.source_range.duration,
                            otio.opentime.RationalTime(
                                self.sg_cut_items[i]["cut_item_duration"],
                                24,
                            )
                        )
                    # Check compare command, write new Cut to SG
                    command.compare_to_sg(file_path=path, sg_cut_id=self.sg_cuts[0]["id"], write=True)
                    new_cut = self.mock_sg.find_one(
                        "Cut",
                        [["id", "greater_than", self.sg_cuts[0]["id"]]],
                    )
                    self.assertTrue(new_cut)
                    self._sg_entities_to_delete.append(new_cut)

                    # Check we can save reports
                    _, report_path = tempfile.mkstemp(suffix=".txt")
                    command.compare_to_sg(file_path=path, sg_cut_id=self.sg_cuts[0]["id"], report_path=report_path)
                    self.assertTrue(os.path.isfile(report_path))
                    _, report_path = tempfile.mkstemp(suffix=".csv")
                    command.compare_to_sg(file_path=path, sg_cut_id=self.sg_cuts[0]["id"], report_path=report_path)
                    self.assertTrue(os.path.isfile(report_path))
                    with open(report_path, newline="") as csvfile:
                        reader = csv.reader(csvfile)
                        # Just check that we have more rows than the number
                        # of items
                        self.assertTrue(len([row for row in reader]) > len(self.sg_cut_items))

                    _, new_path = tempfile.mkstemp(suffix=".otio")
                    command.read_from_sg(
                        sg_cut_id=new_cut["id"],
                        file_path=new_path,
                    )
                    new_timeline = otio.adapters.read_from_file(new_path)
                    self.assertEqual(len(new_timeline.tracks), 1)
                    new_track = new_timeline.tracks[0]
                    self.assertIsNotNone(new_track.metadata.get("sg"))
                    sg_data = new_track.metadata["sg"]
                    self.assertEqual(sg_data["type"], "Cut")
                    self.assertEqual(sg_data["id"], new_cut["id"])
                    self.assertEqual(len(new_track), len(self.sg_cut_items))
                    for i, clip in enumerate(new_track.find_clips()):
                        # Just check basic stuff
                        self.assertEqual(clip.name, self.sg_cut_items[i]["code"])
                        self.assertEqual(
                            clip.source_range.duration,
                            otio.opentime.RationalTime(
                                self.sg_cut_items[i]["cut_item_duration"],
                                24,
                            )
                        )
                    # Check write command
                    command.write_to_sg(new_path, self.sg_sequences[0]["type"], self.sg_sequences[0]["id"])
                    new_cut2 = self.mock_sg.find_one(
                        "Cut",
                        [["id", "greater_than", new_cut["id"]]],
                    )
                    self.assertTrue(new_cut2)
                    self._sg_entities_to_delete.append(new_cut2)
                    command.read_from_sg(
                        sg_cut_id=new_cut2["id"],
                        file_path=new_path,
                    )
                    new_timeline = otio.adapters.read_from_file(new_path)
                    self.assertEqual(len(new_timeline.tracks), 1)
                    new_track = new_timeline.tracks[0]
                    self.assertIsNotNone(new_track.metadata.get("sg"))
                    sg_data = new_track.metadata["sg"]
                    self.assertEqual(sg_data["type"], "Cut")
                    self.assertEqual(sg_data["id"], new_cut2["id"])
                    self.assertEqual(len(new_track), len(self.sg_cut_items))
                    for i, clip in enumerate(new_track.find_clips()):
                        # Just check basic stuff
                        self.assertEqual(clip.name, self.sg_cut_items[i]["code"])
                        self.assertEqual(
                            clip.source_range.duration,
                            otio.opentime.RationalTime(
                                self.sg_cut_items[i]["cut_item_duration"],
                                24,
                            )
                        )
                    with mock.patch.object(SGTrackDiff, "sg_link", new_callable=mock.PropertyMock) as mocked:
                        mocked.return_value = None
                        with self.assertRaisesRegex(
                            ValueError,
                            "Can't update a Cut without a SG link"
                        ):
                            command.compare_to_sg(file_path=path, sg_cut_id=new_cut2["id"], write=True)
            os.remove(path)
            os.remove(new_path)
