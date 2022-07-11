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

from .utils import compute_clip_version_name

logger = logging.getLogger(__name__)


class MediaCutter(object):
    """
    Class to extract media from a movie using ffmpeg.

    A timeline is provided (we only consider the first video track), along with a movie representing
    the video track.

    For each clip that does not have a Media Reference, use ffmpeg to extract the media from the movie.
    These extractions are done in parallel.
    """

    def __init__(self, timeline, movie):
        """
        Initialize the Media Cutter.

        :param timeline: An instance of :class:`otio.schema.Timeline`.
        :param str movie: The path to the movie to extract media from.
        """
        super(MediaCutter, self).__init__()
        self._movie = movie
        self._media_dir = None
        self._executor = ProcessPoolExecutor()
        if not timeline.video_tracks():
            raise ValueError("Timeline must have a video track.")
        if len(timeline.video_tracks()) > 1:
            logger.warning("Only one video track is supported, using the first one.")
        if not self.ffmpeg:
            raise RuntimeError("ffmpeg cannot be found.")
        self._video_track = timeline.video_tracks()[0]
        self._media_filenames = []

    def cancel(self):
        """
        Cancel the extraction.
        """
        self._executor.shutdown(wait=False)

    @property
    def ffmpeg(self):
        """
        Return the path to the ffmpeg executable, if any.

        :returns: A string.
        """
        return find_executable("ffmpeg")

    @property
    def media_dir(self):
        """
        Return a temporary directory to store extracted media.

        :returns: A temporary directory path.
        """
        if not self._media_dir:
            self._media_dir = tempfile.mkdtemp()
        return self._media_dir

    def cut_media_for_clips(self):
        """
        Extract media for clips in the timeline that don't have a media reference.

        If all clips have a media reference, this method does nothing.
        The extraction is done in parallel, but this method waits for all the extractions to finish.
        """
        clips_with_no_media_references = []
        clip_media_names = []
        for i, clip in enumerate(self._video_track.each_clip()):
            if clip.media_reference.is_missing_reference:
                clips_with_no_media_references.append(clip)
                clip_media_names.append(compute_clip_version_name(clip, i + 1))
        if not clips_with_no_media_references:
            logger.info("No clips need extracting from movie.")
            return
        futures = []
        clips_to_extract_names = []
        FFmpegExtractor.ffmpeg = self.ffmpeg
        for clip, media_name in zip(clips_with_no_media_references, clip_media_names):
            futures.append(self._extract_clip_media(clip, media_name))
            clips_to_extract_names.append(clip.name)
        if not futures:
            logger.info("No clips need extracting from movie.")
            return
        logger.info("Extracting clips %s media from movie %s..." % (clips_to_extract_names, self._movie))
        # The function will return when any future finishes by raising an exception.
        # If no future raises an exception then it is equivalent to ALL_COMPLETED.
        # See https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.wait
        try:
            _, not_done = wait(futures, return_when=FIRST_EXCEPTION)
        except Exception:
            # Cancel the remaining futures before re-raising the exception.
            if not_done:
                self.cancel()
            raise
        # Double check what we extracted
        missing = []
        for clip in clips_with_no_media_references:
            media_filename = clip.media_reference.target_url.replace("file://", "")
            if not os.path.exists(media_filename):
                missing.append("%s: %s" % (media_name, media_filename))
        if missing:
            raise RuntimeError("Failed to extract %s" % missing)
        logger.info("Finished extracting media from movie %s" % self._movie)

    def _get_media_filename(self, media_name):
        """
        Return the path to the media file for the given media name.

        It checks for name collisions and appends a number to the name if necessary.

        :param str media_name: The name of the media file.
        :returns: The path to the media file.
        """
        filename = os.path.join(self.media_dir, "%s.mov" % media_name)
        i = 1
        while True:
            if filename not in self._media_filenames:
                self._media_filenames.append(filename)
                return filename
            filename = os.path.join(self._media_dir, "%s_%03d.mov" % (media_name, i))
            i += 1

    def _extract_clip_media(self, clip, media_name):
        """
        Submit a future to extract the media for the given clip.

        :param clip: An instance of :class:`otio.schema.Clip`
        :param str media_name: The name of the media to extract.
        :returns: An instance of :class:`concurrent.futures.Future`.
        """
        # We're looking for the range of the clip in the track, without taking
        # into account the track offset, since the movie provided for cutting
        # starts at frame 0.
        clip_range_in_track = clip.transformed_time_range(clip.visible_range(), clip.parent())
        media_filename = self._get_media_filename(media_name)

        logger.info("Extracting %s to %s" % (media_name, media_filename))

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
        clip.media_reference = otio.schema.ExternalReference(
            target_url="file://" + media_filename,
            available_range=clip.visible_range()
        )
        # Name is not in the constructor.
        clip.media_reference.name = media_name
        return future


class FFmpegExtractor(object):
    """
    Class to extract media from a movie using ffmpeg.
    """
    ffmpeg = None

    def __init__(self, input_media, output_media, start_time, end_time, nb_frames):
        """
        Initialize the FFmpeg extractor.

        :param str input_media: The path to the movie to extract media from.
        :param str output_media: The path to the media file to extract to.
        :param int start_time: The start time of the media to extract in seconds.
        :param int end_time: The end time of the media to extract in seconds (exclusive).
        :param int nb_frames: The number of frames to extract.
        """
        self._input_media = input_media
        self._output_media = output_media
        self._start_time = start_time
        self._end_time = end_time
        self._progress = 0
        self._progress_max = nb_frames

    def __call__(self):
        """
        Extract the media.

        This is needed in Python 2 so that we can submit this class to a ProcessPoolExecutor.
        In Python 3, we could just submit the call to extract() to the executor.
        """
        return self.extract()

    def progress_changed(self, line):
        """
        Update the progress of the extraction.

        Called for each line of output from ffmpeg, and finds lines that contain "frame=XXX"
        to update the progress.

        :param str line: A ffmpeg output line.
        """
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
        """
        Return the ffmpeg command arguments to extract the media.

        :returns: A list of arguments.
        """
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
            # These settings allow getting only progress stats or errors in the output.
            "-y", "-nostdin", "-progress", "-", "-loglevel", "error", "-nostats",
            "-i", self._input_media,
            "-ss", str(self._start_time),
            "-to", str(self._end_time),
            self._output_media
        ]

    def extract(self):
        """
        Run the ffmpeg command to extract the media.

        :returns: A tuple, the subprocess exit code, as an integer, ``0`` meaning success,
                  and the output of the command as an array of output lines.
        """
        cmd_args = self._movie_extract_command
        logger.info("Running %s" % " ".join(cmd_args))
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
