# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import os
import unittest
from functools import partial

import shotgun_api3
from shotgun_api3.lib import mockgun

try:
    # Python 3.3 forward includes the mock module
    from unittest import mock
except ImportError:
    import mock


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
        self.mock_sg = mockgun.Shotgun(
            "https://mysite.shotgunstudio.com",
            "foo",
            "xxxx"
        )
        self._SESSION_TOKEN = self.mock_sg.get_session_token()

        # Avoid NotImplementedError for mock_sg.upload
        self.mock_sg.upload = mock.MagicMock()
        # Fix the mockgun update method since it returns a list instead of a dict
        # We unfortunately also need to fix the batch method since it assumes a list
        self.mock_sg.update = mock.MagicMock(side_effect=partial(self.mock_sg_update, self.mock_sg.update))
        self.mock_sg.batch = mock.MagicMock(side_effect=self.mock_sg_batch)
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
                # note: This is the only different line with mockgun.batch.
                # Since mockgun.update returns a list instead of a dict (which is the case for shotgun),
                # mockgun.batch here returns the first item of the list, but since we patch mockgun.update
                # to return a dict, we also need to amend this line to append the dict and not the first element
                # of a list.
                results.append(self.mock_sg.update(request["entity_type"], request["entity_id"], request["data"]))
            elif request["request_type"] == "delete":
                results.append(self.mock_sg.delete(request["entity_type"], request["entity_id"]))
            else:
                raise shotgun_api3.ShotgunError("Invalid request type %s in request %s" % (request["request_type"], request))
        return results

    def add_to_sg_mock_db(self, entities):
        """
        Adds an entity or entities to the mocked ShotGrid database.

        This is required because when finding entities with mockgun, it
        doesn't return a "name" key.

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

            self.mock_sg._db[et][eid] = entity
