# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import logging
import os
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class MediaUploader(object):
    """
    A class for uploading movies to Versions in SG, in parallel.
    """

    def __init__(self, sg, sg_versions, movies):
        """
        Initialize a :class:`MediaUploader` instance.

        :param sg: A SG API session handle.
        :param sg_versions: A list of SG Versions to upload to.
        :param movies: A list of movies to upload.
        :raises ValueError: If the number of movies does not match the number of versions.
        """
        if len(sg_versions) != len(movies):
            raise ValueError(
                "sg_versions and movies must be the same length, not %d and %d" % (
                    len(sg_versions), len(movies)
                )
            )
        self._sg = sg
        self._sg_versions = sg_versions
        self._movies = movies
        self._progress = 0
        self._progress_max = len(sg_versions)

    @property
    def progress_max(self):
        """
        Returns the maximum number of progress steps.

        :returns: An integer.
        """
        return self._progress_max

    @property
    def progress(self):
        """
        Returns the current progress step.

        :returns: An integer.
        """
        return self._progress

    @progress.setter
    def progress(self, value):
        """
        Sets the current progress step.

        :param value: An integer.
        """
        logger.debug("Progress: %d/%d" % (value, self._progress_max))
        self._progress = value

    def upload_versions(self, max_workers=None):
        """
        Uploads movies to Versions in SG, in parallel.

        :param int max_workers: The maximum number of workers to run in parallel.
                                If ``None``, the default system value is used.
        """
        self._progress = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # map executes the calls to upload version in parallel, and yields the results as
            # soon as available.
            # See https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Executor.map
            try:
                for sg_version, movie in executor.map(
                    self.upload_version, self._sg_versions, self._movies
                ):
                    logger.info("Uploaded %s to %s" % (os.path.basename(movie), sg_version["code"]))
                    self.progress += 1
            except Exception:
                # Exceptions raised by the futures are re-raised when getting their
                # result. This means that we will need to use something else
                # than map if we want to get a complete report of successes
                # and failures.
                logger.error(
                    "Only managed to upload %d media out of %d" % (self.progress, self.progress_max)
                )
                raise

    def upload_version(self, sg_version, movie):
        """
        Uploads a movie to a SG Version.

        :param sg_version: The SG Version to upload to.
        :param movie: The movie to upload.
        :returns: A tuple with the SG Version dictionary and the movie which was
                  uploaded.
        """
        self._sg.upload(
            "Version",
            sg_version["id"],
            movie,
            "sg_uploaded_movie"
        )
        return sg_version, movie
