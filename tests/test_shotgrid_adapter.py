import logging
import os
import sys
import tempfile
import unittest

import opentimelineio as otio
import shotgun_api3
from shotgun_api3.lib import mockgun

try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock

logger = logging.getLogger(__name__)


class ShotgridAdapterTest(unittest.TestCase):
    """
    Tests for the ShotGrid adapter.

    To be able to run these tests you need to run pip install -e . in the parent
    directory. And do the same for the sg_otio local repo.
    """
    def setUp(self):
        """
        Setup the tests suite.
        """
        # Retrieve SG credentials from the environment
        # The SG site
        self._SG_SITE = os.getenv("SG_TEST_SITE") or "https://mysite.shotgunstudio.com"
        # The SG script name
        self._SCRIPT_NAME = os.getenv("SG_TEST_SCRIPT_NAME") or "sg_events"
        # And its key
        self._SCRIPT_KEY = os.getenv("SG_TEST_SCRIPT_KEY") or "xxxx"

        # setup mockgun, connect to Shotgun only once
        self.mock_sg = mockgun.Shotgun(self._SG_SITE, self._SCRIPT_NAME, self._SCRIPT_KEY)
        # Avoid NotImplementedError for mock_sg.upload
        self.mock_sg.upload = mock.MagicMock()
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
            "code": "local_storage",
            "id": 1,
            self.path_field: tempfile.gettempdir()}
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
            "timecode_end_text": "01:04:00:00",
            "revision_number": 1,
            "entity": self.mock_sequence
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
                    "cut_item_in": 0,
                    "cut_item_duration": self.fps * 60,
                    "shot": shot,
                    "version": version,
                    "cut": self.mock_cut,
                    "cut_order": i,
                }
            )
        self._add_to_sg_mock_db(self.mock_sg, self.mock_cut_items)
        self._SG_CUT_URL = "{}/Cut?script={}&api_key={}&id={}".format(
            self._SG_SITE,
            self._SCRIPT_NAME,
            self._SCRIPT_KEY,
            self.mock_cut_id
        )

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
            -otio.opentime.from_timecode(self.mock_cut["timecode_end_text"], self.fps),

        )
        self.assertEqual(
            track.source_range.end_time_exclusive(),
            -otio.opentime.from_timecode(self.mock_cut["timecode_start_text"], self.fps)
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
                clip.source_range.start_time,
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

    def test_read_write_sg_cut(self):
        """
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
                cut_item = self.mock_cut_items[i]
                for k, v in cut_item.items():
                    if k in ["entity", "project", "cut", "shot", "version"]:
                        # Just check the type and id
                        self.assertEqual(sg_data[k]["type"], v["type"])
                        self.assertEqual(sg_data[k]["id"], v["id"])
                    else:
                        self.assertEqual(sg_data[k], v)
            self.assertEqual(i + 1, len(self.mock_cut_items))
            # Now write it back to SG
            otio.adapters.write_to_file(timeline, self._SG_CUT_URL, "ShotGrid")
            # Unset the Cut id on the track
            track.metadata["sg"]["id"] = None
            otio.adapters.write_to_file(timeline, self._SG_CUT_URL, "ShotGrid")
            sg_cuts = self.mock_sg.find("Cut", [], [])
            self.assertEqual(len(sg_cuts), 2)

#     def test_read_write_to_edl(self):
#         """
#         Test reading from SG and writing to an EDL.
#         """
#         # Note: we need to use the single mocked sg instance created in setUp
#         # for all tests.
#         with mock.patch.object(shotgun_api3, "Shotgun", return_value=self.mock_sg):
#             timeline = otio.adapters.read_from_file(
#                 self._SG_CUT_URL,
#                 "ShotGrid",
#             )
#         edl_text = otio.adapters.write_to_string(timeline, adapter_name="cmx_3600")
#         expected_edl_text = """TITLE: Cut01
#
# 001  001_v001 V     C        00:00:00:00 00:01:00:00 01:04:00:00 01:05:00:00
# * FROM CLIP NAME:  001_v001
# 002  002_v001 V     C        00:00:00:00 00:01:00:00 01:05:00:00 01:06:00:00
# * FROM CLIP NAME:  002_v001
# 003  003_v001 V     C        00:00:00:00 00:01:00:00 01:06:00:00 01:07:00:00
# * FROM CLIP NAME:  003_v001
# """
#         self.assertMultiLineEqual(edl_text, expected_edl_text)
#
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