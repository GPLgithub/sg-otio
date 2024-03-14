# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the SG Otio project

# Workaround until https://github.com/AcademySoftwareFoundation/OpenTimelineIO/pull/1705
# is approved and merged
import json
from opentimelineio.core._core_utils import AnyDictionary
from opentimelineio.core import add_method, _value_to_any, _serialize_json_to_string


@add_method(AnyDictionary)  # noqa: F811
def to_dict(self):  # noqa: F811
    """
    Convert to a built-in dict. It will recursively convert all values
    to their corresponding python built-in types.
    """
    return json.loads(_serialize_json_to_string(_value_to_any(self), {}, 0))
