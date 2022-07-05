# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
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
        self._executor = ThreadPoolExecutor()

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

    def upload_versions(self):
        """
        Uploads movies to Versions in SG, in parallel.
        """
        self._progress = 0

        # map executes the calls to upload version in parallel, and yields the results as
        # soon as available. That's why we can loop over them and increment the progress.
        # See https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Executor.map
        for _ in self._executor.map(
            self.upload_version, self._sg_versions, self._movies
        ):
            self.progress += 1

    def upload_version(self, sg_version, movie):
        """
        Uploads a movie to a SG Version.

        :param sg_version: The SG Version to upload to.
        :param movie: The movie to upload.
        """
        self._sg.upload(
            "Version",
            sg_version["id"],
            movie,
            "sg_uploaded_movie"
        )
        logger.debug("Uploaded %s to %s" % (os.path.basename(movie), sg_version["code"]))
