# TODO: Support for Shots.
SG_SUPPORTED_ENTITY_TYPES = ["Cut"]

# CutItem and Shot fields used to flag edit retimes and effects.
_RETIME_FIELD = "sg_respeed"
_EFFECTS_FIELD = "sg_effects"
_EFFECTS_DURATION_FIELD = "sg_effects_duration"
# Field used to store absolute cut order on CutItems and Shots.
_ABSOLUTE_CUT_ORDER_FIELD = "sg_absolute_cut_order"
# Field used to store cut order on Entities (Reel, Sequence, etc...)
_ENTITY_CUT_ORDER_FIELD = "sg_cut_order"

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
