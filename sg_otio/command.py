# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging
import os

import opentimelineio as otio

from .sg_settings import SGSettings
from .utils import get_write_url, get_read_url
from .media_cutter import MediaCutter
from .track_diff import SGTrackDiff

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sg-otio")


class SGOtioCommand(object):
    """
    A class to run SGOtio commands.
    """
    def __init__(self, sg, verbose=False):
        """
        Instantiate a new :class:`SGOtioCommand`.

        :param sg: A connected SG handle.
        """
        self._sg = sg
        self._sg_session_token = self._sg.get_session_token()
        if verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

    def read_from_sg(self, sg_cut_id, file_path=None, adapter_name=None, frame_rate=24):
        """
        Reads information from a Cut in ShotGrid and print it
        to stdout, or write it to a file.

        If printed to stdout, the output is in OTIO format.
        If written to a file, the output depends on the extension of the file
        or the adapter chosen.

        The retrieved SG entities are stored in the items metadata.

        :param sg_cut_id: A SG Cut id.
        :param str file_path: Optional file path to write to.
        :param str adapter_name: Optional otio adapter name, e.g. cmx_3600.
        :param float frame_rate: Optional frame rate to use when reading the file.
        """
        url = get_read_url(
            sg_site_url=self._sg.base_url,
            cut_id=sg_cut_id,
            session_token=self._sg_session_token
        )
        timeline = otio.adapters.read_from_file(
            url,
            adapter_name="ShotGrid",
        )
        if not file_path:
            if adapter_name:
                # It seems otio write_to_string choke on unset adapter?
                logger.info(otio.adapters.write_to_string(timeline, adapter_name=adapter_name))
            else:
                logger.info(otio.adapters.write_to_string(timeline))
        else:
            _, ext = os.path.splitext(file_path)
            if (ext and ext.lower() == ".edl") or adapter_name == "cmx_3600":
                otio.adapters.write_to_file(
                    timeline,
                    file_path,
                    adapter_name=adapter_name,
                    rate=frame_rate,  # param specific to cmx_3600 adapter
                )
            else:
                otio.adapters.write_to_file(timeline, file_path, adapter_name=adapter_name)

    def read_timeline_from_file(self, file_path, adapter_name=None, frame_rate=24):
        """
        Read and return a timeline from a file.

        :param str file_path: Full path to the file to read.
        :param str adapter_name: Optional otio adapter name, e.g. cmx_3600.
        :param float frame_rate: Optional frame rate to use when reading the file.
        :returns: A :class:`otio.schema.Timeline` instance.
        """
        _, ext = os.path.splitext(file_path)
        if (ext and ext.lower() == ".edl") or adapter_name == "cmx_3600":
            # rate param is specific to cmx_3600 adapter
            timeline = otio.adapters.read_from_file(
                file_path, adapter_name=adapter_name, rate=frame_rate
            )
        else:
            timeline = otio.adapters.read_from_file(
                file_path, adapter_name=adapter_name
            )
        return timeline

    def write_to_sg(
        self,
        file_path,
        entity_type,
        entity_id,
        adapter_name=None,
        frame_rate=24,
        settings=None,
        movie=None,
    ):
        """
        Write an input file to SG as a Cut.

        The input file can be any format supported by OTIO.
        If no adapter is provided, the default adapter for the file extension is used.

        :param str file_path: Full path to the file to read.
        :param str entity_type: A valid SG Entity type.
        :param entity_id: A valid SG Entity id for the given Entity type.
        :param str adapter_name: Optional otio adapter name, e.g. cmx_3600.
        :param float frame_rate: Optional frame rate to use when reading the file.
        :param str settings: Optional settings file path to use.
        :param str movie: Optional movie file path to use with the Cut.
        """
        url = get_write_url(
            sg_site_url=self._sg.base_url,
            entity_type=entity_type,
            entity_id=entity_id,
            session_token=self._sg_session_token
        )
        timeline = self.read_timeline_from_file(file_path, adapter_name, frame_rate)
        if not timeline.video_tracks():
            raise ValueError("The input file does not contain any video tracks.")
        if settings:
            SGSettings.from_file(settings)
        if movie:
            if not os.path.isfile(movie):
                raise ValueError("%s does not exist" % movie)
        if SGSettings().create_missing_versions and movie:
            media_cutter = MediaCutter(
                timeline,
                movie,
            )
            media_cutter.cut_media_for_clips()

        otio.adapters.write_to_file(
            timeline,
            url,
            adapter_name="ShotGrid",
            input_media=movie,
            input_file=file_path,
        )
        logger.info("File %s successfully written to %s" % (file_path, url))

    def compare_to_sg(
        self,
        file_path,
        sg_cut_id,
        adapter_name=None,
        frame_rate=24,
        write=False,
        report_path=None,
    ):
        """
        Compare an input file to a SG Cut.

        :param str file_path: Full path to the file to read.
        :param sg_cut_id: A valid SG Cut id.
        :param str adapter_name: Optional otio adapter name, e.g. cmx_3600.
        :param float frame_rate: Optional frame rate to use when reading the file.
        :param bool write: If ``True`` import the new Cut in SG.
        :param str report_path: If set, write a CSV report to the given file.
        """
        timeline = self.read_timeline_from_file(file_path, adapter_name, frame_rate)
        if not timeline.video_tracks():
            raise ValueError("The input file does not contain any video tracks.")
        new_track = timeline.video_tracks()[0]
        url = get_read_url(
            sg_site_url=self._sg.base_url,
            cut_id=sg_cut_id,
            session_token=self._sg_session_token
        )
        old_timeline = otio.adapters.read_from_file(
            url,
            adapter_name="ShotGrid",
        )
        if not old_timeline.video_tracks():
            raise ValueError("The SG Cut does not contain any video tracks.")
        sg_track = old_timeline.video_tracks()[0]
        metadata = sg_track.metadata.to_dict()
        diff = SGTrackDiff(
            self._sg,
            metadata["sg"]["project"],
            new_track=new_track,
            old_track=sg_track
        )
        old_cut_url = "%s/detail/Cut/%s" % (self._sg.base_url, sg_cut_id)
        title, report = diff.get_report(
            "%s" % os.path.basename(file_path),
            sg_links=[old_cut_url]
        )
        if report_path:
            if os.path.splitext(report_path) in [".csv", ".CSV"]:
                diff.write_csv_report(
                    report_path, title, sg_links=[old_cut_url]
                )
            else:
                with open(report_path, "w") as f:
                    f.write(title)
                    f.write(report)
            logger.info("Report written to %s" % report_path)
        else:
            logger.info(title)
            logger.info(
                report,
            )
        if write:
            sg_entity = diff.sg_link
            if not sg_entity:
                raise ValueError("Can't update a Cut without a SG link.")
            logger.info(
                "Writing Cut %s to SG for %s %s..." % (
                    new_track.name, sg_entity["type"], sg_entity["id"]
                )
            )
            write_url = get_write_url(
                sg_site_url=self._sg.base_url,
                entity_type=sg_entity["type"],
                entity_id=sg_entity["id"],
                session_token=self._sg_session_token
            )

            otio.adapters.write_to_file(
                new_track,
                write_url,
                adapter_name="ShotGrid",
                previous_track=sg_track,
                input_file=file_path,
            )
