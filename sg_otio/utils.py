# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import os
import random
import re
import string
import sys

from six.moves.urllib import parse

from .sg_settings import SGSettings


def get_write_url(sg_site_url, entity_type, entity_id, session_token):
    """
    Get the URL to write a Cut to SG.

    The Entity type can be the Cut itself, the Project, or any Entity
    to link the Cut to (e.g. Sequence, Reel, etc).

    :param str sg_site_url: The SG site URL.
    :param str entity_type: The SG Entity type to link the Cut to.
    :param int entity_id: The SG Entity ID.
    :param str session_token: A SG session token.
    """
    # Construct the URL with urlparse
    parsed_url = parse.urlparse(sg_site_url)
    query = "session_token=%s&id=%s" % (
        session_token,
        entity_id,
    )
    # If no scheme was provided, netloc is empty and the whole url is in the path.
    # So we just append Cut to it.
    path = "%s/%s" % (parsed_url.path, entity_type)
    # Make sure to add https:// if the url was provided without it.
    return parsed_url._replace(
        scheme="https", query=query, path=path
    ).geturl()


def get_read_url(sg_site_url, cut_id, session_token):
    """
    Get the URL to read a Cut from SG.

    :param str sg_site_url: The SG site URL.
    :param int cut_id: The SG Cut ID.
    :param str session_token: A SG session token.
    """
    # Construct the URL with urlparse
    parsed_url = parse.urlparse(sg_site_url)
    query = "session_token=%s&id=%s" % (
        session_token,
        cut_id
    )
    # If no scheme was provided, netloc is empty and the whole url is in the path.
    # So we just append Cut to it.
    path = "%s/Cut" % parsed_url.path
    # Make sure to add https:// if the url was provided without it.
    return parsed_url._replace(
        scheme="https", query=query, path=path
    ).geturl()


def get_platform_name():
    """
    Get the platform name.

    This is used for fields in SG that are platform specific,
    like the local storage paths, e.g. "mac_path", and the
    published file paths, e.g. "local_path_mac".

    :returns: A str.
    """
    platform = sys.platform
    if platform == "win32":
        return "windows"
    elif platform == "darwin":
        return "mac"
    elif platform.startswith("linux"):
        return "linux"
    else:
        raise RuntimeError("Platform %s is not supported" % platform)


def compute_clip_shot_name(clip):
    r"""
    Processes a clip to find information about the shot name.

    The shot name can be found in the following places, in order of preference:
    - SG metadata about the Cut Item, if it has a shot field.
    - A :class:`otio.schema.Marker`, in an EDL it would be
      * LOC: 00:00:02:19 YELLOW  053_CSC_0750_PC01_V0001 997 // 8-8 Match to edit,
      which otio would convert to a marker with name "name='053_CSC_0750_PC01_V0001 997 // 8-8 Match to edit".
      We would only consider the first part of the name, split by " ".
    - In an EDL "pure" comment, e.g. "* COMMENT : 053_CSC_0750_PC01_V0001"
    - In an EDL comment, e.g. "* 053_CSC_0750_PC01_V0001"
    - The reel name.

    The reel name is only used if `_use_clip_names_for_shot_names` is True.
    If a `_clip_name_shot_regexp` is set, it will be used to extract the shot name from the reel name.

    :param clip: A :class:`otio.schema.Clip`
    :returns: A string containing the shot name or ``None``.
    """
    settings = SGSettings()
    sg_metadata = clip.metadata.get("sg", {}) or {}
    shot_metadata = sg_metadata.get("shot", {}) or {}
    if shot_metadata.get("code"):
        return clip.metadata["sg"]["shot"]["code"]
    if clip.markers:
        return clip.markers[0].name.split()[0]
    comment_match = None
    if clip.metadata.get("cmx_3600") and clip.metadata["cmx_3600"].get("comments"):
        comments = clip.metadata["cmx_3600"]["comments"]
        if comments:
            pure_comment_regexp = r"\*?(\s*COMMENT\s*:)?\s*([a-z0-9A-Z_-]+)$"
            pure_comment_match = None
            for comment in comments:
                m = re.match(pure_comment_regexp, comment)
                if m:
                    if m.group(1):
                        # Priority is given to matches from line beginning with
                        # * COMMENT
                        pure_comment_match = m.group(2)
                    # If we already matched one, no need to rematch
                    elif not comment_match:
                        comment_match = m.group(2)
                if pure_comment_match:
                    comment_match = pure_comment_match
                    break
    if comment_match:
        return comment_match
    if not settings.use_clip_names_for_shot_names:
        return None
    if not settings.clip_name_shot_regexp:
        return clip.name
    # Support both pre-compiled regexp and strings
    regexp = settings.clip_name_shot_regexp
    if isinstance(regexp, str):
        regexp = re.compile(regexp)
    m = regexp.search(
        clip.name
    )
    if m:
        # If we have capturing groups, use the first one
        # otherwise use the whole match.
        if len(m.groups()):
            return m.group(1)
        else:
            return m.group()


def get_available_filename(folder, name, extension):
    """
    Get a filename that is available in the given folder.

    :param str folder: The folder to check.
    :param str name: The name of the file without extension.
    :param str extension: The extension of the file.
    :returns: A string containing the filename.
    """
    # If the file already exists, add a number to the end
    # until it doesn't exist.
    i = 1
    filename = os.path.join(folder, "%s.%s" % (name, extension))
    while True:
        if not os.path.exists(filename):
            return filename
        filename = os.path.join(folder, "%s_%03d.%s" % (name, i, extension))
        i += 1


def compute_clip_version_name(clip, clip_index):
    settings = SGSettings()
    # Clip names cannot be None, only empty strings.
    clip_name = clip.name
    # If the clip has a reel name, use it.
    if clip.metadata.get("cmx_3600") and clip.metadata["cmx_3600"].get("reel"):
        clip_name = clip.metadata["cmx_3600"]["reel"]
    # If the clip name has an extension, get rid of it.
    clip_name = os.path.splitext(clip_name)[0]
    if not settings.version_names_template:
        return clip_name
    sg_metadata = clip.metadata.get("sg", {}) or {}
    cut_item_name = sg_metadata.get("code")
    data = {
        "CLIP_NAME": clip_name,
        "CUT_ITEM_NAME": cut_item_name or "",
        "SHOT": compute_clip_shot_name(clip) or "",
        # Ensure an int, even if not set.
        "CLIP_INDEX": clip_index,
        "UUID": get_uuid(6)
    }
    return settings.version_names_template.format(**data)


def get_uuid(length):
    """
    Generate a UUID, with a method which is one of the best
    to avoid collisions.

    Tested 40 times with 6 digits and 10 000 iterations,
    and there were no collisions.

    :param int length: The length of the UUID to return, preferably
                       long to avoid collisions.
    :returns: A string, a UUID.
    """
    _ALPHABET = string.ascii_lowercase + string.digits
    r = random.SystemRandom()
    return "".join([r.choice(_ALPHABET) for _ in range(length)])