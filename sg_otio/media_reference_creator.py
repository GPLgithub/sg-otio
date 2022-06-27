from concurrent.futures import ProcessPoolExecutor, wait, FIRST_EXCEPTION
import logging
import os
import tempfile
import subprocess
from distutils.spawn import find_executable

import opentimelineio as otio

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class MediaReferenceCreator(object):

    def __init__(self, timeline, movie=None, version_names_template=None):
        # TODO: Check that Versions don't already exist in SG?
        self._timeline = timeline
        self._movie = movie
        self._version_names_template = version_names_template
        self._media_dir = None
        self._media_names = []
        self._pool = ProcessPoolExecutor()

    @property
    def ffmpeg(self):
        ffmpeg = find_executable("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("Could not find executable ffmpeg.")
        return ffmpeg

    @property
    def media_dir(self):
        if not self._media_dir:
            self._media_dir = tempfile.mkdtemp()
        return self._media_dir

    def _get_media_name(self, clip):
        if clip.name:
            # Make sure we don't have an extension in the name
            clip_name = os.path.splitext(clip.name)[0]

        else:
            # TODO: If there's no name, we need to generate one from the template.
            raise ValueError("Clip %s has no name" % clip)
        index = 1
        clip_unique_name = clip_name
        while True:
            if clip_unique_name not in self._media_names:
                self._media_names.append(clip_unique_name)
                return clip_unique_name
            clip_unique_name = "%s_%03d" % (clip_name, index)
            index += 1

    def create_media_references(self):
        if not self._timeline.video_tracks:
            raise ValueError("Timeline has no video tracks")
        if len(self._timeline.video_tracks()) > 1:
            logger.warning("Only one video track is supported, using the first one.")
        video_track = self._timeline.video_tracks()[0]
        clips_to_extract = []
        for clip in video_track.each_clip():
            if not clip.media_reference.is_missing_reference:
                # Just make sure that the media reference has a name, and it's unique
                clip.media_reference.name = self._get_media_name(clip)
            else:
                if not self._movie:
                    raise ValueError("Clip %s has no media reference, but no movie was provided" % clip.name)
                clips_to_extract.append(clip)
        if clips_to_extract:
            logger.info("Extracting %d clips media from movie %s..." % (len(clips_to_extract), self._movie))
            # Make sure ffmpeg is available before we start.
            _ = self.ffmpeg
            futures = [self.extract_clip_media(clip) for clip in clips_to_extract]
            wait(futures, return_when=FIRST_EXCEPTION)
            for future in futures:
                if future.exception():
                    raise future.exception()
        logger.info("Finished extracting media from movie %s" % self._movie)

    def extract_clip_media(self, clip):
        clip_range_in_track = clip.transformed_time_range(clip.visible_range(), clip.parent())
        media_name = self._get_media_name(clip)
        media_filename = os.path.join(self.media_dir, "%s.mov" % media_name)
        # Movie extract command
        # Why -ss is added after -i? From the docs:
        # " When used as an input option (before -i), seeks in this input file to position.
        # Note that in most formats it is not possible to seek exactly, so ffmpeg will seek
        # to the closest seek point before position. When transcoding and -accurate_seek is enabled (the default),
        # this extra segment between the seek point and position will be decoded and discarded.
        # When doing stream copy or when -noaccurate_seek is used, it will be preserved.
        # When used as an output option (before an output url), decodes but discards input
        # until the timestamps reach position."
        # Since we stream copy, we don't want to preserve the part between the input start point
        # and the stipulated start time.
        cmd = [
            self.ffmpeg,
            "-y", "-nostdin", "-loglevel", "error", "-nostats",
            "-i", self._movie,
            "-ss", str(clip_range_in_track.start_time.to_seconds()),
            "-to", str(clip_range_in_track.end_time_exclusive().to_seconds()),
            media_filename
        ]
        logger.info("Extracting clip %s" % clip.name)
        logger.debug("Executing command: %s" % " ".join(cmd))
        future = self._pool.submit(subprocess.check_call, cmd)
        clip.media_reference = otio.schema.ExternalReference(
            target_url="file://" + media_filename,
        )
        # Name is not in the constructor.
        clip.media_reference.name = media_name
        return future
