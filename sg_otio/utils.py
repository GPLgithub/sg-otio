# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
import logging
import os
import random
import re
import string
import sys

import opentimelineio as otio
from six.moves.urllib import parse

from .constants import _PUBLISHED_FILE_FIELDS, _VERSION_FIELDS
from .sg_settings import SGSettings

logger = logging.getLogger(__name__)


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
    """
    Compute the version name for a clip.

    The name of the version is, in order of preference:
    - If a name template is provided, the name computed from the template.
    - The reel name if it's available (only for EDLs).
    - The clip name.

    ..seealso::sg_settings.SGSettings.version_names_template

    :param clip: A :class:`otio.schema.Clip` or :class:`CutClip`.
    :param int clip_index: The index of the clip in the Track.
    :returns: A string containing the version name.
    """
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


def get_path_from_target_url(url):
    """
    Get the path from a target URL.

    The URLs in Media References that represent local files can be:
    - file:///path/to/file
    - file://localhost/path/to/file (coming from Premiere XML)

    Return a local filepath instead.

    :param str url: The target URL.
    :returns: A string, the path.
    """
    # Premiere XMLs start with file://localhost followed by an absolute path.
    path = url.replace("file://localhost", "")
    # EDLs start with file:// followed by an absolute path.
    path = path.replace("file://", "")
    return path


def add_media_references_from_sg(track, sg, project):
    """
    Add Media References from Shotgun to clips in a track.

    For clips that don't have a Media Reference, try to find one in Shotgun.

    :param track: A :class:`otio.schema.Track` or :class:`CutTrack` instance.
    :param sg: A SG session handle.
    :param project: A SG Project entity.
    """
    clips_with_no_media_references = []
    clip_media_names = []
    for i, clip in enumerate(track.each_clip()):
        if clip.media_reference.is_missing_reference:
            clips_with_no_media_references.append(clip)
            clip_media_names.append(compute_clip_version_name(clip, i + 1))
        # TODO: Deal with clips with media references with local filepaths that cannot be found.
    if not clips_with_no_media_references:
        return
    sg_published_files = sg.find(
        "PublishedFile",
        [
            ["project", "is", project],
            ["code", "in", clip_media_names],
            # If there is no Version linked to the PublishedFile,
            # we don't want to consider it
            ["version", "is_not", None],
            ["published_file_type.PublishedFileType.code", "is", "mov"]
        ],
        _PUBLISHED_FILE_FIELDS,
        order=[{"field_name": "id", "direction": "desc"}]
    )
    # If there are multiple published files with the same name, take the first one only.
    sg_published_files_by_code = {}
    for published_file in sg_published_files:
        if published_file["code"] not in sg_published_files_by_code:
            sg_published_files_by_code[published_file["code"]] = published_file
    # If a published file is not found, maybe a Version can be used.
    missing_names = list(set(clip_media_names) - set(sg_published_files_by_code.keys()))
    sg_versions = []
    if missing_names:
        sg_versions = sg.find(
            "Version",
            [
                ["project", "is", project],
                ["code", "in", missing_names],
            ],
            _VERSION_FIELDS
        )
    if not sg_published_files and not sg_versions:
        # Nothing was found to link to the clips.
        return
    sg_versions_by_code = {v["code"]: v for v in sg_versions}
    all_versions = sg_versions + [pf["version"] for pf in sg_published_files if pf["version"]]
    sg_cut_items = sg.find(
        "CutItem",
        [["project", "is", project], ["version", "in", all_versions]],
        ["cut_item_in", "cut_item_out", "version.Version.id"]
    )
    sg_cut_items_by_version_id = {
        cut_item["version.Version.id"]: cut_item for cut_item in sg_cut_items
    }
    platform_name = get_platform_name()
    for clip, media_name in zip(clips_with_no_media_references, clip_media_names):
        published_file = sg_published_files_by_code.get(media_name)
        if published_file:
            cut_item = sg_cut_items_by_version_id.get(published_file["version.Version.id"])
            add_pf_media_reference_to_clip(clip, published_file, platform_name, cut_item)
            logger.debug(
                "Added Media Reference to clip %s from Published File %s" % (
                    clip.name, published_file["code"]
                )
            )
        else:
            version = sg_versions_by_code.get(media_name)
            if version and version["sg_uploaded_movie"]:
                cut_item = sg_cut_items_by_version_id.get(version["id"])
                add_version_media_reference_to_clip(clip, version, cut_item)
                logger.debug(
                    "Added Media Reference to clip %s from Version %s" % (
                        clip.name, version["code"]
                    )
                )


