#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import argparse
import logging
import os

import opentimelineio as otio
from shotgun_api3 import Shotgun

from sg_otio.sg_settings import SGSettings
from sg_otio.utils import get_write_url, get_read_url
from sg_otio.media_cutter import MediaCutter
from sg_otio.constants import _SG_OTIO_MANIFEST_PATH
from sg_otio.track_diff import SGTrackDiff

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
    if args.command == "read":
        read_from_sg(args)
    elif args.command == "write":
        write_to_sg(args)
    elif args.command == "compare":
        compare_to_sg(args)


def read_from_sg(args):
    """
    Reads information from a Cut in ShotGrid and print it
    to stdout, or write it to a file.

    If printed to stdout, the output is in OTIO format.
    If written to a file, the output depends on the extension of the file
    or the adapter chosen.

    The retrieved SG entities are stored in the items metadata.

    :param args: The command line arguments.
    """
    url = get_read_url(
        sg_site_url=args.sg_site_url,
        cut_id=args.cut_id,
        session_token=_get_session_token(args)
    )
    timeline = otio.adapters.read_from_file(
        url,
        adapter_name="ShotGrid",
    )
    if not args.file:
        if args.adapter:
            # It seems otio write_to_string choke on unset adapter?
            logger.info(otio.adapters.write_to_string(timeline, adapter_name=args.adapter))
        else:
            logger.info(otio.adapters.write_to_string(timeline))
    else:
        _, ext = os.path.splitext(args.file)
        if (ext and ext.lower() == ".edl") or args.adapter == "cmx_3600":
            otio.adapters.write_to_file(
                timeline,
                args.file,
                adapter_name=args.adapter,
                rate=args.frame_rate,  # param specific to cmx_3600 adapter
            )
        else:
            otio.adapters.write_to_file(timeline, args.file, adapter_name=args.adapter)


def read_timeline_from_file(args):
    """
    Read and return a timeline from the args.

    :returns: A :class:`otio.schema.Timeline` instance.
    """
    _, ext = os.path.splitext(args.file)
    if (ext and ext.lower() == ".edl") or args.adapter == "cmx_3600":
        # rate param is specific to cmx_3600 adapter
        timeline = otio.adapters.read_from_file(
            args.file, adapter_name=args.adapter, rate=args.frame_rate
        )
    else:
        timeline = otio.adapters.read_from_file(
            args.file, adapter_name=args.adapter
        )
    return timeline


def write_to_sg(args):
    """
    Write an input file to SG as a Cut.

    The input file can be any format supported by OTIO.
    If no adapter is provided, the default adapter for the file extension is used.

    :param args: The command line arguments.
    """
    session_token = _get_session_token(args)
    url = get_write_url(
        sg_site_url=args.sg_site_url,
        entity_type=args.entity_type,
        entity_id=args.entity_id,
        session_token=session_token
    )
    timeline = read_timeline_from_file(args)
    if not timeline.video_tracks():
        raise ValueError("The input file does not contain any video tracks.")
    if args.settings:
        SGSettings.from_file(args.settings)
    if args.movie:
        if not os.path.isfile(args.movie):
            raise ValueError("%s does not exist" % args.movie)
    if SGSettings().create_missing_versions and args.movie:
        media_cutter = MediaCutter(
            timeline,
            args.movie,
        )
        media_cutter.cut_media_for_clips()

    otio.adapters.write_to_file(
        timeline,
        url,
        adapter_name="ShotGrid",
        input_media=args.movie,
        input_file=args.file,
    )
    logger.info("File %s successfully written to %s" % (args.file, url))


def compare_to_sg(args):
    """
    Compare an input file to a SG Cut.

    :param args: The command line arguments.
    """
    timeline = read_timeline_from_file(args)
    if not timeline.video_tracks():
        raise ValueError("The input file does not contain any video tracks.")
    new_track = timeline.video_tracks()[0]
    session_token = _get_session_token(args)
    url = get_read_url(
        sg_site_url=args.sg_site_url,
        cut_id=args.cut_id,
        session_token=session_token
    )
    old_timeline = otio.adapters.read_from_file(
        url,
        adapter_name="ShotGrid",
    )
    if not old_timeline.video_tracks():
        raise ValueError("The SG Cut does not contain any video tracks.")
    sg_track = old_timeline.video_tracks()[0]
    sg = Shotgun(args.sg_site_url, session_token=session_token)
    diff = SGTrackDiff(
        sg,
        sg_track.metadata["sg"]["project"],
        new_track=new_track,
        old_track=sg_track
    )
    old_cut_url = "%s/detail/Cut/%s" % (sg.base_url, args.cut_id)
    title, report = diff.get_report(
        "%s" % os.path.basename(args.file),
        sg_links=[old_cut_url]
    )
    logger.info(title)
    logger.info(
        report,
    )
    if args.write:
        sg_entity = diff.sg_link
        if not sg_entity:
            raise ValueError("Can't update a Cut without a SG link.")
        logger.info(
            "Writing Cut %s to SG for %s %s..." % (
                new_track.name, sg_entity["type"], sg_entity["id"]
            )
        )
        write_url = get_write_url(
            sg_site_url=args.sg_site_url,
            entity_type=sg_entity["type"],
            entity_id=sg_entity["id"],
            session_token=session_token
        )

        otio.adapters.write_to_file(
            new_track,
            write_url,
            adapter_name="ShotGrid",
            previous_track=sg_track,
            input_file=args.file,
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


def _get_session_token(args):
    """
    Get the session token from the arguments.

    :param args: The command line arguments.
    """
    if args.session_token:
        return args.session_token
    if args.login and args.password:
        sg = Shotgun(args.sg_site_url, login=args.login, password=args.password)
    elif args.script_name and args.api_key:
        sg = Shotgun(args.sg_site_url, script_name=args.script_name, api_key=args.api_key)
    return sg.get_session_token()


if __name__ == "__main__":
    run()
