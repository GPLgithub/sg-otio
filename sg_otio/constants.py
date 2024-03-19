# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

import enum
import os

# Default head in and handle values
_DEFAULT_HEAD_IN = 1001
_DEFAULT_HEAD_IN_DURATION = 8
_DEFAULT_TAIL_OUT_DURATION = 8

# CutItem and Shot fields used to flag edit retimes and effects.
_RETIME_FIELD = "sg_respeed"
_EFFECTS_FIELD = "sg_effects"
_EFFECTS_DURATION_FIELD = "sg_effects_duration"
# Field used to store absolute cut order on CutItems and Shots.
_ABSOLUTE_CUT_ORDER_FIELD = "sg_absolute_cut_order"
# Field used to store cut order on Entities (Reel, Sequence, etc...)
_ENTITY_CUT_ORDER_FIELD = "sg_cut_order"

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
    "timecode_edit_in_text",
    "timecode_edit_out_text",
    "cut_order",
    "cut_item_in",
    "cut_item_out",
    "edit_in",
    "edit_out",
    "shot",
    "shot.Shot.code",
    # "cut_duration",  # Does not seem to exist?
    "cut_item_duration",
    "cut.Cut.fps",
    "version",
    "version.Version.id",
    "version.Version.code",
    "version.Version.entity",
    "version.Version.image",
]

# Fields we need to retrieve on Shots
_SHOT_FIELDS = [
    "code",
    "sg_status_list",
    "sg_head_in",
    "sg_tail_out",
    "sg_cut_in",
    "sg_cut_out",
    "smart_head_in",
    "smart_head_out",
    "smart_tail_in",
    "smart_tail_out",
    "smart_cut_in",
    "smart_cut_out",
    "smart_cut_duration",
    "smart_working_duration",
    "sg_cut_order",
    "sg_working_duration",
    "image"
]

# Fields we need to retrieve on Versions
_VERSION_FIELDS = [
    "code",
    "sg_first_frame",
    "sg_last_frame",
    "sg_path_to_movie",
    "sg_uploaded_movie",
    "entity",
    "entity.Shot.code",
    "entity.Shot.id",
    "image",
]

# Fields we need to retrieve on Published Files
_PUBLISHED_FILE_FIELDS = [
    "code",
    "path",
    "path_cache",
    "project",
    "published_file_type",
    "version_number",
    "version",
    "entity",
    "version.Version.id",
    "version.Version.code",
    "version.Version.sg_first_frame",
    "version.Version.sg_last_frame",
    "version.Version.sg_path_to_movie",
    "version.Version.entity",
    "version.Version.entity.Shot.code",
    "version.Version.entity.Shot.id",
    "version.Version.image",
]

# Shot field templates used for alternate Shot cut fields
_ALT_SHOT_STATUS_FIELD_TEMPLATE = "sg_%s_status_list"
_ALT_SHOT_HEAD_IN_FIELD_TEMPLATE = "sg_%s_head_in"
_ALT_SHOT_TAIL_OUT_FIELD_TEMPLATE = "sg_%s_tail_out"
_ALT_SHOT_CUT_IN_FIELD_TEMPLATE = "sg_%s_cut_in"
_ALT_SHOT_CUT_OUT_FIELD_TEMPLATE = "sg_%s_cut_out"
_ALT_SHOT_CUT_ORDER_FIELD_TEMPLATE = "sg_%s_cut_order"
_ALT_SHOT_CUT_DURATION_FIELD_TEMPLATE = "sg_%s_cut_duration"
_ALT_SHOT_WORKING_DURATION_FIELD_TEMPLATE = "sg_%s_working_duration"

_ALT_SHOT_FIELDS = [
    _ALT_SHOT_STATUS_FIELD_TEMPLATE,
    _ALT_SHOT_HEAD_IN_FIELD_TEMPLATE,
    _ALT_SHOT_TAIL_OUT_FIELD_TEMPLATE,
    _ALT_SHOT_CUT_IN_FIELD_TEMPLATE,
    _ALT_SHOT_CUT_OUT_FIELD_TEMPLATE,
    _ALT_SHOT_CUT_ORDER_FIELD_TEMPLATE,
    _ALT_SHOT_CUT_DURATION_FIELD_TEMPLATE,
    _ALT_SHOT_WORKING_DURATION_FIELD_TEMPLATE,
]

# When creating missing Versions, the default relative path template from the local storage chosen
# to save the Versions to.
_DEFAULT_VERSIONS_PATH_TEMPLATE = "{PROJECT}/{LINK}/{YYYY}{MM}{DD}/cuts"

# Different timecode in values to frame mapping modes
# Three mapping modes are available, which are only relevant for straight
# imports (without comparing to a previous Cut):
# - Automatic: timecode in is mapped to the Shot head in.
# - Absolute: timecode in is converted to an absolute frame
#             number.
# - Relative: timecode in is converted to an arbitrary frame
#             number specified through settings.
_TC2FRAME_ABSOLUTE_MODE, _TC2FRAME_AUTOMATIC_MODE, _TC2FRAME_RELATIVE_MODE = range(3)

# The path to the sg-otio manifest file.
_SG_OTIO_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "plugin_manifest.json")

# Values for CutDiff types
_DIFF_TYPES = enum.Enum(
    "CutDiffType", {
        "NEW": 0,              # A new Shot will be created
        "OMITTED": 1,          # The Shot is not part of the cut anymore
        "REINSTATED": 2,       # The Shot is back in the cut
        "RESCAN": 3,           # A rescan will be needed with the new in / out points
        "CUT_CHANGE": 4,       # Some values changed, but don't fall in previous categories
        "NO_CHANGE": 5,        # Values are identical to previous ones
        "NO_LINK": 6,          # Related Shot name couldn't be found
        "NEW_IN_CUT": 7,       # A new Shot entry is added, but the Shot already exists
        "OMITTED_IN_CUT": 8,   # A repeated Shot entry was removed
    }
)

# Special value to specify that Shots should be reinstated with the status
# they had before being omitted.
_REINSTATE_FROM_PREVIOUS_STATUS = "Previous Status"