def add_pf_media_reference_to_clip(clip, published_file, platform_name, cut_item=None):
    """
    Add a Media Reference to a clip from a PublishedFile.

    :param clip: A :class:`otio.schema.Clip` or :class:`CutClip` instance.
    :param published_file: A SG PublishedFile entity.
    :param cut_item: A SG CutItem entity or ``None``.
    :param platform_name: The platform name.
    """
    path_field = "local_path_%s" % platform_name
    url = "file://%s" % published_file["path"][path_field]
    first_frame = published_file["version.Version.sg_first_frame"]
    last_frame = published_file["version.Version.sg_last_frame"]
    name = published_file["code"]
    media_available_range = None
    if cut_item and first_frame and last_frame:
        # The visible range of the clip is taken from
        # timecode_cut_item_in_text and timecode_cut_item_out_text,
        # but cut_item_in, cut_item_out (on CutItem) and first_frame,
        # last_frame (on Version) have an offset of head_in + head_in_duration.
        # Since we cannot know what the offset is, we check the offset between cut_item_in and first_frame,
        # and that tells us what is the offset between visible range and available range.
        start_time_offset = cut_item["cut_item_in"] - first_frame
        duration = last_frame - first_frame + 1
        rate = clip.source_range.start_time.rate
        media_available_range = otio.opentime.TimeRange(
            clip.source_range.start_time - otio.opentime.RationalTime(start_time_offset, rate),
            otio.opentime.RationalTime(duration, rate)
        )
    clip.media_reference = otio.schema.ExternalReference(
        target_url=url,
        available_range=media_available_range,
    )
    clip.media_reference.name = name
    clip.media_reference.metadata["sg"] = published_file


def add_version_media_reference_to_clip(clip, version, cut_item=None):
    """
    Add a Media Reference to a clip from a Version.

    :param clip: A :class:`otio.schema.Clip` or :class:`CutClip` instance.
    :param version: A SG Version entity.
    :param cut_item: A SG CutItem entity or ``None``.
    """
    media_available_range = None
    rate = clip.source_range.start_time.rate
    if cut_item and version["sg_first_frame"] and version["sg_last_frame"]:
        # The visible range of the clip is taken from
        # timecode_cut_item_in_text and timecode_cut_item_out_text,
        # but cut_item_in, cut_item_out (on CutItem) and first_frame,
        # last_frame (on Version) have an offset of head_in + head_in_duration.
        # Since we cannot know what the offset is, we check the offset between cut_item_in and first_frame,
        # and that tells us what is the offset between visible range and available range.
        start_time_offset = cut_item["cut_item_in"] - version["sg_first_frame"]
        duration = version["sg_last_frame"] - version["sg_first_frame"] + 1
        media_available_range = otio.opentime.TimeRange(
            clip.source_range.start_time - otio.opentime.RationalTime(start_time_offset, rate),
            otio.opentime.RationalTime(duration, rate)
        )
    # TODO: what can be done with AWS links expiring? should we download the movie somewhere?
    clip.media_reference = otio.schema.ExternalReference(
        target_url=version["sg_uploaded_movie"]["url"],
        available_range=media_available_range,
    )
    clip.media_reference.name = version["code"]
    # The SG metadata should be a published file, but since we only have the Version,
    # set all Published File fields as None, except the version.Version.XXX fields.
    pf_data = {
        "type": "PublishedFile",
        "id": None,
    }
    for field in _PUBLISHED_FILE_FIELDS:
        if field.startswith("version.Version"):
            pf_data[field] = version[field.replace("version.Version.", "")]
        else:
            pf_data[field] = None
    clip.media_reference.metadata["sg"] = pf_data
