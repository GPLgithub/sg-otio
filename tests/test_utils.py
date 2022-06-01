# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#

import unittest

from sg_otio.sg_settings import SGSettings
from sg_otio.constants import DEFAULT_HEAD_IN


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
        self.assertEqual(sg_settings.default_head_in, DEFAULT_HEAD_IN)
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


if __name__ == "__main__":
    unittest.main()
