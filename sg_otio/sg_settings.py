# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import json
import logging

from .constants import _DEFAULT_HEAD_IN, _DEFAULT_HEAD_IN_DURATION, _DEFAULT_TAIL_OUT_DURATION
from .constants import _ALT_SHOT_CUT_DURATION_FIELD_TEMPLATE
from .constants import _ALT_SHOT_WORKING_DURATION_FIELD_TEMPLATE
from .constants import _ALT_SHOT_CUT_IN_FIELD_TEMPLATE, _ALT_SHOT_CUT_OUT_FIELD_TEMPLATE
from .constants import _ALT_SHOT_CUT_ORDER_FIELD_TEMPLATE, _ALT_SHOT_STATUS_FIELD_TEMPLATE
from .constants import _ALT_SHOT_FIELDS, _SHOT_FIELDS
from .constants import _ALT_SHOT_HEAD_IN_FIELD_TEMPLATE, _ALT_SHOT_TAIL_OUT_FIELD_TEMPLATE
from .constants import _EFFECTS_FIELD, _RETIME_FIELD, _ABSOLUTE_CUT_ORDER_FIELD
from .constants import _DEFAULT_VERSIONS_PATH_TEMPLATE, _DEFAULT_VERSION_NAMES_TEMPLATE

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Singleton(type):
    """
    A singleton meta class.
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class SGSettings(Singleton("SGSettings", (object,), {})):
    """
    A class to store and retrieve global SG settings.
    """
    def __init__(self):
        """
        Instantiate a new :class:`SGSettings`.
        """
        self.reset_to_defaults()

    @classmethod
    def from_file(cls, json_file):
        """
        Load settings from a JSON file.

        :returns: The :class:`SGSettings` singleton instance.
        """
        with open(json_file, "r") as f:
            json_data = json.loads(f.read())
        settings = SGSettings()
        settings.reset_to_defaults()
        for key, value in json_data.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
            else:
                raise ValueError("Unknown setting %s with value %s" % (key, value))
        # We return the settings, but since it's a singleton, it's not really needed.
        return settings

    @property
    def default_head_in(self):
        """
        Return the default head in value to use.

        :returns: An integer.
        """
        return self._default_head_in

    @default_head_in.setter
    def default_head_in(self, value):
        """
        Set the default head in value.

        :param int value: The value to set.
        """
        self._default_head_in = value

    @property
    def default_head_in_duration(self):
        """
        Return the default head in duration value to use.

        :returns: An integer.
        """
        return self._default_head_in_duration

    @default_head_in_duration.setter
    def default_head_in_duration(self, value):
        """
        Set the default head in duration value.

        :param int value: The value to set.
        """
        self._default_head_in_duration = value

    @property
    def default_tail_out_duration(self):
        """
        Return the default tail out duration value to use.

        :returns: An integer.
        """
        return self._default_tail_out_duration

    @default_tail_out_duration.setter
    def default_tail_out_duration(self, value):
        """
        Set the default tail out duration value.

        :param int value: The value to set.
        """
        self._default_tail_out_duration = value

    @property
    def use_clip_names_for_shot_names(self):
        """
        Return ``True`` if clip names should be used for Shot names.

        :returns: A boolean.
        """
        return self._use_clip_names_for_shot_names

    @use_clip_names_for_shot_names.setter
    def use_clip_names_for_shot_names(self, value):
        """
        Disable or allow using clip names for Shot names.

        :param bool value: The value to set.
        """
        self._use_clip_names_for_shot_names = value

    @property
    def clip_name_shot_regexp(self):
        """
        Return a regular expression to use when extracting Shot names from clip
        names.

        :returns: A string or ``None``.
        """
        return self._clip_name_shot_regexp

    @clip_name_shot_regexp.setter
    def clip_name_shot_regexp(self, value):
        """
        Set the regular expression to use when extracting Shot names from clip
        names.

        :param str value: The regular expression to use.
        """
        self._clip_name_shot_regexp = value

    @property
    def local_storage_name(self):
        """
        Return the name of the local storage to use when publishing files.

        :returns: A string.
        """
        return self._local_storage_name

    @local_storage_name.setter
    def local_storage_name(self, value):
        """
        Set the name of the local storage to use when publishing files.

        :param str value: The name of the local storage to use.
        """
        self._local_storage_name = value

    @property
    def versions_path_template(self):
        """
        Return the path template to use when publishing versions.

        :returns: A string.
        """
        return self._versions_path_template

    @versions_path_template.setter
    def versions_path_template(self, value):
        """
        Set the path template to use when publishing versions.

        :param str value: The path template to use.
        """
        self._versions_path_template = value

    @property
    def version_names_template(self):
        """
        Return the template to use when naming versions.

        :returns: A string.
        """
        return self._version_names_template

    @version_names_template.setter
    def version_names_template(self, value):
        """
        Set the template to use when naming versions.

        :param str value: The template to use.
        """
        self._version_names_template = value

    @property
    def create_missing_versions(self):
        """
        Return ``True`` if missing versions should be created.

        :returns: A boolean.
        """
        return self._create_missing_versions

    @create_missing_versions.setter
    def create_missing_versions(self, value):
        """
        Set whether missing versions should be created.

        :param bool value: The value to set.
        """
        self._create_missing_versions = value

    @property
    def log_level(self):
        """
        Return the log level to use.

        :returns: A logging level.
        """
        return self._log_level

    @log_level.setter
    def log_level(self, value):
        """
        Set the log level to use.

        :param int value: The logging level to use.
        """
        self._log_level = value

    def reset_to_defaults(self):
        """
        Reset settings to all default values.
        """
        self._default_head_in = _DEFAULT_HEAD_IN
        self._default_head_in_duration = _DEFAULT_HEAD_IN_DURATION
        self._default_tail_out_duration = _DEFAULT_TAIL_OUT_DURATION
        self._use_clip_names_for_shot_names = False
        self._clip_name_shot_regexp = None
        self._local_storage_name = "primary"
        self._versions_path_template = _DEFAULT_VERSIONS_PATH_TEMPLATE
        self._version_names_template = _DEFAULT_VERSION_NAMES_TEMPLATE
        self._create_missing_versions = True
        self._log_level = logging.DEBUG


class SGShotFieldsConfig(object):
    """
    This class is used to configure the fields that are used to represent cut information
    on a SG Shot.

    There are three possible set of fields used to represent cut information:
    - The default fields (e.g. sg_cut_in, sg_cut_out, sg_cut_duration, sg_cut_order...)
    - SG smart fields (See https://developer.shotgridsoftware.com/python-api/cookbook/smart_cut_fields.html)
    - Custom fields (e.g. sg_prefix_cut_in, sg_prefix_cut_out... with prefix chosen when instantiating this class)

    It's important to note that for smart fields, we return the raw fields used for updating the Cut information,
    not the smart fields themselves, which are only useful for querying.
    """
    _shot_schema = None
    _entity_schema = None

    def __init__(self, sg, linked_entity_type=None, use_smart_fields=False, shot_cut_fields_prefix=None):
        self._linked_entity_type = linked_entity_type
        self._sg = sg
        self._use_smart_fields = use_smart_fields
        self.validate_shot_cut_fields_prefix(shot_cut_fields_prefix)
        self._shot_cut_fields_prefix = shot_cut_fields_prefix
        self._sg_shot_link_field = None
        self._shot_schema = None

    @property
    def shot_schema(self):
        """
        Return the schema for the Shot entity.
        """
        if self._shot_schema is None:
            self._shot_schema = self._sg.schema_field_read("Shot")
        return self._shot_schema

    @property
    def use_smart_fields(self):
        """
        Return ``True`` if the Shot cut fields used are smart fields, ``False`` otherwise.

        :returns: A bool.
        """
        return self._use_smart_fields

    def validate_shot_cut_fields_prefix(self, value):
        """
        Validate the given Shot cut fields prefix value against the ShotGrid Shot
        schema.

        :param str value: The prefix to validate.
        :raises ValueError: If any of the required Shot cut fields for the given
                            prefix is missing.
        """
        if not value:
            return
        missing = []
        for sg_field in [
            x % value for x in _ALT_SHOT_FIELDS
        ]:
            if sg_field not in self.shot_schema:
                missing.append(sg_field)
        if missing:
            raise ValueError(
                "Following Shotgun Shot fields are missing %s" % missing
            )

    @property
    def head_in(self):
        """
        Get the field to use for head in.

        :returns: A str.
        """
        if self._use_smart_fields:
            return "head_in"
        if self._shot_cut_fields_prefix:
            return _ALT_SHOT_HEAD_IN_FIELD_TEMPLATE % self._shot_cut_fields_prefix
        return "sg_head_in"

    @property
    def cut_in(self):
        """
        Get the field to use for cut in.

        :returns: A str.
        """
        if self._use_smart_fields:
            return "cut_in"
        if self._shot_cut_fields_prefix:
            return _ALT_SHOT_CUT_IN_FIELD_TEMPLATE % self._shot_cut_fields_prefix
        return "sg_cut_in"

    @property
    def cut_out(self):
        """
        Get the field to use for cut out.

        :returns: A str.
        """
        if self._use_smart_fields:
            return "cut_out"
        if self._shot_cut_fields_prefix:
            return _ALT_SHOT_CUT_OUT_FIELD_TEMPLATE % self._shot_cut_fields_prefix
        return "sg_cut_out"

    @property
    def tail_out(self):
        """
        Get the field to use for tail out information.

        :returns: A str.
        """
        if self._use_smart_fields:
            return "tail_out"
        if self._shot_cut_fields_prefix:
            return _ALT_SHOT_TAIL_OUT_FIELD_TEMPLATE % self._shot_cut_fields_prefix
        return "sg_tail_out"

    @property
    def cut_duration(self):
        """
        Get the field for cut duration.

        :returns: A str.
        """
        if self._use_smart_fields:
            return "cut_duration"
        if self._shot_cut_fields_prefix:
            return _ALT_SHOT_CUT_DURATION_FIELD_TEMPLATE % self._shot_cut_fields_prefix
        return "sg_cut_duration"

    @property
    def working_duration(self):
        """
        Get the field for working duration.

        :returns: A str.
        """
        if self._use_smart_fields:
            return None
        if self._shot_cut_fields_prefix:
            return _ALT_SHOT_WORKING_DURATION_FIELD_TEMPLATE % self._shot_cut_fields_prefix
        return "sg_working_duration"

    @property
    def cut_order(self):
        """
        Get the field to use for cut order information.

        :returns: A str.
        """
        if not self._use_smart_fields and self._shot_cut_fields_prefix:
            return _ALT_SHOT_CUT_ORDER_FIELD_TEMPLATE % self._shot_cut_fields_prefix
        return "sg_cut_order"

    @property
    def status(self):
        """
        Get the field to use for status information.

        :returns: A str.
        """
        if not self._use_smart_fields and self._shot_cut_fields_prefix:
            return _ALT_SHOT_STATUS_FIELD_TEMPLATE % self._shot_cut_fields_prefix
        return "sg_status"

    @property
    def head_out(self):
        """
        Get the field to use for head out, if any.

        :returns: A str or ``None``.
        """
        if self._use_smart_fields:
            return "head_out"
        return None

    @property
    def head_duration(self):
        """
        Get the field to use for head duration, if any.

        :returns: A str or ``None``.
        """
        if self._use_smart_fields:
            return "head_duration"
        return None

    @property
    def tail_in(self):
        """
        Return the field for tail in, if any.
        """
        if self._use_smart_fields:
            return "tail_in"
        return None

    @property
    def tail_duration(self):
        """
        Get the field for tail duration, if any.

        :returns: A str, or ``None``.
        """
        if self._use_smart_fields:
            return "tail_duration"
        return None

    @property
    def has_effects(self):
        """
        Get the field for whether the Shot has effects, if any.

        :returns: A str or ``None``.
        """
        if _EFFECTS_FIELD in self.shot_schema:
            return _EFFECTS_FIELD
        return None

    @property
    def has_retime(self):
        """
        Get the field for whether the Shot has retime, if any.

        :returns: A str or ``None``.
        """
        if _RETIME_FIELD in self.shot_schema:
            return _RETIME_FIELD
        return None

    @property
    def absolute_cut_order(self):
        """
        Get the field for absolute cut order, if any.

        :returns: A str or ``None``.
        """
        if _ABSOLUTE_CUT_ORDER_FIELD in self.shot_schema:
            return _ABSOLUTE_CUT_ORDER_FIELD
        return None

    @property
    def all(self):
        """
        Returns the list of all Shot fields to retrieve from ShotGrid.

        :returns: A list of str.
        """
        sg_shot_fields = list(_SHOT_FIELDS)  # Make a copy, smart cut fields are included
        if self.shot_link_field:
            sg_shot_fields.append(self.shot_link_field)
        if self._shot_cut_fields_prefix:
            sg_shot_fields.extend([
                x % self._shot_cut_fields_prefix for x in _ALT_SHOT_FIELDS
            ])
        return sg_shot_fields

    @property
    def shot_link_field(self):
        """
        Retrieve a "link" field on Shots which accepts the given Entity type.

        :returns: A field name or ``None``.
        :raises ValueError: If the given Entity type is not found in the schema.
        """
        if not self._linked_entity_type:
            return None
        if self._sg_shot_link_field:
            return self._sg_shot_link_field
        sg_shot_link_field_name = None
        # Prefer a sg_<entity type> field if available
        if not self._entity_schema:
            self._entity_schema = self._sg.schema_entity_read()
        schema_entity_type = self._entity_schema.get(self._linked_entity_type)
        if not schema_entity_type:
            raise ValueError("Cannot find schema for entity type %s" % self._linked_entity_type)
        entity_type_name = schema_entity_type["name"]["value"]
        field_name = "sg_%s" % entity_type_name.lower()
        field = self.shot_schema.get(field_name)
        if(
            field
            and field["data_type"]["value"] == "entity"
            and self._linked_entity_type in field["properties"]["valid_types"]["value"]
        ):
            logger.debug("Using preferred Shot field %s" % field_name)
            sg_shot_link_field_name = field_name
        else:
            # General lookup
            for field_name, field in self.shot_schema.items():
                # the field has to accept entities and be editable.
                if(
                    field["data_type"]["value"] == "entity"
                    and field["editable"]["value"]
                    and self._linked_entity_type in field["properties"]["valid_types"]["value"]
                ):
                    sg_shot_link_field_name = field_name
                    break

        if not sg_shot_link_field_name:
            logger.warning("Couldn't retrieve a field accepting %s on shots" % (
                self._linked_entity_type,
            ))
        else:
            logger.info("Will use field %s to link %s to shots" % (
                sg_shot_link_field_name,
                self._linked_entity_type
            ))
        self._sg_shot_link_field = sg_shot_link_field_name
        return sg_shot_link_field_name
