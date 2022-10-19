# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging
import os


try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock

from sg_otio.media_uploader import MediaUploader
from .python.sg_test import SGBaseTest

logger = logging.getLogger(__name__)


class TestMediaUploader(SGBaseTest):

    def setUp(self):
        """
        Setup the tests suite.
        """
        super(TestMediaUploader, self).setUp()
        self.mock_versions = []
        for i in range(1, 10):
            self.mock_versions.append({
                "type": "Version",
                "id": i + 1,
                "project": self.mock_project,
                "code": "version_%04d_v001" % i,
            })
        self.add_to_sg_mock_db(self.mock_versions)

#    def test_media_cutter_errors(self):
#        """
#        Test that errors are correctly handled by the MediaCutter
#        """
#        settings = SGSettings()
#        # For this test, do not compute version names
#        settings.version_names_template = None
#        # blue_v01 has a Media Reference since there's a FROM FILE: foo.mov
#        edl = """
#        000001 green_tape     V     C        00:00:00:00 00:00:00:16 01:00:00:00 01:00:00:16
#        * FROM CLIP NAME: green_v01.mov
#        000002 pink_tape      V     C        00:00:00:05 00:00:00:11 01:00:00:16 01:00:00:22
#        * FROM CLIP NAME: pink_v01.mov
#        000003 green_tape     V     C        00:00:00:05 00:00:00:16 01:00:00:22 01:00:01:09
#        * FROM CLIP NAME: green_v01.mov
#        000004 red_tape       V     C        00:00:00:12 00:00:01:00 01:00:01:09 01:00:01:21
#        * FROM CLIP NAME: red_v01.mov
#        000005 blue_tape      V     C        00:00:00:00 00:00:02:00 01:00:01:21 01:00:03:21
#        * FROM CLIP NAME: blue_v01.mov
#        * FROM FILE: foo.mov
#        000006 red_tape       V     C        00:00:00:00 00:00:00:13 01:00:03:21 01:00:04:10
#        * FROM CLIP NAME: red_v01.mov
#        """
#        movie_filepath = os.path.join(self.resources_dir, "media_cutter.mov")
#        timeline = otio.adapters.read_from_string(edl, adapter_name="cmx_3600")
#        media_cutter = MediaCutter(timeline, movie_filepath)
#        # Mocked resutls for extract: process exit code and output lines
#        _mock_extract = [
#            (0, ["mocked"]),
#            (0, ["mocked"]),
#            (0, ["mocked"]),
#            (10, ["mocked"]),  # Fake a failure
#            (0, ["mocked"]),
#        ]
#
#        with mock.patch("sg_otio.media_cutter.FFmpegExtractor.extract", side_effect=_mock_extract):
#            # Since we're not generating any media we should get a RuntimeError.
#            with six.assertRaisesRegex(self, RuntimeError, r"^Failed to extract") as cm:
#                media_cutter.cut_media_for_clips(max_workers=1)
#            # All files should be mentioned in the error message, not only the
#            # one for which we faked a failure.
#            for missing in media_cutter._media_filenames:
#                self.assertIn(missing, "%s" % cm.exception)

    def test_media_uploader(self):
        """
        Test uploading media to Versions.
        """
        movie_path = os.path.join(self.resources_dir, "blue.mov")
        movie_paths = [movie_path] * len(self.mock_versions)
        uploader = MediaUploader(
            self.mock_sg,
            self.mock_versions,
            movie_paths,
        )
        uploader.upload_versions(max_workers=2)
        self.assertEqual(uploader.progress, len(self.mock_versions))

    def test_media_uploader_errors(self):
        """
        Test errors when uploading media to Versions.
        """
        movie_path = os.path.join(self.resources_dir, "blue.mov")
        movie_paths = [movie_path] * len(self.mock_versions)
        uploader = MediaUploader(
            self.mock_sg,
            self.mock_versions,
            movie_paths,
        )
        # Any error makes everything fail, without the ability to know what
        # failed or succeeded.
        with mock.patch.object(uploader, "upload_version") as mocked:
            mocked.side_effect = [UserWarning("faked error")] + [(x, movie_path) for x in self.mock_versions[:-2]]
            with self.assertRaises(UserWarning) as cm:
                uploader.upload_versions(max_workers=2)
            self.assertEqual("%s" % cm.exception, "faked error")
        self.assertLess(uploader.progress, len(self.mock_versions))
