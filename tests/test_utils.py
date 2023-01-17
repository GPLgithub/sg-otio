# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import os
import sys
import tempfile
import unittest
from functools import partial

import opentimelineio as otio

from sg_otio.constants import _DEFAULT_HEAD_IN
from sg_otio.sg_settings import SGSettings
from sg_otio.utils import get_platform_name
from sg_otio.utils import compute_clip_version_name
from sg_otio.utils import get_local_storage_relative_path
from sg_otio.sg_cut_reader import SGCutReader

from .python.sg_test import SGBaseTest

try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock


class TestUtils(SGBaseTest):
    """
    Test various utilities provided by the package
    """

    def setUp(self):
        super(TestUtils, self).setUp()
        sg_settings = SGSettings()
        sg_settings.reset_to_defaults()

        self.mock_sg.find = mock.Mock(side_effect=partial(self.mock_find, self.mock_sg.find))
        self.path_field = "%s_path" % get_platform_name()
        self.mock_local_storage = {
            "type": "LocalStorage",
            "code": "primary",
            "id": 1,
            self.path_field: tempfile.mkdtemp()}
        self.add_to_sg_mock_db(self.mock_local_storage)
        self.published_file_type = {
            "type": "PublishedFileType",
            "code": "mov",
            "id": 1,
        }
        self.add_to_sg_mock_db(self.published_file_type)

    def mock_find(self, mockgun_find, *args, **kwargs):
        """
        Mock the find method to add the URL of a sg uploaded movie if needed

        :param mockgun_find: The mockgun find method
        :returns: A list of Entities.
        """
        entities = mockgun_find(*args, **kwargs)
        for entity in entities:
            for field in entity.keys():
                if field == "sg_uploaded_movie" and entity[field]:
                    attachment = self.mock_sg.find_one(
                        "Attachment",
                        [["id", "is", entity[field]["id"]]],
                        ["url"]
                    )
                    entity[field]["url"] = attachment["url"]
        return entities

    def test_sg_settings(self):
        """
        Test retrieving and setting SG settings.
        """
        sg_settings = SGSettings(
        )
        # Make sure we have default values.
        sg_settings.reset_to_defaults()
        # Check a couple of them.
        self.assertEqual(sg_settings.default_head_in, _DEFAULT_HEAD_IN)
        self.assertFalse(sg_settings.use_clip_names_for_shot_names)
        # Check that set values are global
        sg_settings.default_head_in = 1234
        sg_settings.default_head_duration = 24
        sg_settings.default_tail_duration = 36
        sg_settings.use_clip_names_for_shot_names = True
        sg_settings.clip_name_shot_regexp = r"\d+"
        sg_settings = SGSettings()
        self.assertEqual(sg_settings.default_head_in, 1234)
        self.assertEqual(sg_settings.default_head_duration, 24)
        self.assertEqual(sg_settings.default_tail_duration, 36)
        self.assertTrue(sg_settings.use_clip_names_for_shot_names)
        self.assertEqual(sg_settings.clip_name_shot_regexp, r"\d+")

    @mock.patch("sg_otio.utils.get_uuid", return_value="123456")
    def test_compute_version_name(self, _):
        """
        Test computing media names.
        """
        settings = SGSettings()
        settings.reset_to_defaults()
        settings.version_names_template = None
        clip = otio.schema.Clip(name="foo")
        # If there's no version name template, it just returns the clip name
        self.assertEqual(
            compute_clip_version_name(clip, 1),
            "foo"
        )
        # If there's a version name template, it uses it
        # First test the default template, {CLIP_NAME}_{UUID}
        settings.reset_to_defaults()
        settings.version_names_template = "{CLIP_NAME}_{UUID}"
        self.assertEqual(
            compute_clip_version_name(clip, 1),
            "foo_123456"
        )
        # Now test a custom template with all keys present,
        # but the clip has no SG metadata so the cut item name is empty
        # The shot name should be also empty in this default case.
        settings.version_names_template = "{CLIP_NAME}_{CUT_ITEM_NAME}_{SHOT}_{CLIP_INDEX}_{UUID}"
        self.assertEqual(
            compute_clip_version_name(clip, 1),
            "foo___1_123456"
        )
        # Now the same template but with a shot name == clip name
        settings.use_clip_names_for_shot_names = True
        self.assertEqual(
            compute_clip_version_name(clip, 1),
            "foo__foo_1_123456"
        )
        # Now let's add some metadata for the cut item name
        clip.metadata["sg"] = {"code": "foo001"}
        self.assertEqual(
            compute_clip_version_name(clip, 1),
            "foo_foo001_foo_1_123456"
        )
        # Now let's try with some formatting
        settings.reset_to_defaults()
        settings.version_names_template = "{CLIP_NAME}_{CLIP_INDEX:04d}"
        self.assertEqual(
            compute_clip_version_name(clip, 4),
            "foo_0004"
        )

    def test_add_media_reference_from_sg_non_existing(self):
        """
        Test that add media references from SG does nothing if the
        clip has no corresponding Published File or Version in SG.
        """
        settings = SGSettings()
        settings.reset_to_defaults()
        # Don't use a template, so it's easy to infer the Version/PublishedFile name.
        settings.version_names_template = None
        # Create a clip and add it to a Track
        track = otio.schema.Track()
        clip = otio.schema.Clip(name="foo")
        track.append(clip)
        SGCutReader(self.mock_sg).add_media_references_from_sg(track, self.mock_project)
        self.assertTrue(clip.media_reference.is_missing_reference)

    def test_add_media_reference_from_sg_version(self):
        """
        Test that add media references from SG adds a reference from a sg_uploaded_movie
        If it finds a corresponding Version but not a PublishedFile
        """
        settings = SGSettings()
        settings.reset_to_defaults()
        # Don't use a template, so it's easy to infer the Version/PublishedFile name.
        settings.version_names_template = None
        # Create a clip and add it to a Track
        track = otio.schema.Track()
        # The name of the media should be the name of the clip
        clip = otio.schema.Clip(name="foo")
        # The clip needs a source range to calculate the media reference available range
        clip.source_range = otio.opentime.TimeRange(
            otio.opentime.RationalTime(5, 24),
            otio.opentime.RationalTime(10, 24)
        )
        track.append(clip)
        try:
            # Add a Version to the mock DB
            # first add a dummy uploaded movie
            attachment = {
                "url": "https://foo.com",
                "type": "Attachment",
                "id": 1
            }
            self.add_to_sg_mock_db(attachment)
            version = {
                "type": "Version",
                "code": "foo",
                "id": 123,
                "project": self.mock_project,
                "sg_first_frame": 1000,
                "sg_last_frame": 1019,
                "sg_uploaded_movie": attachment,
            }
            self.add_to_sg_mock_db(version)
            # We also need a Cut Item.
            cut_item = {
                "type": "CutItem",
                "id": 234,
                "version": version,
                "cut_item_in": 1005,
                "cut_item_out": 1009,
                "project": self.mock_project,
            }
            self.add_to_sg_mock_db(cut_item)
            SGCutReader(self.mock_sg).add_media_references_from_sg(track, self.mock_project)
            self.assertFalse(clip.media_reference.is_missing_reference)
            self.assertEqual(clip.media_reference.name, version["code"])
            self.assertEqual(clip.media_reference.target_url, attachment["url"])
            # We set the source range from 5 to 10, to represent the cut item that goes
            # from 1005 to 1009 (5 frames).
            # The Version goes from 1000 to 1019, so the available range should be
            # 0 to 20
            available_range = otio.opentime.TimeRange(
                otio.opentime.RationalTime(0, 24),
                otio.opentime.RationalTime(20, 24)
            )
            self.assertEqual(clip.media_reference.available_range, available_range)
            self.assertEqual(
                clip.media_reference.metadata["sg"]["version.Version.id"],
                version["id"]
            )

        finally:
            # Remove the version from the mock DB
            self.mock_sg.delete("Version", version["id"])
            self.mock_sg.delete("Attachment", attachment["id"])
            self.mock_sg.delete("CutItem", cut_item["id"])

    def test_add_media_reference_from_sg_published_file(self):
        """
        Test that add media references from SG adds a reference from a Published File.
        """
        settings = SGSettings()
        settings.reset_to_defaults()
        # Don't use a template, so it's easy to infer the Version/PublishedFile name.
        settings.version_names_template = None
        # Create a clip and add it to a Track
        track = otio.schema.Track()
        # The name of the media should be the name of the clip
        clip = otio.schema.Clip(name="foo")
        # The clip needs a source range to calculate the media reference available range
        clip.source_range = otio.opentime.TimeRange(
            otio.opentime.RationalTime(5, 24),
            otio.opentime.RationalTime(10, 24)
        )
        track.append(clip)

        try:
            version = {
                "type": "Version",
                "code": "foo",
                "id": 123,
                "project": self.mock_project,
                "sg_first_frame": 1000,
                "sg_last_frame": 1019,
            }
            self.add_to_sg_mock_db(version)
            published_file_data = {
                "code": "foo",
                "project": self.mock_project,
                "version": version,
                "path": {
                    "relative_path": "foo.mov",
                    "local_path": os.path.join(self.mock_local_storage[self.path_field], "foo.mov"),
                    "local_storage": self.mock_local_storage
                },
                "published_file_type": self.published_file_type,
            }
            # We don't add it with add_to_sg_mock_db,
            # because mockgun adds the "local_path_XXX" fields on create.
            published_file = self.mock_sg.create("PublishedFile", published_file_data)

            # We also need a Cut Item.
            cut_item = {
                "type": "CutItem",
                "id": 234,
                "version": version,
                "cut_item_in": 1005,
                "cut_item_out": 1009,
                "project": self.mock_project,
            }
            self.add_to_sg_mock_db(cut_item)
            SGCutReader(self.mock_sg).add_media_references_from_sg(track, self.mock_project)
            self.assertFalse(clip.media_reference.is_missing_reference)
            self.assertEqual(clip.media_reference.name, published_file["code"])
            self.assertEqual(
                clip.media_reference.target_url,
                "file://%s" % os.path.join(self.mock_local_storage[self.path_field], "foo.mov")
            )
            # We set the source range from 5 to 10, to represent the cut item that goes
            # from 1005 to 1009 (5 frames).
            # The Version goes from 1000 to 1019, so the available range should be
            # 0 to 20
            available_range = otio.opentime.TimeRange(
                otio.opentime.RationalTime(0, 24),
                otio.opentime.RationalTime(20, 24)
            )
            self.assertEqual(clip.media_reference.available_range, available_range)
            self.assertEqual(clip.media_reference.metadata["sg"]["id"], published_file["id"])
            self.assertEqual(
                clip.media_reference.metadata["sg"]["version.Version.id"],
                version["id"]
            )

        finally:
            # Remove the version from the mock DB
            self.mock_sg.delete("Version", version["id"])
            self.mock_sg.delete("PublishedFile", published_file["id"])
            self.mock_sg.delete("CutItem", cut_item["id"])

    def test_get_local_storage_relative_path(self):
        """
        Test SG Local Storages and paths.
        """
        # First local storage test.
        local_storage = {
            "mac_path": "/foo/bar",
            "windows_path": "C:\\foo\\bar",
            "linux_path": "/foo/bar",
        }
        # Check that it matches
        filepaths = {
            "mac": "/foo/bar/baz.mov",
            "windows": "C:\\foo\\bar\\baz.mov",
            "linux": "/foo/bar/baz.mov",
        }
        filepath = filepaths[get_platform_name()]
        relative_path = get_local_storage_relative_path(local_storage, filepath)
        self.assertEqual(relative_path, "baz.mov")
        # Check that something in /foo/barbaz doesn't match
        filepaths = {
            "mac": "/foo/barbaz/baz.mov",
            "windows": "C:\\foo\\barbaz\\baz.mov",
            "linux": "/foo/barbaz/baz.mov",
        }
        filepath = filepaths[get_platform_name()]
        relative_path = get_local_storage_relative_path(local_storage, filepath)
        self.assertIsNone(relative_path)

        # Test with an edge case.
        local_storage = {
            "mac_path": "/",
            "windows_path": "C:\\",
            "linux_path": "/",
        }
        # Check that it matches
        filepaths = {
            "mac": "/foo/foo.mov",
            "windows": "C://foo/foo.mov",
            "linux": "/foo/foo.mov",
        }
        filepath = filepaths[get_platform_name()]
        relative_path = get_local_storage_relative_path(local_storage, filepath)
        self.assertEqual(relative_path, "foo/foo.mov")

        # A couple more tests on Windows
        if sys.platform == "win32":
            local_storage = {
                "windows_path": "//server/share",
            }
            # Check that it matches
            filepath = "//server/share/foo/foo.mov"
            relative_path = get_local_storage_relative_path(local_storage, filepath)
            self.assertEqual(relative_path, "foo/foo.mov")


if __name__ == "__main__":
    unittest.main()
