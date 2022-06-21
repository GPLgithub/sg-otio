# Copyright 2022 GPL Solutions, LLC.  All rights reserved.
#
# Use of this software is subject to the terms of the GPL Solutions license
# agreement provided at the time of installation or download, or which otherwise
# accompanies this software in either electronic or hard copy form.
#
from six.moves.urllib import parse


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
