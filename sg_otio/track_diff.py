# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#

from .utils import compute_clip_shot_name


class SGTrackDiff(object):
    """
    """
    def __init__(self, previous_track, new_track):
        """
        """

        # Retrieve Shots from the previous_track
        for clip in previous_track.each_clip():
            # Check if we have some SG meta data
            sg_cut_item = clip.get("sg")
            if sg_cut_item:
                shot_name = sg_cut_item["shot"]["code"]

            shot_name = compute_clip_shot_name(clip)
        # Match clips in the new track with:
        # - Is it linked to the same Shot?
        # - Is it linked to the same Version?
        # - Is the Cut order the same?
        # - Is the tc in the same?
        # - Is the tc out the same?
