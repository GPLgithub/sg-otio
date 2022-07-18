# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import os
import logging
import sys

import shotgun_api3
from shotgun_api3.lib import mockgun

from sg_otio.constants import _SG_OTIO_MANIFEST_PATH

# Define a standard logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(__file__))


# Set the manifest path to sg-otio manifest so that our own cmx_3600 adapter takes precedence
# over the built-in cmx_3600 adapter.
manifest_path = os.getenv("OTIO_PLUGIN_MANIFEST_PATH")
if not manifest_path:
    os.environ["OTIO_PLUGIN_MANIFEST_PATH"] = _SG_OTIO_MANIFEST_PATH


def pytest_addoption(parser):
    """
    Add custom command line arguments to pytest to generate the Mockgun schema
    files.
    """
    parser.addoption(
        "--generate_schema",
        action="store",
        dest="generate_schema",
        nargs=3,
        required=False,
        help="A SG url, script name and its key to generate a schema"
    )


def get_default_mockgun_schema_paths():
    """
    Return the default Mockgun schema and schema_entity file paths

    :returns: A tuple with two strings.
    """
    fixtures_root = os.path.join(
        os.path.dirname(__file__),
        "fixtures",
    )
    mockgun_schema_path = os.path.join(
        fixtures_root, "mockgun", "schema.pickle"
    )
    mockgun_schema_entity_path = os.path.join(
        fixtures_root, "mockgun", "schema_entity.pickle"
    )
    return mockgun_schema_path, mockgun_schema_entity_path


def pytest_configure(config):
    """
    Treat additional arguments which were specified on the command line.
    """
    if config.option.generate_schema:
        mockgun_schema_path, mockgun_schema_entity_path = get_default_mockgun_schema_paths()
        sg_site, sg_script, sg_script_key = config.option.generate_schema
        logger.info(
            "Generating schema files for %s in %s and %s" % (
                sg_site, mockgun_schema_path, mockgun_schema_entity_path
            )
        )
        sg = shotgun_api3.Shotgun(sg_site, sg_script, sg_script_key)
        mockgun.generate_schema(
            sg,
            mockgun_schema_path,
            mockgun_schema_entity_path,
        )
        logger.info(
            "Schema for files %s generated in %s and %s" % (
                sg_site, mockgun_schema_path, mockgun_schema_entity_path
            )
        )


def pytest_sessionstart(session):
    """
    Set Mockgun schema files for the current session.
    """
    mockgun_schema_path, mockgun_schema_entity_path = get_default_mockgun_schema_paths()
    mockgun.Shotgun.set_schema_paths(
        mockgun_schema_path, mockgun_schema_entity_path
    )
