# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import os
import unittest


from .mock_grid import MockGrid


class SGBaseTest(unittest.TestCase):
    """
    A class to use as a base for SG related tests.
    """

    def setUp(self):
        """
        Setup the tests suite.
        """
        self.resources_dir = os.path.join(
            os.path.dirname(__file__),
            "..",
            "resources"
        )
        # Setup mockgun.
        self.mock_sg = MockGrid(
            "https://mysite.shotgunstudio.com",
            "foo",
            "xxxx"
        )
        self._SESSION_TOKEN = self.mock_sg.get_session_token()

        project = {"type": "Project", "name": "project", "id": 1}
        self.add_to_sg_mock_db(
            project
        )
        self.mock_project = project
        user = {"type": "HumanUser", "name": "James Bond", "id": 1}
        self.add_to_sg_mock_db(
            user
        )
        self.mock_user = user

    def add_to_sg_mock_db(self, entities):
        """
        Adds an entity or entities to the mocked ShotGrid database.
        """
        return self.mock_sg.add_to_db(entities)
