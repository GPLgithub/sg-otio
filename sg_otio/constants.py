# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#

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
    "version.Version.sg_path_to_movie"
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
# When creating missing Versions, the default version name template.
_DEFAULT_VERSION_NAMES_TEMPLATE = "{CLIP_NAME}_{UUID}"
