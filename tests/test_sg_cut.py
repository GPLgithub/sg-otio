import os
import sys
import tempfile
import unittest

import opentimelineio as otio
import shotgun_api3
from shotgun_api3.lib import mockgun

from sg_otio.sg_cut import SGCut
from sg_otio.sg_shot import SGShotFieldsConfig

try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock

try:
    # For Python 3.4 or later
    from pathlib import Path
except ImportError:
    # fallback to library in required packages
    from pathlib2 import Path


@unittest.skipUnless(
    os.getenv("SG_TEST_SITE") and os.getenv("SG_TEST_SCRIPT_NAME") and os.getenv("SG_TEST_SCRIPT_KEY"),
    "SG_TEST_SITE, SG_TEST_SCRIPT_NAME and SG_TEST_SCRIPT_KEY env variables must be set"
)
class SGCutTest(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        # Retrieve SG credentials from the environment
        # The SG site
        self._SG_SITE = os.getenv("SG_TEST_SITE")  # e.g. "https://mysite.shotgunstudio.com"
        # The SG script name
        self._SCRIPT_NAME = os.getenv("SG_TEST_SCRIPT_NAME")  # e.g. "sg_events"
        # And its key
        self._SCRIPT_KEY = os.getenv("SG_TEST_SCRIPT_KEY")
        # setup mockgun, connect to Shotgun only once
        sg = shotgun_api3.Shotgun(self._SG_SITE, self._SCRIPT_NAME, self._SCRIPT_KEY)

        mockgun.generate_schema(sg, "/tmp/schema", "/tmp/entity_schema")
        mockgun.Shotgun.set_schema_paths("/tmp/schema", "/tmp/entity_schema")

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

    @staticmethod
    def _add_to_sg_mock_db(mock_sg, entities):
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

    def test_cut_create(self):
        """
        Test creating a SG Cut from a simple EDL.
        """
        edl = """
            TITLE:   CUT_CREATE_TEST
        
            001  ABC0100 V     C        00:00:00:00 00:00:01:00 01:00:00:00 01:00:01:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
            
            002  ABC0200 V     C        00:00:01:00 00:00:02:00 01:00:01:00 01:00:02:00
            * FROM CLIP NAME: shot_002_v001
            * COMMENT: shot_002
        """
        # Set the rate to something different than 24.0 to see it in the cut
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600", rate=30)
        track = timeline.tracks[0]
        # Set the track name as the timeline name, if not it's simply "V"
        track.name = timeline.name
        fake_input_media_name = "test"
        fake_input_media = os.path.join(self.mock_local_storage[self.path_field], "%s.mov" % fake_input_media_name)
        Path(fake_input_media).touch()
        cut = SGCut(
            track=track,
            sg=self.mock_sg,
            entity_type="Cut",
            project=self.mock_project,
            linked_entity=self.mock_sequence,
            user=self.mock_user,
            description="foo",
            input_media=fake_input_media,
            local_storage_name=self.mock_local_storage["code"],
            shot_regexp=None,
        )
        sg_cut = cut.create_sg_cut()
        # Since we don't know the exact version created, pop it for later use
        sg_cut_version = sg_cut.pop("version")
        sg_cut_data = {
            "type": "Cut",
            "id": sg_cut["id"],
            "project": {"type": "Project", "id": 1},
            "code": "CUT_CREATE_TEST",
            "entity": {"type": "Sequence", "id": 2},
            "fps": 30.0,
            "timecode_start_text": "01:00:00:00",
            "timecode_end_text": "01:00:02:00",
            "duration": 60,
            "revision_number": 1,
            "created_by": {"type": "HumanUser", "id": 1},
            "updated_by": {"type": "HumanUser", "id": 1},
            "description": "foo",
        }
        self.assertEqual(sg_cut, sg_cut_data)

        # Check the Version data
        sg_version = self.mock_sg.find_one(
            "Version",
            [["id", "is", sg_cut_version["id"]]],
            ["project", "code", "entity", "description", "sg_first_frame", "sg_movie_has_slate", "sg_path_to_movie"]
        )
        sg_version_data = {
            "type": "Version",
            "id": sg_cut_version["id"],
            "project": {"type": "Project", "id": 1},
            "code": fake_input_media_name,
            "entity": {"type": "Sequence", "id": 2},
            "description": "Base media layer imported with Cut: %s" % sg_cut["code"],
            "sg_first_frame": 1,
            "sg_movie_has_slate": False,
            "sg_path_to_movie": fake_input_media
        }
        self.assertEqual(sg_version, sg_version_data)

        # Check the published file data
        sg_publish = self.mock_sg.find_one(
            "PublishedFile",
            [["version", "is", sg_version]],
            [
                "code",
                "project",
                "entity",
                "path",
                "published_file_type.PublishedFileType.code",
                "version_number",
                "version"
            ]
        )
        sg_publish_data = {
            "type": "PublishedFile",
            "id": sg_publish["id"],
            "code": "test",
            "project": {"type": "Project", "id": 1},
            "entity": {"type": "Sequence", "id": 2},
            "path": {
                "local_storage": {
                    "id": self.mock_local_storage["id"],
                    "type": "LocalStorage",
                    "mac_path": self.mock_local_storage[self.path_field],
                    "path": self.mock_local_storage[self.path_field],
                },
                "relative_path": "/test.mov"
            },
            "published_file_type.PublishedFileType.code": "mov",
            "version": {"type": "Version", "id": sg_version["id"], "name": "test"},
            "version_number": 1
        }
        self.assertEqual(sg_publish, sg_publish_data)
        # Create another cut to see how revision number is incremented
        sg_cut = cut.create_sg_cut()
        self.assertEqual(sg_cut["revision_number"], 2)
        # Create another cut but this time without input media to confirm that no Version gets created
        cut._input_media = None
        sg_cut = cut.create_sg_cut()
        self.assertIsNone(sg_cut.get("version"))

    def test_shot_creation(self):
        """
        Test that if Shots are not in SG for some CutItems, they do get created properly.
        """
        # This test is very simple, with one shot only.
        edl = """
            TITLE:   CUT_CREATE_TEST
            
            001  ABC0100 V     C        00:00:00:00 00:00:01:00 01:00:00:00 01:00:01:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
        """
        # Test with non default fps, to make sure it's taken into account
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600", rate=30)
        track = timeline.tracks[0]
        # Set the track name as the timeline name, if not it's simply "V"
        track.name = timeline.name
        # Set non default values to see them reflected in the shot data
        head_in = 555
        head_in_duration = 6
        tail_out_duration = 12

        cut = SGCut(
            track=track,
            sg=self.mock_sg,
            entity_type="Cut",
            project=self.mock_project,
            linked_entity=self.mock_sequence,
            head_in=head_in,
            head_in_duration=head_in_duration,
            tail_out_duration=tail_out_duration
        )
        cut._create_or_update_sg_shots()
        clip_1 = list(track.each_clip())[0]
        shot_name, cut_items = list(cut._cut_items_by_shot.items())[0]
        sg_shot = cut_items[0].sg_shot
        sg_shot.pop("id")
        self.assertEqual(shot_name, "shot_001")
        shot_data = {
            "type": "Shot",
            "code": "shot_001",
            "project": {"id": 1, "type": "Project"},
            "sg_sequence": {"type": "Sequence", "id": 2},
            "sg_cut_order": 1,
            "sg_cut_in": head_in + head_in_duration,
            "sg_cut_out": head_in + head_in_duration + clip_1.duration().to_frames() - 1,
            "sg_cut_duration": clip_1.duration().to_frames(),
            "sg_head_in": head_in,
            "sg_tail_out": head_in + head_in_duration + clip_1.duration().to_frames() + tail_out_duration - 1,
            "sg_effects": False,
            "sg_respeed": False,
        }
        self.assertEqual(sg_shot, shot_data)

    def test_shot_creation_smart_fields(self):
        """
        Test that a shot gets properly created and has the proper smart field values.
        """
        edl = """
            TITLE:   CUT_CREATE_TEST

            001  ABC0100 V     C        00:00:00:00 00:00:01:00 01:00:00:00 01:00:01:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
        """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600", rate=30)
        track = timeline.tracks[0]
        # Set the track name as the timeline name, if not it's simply "V"
        track.name = timeline.name
        # Set non default values to see them reflected in the shot data
        head_in = 555
        head_in_duration = 6
        tail_out_duration = 12

        cut = SGCut(
            track=track,
            sg=self.mock_sg,
            entity_type="Cut",
            project=self.mock_project,
            linked_entity=self.mock_sequence,
            head_in=head_in,
            head_in_duration=head_in_duration,
            tail_out_duration=tail_out_duration,
            use_smart_fields=True
        )
        cut._create_or_update_sg_shots()
        clip_1 = list(track.each_clip())[0]
        shot_name, cut_items = list(cut._cut_items_by_shot.items())[0]
        sg_shot = cut_items[0].sg_shot
        sg_shot.pop("id")
        self.assertEqual(shot_name, "shot_001")
        shot_data = {
            "type": "Shot",
            "code": "shot_001",
            "project": {"id": 1, "type": "Project"},
            "sg_sequence": {"type": "Sequence", "id": 2},
            "sg_cut_order": 1,
            "head_in": head_in,
            "head_out": head_in + head_in_duration - 1,
            "head_duration": head_in_duration,
            "tail_in": head_in + head_in_duration + clip_1.duration().to_frames(),
            "tail_out": head_in + head_in_duration + clip_1.duration().to_frames() + tail_out_duration - 1,
            "tail_duration": tail_out_duration,
            "cut_in": head_in + head_in_duration,
            "cut_out": head_in + head_in_duration + clip_1.duration().to_frames() - 1,
            "cut_duration": clip_1.duration().to_frames(),
            "sg_effects": False,
            "sg_respeed": False,
        }
        self.assertEqual(sg_shot, shot_data)

    def test_shot_creation_custom_fields(self):
        """
        Test that a Shot gets properly created when requesting fields with a custom prefix.
        """
        edl = """
            TITLE:   CUT_CREATE_TEST

            001  ABC0100 V     C        00:00:00:00 00:00:01:00 01:00:00:00 01:00:01:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
        """
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600", rate=24)
        track = timeline.tracks[0]
        # Set the track name as the timeline name, if not it's simply "V"
        track.name = timeline.name
        # Set non default values to see them reflected in the shot data
        head_in = 1001
        head_in_duration = 8
        tail_out_duration = 8

        # we have to mock the batch, since some fields won't exist.
        def mock_batch(batch_data):
            res = []
            for d in batch_data:
                res.append(d["data"])
            return res

        with mock.patch('shotgun_api3.lib.mockgun.Shotgun.batch', side_effect=mock_batch):
            with mock.patch.object(SGShotFieldsConfig, "validate_shot_cut_fields_prefix"):
                cut = SGCut(
                    track=track,
                    sg=self.mock_sg,
                    entity_type="Cut",
                    project=self.mock_project,
                    linked_entity=self.mock_sequence,
                    head_in=head_in,
                    head_in_duration=head_in_duration,
                    tail_out_duration=tail_out_duration,
                    shot_cut_fields_prefix="my_precious"
                )
                cut._create_or_update_sg_shots()
        clip_1 = list(track.each_clip())[0]
        shot_name, cut_items = list(cut._cut_items_by_shot.items())[0]
        sg_shot = cut_items[0].sg_shot
        sequence = sg_shot.pop("sg_sequence")
        self.assertEqual(sequence["id"], self.mock_sequence["id"])
        self.assertEqual(shot_name, "shot_001")
        shot_data = {
            "code": "shot_001",
            "project": self.mock_project,
            "sg_my_precious_cut_order": 1,
            "sg_my_precious_cut_in": head_in + head_in_duration,
            "sg_my_precious_cut_out": head_in + head_in_duration + clip_1.duration().to_frames() - 1,
            "sg_my_precious_cut_duration": clip_1.duration().to_frames(),
            "sg_my_precious_head_in": head_in,
            "sg_my_precious_tail_out": head_in + head_in_duration + clip_1.duration().to_frames() + tail_out_duration - 1,
            "sg_effects": False,
            "sg_respeed": False,
        }
        self.assertEqual(sg_shot, shot_data)

    def test_shot_creation_repeated_shots(self):
        """
        Test that Shot values are correct on creation when there are multiple clips for the same Shot.
        """
        # 3 clips for the same shot
        # The smallest source in is 01:00:00:00
        # The largest source out is 01:00:10:00
        edl = """
            TITLE:   CUT_CREATE_TEST

            001  ABC0100 V     C        01:00:01:00 01:00:10:00 01:00:00:00 01:00:09:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
            002  ABC0200 V     C        01:00:02:00 01:00:05:00 01:00:09:00 01:00:12:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
            003  ABC0200 V     C        01:00:00:00 01:00:04:00 01:00:12:00 01:00:16:00
            * FROM CLIP NAME: shot_001_v001
            * COMMENT: shot_001
        """
        # Test with non default fps, to make sure it's taken into account
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600", rate=24)
        track = timeline.tracks[0]
        # Set the track name as the timeline name, if not it's simply "V"
        track.name = timeline.name
        # Set non default values to see them reflected in the shot data
        head_in = 1001
        head_in_duration = 8
        tail_out_duration = 8

        cut = SGCut(
            track=track,
            sg=self.mock_sg,
            entity_type="Cut",
            project=self.mock_project,
            linked_entity=self.mock_sequence,
            head_in=head_in,
            head_in_duration=head_in_duration,
            tail_out_duration=tail_out_duration
        )
        cut._create_or_update_sg_shots()
        # clip_1 is the one with the biggest source out
        # clip_3 is the one with the smallest source in
        clip_1 = list(track.each_clip())[0]
        clip_3 = list(track.each_clip())[2]
        shot_duration = (clip_1.source_range.end_time_exclusive() - clip_3.source_range.start_time).to_frames()
        shot_name, cut_items = list(cut._cut_items_by_shot.items())[0]
        sg_shot = cut_items[0].sg_shot
        sg_shot.pop("id")
        self.assertEqual(shot_name, "shot_001")
        shot_data = {
            "type": "Shot",
            "code": "shot_001",
            "project": {"id": 1, "type": "Project"},
            "sg_sequence": {"id": 2, "type": "Sequence"},
            "sg_cut_order": 1,
            "sg_cut_in": head_in + head_in_duration,
            "sg_cut_out": head_in + head_in_duration + shot_duration - 1,
            "sg_cut_duration": shot_duration,
            "sg_head_in": head_in,
            "sg_tail_out": head_in + head_in_duration + shot_duration + tail_out_duration - 1,
            "sg_effects": False,
            "sg_respeed": False,
        }
        self.assertEqual(sg_shot, shot_data)


if __name__ == '__main__':
    unittest.main()