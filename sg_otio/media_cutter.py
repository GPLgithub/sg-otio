# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging
import os
import subprocess
import sys
import tempfile
from concurrent.futures import wait, FIRST_EXCEPTION, ProcessPoolExecutor
from distutils.spawn import find_executable

import opentimelineio as otio

from .utils import get_available_filename, compute_clip_version_name, get_path_from_target_url

logger = logging.getLogger(__name__)


class MediaCutter(object):
    """
    Class to extract media from a movie using ffmpeg.

    A timeline is provided (we only consider the first video track), along with a movie representing
    the video track.

    For each clip that does not have a Media Reference

    """

    def __init__(self, sg, timeline, movie):
        super(MediaCutter, self).__init__()
        self._sg = sg
        self._movie = movie
        self._media_dir = None
        self._executor = ProcessPoolExecutor()
        if not timeline.video_tracks:
            raise ValueError("Timeline has no video tracks")
        if len(timeline.video_tracks()) > 1:
            logger.warning("Only one video track is supported, using the first one.")
        self._video_track = timeline.video_tracks()[0]

    def cancel(self):
        self._executor.shutdown(wait=False)

    @property
    def media_dir(self):
        if not self._media_dir:
            self._media_dir = tempfile.mkdtemp()
        return self._media_dir

    def cut_media_for_clips(self):
        clips_with_no_media_references = []
        clip_media_names = []
        for i, clip in enumerate(self._video_track.each_clip()):
            if clip.media_reference.is_missing_reference:
                clips_with_no_media_references.append(clip)
                clip_media_names.append(compute_clip_version_name(clip, i + 1))
            # TODO: Deal with clips with media references with local filepaths that cannot be found.
        if not clips_with_no_media_references:
            logger.info("No clips need extracting from movie.")
            return
        # Get the clips which have media names that already exist in SG, to avoid recreating Versions if
        # they already exist.
        sg_versions = self._sg.find(
            "Version",
            [["code", "in", clip_media_names]],
            ["code"]
        )
        sg_version_codes = [version["code"] for version in sg_versions]
        futures = []
        clips_to_extract_names = []
        for clip, media_name in zip(clips_with_no_media_references, clip_media_names):
            if media_name in sg_version_codes:
                logger.debug("Clip %s already exists in SG, skipping extraction." % media_name)
            else:
                futures.append(self._extract_clip_media(clip, media_name))
                clips_to_extract_names.append(clip.name)
        if not futures:
            logger.info("No clips need extracting from movie.")
            return
        logger.info("Extracting clips %s media from movie %s..." % (clips_to_extract_names, self._movie))
        # The function will return when any future finishes by raising an exception.
        # If no future raises an exception then it is equivalent to ALL_COMPLETED.
        # See https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.wait
        wait(futures, return_when=FIRST_EXCEPTION)
        logger.info("Finished extracting media from movie %s" % self._movie)

    def _get_media_filename(self, media_name):
        filename = get_available_filename(self.media_dir, media_name, "mov")
        # Create an empty file to be able to get available filenames if some clips have the same media name.
        open(filename, "w").close()
        return filename

    def _extract_clip_media(self, clip, media_name):
        clip_range_in_track = clip.transformed_time_range(clip.visible_range(), clip.parent())
        media_filename = self._get_media_filename(media_name)

        logger.debug("Extracting clip %s" % media_name)
        logger.debug("Extracting to %s" % media_filename)

        extractor = FFmpegExtractor(
            self._movie,
            media_filename,
            clip_range_in_track.start_time.to_seconds(),
            clip_range_in_track.end_time_exclusive().to_seconds(),
            clip_range_in_track.duration.to_frames()
        )
        future = self._executor.submit(
            extractor,
        )
        # future.add_done_callback(self.progress_incremented)
        clip.media_reference = otio.schema.ExternalReference(
            target_url="file://" + media_filename,
            available_range=clip.visible_range()
        )
        # Name is not in the constructor.
        clip.media_reference.name = media_name
        return future


class FFmpegExtractor(object):
    def __init__(self, input_media, output_media, start_time, end_time, nb_frames):
        self._input_media = input_media
        self._output_media = output_media
        self._start_time = start_time
        self._end_time = end_time
        self._progress = 0
        self._progress_max = nb_frames

    def __call__(self):
        return self.extract()

    @property
    def ffmpeg(self):
        ffmpeg = find_executable("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("Could not find executable ffmpeg.")
        return ffmpeg

    def progress_changed(self, line):
        if "frame=" in line:
            self._progress = int(line.split("=")[1].strip())
            logger.debug(
                "%s progress=%d/%d" % (os.path.basename(self._output_media), self._progress, self._progress_max)
            )
        elif "progress=end" in line:
            # This should not be necessary since there always seems to be a frame=last_frame output,
            # but just in case.
            self._progress = self._progress_max
            logger.debug(
                "%s progress=%d/%d" % (os.path.basename(self._output_media), self._progress, self._progress_max)
            )

    @property
    def _movie_extract_command(self):
        # Movie extract command
        # Why -ss is added after -i? From the docs:
        # "When used as an input option (before -i), seeks in this input file to position.
        # Note that in most formats it is not possible to seek exactly, so ffmpeg will seek
        # to the closest seek point before position. When transcoding and -accurate_seek is enabled (the default),
        # this extra segment between the seek point and position will be decoded and discarded.
        # When doing stream copy or when -noaccurate_seek is used, it will be preserved.
        # When used as an output option (before an output url), decodes but discards input
        # until the timestamps reach position."
        # Since we stream copy, we don't want to preserve the part between the input start point
        # and the stipulated start time.
        return [
            self.ffmpeg,
            "-y", "-nostdin", "-progress", "-", "-loglevel", "error", "-nostats",
            "-i", self._input_media,
            "-ss", str(self._start_time),
            "-to", str(self._end_time),
            self._output_media
        ]

    def extract(self):
        """
        Run the given command in a subprocess and parse the output with the
        given parser.

        :param command_args: The command to run as a list suitable for :meth:`subprocess.Popen`.
        :param line_parser: A callable accepting a string as unique parameter.
        :returns: A tuple, the subprocess exit code, as an integer, ``0`` meaning success,
                  and the output of the command as an array of output lines.
        """
        cmd_args = self._movie_extract_command
        logger.debug("Running %s" % " ".join(cmd_args))
        close_fds = True
        # Although subprocess technically supports using close_fds on
        # Windows, it cannot be used when stdin, stdout, and stderr are
        # redirected without an exception being raised.
        # Note: this was fixed in Python 3.4
        # https://stackoverflow.com/questions/48671215/howto-workaround-of-close-fds-true-and-redirect-stdout-stderr-on-windows
        if sys.platform == "win32":
            close_fds = False

        subproc = subprocess.Popen(
            cmd_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            universal_newlines=True,
            close_fds=close_fds,
        )
        lines = []
        while True:
            line = subproc.stdout.readline()
            if not line:
                break
            self.progress_changed(line)
            lines.append(line)
        # Flush stdout / stderr to avoid deadlocks
        # and retrieve exit code
        subproc.communicate()
        return subproc.returncode, lines
