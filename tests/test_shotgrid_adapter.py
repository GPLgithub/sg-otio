# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging
import os
import re
import tempfile
import unittest

import opentimelineio as otio
import shotgun_api3

from .python.sg_test import SGBaseTest
from sg_otio.constants import _CUT_FIELDS, _CUT_ITEM_FIELDS
from sg_otio.media_cutter import MediaCutter
from sg_otio.sg_settings import SGSettings, SGShotFieldsConfig
from sg_otio.utils import compute_clip_version_name, get_platform_name
from sg_otio.utils import get_write_url, get_read_url
from sg_otio.cut_clip import SGCutClip


try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock

logger = logging.getLogger(__name__)


class ShotgridAdapterTest(SGBaseTest):
    """
    Tests for the ShotGrid adapter.

    To be able to run these tests you need to run pip install -e .[dev] in the parent
    directory.
    """
    def setUp(self):
        """
        Setup the tests suite.
        """
        self.maxDiff = None
        sg_settings = SGSettings()
        sg_settings.reset_to_defaults()
        self.resources_dir = os.path.join(os.path.dirname(__file__), "resources")
        sg_settings.use_clip_names_for_shot_names = True

        super(ShotgridAdapterTest, self).setUp()

        self.mock_sequence = {
            "project": self.mock_project,
            "type": "Sequence",
            "code": "SEQ01",
            "id": 2,
            "sg_cut_order": 2
        }
        self.add_to_sg_mock_db(self.mock_sequence)
        self.mock_sequence_absolute_cut_order = {
            "project": self.mock_project,
            "type": "Sequence",
            "code": "SEQ02",
            "id": 3,
            "sg_cut_order": 3,
            "sg_absolute_cut_order": 3
        }
        self.add_to_sg_mock_db(self.mock_sequence_absolute_cut_order)
        self.path_field = "%s_path" % get_platform_name()
        self.mock_local_storage = {
            "type": "LocalStorage",
            "code": "primary",
            "id": 1,
            self.path_field: tempfile.mkdtemp()}
        self.add_to_sg_mock_db(self.mock_local_storage)
        # Create some Shots
        self.mock_shots = []
        for i in range(1, 4):
            self.mock_shots.append(
                {"type": "Shot", "code": "TestShot%03d" % i, "project": self.mock_project, "id": i}
            )
        self.add_to_sg_mock_db(self.mock_shots)
        # Create a Cut
        self.fps = 24
        self.mock_cut = {
            "type": "Cut",
            "id": 1,
            "code": "Cut01",
            "project": self.mock_project,
            "fps": self.fps,
            "timecode_start_text": "01:00:00:00",
            "timecode_end_text": "01:04:00:00",  # 5760 frames at 24 fps.
            "revision_number": 1,
            "entity": self.mock_sequence,
            "sg_status_list": "ip",
            "image": None,
            "description": "Mocked Cut",
        }
        self.add_to_sg_mock_db(self.mock_cut)
        self.mock_cut_id = self.mock_cut["id"]
        # Create a Version for each Shot
        self.mock_versions = []
        for i, shot in enumerate(self.mock_shots):
            self.mock_versions.append({
                "type": "Version",
                "id": i + 1,
                "project": self.mock_project,
                "entity": shot,
                "code": "%s_v001" % shot["code"],
                "image": "file:///my_image.jpg",
            })
        self.add_to_sg_mock_db(self.mock_versions)
        # Create some Cut Items for each Version/Shot
        self.mock_cut_items = []
        for i, (shot, version) in enumerate(zip(self.mock_shots, self.mock_versions)):
            self.mock_cut_items.append(
                {
                    "type": "CutItem",
                    "id": i + 1,
                    "code": "%s" % version["code"],
                    # FIXME: get real actual values we can check
                    "cut_item_in": 1009,
                    "cut_item_out": 1009 + (self.fps * 60) - 1,
                    "cut_item_duration": self.fps * 60,
                    "timecode_cut_item_in_text": "00:00:00:00",
                    "timecode_cut_item_out_text": "00:01:00:00",
                    "timecode_edit_in_text": "01:%02d:00:00" % i,
                    "timecode_edit_out_text": "01:%02d:00:00" % (i + 1),
                    "edit_in": i * (self.fps * 60) + 1,
                    "edit_out": (i + 1) * (self.fps * 60),
                    "shot": shot,
                    "shot.Shot.code": shot["code"],
                    "version": version,
                    "version.Version.code": version["code"],
                    "version.Version.entity": version["entity"],
                    "version.Version.image": version["image"],
                    "cut": self.mock_cut,
                    "cut.Cut.fps": self.mock_cut["fps"],
                    "cut_order": i + 1,
                }
            )
        self.add_to_sg_mock_db(self.mock_cut_items)
        self._SG_CUT_URL = get_write_url(
            self.mock_sg.base_url,
            "Cut",
            self.mock_cut_id,
            self._SESSION_TOKEN
        )
        self._SG_SEQ_URL = get_write_url(
            self.mock_sg.base_url,
            "Sequence",
            self.mock_sequence["id"],
            self._SESSION_TOKEN
        )
        self._SG_SEQ_ABSOLUTE_CUT_ORDER_URL = get_write_url(
            self.mock_sg.base_url,
            "Sequence",
            self.mock_sequence_absolute_cut_order["id"],
            self._SESSION_TOKEN
        )

    @staticmethod
    def _mock_compute_clip_shot_name(clip):
        """
        Override compute clip shot name to get a unique shot name per clip.
        """
        return "Shot_%d" % (6665 + list(clip.parent().find_clips()).index(clip) + 1)

    def test_read(self):
        """
        Test reading an SG Cut.
        """
        # Note: we need to use the single mocked sg instance created in setUp
        # for all tests.
        # Read the Cut from SG
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            timeline = otio.adapters.read_from_file(
                self._SG_CUT_URL,
                "ShotGrid",
            )
        self.assertEqual(timeline.name, self.mock_cut["code"])
        # We should have a single track for the SG Cut
        tracks = list(timeline.tracks)
        self.assertEqual(len(tracks), 1)
        track = tracks[0]
        # Check the source range which should match Cut values
        self.assertEqual(
            track.source_range.start_time,
            -otio.opentime.from_timecode(self.mock_cut["timecode_start_text"], self.fps),

        )
        self.assertEqual(
            (otio.opentime.from_timecode(self.mock_cut["timecode_start_text"], self.fps) + track.source_range.duration).to_timecode(),
            self.mock_cut["timecode_end_text"],
        )
        # Check the track metadata
        for k, v in self.mock_cut.items():
            if k == "entity":
                # Just check the type and id
                self.assertEqual(track.metadata["sg"][k]["type"], v["type"])
                self.assertEqual(track.metadata["sg"][k]["id"], v["id"])
            else:
                self.assertEqual(track.metadata["sg"][k], v)
        # Check the track clips
        for i, clip in enumerate(track.find_clips()):
            self.assertEqual(clip.name, self.mock_versions[i]["code"])
            self.assertEqual(
                # Cut item in has 1001 + 8 frames more than the source range.
                clip.source_range.start_time + otio.opentime.from_frames(1009, self.fps),
                otio.opentime.RationalTime(
                    self.mock_cut_items[i]["cut_item_in"],
                    self.fps
                )
            )
            self.assertEqual(
                clip.source_range.duration,
                otio.opentime.RationalTime(
                    self.mock_cut_items[i]["cut_item_duration"],
                    self.fps
                )
            )

    def test_read_raises_error_if_overlap(self):
        """
        Test reading a SG Cut with overlapping cut items.
        """
        mock_cut_id = 1000
        mock_cut = {
            "type": "Cut",
            "id": mock_cut_id,
            "code": "Cut_Overlapping_cut_items",
            "project": self.mock_project,
            "fps": self.fps,
            "timecode_start_text": "01:00:00:00",
            "timecode_end_text": "01:02:00:00",  # 5760 frames at 24 fps.
            "revision_number": 1,
            "entity": self.mock_sequence,
            "sg_status_list": "ip",
            "image": None,
            "description": "Mocked Cut",
        }
        # When edit in and edit out are provided, the overlap is calculated with the edit in and out,
        # not the text fields.
        # SG, for edit_in and edit_out, adds 1 frame to the next edit_in, e.g. first clip 1-24, next
        # clip 25-48, etc.
        mock_cut_items = [
            {
                "type": "CutItem",
                "id": 1000,
                "code": "first",
                "cut": mock_cut,
                "timecode_cut_item_in_text": "00:00:00:00",
                "timecode_cut_item_out_text": "00:01:00:00",
                "timecode_edit_in_text": "01:00:00:00",
                "timecode_edit_out_text": "01:01:00:00",
                "edit_in": 1,
                "edit_out": 24,
                "cut_order": 1,
            },
            {
                "type": "CutItem",
                "id": 1001,
                "code": "second",
                "cut": mock_cut,
                "timecode_cut_item_in_text": "00:00:00:00",
                "timecode_cut_item_out_text": "00:01:00:00",
                # One frame overlap with previous
                "timecode_edit_in_text": "01:00:59:00",
                "timecode_edit_out_text": "01:02:00:00",
                "edit_in": 24,
                "edit_out": 48,
                "cut_order": 2,
            }
        ]
        try:
            self.add_to_sg_mock_db(mock_cut)
            self.add_to_sg_mock_db(mock_cut_items)
            SG_CUT_URL = "{}/Cut?session_token={}&id={}".format(
                self.mock_sg.base_url,
                self._SESSION_TOKEN,
                mock_cut_id
            )
            with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
                with self.assertRaises(ValueError) as cm:
                    otio.adapters.read_from_file(
                        SG_CUT_URL,
                        "ShotGrid",
                    )
                self.assertIn(
                    "Overlapping cut items detected",
                    str(cm.exception)
                )

            # Now test with the edit in and edit out text fields.
            self.mock_sg.update("CutItem", 1000, {"edit_out": None})
            self.mock_sg.update("CutItem", 1001, {"edit_in": None})
            with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
                with self.assertRaises(ValueError) as cm:
                    otio.adapters.read_from_file(
                        SG_CUT_URL,
                        "ShotGrid",
                    )
                self.assertIn(
                    "Overlapping cut items detected",
                    str(cm.exception)
                )
        finally:
            self.mock_sg.delete("Cut", mock_cut_id)
            self.mock_sg.delete("CutItem", 1000)
            self.mock_sg.delete("CutItem", 1001)

    def test_read_adds_gap(self):
        """
        Test that reading a SG Cut with gaps also adds gaps to the track.
        """
        mock_cut_id = 1000
        mock_cut = {
            "type": "Cut",
            "id": mock_cut_id,
            "code": "Cut_with_gaps",
            "project": self.mock_project,
            "fps": self.fps,
            "timecode_start_text": "01:00:00:00",
            "timecode_end_text": "01:03:00:00",  # 5760 frames at 24 fps.
            "revision_number": 1,
            "entity": self.mock_sequence,
            "sg_status_list": "ip",
            "image": None,
            "description": "Mocked Cut",
        }
        mock_cut_items = [
            {
                "type": "CutItem",
                "id": 1000,
                "code": "first",
                "cut": mock_cut,
                "timecode_cut_item_in_text": "00:00:00:00",
                "timecode_cut_item_out_text": "00:01:00:00",
                "timecode_edit_in_text": "01:00:00:00",
                "timecode_edit_out_text": "01:01:00:00",
                "edit_in": 1,
                "edit_out": 24,
                "cut_order": 1,
            },
            {
                "type": "CutItem",
                "id": 1001,
                "code": "second",
                "cut": mock_cut,
                "timecode_cut_item_in_text": "00:00:00:00",
                "timecode_cut_item_out_text": "00:01:00:00",
                "timecode_edit_in_text": "01:02:00:00",
                "timecode_edit_out_text": "01:03:00:00",
                "edit_in": 49,
                "edit_out": 72,
                "cut_order": 2,
            }
        ]
        try:
            self.add_to_sg_mock_db(mock_cut)
            self.add_to_sg_mock_db(mock_cut_items)
            SG_CUT_URL = "{}/Cut?session_token={}&id={}".format(
                self.mock_sg.base_url,
                self._SESSION_TOKEN,
                mock_cut_id
            )
            with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
                timeline = otio.adapters.read_from_file(
                    SG_CUT_URL,
                    "ShotGrid",
                )
            tracks = list(timeline.tracks)
            self.assertEqual(len(tracks), 1)
            track = tracks[0]
            clips = list(track.find_clips())
            self.assertEqual(len(clips), 2)
            children = list(track.find_children())
            self.assertEqual(len(children), 3)
            self.assertTrue(isinstance(children[0], otio.schema.Clip))
            self.assertTrue(isinstance(children[2], otio.schema.Clip))
            gap = children[1]
            self.assertTrue(isinstance(gap, otio.schema.Gap))
            source_range = otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, self.fps),
                duration=otio.opentime.RationalTime(24, self.fps)
            )
            self.assertEqual(gap.source_range, source_range)
        finally:
            self.mock_sg.delete("Cut", mock_cut_id)
            self.mock_sg.delete("CutItem", 1000)
            self.mock_sg.delete("CutItem", 1001)

    def test_read_write_sg_cut(self):
        """
        Test reading an SG Cut, saving it to otio and writing it to SG.
        """
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            # Just make sure that finding entities by name is case insensitive
            # like for regular SG.
            sg_shot = self.mock_sg.find_one("Shot", [["code", "is", self.mock_shots[0]["code"]]])
            self.assertIsNotNone(sg_shot)
            sg_shot = self.mock_sg.find_one("Shot", [["code", "is", self.mock_shots[0]["code"].lower()]])
            self.assertIsNotNone(sg_shot)
            self.mock_sg.update(
                sg_shot["type"],
                sg_shot["id"],
                {"sg_status_list": SGSettings().shot_omit_status}
            )
            timeline = otio.adapters.read_from_file(
                self._SG_CUT_URL,
                "ShotGrid",
            )
            tmp_path = tempfile.mkdtemp()
            # Save the timeline to otio format
            otio_file = os.path.join(tmp_path, "test_read_write_sg_cut.otio")
            otio.adapters.write_to_file(timeline, otio_file)
            # Read it back and check the result
            timeline = otio.adapters.read_from_file(otio_file)
            self.assertEqual(timeline.name, self.mock_cut["code"])
            # We should have a single track for the SG Cut
            tracks = list(timeline.tracks)
            self.assertEqual(len(tracks), 1)
            track = tracks[0]
            # Check the source range which should match Cut values
            self.assertEqual(
                track.source_range.start_time,
                -otio.opentime.from_timecode(self.mock_cut["timecode_start_text"], self.fps),
            )

            # Check the track metadata
            for k, v in self.mock_cut.items():
                logger.info(
                    "Checking meta data %s %s vs %s" % (k, track.metadata["sg"][k], v)
                )
                if k == "entity":
                    # Just check the type and id
                    self.assertEqual(track.metadata["sg"][k]["type"], v["type"])
                    self.assertEqual(track.metadata["sg"][k]["id"], v["id"])
                    self.assertEqual(track.metadata["sg"][k]["name"], v["code"])
                else:
                    self.assertEqual(track.metadata["sg"][k], v)
            # Check the track clips
            for i, clip in enumerate(track.find_clips()):
                sg_data = clip.metadata["sg"]
                self.assertEqual(sg_data["type"], "CutItem")
                cut_item = self.mock_cut_items[i]
                for k, v in cut_item.items():
                    if isinstance(v, dict):
                        # Just check the type and id
                        self.assertEqual(sg_data[k]["type"], v["type"])
                        self.assertEqual(sg_data[k]["id"], v["id"])
                    else:
                        self.assertEqual(sg_data[k], v)
            self.assertEqual(i + 1, len(self.mock_cut_items))
            # Now write it back to SG
            otio.adapters.write_to_file(timeline, self._SG_CUT_URL, "ShotGrid")
            sg_cuts = self.mock_sg.find("Cut", [["id", "is_not", self.mock_cut["id"]]], _CUT_FIELDS)
            # We should have updated the existing Cut
            self.assertEqual(len(sg_cuts), 0)
            # We should have the same number of cut items (the previously existing ones)
            sg_cut_items = self.mock_sg.find(
                "CutItem", [["cut", "is", self.mock_cut]], _CUT_ITEM_FIELDS,
                order=[{"field_name": "cut_order", "direction": "asc"}]
            )
            self.assertEqual(len(self.mock_cut_items), len(sg_cut_items))

            # Create a new Cut linked to the test Sequence
            otio.adapters.write_to_file(timeline, self._SG_SEQ_URL, "ShotGrid")
            sg_cuts = self.mock_sg.find("Cut", [["id", "is_not", self.mock_cut["id"]]], _CUT_FIELDS)
            # We should now have a second Cut with all CutItems duplicated
            self.assertEqual(len(sg_cuts), 1)
            # Check values are identical
            for field in _CUT_FIELDS:
                logger.info("Checking Cut %s" % field)
                if field == "revision_number":
                    self.assertEqual(sg_cuts[0][field], self.mock_cut[field] + 1)
                elif field not in ["id", "created_by", "updated_by", "updated_at", "created_at", "description"]:
                    if isinstance(sg_cuts[0][field], dict):
                        self.assertEqual(sg_cuts[0][field]["type"], self.mock_cut[field]["type"])
                        self.assertEqual(sg_cuts[0][field]["id"], self.mock_cut[field]["id"])
                    else:
                        self.assertEqual(sg_cuts[0][field], self.mock_cut[field])
            sg_cut_items = self.mock_sg.find(
                "CutItem", [["cut", "is", sg_cuts[0]]], _CUT_ITEM_FIELDS,
                order=[{"field_name": "cut_order", "direction": "asc"}]
            )
            self.assertEqual(len(sg_cut_items), len(self.mock_cut_items))
            for i, sg_cut_item in enumerate(sg_cut_items):
                for field in _CUT_ITEM_FIELDS:

                    if field not in [
                        "id", "cut", "created_by", "updated_by", "updated_at", "created_at", "shot.Shot.code",
                        # Not yet implemented
                        "version", "version.Version.code", "version.Version.entity", "version.Version.id",
                        "version.Version.image",
                    ]:
                        logger.info(
                            "Checking item %d %s %s vs %s" % (i, field, sg_cut_item[field], self.mock_cut_items[i][field])
                        )
                        if isinstance(sg_cut_item[field], dict):
                            self.assertEqual(
                                sg_cut_item[field]["type"], self.mock_cut_items[i][field]["type"]
                            )
                            self.assertEqual(sg_cut_item[field]["id"], self.mock_cut_items[i][field]["id"])
                        else:
                            self.assertEqual(sg_cut_item[field], self.mock_cut_items[i][field])

            # Check the SG metadata
            self.assertEqual(track.metadata["sg"]["id"], sg_cuts[0]["id"])
            for i, clip in enumerate(track.find_clips()):
                self.assertEqual(clip.metadata["sg"]["type"], "CutItem")
                self.assertEqual(clip.metadata["sg"]["id"], sg_cut_items[i]["id"])

    def test_read_write_absolute_cut_order(self):
        """
        Test that absolute cut order/entity cut order work as expected.
        """
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            timeline = otio.adapters.read_from_file(
                self._SG_CUT_URL,
                "ShotGrid",
            )
        track = timeline.tracks[0]
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            otio.adapters.write_to_file(timeline, self._SG_SEQ_ABSOLUTE_CUT_ORDER_URL, "ShotGrid")
            track = timeline.tracks[0]
            self.assertIsNotNone(track.metadata.get("sg"))
            sg_data = track.metadata["sg"]
            self.assertEqual(sg_data["type"], "Cut")
            self.assertIsNotNone(sg_data.get("id"))
            # Retrieve the Cut from SG
            sg_cut = self.mock_sg.find_one("Cut", [["id", "is", sg_data["id"]]], [])
            self.assertIsNotNone(sg_cut)
            # Retrieve the CutItems
            sg_cut_items = self.mock_sg.find(
                "CutItem", [["cut", "is", sg_cut]], [],
                order=[{"field_name": "cut_order", "direction": "asc"}]
            )
            self.assertEqual(len(sg_cut_items), 3)
            for i, clip in enumerate(track.find_clips()):
                metadata_sg_shot = clip.metadata["sg"]["shot"]
                sg_shot = self.mock_sg.find_one("Shot", [["id", "is", metadata_sg_shot["id"]]], ["sg_absolute_cut_order", "code"])
                # Cut order should be 1000 * entity_cut_order + cut_item["cut_order"]
                entity_cut_order = self.mock_sequence_absolute_cut_order["sg_absolute_cut_order"]
                self.assertEqual(sg_shot["sg_absolute_cut_order"], 1000 * entity_cut_order + clip.metadata["sg"]["cut_order"])

    def test_read_write_to_edl(self):
        """
        Test reading from SG and writing to an EDL.
        """
        # Note: we need to use the single mocked sg instance created in setUp
        # for all tests.
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            timeline = otio.adapters.read_from_file(
                self._SG_CUT_URL,
                "ShotGrid",
            )
        edl_text = otio.adapters.write_to_string(timeline, adapter_name="cmx_3600")
        expected_edl_text = (
            "TITLE: Cut01\n\n"
            "001  TestShot001_v001 V     C        00:00:00:00 00:01:00:00 01:00:00:00 01:01:00:00\n"
            "* FROM CLIP NAME:  TestShot001_v001\n"
            "002  TestShot002_v001 V     C        00:00:00:00 00:01:00:00 01:01:00:00 01:02:00:00\n"
            "* FROM CLIP NAME:  TestShot002_v001\n"
            "003  TestShot003_v001 V     C        00:00:00:00 00:01:00:00 01:02:00:00 01:03:00:00\n"
            "* FROM CLIP NAME:  TestShot003_v001\n"
        )
        self.assertMultiLineEqual(edl_text, expected_edl_text)
        # Read back the EDL and write to SG
        timeline = otio.adapters.read_from_string(expected_edl_text, adapter_name="cmx_3600")
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            otio.adapters.write_to_file(timeline, self._SG_SEQ_URL, "ShotGrid")
            track = timeline.tracks[0]
            self.assertIsNotNone(track.metadata.get("sg"))
            sg_data = track.metadata["sg"]
            self.assertEqual(sg_data["type"], "Cut")
            self.assertIsNotNone(sg_data.get("id"))
            # Retrieve the Cut from SG
            sg_cut = self.mock_sg.find_one("Cut", [["id", "is", sg_data["id"]]], [])
            self.assertIsNotNone(sg_cut)
            # Retrieve the CutItems
            sg_cut_items = self.mock_sg.find(
                "CutItem", [["cut", "is", sg_cut]], [],
                order=[{"field_name": "cut_order", "direction": "asc"}]
            )
            self.assertEqual(len(sg_cut_items), 3)
            for i, clip in enumerate(track.find_clips()):
                self.assertEqual(clip.metadata["sg"]["id"], sg_cut_items[i]["id"])

    def test_write_read_edl_with_versions(self):
        """
        Test that when we write to SG, we create a new version for each CutItem.
        """
        settings = SGSettings()
        # The default settings create Versions for each CutItem, e.g. settings.create_missing_versions = True
        settings.reset_to_defaults()
        # The default template uses UUID, let's test with a more simple template
        settings.version_names_template = "from_edl_{SHOT}_{CLIP_NAME}_{CLIP_INDEX:04d}"
        # Create a cut with no Cut Items
        mock_cut = {
            "type": "Cut",
            "id": 1000,
            "code": "Cut_with_versions",
            "project": self.mock_project,
            "entity": self.mock_sequence,
        }
        mock_cut_url = get_write_url(
            self.mock_sg.base_url,
            "Cut",
            mock_cut["id"],
            self._SESSION_TOKEN
        )
        self.add_to_sg_mock_db(mock_cut)
        try:
            edl = """
            TITLE: Cut01
            000001 green_tape     V     C        00:00:00:00 00:00:00:16 01:00:00:00 01:00:00:16
            * COMMENT : 001
            * FROM CLIP NAME: green.mov
            000002 pink_tape      V     C        00:00:00:05 00:00:00:11 01:00:00:16 01:00:00:22
            * COMMENT : 002
            * FROM CLIP NAME: pink.mov
            000003 green_tape     V     C        00:00:00:05 00:00:00:16 01:00:00:22 01:00:01:09
            * COMMENT : 003
            * FROM CLIP NAME: green.mov
            000004 red_tape       V     C        00:00:00:12 00:00:01:00 01:00:01:09 01:00:01:21
            * COMMENT : 004
            * FROM CLIP NAME: red.mov
            000005 blue_tape      V     C        00:00:00:00 00:00:02:00 01:00:01:21 01:00:03:21
            * FROM CLIP NAME: blue.mov
            000006 red_tape       V     C        00:00:00:00 00:00:00:13 01:00:03:21 01:00:04:10
            * FROM CLIP NAME: red.mov
            """
            edl_movie = os.path.join(self.resources_dir, "media_cutter.mov")
            timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
            media_cutter = MediaCutter(timeline, edl_movie)
            media_cutter.cut_media_for_clips()
            with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
                with mock.patch("sg_otio.clip_group.compute_clip_shot_name", wraps=self._mock_compute_clip_shot_name):
                    otio.adapters.write_to_file(timeline, mock_cut_url, "ShotGrid", input_media=edl_movie)
                # We should now have 6 new Shots
                sg_shots = self.mock_sg.find(
                    "Shot",
                    [["code", "starts_with", "shot_"]],
                    ["code"],
                )
                self.assertEqual(len(sg_shots), 6)
                # Name case should have been preserved
                for sg_shot in sg_shots:
                    self.assertTrue(sg_shot["code"].startswith("Shot_"))
                # We should have Versions created linked to Shots
                sg_versions = self.mock_sg.find(
                    "Version",
                    [
                        ["code", "starts_with", "from_edl_"],
                        ["entity", "type_is", "Shot"]
                    ],
                    ["code", "entity"]
                )
                self.assertEqual(len(sg_versions), 6)

                # Let's read it from SG.
                timeline_from_sg = otio.adapters.read_from_file(mock_cut_url, adapter_name="ShotGrid")

            # Check all the information relevant to media references is correct.
            for i, (orig_clip, clip) in enumerate(zip(timeline.find_clips(), timeline_from_sg.find_clips())):
                clip_version_name = compute_clip_version_name(orig_clip, i + 1)
                self.assertEqual(orig_clip.media_reference.name, clip_version_name)
                self.assertEqual(orig_clip.media_reference.name, clip.media_reference.name)
                self.assertEqual(orig_clip.media_reference.target_url, clip.media_reference.target_url)
                self.assertEqual(orig_clip.media_reference.available_range, clip.media_reference.available_range)
                orig_clip_pf = orig_clip.media_reference.metadata["sg"]
                clip_pf = clip.media_reference.metadata["sg"]
                all_fields = list(set(orig_clip_pf.keys()) | set(clip_pf.keys()))
                for field in all_fields:
                    # The only fields that we don't have when we write compared to when we read are the
                    # version.Version fields
                    if not field.startswith("version.Version"):
                        # If a dict and not "path" assume an Entity dict and only
                        # check the type and id
                        if isinstance(orig_clip_pf[field], (dict, otio._otio.AnyDictionary)) and field != "path":
                            self.assertEqual(orig_clip_pf[field]["type"], clip_pf[field]["type"])
                            self.assertEqual(orig_clip_pf[field]["id"], clip_pf[field]["id"])
                        else:
                            self.assertEqual(orig_clip_pf[field], clip_pf[field])
                self.assertEqual(orig_clip.metadata["sg"]["version"], clip.metadata["sg"]["version"])
                # TODO: test published file dependencies, but mockgun does not populate upstream_dependencies
        finally:
            self.mock_sg.delete("Cut", mock_cut["id"])

    def test_write_read_premiere_xml_with_versions(self):
        """
        Test that when we write to SG from a Premiere xml with media references,
        when we read it back from SG we get the same information.
        """
        settings = SGSettings()
        # The default settings create Versions for each CutItem, e.g. settings.create_missing_versions = True
        settings.reset_to_defaults()
        # The default template uses UUID, let's test with a more simple template
        settings.version_names_template = "from_premiere_{SHOT}_{CLIP_NAME}_{CLIP_INDEX:04d}"
        # The clip used in the Premiere xml is from frame 0 to frame 48,
        # but only frames 5 to 25 are in the track.
        # Note that we don't use media cutter, the media ref comes straight from Premiere.
        xml_file = os.path.join(self.resources_dir, "blue_frame_5_to_25.xml")
        timeline = otio.adapters.read_from_file(xml_file)
        # The path to the media is relative to the machine, replace it.
        clip = list(timeline.find_clips())[0]
        file_path = os.path.join(self.resources_dir, "blue.mov")
        # Premiere prepends its path with file://localhost, and then an absolute path.
        # Keep it to test it would work properly.
        clip.media_reference.target_url = "file://localhost" + file_path
        mock_cut = {
            "type": "Cut",
            "id": 1000,
            "code": "Cut_with_versions",
            "project": self.mock_project,
        }
        mock_cut_url = get_write_url(
            self.mock_sg.base_url,
            "Cut",
            mock_cut["id"],
            self._SESSION_TOKEN
        )
        self.add_to_sg_mock_db(mock_cut)
        try:
            with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
                with mock.patch("sg_otio.clip_group.compute_clip_shot_name", wraps=self._mock_compute_clip_shot_name):
                    otio.adapters.write_to_file(timeline, mock_cut_url, "ShotGrid")
                # We should now have 1 new Shot
                sg_shots = self.mock_sg.find(
                    "Shot",
                    [["code", "starts_with", "shot_"]],
                    ["code"],
                )
                self.assertEqual(len(sg_shots), 1)
                # We should have Versions created linked to Shots
                sg_versions = self.mock_sg.find(
                    "Version",
                    [
                        ["code", "starts_with", "from_premiere_"],
                        ["entity", "type_is", "Shot"]
                    ],
                    ["code", "entity"]
                )
                self.assertEqual(len(sg_versions), 1)
                timeline_from_sg = otio.adapters.read_from_file(mock_cut_url, adapter_name="ShotGrid")
            # Check all the information relevant to media references and ranges is correct.
            for i, (orig_clip, clip) in enumerate(zip(timeline.find_clips(), timeline_from_sg.find_clips())):
                self.assertEqual(orig_clip.media_reference.target_url, clip.media_reference.target_url)
                # In the case of this test, the available range is different than the visible range.
                # Since we know the values from the files, also check them.
                self.assertEqual(orig_clip.visible_range(), clip.visible_range())
                self.assertEqual(orig_clip.visible_range().start_time.to_frames(), 5)
                self.assertEqual(orig_clip.visible_range().duration.to_frames(), 20)
                self.assertEqual(orig_clip.available_range(), clip.available_range())
                self.assertEqual(orig_clip.available_range().start_time.to_frames(), 0)
                self.assertEqual(orig_clip.available_range().duration.to_frames(), 48)
                orig_clip_pf = orig_clip.media_reference.metadata["sg"]
                clip_pf = clip.media_reference.metadata["sg"]
                all_fields = list(set(orig_clip_pf.keys()) | set(clip_pf.keys()))
                for field in all_fields:
                    # The only fields that we don't have when we write compared to when we read are the
                    # version.Version fields
                    if not field.startswith("version.Version"):
                        # If a dict and not "path" assume an Entity dict and only
                        # check the type and id
                        if isinstance(orig_clip_pf[field], (dict, otio._otio.AnyDictionary)) and field != "path":
                            self.assertEqual(orig_clip_pf[field]["type"], clip_pf[field]["type"])
                            self.assertEqual(orig_clip_pf[field]["id"], clip_pf[field]["id"])
                        else:
                            self.assertEqual(orig_clip_pf[field], clip_pf[field])
        finally:
            self.mock_sg.delete("Cut", mock_cut["id"])

    def test_unique_cut_items(self):
        """
        Test that cut item names for a SG Cut are unique.
        """
        edl = """
        TITLE: Cut01
        000001 reelname     V     C        00:00:00:00 00:00:00:16 01:00:00:00 01:00:00:16
        000002 other_reelname      V     C        00:00:00:05 00:00:00:11 01:00:00:16 01:00:00:22
        000003 reelname     V     C        00:00:00:05 00:00:00:16 01:00:00:22 01:00:01:09
        000004 other_reelname       V     C        00:00:00:12 00:00:01:00 01:00:01:09 01:00:01:21
        """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        track = timeline.tracks[0]
        # Check all clips have the same name
        for clip in track.find_clips():
            self.assertIn(SGCutClip(clip).name, ["reelname", "other_reelname"])
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            otio.adapters.write_to_file(timeline, self._SG_SEQ_URL, "ShotGrid")
            # All should have different names
            names = []
            for i, clip in enumerate(track.find_clips()):
                self.assertIsNotNone(clip.metadata.get("sg"))
                self.assertNotIn(clip.metadata["sg"]["code"], names)
                names.append(clip.metadata["sg"]["code"])
                # Check it has the expected form
                self.assertTrue(
                    re.match(
                        r"^%s(_\d+)?" % SGCutClip(clip).name,
                        clip.metadata["sg"]["code"]
                    )
                )

    def test_write_shot(self):
        """
        Test saving a Cut to SG with Shots created from the save.
        """
        edl = """
            TITLE:   CUT_DIFF_TEST

            001  clip_1 V     C        01:00:01:00 01:00:10:00 01:00:00:00 01:00:09:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: test_write_shot_SHOT_001
            002  clip_2 V     C        01:00:02:00 01:00:05:00 01:00:09:00 01:00:12:00
            * FROM CLIP NAME: shot_002_v001
            * COMMENT: test_write_shot_shot_002
            003  clip_3 V     C        01:00:00:00 01:00:04:00 01:00:12:00 01:00:16:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: test_write_shot_shot_001
        """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        track = timeline.tracks[0]
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            otio.adapters.write_to_file(timeline, self._SG_SEQ_URL, "ShotGrid")
            clip = track[0]
            self.assertEqual(clip.metadata["sg"]["cut_order"], 1)
            self.assertEqual(clip.metadata["sg"]["cut_item_in"], 1033)
            self.assertEqual(clip.metadata["sg"]["shot"]["code"], "test_write_shot_SHOT_001")
            clip = track[1]
            self.assertEqual(clip.metadata["sg"]["cut_order"], 2)
            self.assertEqual(clip.metadata["sg"]["cut_item_in"], 1009)
            clip = track[2]
            self.assertEqual(clip.metadata["sg"]["cut_order"], 3)
            self.assertEqual(clip.metadata["sg"]["cut_item_in"], 1009)
            # Shot name case taken from first entry
            self.assertEqual(clip.metadata["sg"]["shot"]["code"], "test_write_shot_SHOT_001")

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
            self.assertEqual(clip.metadata["sg"]["shot"]["code"], "test_write_shot_SHOT_001")
            clip = sg_track[1]
            self.assertEqual(clip.metadata["sg"]["cut_item_in"], 1009)
            clip = sg_track[2]
            self.assertEqual(clip.metadata["sg"]["cut_item_in"], 1009)
            self.assertEqual(clip.metadata["sg"]["shot"]["code"], "test_write_shot_SHOT_001")

    def test_read_shot_fields(self):
        """
        Test that we get all the Shot fields we need when reading Cuts from SG.
        """
        # Test with default settings
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            timeline = otio.adapters.read_from_file(
                self._SG_CUT_URL,
                "ShotGrid",
            )
        track = timeline.tracks[0]
        link = track.metadata["sg"]["entity"]
        fields_conf = SGShotFieldsConfig(self.mock_sg, link["type"])
        for clip in track:
            sg_meta = clip.metadata["sg"]
            sg_shot = sg_meta["shot"]
            for field in fields_conf.all:
                self.assertTrue(field in sg_shot)
        # Test with smart fields
        SGSettings().use_smart_fields = True
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            timeline = otio.adapters.read_from_file(
                self._SG_CUT_URL,
                "ShotGrid",
            )
        track = timeline.tracks[0]
        link = track.metadata["sg"]["entity"]
        fields_conf = SGShotFieldsConfig(self.mock_sg, link["type"])
        for clip in track:
            sg_meta = clip.metadata["sg"]
            sg_shot = sg_meta["shot"]
            for field in fields_conf.all:
                self.assertTrue(field in sg_shot)
        # Test with alternate fields
        SGSettings().shot_cut_fields_prefix = "myprecious"
        with mock.patch.object(SGShotFieldsConfig, "validate_shot_cut_fields_prefix"):
            with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
                timeline = otio.adapters.read_from_file(
                    self._SG_CUT_URL,
                    "ShotGrid",
                )
            track = timeline.tracks[0]
            link = track.metadata["sg"]["entity"]
            fields_conf = SGShotFieldsConfig(self.mock_sg, link["type"])
        for clip in track:
            sg_meta = clip.metadata["sg"]
            sg_shot = sg_meta["shot"]
            for field in fields_conf.all:
                self.assertTrue(field in sg_shot)


if __name__ == "__main__":
    unittest.main()
