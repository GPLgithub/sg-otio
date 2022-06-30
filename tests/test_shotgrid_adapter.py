import datetime
import logging
import os
import sys
import tempfile
import unittest
from functools import partial

import opentimelineio as otio
import shotgun_api3
from shotgun_api3.lib import mockgun

from sg_otio.constants import _CUT_FIELDS, _CUT_ITEM_FIELDS
from sg_otio.cut_track import CutTrack
from sg_otio.media_cutter import MediaCutter
from sg_otio.sg_settings import SGSettings
from sg_otio.utils import compute_clip_version_name

try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock

logger = logging.getLogger(__name__)
logger.setLevel(SGSettings().log_level)


class ShotgridAdapterTest(unittest.TestCase):
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
        # Retrieve SG credentials from the environment
        # The SG site
        self._SG_SITE = os.getenv("SG_TEST_SITE") or "https://mysite.shotgunstudio.com"
        # The SG script name
        self._SCRIPT_NAME = os.getenv("SG_TEST_SCRIPT_NAME") or "sg_events"
        # And its key
        self._SCRIPT_KEY = os.getenv("SG_TEST_SCRIPT_KEY") or "xxxx"

        # setup mockgun, connect to Shotgun only once
        self.mock_sg = mockgun.Shotgun(self._SG_SITE, self._SCRIPT_NAME, self._SCRIPT_KEY)
        self._SESSION_TOKEN = self.mock_sg.get_session_token()

        # Avoid NotImplementedError for mock_sg.upload
        self.mock_sg.upload = mock.MagicMock()
        # Fix the mockgun update method since it returns a list instead of a dict
        # We unfortunately also need to fix the batch method since it assumes a list
        self.mock_sg.update = partial(self.mock_sg_update, self.mock_sg.update)
        self.mock_sg.batch = self.mock_sg_batch
        project = {"type": "Project", "name": "project", "id": 1}
        self._add_to_sg_mock_db(
            self.mock_sg,
            project
        )
        self.mock_project = project
        user = {"type": "HumanUser", "name": "James Bond", "id": 1}
        self._add_to_sg_mock_db(
            self.mock_sg,
            user
        )
        self.mock_user = user

        self.mock_sequence = {
            "project": self.mock_project,
            "type": "Sequence",
            "code": "SEQ01",
            "id": 2,
            "sg_cut_order": 2
        }
        self._add_to_sg_mock_db(self.mock_sg, self.mock_sequence)
        platform = sys.platform
        if platform == "win32":
            self.path_field = "windows_path"
        elif platform == "darwin":
            self.path_field = "mac_path"
        elif platform.startswith("linux"):
            self.path_field = "linux_path"
        else:
            raise RuntimeError("Unsupported platform: %s" % platform)
        self.mock_local_storage = {
            "type": "LocalStorage",
            "code": "primary",
            "id": 1,
            self.path_field: tempfile.mkdtemp()}
        self._add_to_sg_mock_db(self.mock_sg, self.mock_local_storage)
        # Create some Shots
        self.mock_shots = []
        for i in range(1, 4):
            self.mock_shots.append(
                {"type": "Shot", "code": "%03d" % i, "project": project, "id": i}
            )
        self._add_to_sg_mock_db(self.mock_sg, self.mock_shots)
        # Create a Cut
        self.fps = 24
        self.mock_cut = {
            "type": "Cut",
            "id": 1,
            "code": "Cut01",
            "project": project,
            "fps": self.fps,
            "timecode_start_text": "01:00:00:00",
            "timecode_end_text": "01:04:00:00",  # 5760 frames at 24 fps.
            "revision_number": 1,
            "entity": self.mock_sequence,
            "sg_status_list": "ip",
            "image": None,
            "description": "Mocked Cut",
        }
        self._add_to_sg_mock_db(self.mock_sg, self.mock_cut)
        self.mock_cut_id = self.mock_cut["id"]
        # Create a Version for each Shot
        self.mock_versions = []
        for i, shot in enumerate(self.mock_shots):
            self.mock_versions.append({
                "type": "Version",
                "id": i + 1,
                "project": project,
                "entity": shot,
                "code": "%s_v001" % shot["code"],
                "image": "file:///my_image.jpg",
            })
        self._add_to_sg_mock_db(self.mock_sg, self.mock_versions)
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
        self._add_to_sg_mock_db(self.mock_sg, self.mock_cut_items)
        self._SG_CUT_URL = "{}/Cut?session_token={}&id={}".format(
            self._SG_SITE,
            self._SESSION_TOKEN,
            self.mock_cut_id
        )
        self._SG_SEQ_URL = "{}/Sequence?session_token={}&id={}".format(
            self._SG_SITE,
            self._SESSION_TOKEN,
            self.mock_sequence["id"]
        )

    def mock_sg_update(self, update, entity_type, entity_id, data):
        """
        Update using mockgun.

        Mockgun returns a list whereas shotgun returns a dict.

        :param update: The mockgun update method.
        :param entity_type: The entity type to update.
        :param entity_id: The entity id to update.
        :param data: The data to update.
        """
        return update(entity_type, entity_id, data)[0]

    def mock_sg_batch(self, requests):
        """
        Mockgun batch method.

        Mockgun update returns a list instead of a dict, since we patch it, we also need to
        patch batch.

        :param requests: A list of requests
        :returns: A list of SG Entities.
        """
        # Same code as in mockgun.batch(), except for update we append the result and not the first item.
        results = []
        for request in requests:
            if request["request_type"] == "create":
                results.append(self.mock_sg.create(request["entity_type"], request["data"]))
            elif request["request_type"] == "update":
                # note: Shotgun.update returns a list of a single item
                results.append(self.mock_sg.update(request["entity_type"], request["entity_id"], request["data"]))
            elif request["request_type"] == "delete":
                results.append(self.mock_sg.delete(request["entity_type"], request["entity_id"]))
            else:
                raise shotgun_api3.ShotgunError("Invalid request type %s in request %s" % (request["request_type"], request))
        return results

    def _add_to_sg_mock_db(self, mock_sg, entities):
        """
        Adds an entity or entities to the mocked ShotGrid database.

        This is required because when finding entities with mockgun, it
        doesn't return a "name" key.

        :param mock_sg: The mocked ShotGrid API instance.
        :param entities: A ShotGrid style dictionary with keys for id, type, and name
                         defined. A list of such dictionaries is also valid.
        """
        # make sure it's a list
        if isinstance(entities, dict):
            entities = [entities]
        for src_entity in entities:
            # Make a copy
            entity = dict(src_entity)
            # entity: {"id": 2, "type":"Shot", "name":...}
            # wedge it into the mockgun database
            et = entity["type"]
            eid = entity["id"]

            # special retired flag for mockgun
            entity["__retired"] = False
            # set a created by
            entity["created_by"] = {"type": "HumanUser", "id": 1}
            # turn any dicts into proper type/id/name refs
            for x in entity:
                # special case: EventLogEntry.meta is not an entity link dict
                if isinstance(entity[x], dict) and x != "meta":
                    # make a std sg link dict with name, id, type
                    link_dict = {"type": entity[x]["type"], "id": entity[x]["id"]}

                    # most basic case is that there already is a name field,
                    # in that case we are done
                    if "name" in entity[x]:
                        link_dict["name"] = entity[x]["name"]

                    elif entity[x]["type"] == "Task":
                        # task has a 'code' field called content
                        link_dict["name"] = entity[x]["content"]

                    elif "code" not in entity[x]:
                        # auto generate a code field
                        link_dict["name"] = "mockgun_autogenerated_%s_id_%s" % (
                            entity[x]["type"],
                            entity[x]["id"],
                        )

                    else:
                        link_dict["name"] = entity[x]["code"]

                    # print "Swapping link dict %s -> %s" % (entity[x], link_dict)
                    entity[x] = link_dict

            mock_sg._db[et][eid] = entity

    def tearDown(self):
        pass

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
        for i, clip in enumerate(track.each_clip()):
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
            self._add_to_sg_mock_db(self.mock_sg, mock_cut)
            self._add_to_sg_mock_db(self.mock_sg, mock_cut_items)
            SG_CUT_URL = "{}/Cut?session_token={}&id={}".format(
                self._SG_SITE,
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
            self._add_to_sg_mock_db(self.mock_sg, mock_cut)
            self._add_to_sg_mock_db(self.mock_sg, mock_cut_items)
            SG_CUT_URL = "{}/Cut?session_token={}&id={}".format(
                self._SG_SITE,
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
            clips = list(track.each_clip())
            self.assertEqual(len(clips), 2)
            children = list(track.each_child())
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
                if k == "entity":
                    # Just check the type and id
                    self.assertEqual(track.metadata["sg"][k]["type"], v["type"])
                    self.assertEqual(track.metadata["sg"][k]["id"], v["id"])
                else:
                    self.assertEqual(track.metadata["sg"][k], v)
            # Check the track clips
            for i, clip in enumerate(track.each_clip()):
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
            )
            self.assertEqual(len(sg_cut_items), len(self.mock_cut_items))
            for i, sg_cut_item in enumerate(sg_cut_items):
                for field in _CUT_ITEM_FIELDS:

                    if field not in [
                        "id", "cut", "created_by", "updated_by", "updated_at", "created_at", "shot.Shot.code",
                        # Not yet implemented
                        "version", "version.Version.code", "version.Version.entity",
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
            for i, clip in enumerate(track.each_clip()):
                self.assertEqual(clip.metadata["sg"]["type"], "CutItem")
                self.assertEqual(clip.metadata["sg"]["id"], sg_cut_items[i]["id"])

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
            "001  001_v001 V     C        00:00:00:00 00:01:00:00 01:00:00:00 01:01:00:00\n"
            "* FROM CLIP NAME:  001_v001\n"
            "002  002_v001 V     C        00:00:00:00 00:01:00:00 01:01:00:00 01:02:00:00\n"
            "* FROM CLIP NAME:  002_v001\n"
            "003  003_v001 V     C        00:00:00:00 00:01:00:00 01:02:00:00 01:03:00:00\n"
            "* FROM CLIP NAME:  003_v001\n"
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
                "CutItem", [["cut", "is", sg_cut]], []
            )
            self.assertEqual(len(sg_cut_items), 3)
            for i, clip in enumerate(track.each_clip()):
                self.assertEqual(clip.metadata["sg"]["id"], sg_cut_items[i]["id"])

    def test_write_edl_creates_versions(self):
        """
        Test that when we write to SG, we create a new version for each CutItem.
        :return:
        """
        settings = SGSettings()
        # The default settings create Versions for each CutItem, e.g. settings.create_missing_versions = True
        settings.reset_to_defaults()
        # The default template uses UUID, let's test with a more simple template
        settings.version_names_template = "{CLIP_NAME}_{CLIP_INDEX:04d}"
        # Create a Version to check that the first Version is not added.
        self._add_to_sg_mock_db(
            self.mock_sg,
            {
                "type": "Version",
                "code": "green_tape_0001",
                "id": 1000,
                "sg_first_frame": 1009,
                "sg_last_frame": 1024,
                "entity": self.mock_sequence,
                "sg_path_to_movie": os.path.join(self.mock_local_storage[self.path_field], "green_tape_0001.mov"),
            }
        )
        # Note that the first clip already has a Version, so it shouldn't create a new one.
        edl = """
        TITLE: Cut01
        000001 green_tape     V     C        00:00:00:00 00:00:00:16 01:00:00:00 01:00:00:16
        * FROM CLIP NAME: green.mov
        000002 pink_tape      V     C        00:00:00:05 00:00:00:11 01:00:00:16 01:00:00:22
        * FROM CLIP NAME: pink.mov
        000003 green_tape     V     C        00:00:00:05 00:00:00:16 01:00:00:22 01:00:01:09
        * FROM CLIP NAME: green.mov
        000004 red_tape       V     C        00:00:00:12 00:00:01:00 01:00:01:09 01:00:01:21
        * FROM CLIP NAME: red.mov
        000005 blue_tape      V     C        00:00:00:00 00:00:02:00 01:00:01:21 01:00:03:21
        * FROM CLIP NAME: blue.mov
        000006 red_tape       V     C        00:00:00:00 00:00:00:13 01:00:03:21 01:00:04:10
        * FROM CLIP NAME: red.mov
        """
        edl_movie = os.path.join(self.resources_dir, "media_cutter.mov")
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
        media_cutter = MediaCutter(self.mock_sg, timeline, edl_movie)
        media_cutter.cut_media_for_clips()
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            otio.adapters.write_to_file(timeline, self._SG_SEQ_URL, "ShotGrid", input_media=edl_movie)
        # TODO: test published file dependencies, but mockgun does not populate upstream_dependencies
        #       so I did not have time.
        # sg_cut = timeline.tracks[0].metadata["sg"]
        # # We could find the published file through the Version, but mockgun doesn't support that,
        # # i.e. normally if you create a PublishedFile with a version provided, Version.published_files
        # # will be populated, but not in mockgun.
        # sg_cut_published_file = self.mock_sg.find_one(
        #     "PublishedFile",
        #     [["version.Version.id", "is", sg_cut["version"]["id"]]],
        #     ["code"]
        # )
        # Use our version of timeline to get access to cut_in, cut_out, etc.
        timeline = CutTrack.from_timeline(timeline)
        date = datetime.date.today().strftime('%Y%m%d')
        for i, clip in enumerate(timeline.each_clip()):
            clip_version_name = compute_clip_version_name(clip, i + 1)
            sg_cut_item = clip.metadata["sg"]
            if i == 0:
                self.assertTrue(clip.media_reference.is_missing_reference)
            else:
                self.assertEqual(clip.media_reference.name, clip_version_name)
            sg_version = self.mock_sg.find_one(
                "Version",
                [["id", "is", sg_cut_item["version"]["id"]]],
                ["code", "sg_first_frame", "sg_last_frame", "entity", "sg_path_to_movie"]
            )
            self.assertEqual(sg_version["code"], clip_version_name)
            self.assertEqual(sg_version["sg_first_frame"], clip.cut_in.to_frames())
            self.assertEqual(sg_version["sg_last_frame"], clip.cut_out.to_frames())
            self.assertEqual(sg_version["entity"]["id"], self.mock_sequence["id"])
            if i != 0:
                self.assertEqual(sg_version["sg_path_to_movie"], clip.media_reference.target_url.replace("file://", ""))

                sg_published_file = self.mock_sg.find_one(
                    "PublishedFile",
                    [["version.Version.id", "is", sg_version["id"]]],
                    ["code", "path", "published_file_type.PublishedFileType.code", "upstream_published_files"]
                )
                self.assertEqual(sg_published_file["code"], clip_version_name)
                relative_path = "%s/%s/%s/cuts/" % (
                    self.mock_project["name"], self.mock_sequence["code"], date
                )
                self.assertEqual(sg_published_file["path"]["relative_path"], os.path.join(relative_path, clip_version_name + ".mov"))

    def test_write_premiere_xml_creates_versions(self):
        """
        Test that when we write to SG from a Premiere xml, we do create a Version.

        The media is not extracted, it comes directly from Premiere.
        The cut item's cut_in and cut_out are different than the Version's sg_first_frame and sg_last_frame,
        since the available_range of the media is different.
        """
        settings = SGSettings()
        # The default settings create Versions for each CutItem, e.g. settings.create_missing_versions = True
        settings.reset_to_defaults()
        # The default template uses UUID, let's test with a more simple template
        settings.version_names_template = "{CLIP_NAME}_{CLIP_INDEX:04d}"
        # The clip used in the Premiere xml is from frame 1 to frame 48,
        # but only frames 5 to 25 are in the track.
        xml_file = os.path.join(self.resources_dir, "blue_frame_5_to_25.xml")
        timeline = otio.adapters.read_from_file(xml_file)
        # The path to the media is relative to the machine, replace it.
        clip = list(timeline.each_clip())[0]
        file_path = os.path.join(self.resources_dir, "blue.mov")
        # Premiere prepends its path with file://localhost, and then an absolute path.
        # Keep it to test it would work properly.
        clip.media_reference.target_url = "file://localhost" + file_path
        with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
            otio.adapters.write_to_file(timeline, self._SG_SEQ_URL, "ShotGrid")
        # Use our version of timeline to get access to cut_in, cut_out, etc.
        timeline = CutTrack.from_timeline(timeline)
        for i, clip in enumerate(timeline.each_clip()):
            clip_version_name = compute_clip_version_name(clip, i + 1)
            sg_cut_item = clip.metadata["sg"]
            sg_version = self.mock_sg.find_one(
                "Version",
                [["id", "is", sg_cut_item["version"]["id"]]],
                ["code", "sg_first_frame", "sg_last_frame", "sg_path_to_movie"]
            )
            self.assertFalse(clip.media_reference.is_missing_reference)
            self.assertEqual(clip.media_reference.target_url.replace("file://", ""), sg_version["sg_path_to_movie"])
            self.assertEqual(sg_version["code"], clip_version_name)
            # The Version should have a first frame which is head_in + head_in_duration
            version_first_frame = settings.default_head_in + settings.default_head_in_duration
            version_last_frame = version_first_frame + clip.available_range().duration.to_frames() - 1
            self.assertEqual(sg_version["sg_first_frame"], version_first_frame)
            self.assertEqual(sg_version["sg_last_frame"], version_last_frame)
            # The Cut starts five frames after the Version's media
            cut_in = version_first_frame + 5
            cut_out = cut_in + clip.visible_range().duration.to_frames() - 1
            self.assertEqual(sg_cut_item["cut_item_in"], cut_in)
            self.assertEqual(cut_in, clip.cut_in.to_frames())
            self.assertEqual(sg_cut_item["cut_item_out"], cut_out)
            self.assertEqual(cut_out, clip.cut_out.to_frames())


#     def test_write(self):
#         """
#         Test writing features.
#         """
#         # Note: we need to use the single mocked sg instance created in setUp
#         # for all tests.
#         with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
#             timeline = otio.adapters.read_from_file(
#                 self._SG_CUT_URL,
#                 "ShotGrid",
#             )
#             fake_input_media = os.path.join(self.mock_local_storage[self.path_field], "test.mov")
#             Path(fake_input_media).touch()
#             otio.adapters.write_to_string(
#                 timeline,
#                 "ShotGrid",
#                 sg_url=self._SG_SITE,
#                 script_name=self._SCRIPT_NAME,
#                 api_key=self._SCRIPT_KEY,
#                 entity_type="Cut",
#                 project=self.mock_project,
#                 link=self.mock_sequence,
#                 input_media=fake_input_media
#
#             )
#
#     def test_write_again(self):
#         """
#         Test writing to SG from an EDL.
#         """
#         test_edl = os.path.abspath(
#             os.path.join(
#                 os.path.dirname(__file__),
#                 "..",
#                 "resources",
#                 "otio_test.edl",
#             )
#         )
#         if not os.path.exists(test_edl):
#             logger.warning("Skipping test because of missing EDL %s" % test_edl)
#             return
#
#         timeline = otio.adapters.read_from_file(
#             test_edl,
#             rate=30,
#         )
#         fake_input_media = os.path.join(self.mock_local_storage[self.path_field], "test.mov")
#         Path(fake_input_media).touch()
#         # Note: we need to use the single mocked sg instance created in setUp
#         # for all tests.
#         with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
#             def mock_batch(batch_data):
#                 res = []
#                 for d in batch_data:
#                     res.append(d["data"])
#                     logger.debug("APPENDING", d["data"])
#                 return res
#
#             # with mock.patch('shotgun_api3.lib.mockgun.Shotgun.batch', side_effect=mock_batch):
#             #     with mock.patch.object(SGShotFieldsConfig, "validate_shot_cut_fields_prefix"):
#
#             # input_otio,
#             # sg_url,
#             # script_name,
#             # api_key,
#             # entity_type,
#             # project,
#             # link,
#             # user = None,
#             # description = None,
#             # input_media = None,
#             # local_storage_name = None,
#             # shot_regexp = None,
#             # use_smart_fields = False,
#             # shot_cut_fields_prefix = None,
#             # head_in = 1001,
#             # head_in_duration = 8,
#             # tail_out_duration = 8,
#             # flag_retimes_and_effects = True
#             otio.adapters.write_to_string(
#                 timeline,
#                 "ShotGrid",
#                 sg_url=self._SG_SITE,
#                 script_name=self._SCRIPT_NAME,
#                 api_key=self._SCRIPT_KEY,
#                 entity_type="Cut",
#                 project=self.mock_project,
#                 link=self.mock_sequence,
#                 user=self.mock_user,
#                 input_media=fake_input_media,
#                 local_storage_name=self.mock_local_storage["code"],
#                 # head_in=1000,
#                 # head_in_duration=0,
#                 # tail_out_duration=0,
#                 use_smart_fields=True,
#                 # shot_cut_fields_prefix="myprecious"
#             )
#
#     # def test_get_clip_shot_name(self):
#     #     # If read from SG, and the Cut Item is linked to a Shot, get_clip_shot_name
#     #     # returns it from the SG metadata
#     #     with mock.patch.object(shotgun_api3, 'Shotgun', return_value=self.mock_sg):
#     #         timeline = otio.adapters.read_from_string(
#     #             self._SG_SITE,
#     #             "ShotGrid",
#     #             script_name=self._SCRIPT_NAME,
#     #             api_key=self._SCRIPT_KEY,
#     #             entity_type="Cut",
#     #             entity_id=self.mock_cut_id,
#     #         )
#     #         first_clip = list(timeline.each_clip())[0]
#     #         self.assertEqual(
#     #             first_clip.metadata["sg"]["shot"]["name"],
#     #             SGCutItem.get_clip_shot_name(first_clip)
#     #         )
#     #     # If an EDL has a marker, get_clip_shot_name returns the first part of its name (split by " ")
#     #     edl = """TITLE: Cut01
#     #
#     #     001  001_v001 V     C        00:00:00:00 00:01:00:00 01:04:00:00 01:05:00:00
#     #     * FROM CLIP NAME:  001_v001
#     #     * LOC: 00:00:02:19 YELLOW  shot_001 997 // 8-8 Match to edit
#     #     * COMMENT : shot_002
#     #     * shot_003
#     #     """
#     #     timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
#     #     first_clip = list(timeline.each_clip())[0]
#     #     self.assertEqual(SGCutItem.get_clip_shot_name(first_clip), "shot_001")
#     #
#     #     # If it has no locator, and timeline was read from an EDL, get_clip_shot_name returns the
#     #     # first "pure" comment it finds
#     #     edl = """TITLE: Cut01
#     #
#     #     001  001_v001 V     C        00:00:00:00 00:01:00:00 01:04:00:00 01:05:00:00
#     #     * FROM CLIP NAME:  001_v001
#     #     * shot_001
#     #     * COMMENT : shot_002
#     #     * COMMENT : shot_003
#     #     """
#     #     timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
#     #     first_clip = list(timeline.each_clip())[0]
#     #     self.assertEqual(SGCutItem.get_clip_shot_name(first_clip), "shot_002")
#     #
#     #     # If it has no locator, and timeline was read from an EDL, and there are no "pure" comments,
#     #     # get_clip_shot_name returns the first comment it finds
#     #     edl = """TITLE: Cut01
#     #
#     #     001  001_v001 V     C        00:00:00:00 00:01:00:00 01:04:00:00 01:05:00:00
#     #     * FROM CLIP NAME:  001_v001
#     #     * shot_001
#     #     * shot_002
#     #     """
#     #     timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
#     #     first_clip = list(timeline.each_clip())[0]
#     #     self.assertEqual(SGCutItem.get_clip_shot_name(first_clip), "shot_001")
#     #
#     #     # If there are no locators nor comments, returns None
#     #     edl = """TITLE: Cut01
#     #
#     #     001  001_v001 V     C        00:00:00:00 00:01:00:00 01:04:00:00 01:05:00:00
#     #     """
#     #     timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
#     #     first_clip = list(timeline.each_clip())[0]
#     #     self.assertIsNone(SGCutItem.get_clip_shot_name(first_clip))


if __name__ == "__main__":
    unittest.main()
