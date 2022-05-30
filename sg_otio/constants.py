# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#

# Default head in and handle values
DEFAULT_HEAD_IN = 1001
DEFAULT_HEAD_IN_DURATION = 8
DEFAULT_TAIL_OUT_DURATION = 8

# Fields we need to retrieve from Cuts
_CUT_FIELDS = [
    "code",
    "id",
    "project",
    "entity",
    "sg_status_list",
    "image",
    "description",
    "created_by",
    "updated_by",
    "updated_at",
    "created_at",
    "revision_number",
    "fps",
    "timecode_start_text",
    "timecode_end_text"
]

# Fields we need to retrieve on CutItems
_CUT_ITEM_FIELDS = [
    "code",
    "cut",
    "timecode_cut_item_in_text",
    "timecode_cut_item_out_text",
    "cut_order",
    "cut_item_in",
    "cut_item_out",
    "shot",
    "shot.Shot.code",
    "cut_duration",
    "cut_item_duration",
    "cut.Cut.fps",
    "version",
    "version.Version.code",
    "version.Version.entity",
    "version.Version.image",
]
