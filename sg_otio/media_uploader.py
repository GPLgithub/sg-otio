# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from .sg_settings import SGSettings

logger = logging.getLogger(__name__)
logger.setLevel(SGSettings().log_level)


class MediaUploader(object):

    def __init__(self, sg, sg_versions, movies):
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
        return self._progress_max

    @property
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, value):
        logger.debug("Progress: %d/%d" % (value, self._progress_max))
        self._progress = value

    def upload_versions(self):
        self._progress = 0
        results = self._executor.map(
            self.upload_version, self._sg_versions, self._movies
        )
        for _ in results:
            self.progress += 1

    def upload_version(self, sg_version, movie):
        self._sg.upload(
            "Version",
            sg_version["id"],
            movie,
            "sg_uploaded_movie"
        )
        logger.info("Uploaded %s to %s" % (os.path.basename(movie), sg_version["code"]))
