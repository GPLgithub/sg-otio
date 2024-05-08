# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import json
import logging
import os
import subprocess
import unittest
from distutils.spawn import find_executable

try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock

import opentimelineio as otio

from sg_otio.media_cutter import MediaCutter
from sg_otio.sg_settings import SGSettings

logger = logging.getLogger(__name__)


class TestMediaCutter(unittest.TestCase):

    def setUp(self):
        """
        Setup the tests suite.
        """
        self.resources_dir = os.path.join(os.path.dirname(__file__), "resources")

    def test_media_cutter_errors(self):
        """
        Test that errors are correctly handled by the MediaCutter
        """
        settings = SGSettings()
        # For this test, do not compute version names
        settings.version_names_template = None
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
        media_cutter = MediaCutter(timeline, movie_filepath)
        # Mocked resutls for extract: process exit code and output lines
        _mock_extract = [
            (0, ["mocked"]),
            (0, ["mocked"]),
            (0, ["mocked"]),
            (10, ["mocked"]),  # Fake a failure
            (0, ["mocked"]),
        ]

        with mock.patch("sg_otio.media_cutter.FFmpegExtractor.extract", side_effect=_mock_extract):
            # Since we're not generating any media we should get a RuntimeError.
            with self.assertRaisesRegex(RuntimeError, r"^Failed to extract") as cm:
                media_cutter.cut_media_for_clips(max_workers=1)
            # All files should be mentioned in the error message, not only the
            # one for which we faked a failure.
            for missing in media_cutter._media_filenames:
                self.assertIn(missing, "%s" % cm.exception)

    def test_media_cutter_with_edl(self):
        """
        Test the cut_media_for_clips method with an EDL file.
        """
        settings = SGSettings()
        # For this test, do not compute version names
        settings.version_names_template = None
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
        media_cutter = MediaCutter(timeline, movie_filepath)
        media_cutter.cut_media_for_clips()
        self.assertIsNotNone(media_cutter._media_dir)
        self.assertTrue(os.path.isdir(media_cutter._media_dir))
        logger.info("Generated %s" % os.listdir(media_cutter._media_dir))
        # Note that pink_v01 already exists in SG, and blue_v01 already has a media ref,
        # so they won't be extracted, and media refs from cmx have empty names.
        media_names = ["green_tape", "pink_tape", "green_tape", "red_tape", "", "red_tape"]
        file_names = ["green_tape.mov", "pink_tape.mov", "green_tape_001.mov", "red_tape.mov", "foo.mov", "red_tape_001.mov"]
        ffprobe = find_executable("ffprobe")
        for i, clip in enumerate(timeline.find_clips()):
            self.assertFalse(clip.media_reference.is_missing_reference)
            self.assertEqual(clip.media_reference.name, media_names[i])
            self.assertEqual(os.path.basename(clip.media_reference.target_url), file_names[i])
            # Fourth entry is a dummy reference to "foo.mov"
            if ffprobe and i != 4:
                media_filepath = clip.media_reference.target_url.replace("file://", "")
                self.assertEqual(media_cutter._media_dir, os.path.dirname(media_filepath))
                self.assertTrue(os.path.isdir(media_cutter._media_dir))
                self.assertTrue(os.path.isfile(media_filepath), msg="{} does not exist".format(media_filepath))
                # ffprobe  -count_frames -show_entries stream=nb_read_frames -v error  -print_format csv
                cmd = [
                    "ffprobe",
                    "-count_frames",
                    "-show_entries", "stream=nb_read_frames",
                    "-v", "error",
                    "-print_format", "json",
                    media_filepath
                ]
                output = json.loads(subprocess.check_output(cmd, stderr=subprocess.STDOUT))
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

        media_cutter = MediaCutter(timeline, movie_filepath)
        media_cutter.cut_media_for_clips()
        for i, clip in enumerate(timeline.find_clips()):
            clip_name = clip.metadata["cmx_3600"]["reel"]
            self.assertFalse(clip.media_reference.is_missing_reference)
            self.assertEqual(
                clip.media_reference.name,
                "%s_%04d" % (clip_name, i + 1)
            )
