# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import json
import os
import subprocess
import unittest
from distutils.spawn import find_executable

import opentimelineio as otio
from shotgun_api3.lib import mockgun

from sg_otio.media_cutter import MediaCutter
from sg_otio.sg_settings import SGSettings
from utils import add_to_sg_mock_db

try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock


class TestMediaCutter(unittest.TestCase):

    def setUp(self):
        """
        Setup the tests suite.
        """
        self.resources_dir = os.path.join(os.path.dirname(__file__), "resources")
        sg_settings = SGSettings()
        sg_settings.reset_to_defaults()

        # Setup mockgun.
        self.mock_sg = mockgun.Shotgun(
            "https://mysite.shotgunstudio.com",
            "foo",
            "xxxx"
        )
        project = {"type": "Project", "name": "project", "id": 1}
        add_to_sg_mock_db(
            self.mock_sg,
            project
        )
        self.mock_version = {"type": "Version", "code": "pink_tape", "id": 1}
        add_to_sg_mock_db(
            self.mock_sg,
            self.mock_version
        )
        self.mock_sg.upload = mock.MagicMock()

    def test_media_cutter_with_edl(self):
        """
        Test the cut_media_for_clips method with an EDL file.
        """
        settings = SGSettings()
        # For this test, do not compute version names
        settings.version_names_template = None
        # pink_v01 already exists in SG, and
        # blue_v01 has a Media Reference since there's a FROM FILE: foo.mov
        edl = """
        000001 green_tape     V     C        00:00:00:00 00:00:00:16 01:00:00:00 01:00:00:16
        * FROM CLIP NAME: green_v01.mov
        000002 pink_tape      V     C        00:00:00:05 00:00:00:11 01:00:00:16 01:00:00:22
        * FROM CLIP NAME: pink_v01.mov
        000003 green_tape     V     C        00:00:00:05 00:00:00:16 01:00:00:22 01:00:01:09
        * FROM CLIP NAME: green_v01.mov
        000004 red_tape       V     C        00:00:00:12 00:00:01:00 01:00:01:09 01:00:01:21
        * FROM CLIP NAME: red_v01.mov
        000005 blue_tape      V     C        00:00:00:00 00:00:02:00 01:00:01:21 01:00:03:21
        * FROM CLIP NAME: blue_v01.mov
        * FROM FILE: foo.mov
        000006 red_tape       V     C        00:00:00:00 00:00:00:13 01:00:03:21 01:00:04:10
        * FROM CLIP NAME: red_v01.mov
        """
        movie_filepath = os.path.join(self.resources_dir, "media_cutter.mov")
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")

        media_cutter = MediaCutter(self.mock_sg, timeline, movie_filepath)
        media_cutter.cut_media_for_clips()
        # Note that pink_v01 already exists in SG, and blue_v01 already has a media ref,
        # so they won't be extracted, and media refs from cmx have empty names.
        media_names = ["green_tape", None, "green_tape", "red_tape", "", "red_tape"]
        file_names = ["green_tape.mov", None, "green_tape_001.mov", "red_tape.mov", "foo.mov", "red_tape_001.mov"]
        ffprobe = find_executable("ffprobe")
        for i, clip in enumerate(timeline.each_clip()):
            if i == 1:
                self.assertTrue(clip.media_reference.is_missing_reference)
            else:
                self.assertFalse(clip.media_reference.is_missing_reference)
                self.assertEqual(clip.media_reference.name, media_names[i])
                self.assertEqual(os.path.basename(clip.media_reference.target_url), file_names[i])
                if ffprobe and i != 4:
                    # ffprobe  -count_frames -show_entries stream=nb_read_frames -v error  -print_format csv
                    cmd = [
                        "ffprobe",
                        "-count_frames",
                        "-show_entries", "stream=nb_read_frames",
                        "-v", "error",
                        "-print_format", "json",
                        clip.media_reference.target_url.replace("file://", "")
                    ]
                    output = json.loads(subprocess.check_output(cmd))
                    nb_frames = int(output["streams"][0]["nb_read_frames"])
                    self.assertEqual(nb_frames, clip.visible_range().duration.to_frames())

    def test_media_cutter_with_edl_compute_version_names(self):
        """
        Make sure that if we compute version names, media references get named accordingly
        """
        settings = SGSettings()
        settings.version_names_template = "{CLIP_NAME}_{CLIP_INDEX:04d}"
        # In this test, no Versions already exist in SG
        edl = """
               000001 green_tape     V     C        00:00:00:00 00:00:00:16 01:00:00:00 01:00:00:16
               * FROM CLIP NAME: green_v01.mov
               000002 pink_tape      V     C        00:00:00:05 00:00:00:11 01:00:00:16 01:00:00:22
               * FROM CLIP NAME: purple_v01.mov
               000003 green_tape     V     C        00:00:00:05 00:00:00:16 01:00:00:22 01:00:01:09
               * FROM CLIP NAME: green_v01.mov
               000004 red_tape       V     C        00:00:00:12 00:00:01:00 01:00:01:09 01:00:01:21
               * FROM CLIP NAME: red_v01.mov
               000005 blue_tape      V     C        00:00:00:00 00:00:02:00 01:00:01:21 01:00:03:21
               * FROM CLIP NAME: blue_v01.mov
               000006 AAR0530        V     C        00:00:00:00 00:00:00:13 01:00:03:21 01:00:04:10
               * FROM CLIP NAME: red_v01.mov
        """
        movie_filepath = os.path.join(self.resources_dir, "media_cutter.mov")
        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")

        media_cutter = MediaCutter(self.mock_sg, timeline, movie_filepath)
        media_cutter.cut_media_for_clips()
        for i, clip in enumerate(timeline.each_clip()):
            clip_name = clip.metadata["cmx_3600"]["reel"]
            self.assertFalse(clip.media_reference.is_missing_reference)
            self.assertEqual(
                clip.media_reference.name,
                "%s_%04d" % (clip_name, i + 1)
            )