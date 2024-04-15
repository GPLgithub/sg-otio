#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import argparse
import logging
import os

from shotgun_api3 import Shotgun

from sg_otio.constants import _SG_OTIO_MANIFEST_PATH
from sg_otio.command import SGOtioCommand

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sg-otio")

# Set the manifest path to sg-otio manifest so that our own cmx_3600 adapter takes precedence
# over the built-in cmx_3600 adapter.
manifest_path = os.getenv("OTIO_PLUGIN_MANIFEST_PATH")
if not manifest_path:
    os.environ["OTIO_PLUGIN_MANIFEST_PATH"] = _SG_OTIO_MANIFEST_PATH


def run():
    """
    Parse command line arguments and read Cuts from SG to a file, or write files to SG as Cuts.
    """
    parser = argparse.ArgumentParser(
        prog="sg-otio",
        description="Read Cuts from SG to a file, write files to SG as Cuts, compare files to SG Cuts."
    )
    subparser = parser.add_subparsers(dest="command")
    # Read sub parser
    read_parser = subparser.add_parser(
        "read",
        help="Read a Cut from SG and write it to a file, or to the std output in OTIO format."
    )
    # Write sub parser
    write_parser = subparser.add_parser(
        "write",
        help="Write a Timeline or a video track to SG as a Cut."
    )
    # Compare sub parser
    compare_parser = subparser.add_parser(
        "compare",
        help="Compare a Timeline or a video track to a SG Cut."
    )
    # Common arguments for read, write and compare.
    # We need to add them to the subparsers and not the main parser so that
    # the first positional argument is "read" or "write".
    add_common_args(read_parser)
    add_common_args(write_parser)
    add_common_args(compare_parser)

    # Read parameters
    read_parser.add_argument(
        "--cut-id", "-i",
        required=True,
        help="The ID of the SG Cut to read."
    )
    read_parser.add_argument(
        "--file", "-f",
        required=False,
        help="An optional file to write the Cut to when reading it. "
             "If not provided, the output is printed to stdout in OTIO format."
    )
    # Write parameters
    write_parser.add_argument(
        "--file", "-f",
        required=True,
        help="The file to read the Timeline from (can be OTIO, EDL, etc)."
    )
    write_parser.add_argument(
        "--entity-type", "-e",
        required=True,
        help="The SG Entity type to link the Cut to. It can be a Project, a Cut, or any Entity a Cut can be linked to, "
             "e.g. a Sequence, a Reel."
    )
    write_parser.add_argument(
        "--entity-id", "-i",
        required=True,
        type=int,
        help="The SG Entity id to link the Cut to."
    )
    write_parser.add_argument(
        "--movie", "-m",
        required=False,
        help="An optional movie of the timeline so that it can be published as a Version and used to create Versions"
             "for each clip"
    )

    # Compare parameters
    compare_parser.add_argument(
        "--file", "-f",
        required=True,
        help="The file to read the Timeline from (can be OTIO, EDL, etc)."
    )
    compare_parser.add_argument(
        "--cut-id", "-i",
        required=True,
        help="The ID of the SG Cut to read."
    )
    compare_parser.add_argument(
        "--write", "-w",
        required=False,
        default=False,
        help="If true, update SG with values from the new Cut."
    )
    compare_parser.add_argument(
        "--report", "-rp",
        required=False,
        help="If set, write a report with changes. "
             "Text or CSV files are generated, based on the file extension."
    )

    args = parser.parse_args()

    # We need to have a command to check args set on subparsers.
    if not args.command:
        parser.print_help()
        exit(0)

    # Check that we can log in to SG
    if not (args.login and args.password):
        if not (args.script_name and args.api_key):
            if not args.session_token:
                raise ValueError(
                    "You must provide either a login, password, script name and API key or a session token."
                )
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    command = SGOtioCommand(_get_sg_handle(args), verbose=args.verbose)
    if args.command == "read":
        command.read_from_sg(
            sg_cut_id=args.cut_id,
            file_path=args.file,
            adapter_name=args.adapter,
            frame_rate=args.frame_rate,
        )
    elif args.command == "write":
        command.write_to_sg(
            file_path=args.file,
            entity_type=args.entity_type,
            entity_id=args.entity_id,
            adapter_name=args.adapter,
            frame_rate=args.frame_rate,
            settings=args.settings,
            movie=args.movie,
        )
    elif args.command == "compare":
        command.compare_to_sg(
            file_path=args.file,
            sg_cut_id=args.cut_id,
            adapter_name=args.adapter,
            frame_rate=args.frame_rate,
            write=args.write,
            report_path=args.report,
        )


def add_common_args(parser):
    """
    Add common arguments for reading and writing from/to SG.

    :param parser: An instance of :class:`argparse.ArgumentParser`.
    """
    # Common arguments to read and write
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print debug information."
    )
    parser.add_argument(
        "--sg-site-url", "-u",
        required=True,
        help="The SG URL to read the Cut from."
    )
    # Read login parameters
    # Option 1: login + password
    parser.add_argument(
        "--login", "-l",
        required=False,
        help="The SG login to use to login.",
    )
    parser.add_argument(
        "--password", "-p",
        required=False,
        help="The SG password to use to login."
    )
    # Option 2: script name and API key
    parser.add_argument(
        "--script-name", "-sn",
        required=False,
        help="The SG script name to use to login."
    )
    parser.add_argument(
        "--api-key", "-k",
        required=False,
        help="The SG API key to use to login."
    )
    # Option 3: session token
    parser.add_argument(
        "--session-token", "-t",
        required=False,
        help="The SG session token to use to login."
    )
    parser.add_argument(
        "--adapter", "-a",
        required=False,
        help="The adapter to use to read or write the file. If not provided, the default adapter "
             "for the extension is used."
    )
    parser.add_argument(
        "--settings", "-s",
        required=False,
        help="The settings JSON file to use when reading/writing. If not provided, the default settings are used."
    )
    parser.add_argument(
        "--frame-rate", "-rt",
        required=False,
        type=float,
        default=24,
        help="The frame rate to use when reading EDLs."
    )


def _get_sg_handle(args):
    """
    Get a SG handle from the arguments.

    :param args: The command line arguments.
    """
    if args.session_token:
        return Shotgun(args.sg_site_url, session_token=args.session_token)
    if args.login and args.password:
        return Shotgun(args.sg_site_url, login=args.login, password=args.password)
    elif args.script_name and args.api_key:
        return Shotgun(args.sg_site_url, script_name=args.script_name, api_key=args.api_key)
    raise ValueError("Unable to connect to SG from %s" % args)


if __name__ == "__main__":
    run()
