# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#

import unittest

import opentimelineio as otio

from sg_otio.constants import _DEFAULT_HEAD_IN
from sg_otio.sg_settings import SGSettings
from sg_otio.utils import compute_clip_version_name

try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock


class TestUtils(unittest.TestCase):
    """
    Test various utilities provided by the package
    """
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
        sg_settings.default_head_in_duration = 24
        sg_settings.default_tail_out_duration = 36
        sg_settings.use_clip_names_for_shot_names = True
        sg_settings.clip_name_shot_regexp = r"\d+"
        sg_settings = SGSettings()
        self.assertEqual(sg_settings.default_head_in, 1234)
        self.assertEqual(sg_settings.default_head_in_duration, 24)
        self.assertEqual(sg_settings.default_tail_out_duration, 36)
        self.assertTrue(sg_settings.use_clip_names_for_shot_names)
        self.assertEqual(sg_settings.clip_name_shot_regexp, r"\d+")

    @mock.patch("sg_otio.utils.get_uuid", return_value="123456")
    def test_compute_version_name(self, _):
        """
        Test computing media names.
        """
        # If there's no version name template, it just returns the clip name
        settings = SGSettings()
        settings.reset_to_defaults()
        settings.version_names_template = None
        clip = otio.schema.Clip(name="foo")
        self.assertEqual(
            compute_clip_version_name(clip, 1),
            "foo"
        )
        # If there's a version name template, it uses it
        # First test the default template, {CLIP_NAME}_{UUID}
        settings.reset_to_defaults()
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


if __name__ == "__main__":
    unittest.main()
