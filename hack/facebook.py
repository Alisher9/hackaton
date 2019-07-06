import hashlib
import hmac
import binascii
import base64
import requests
import json
import re

try:
    from urllib.parse import parse_qs, urlencode, urlparse
except ImportError:
    from urlparse import parse_qs, urlparse
    from urllib import urlencode

from . import version


__version__ = version.__version__

FACEBOOK_GRAPH_URL = "https://graph.facebook.com/"
FACEBOOK_WWW_URL = "https://www.facebook.com/"
FACEBOOK_OAUTH_DIALOG_PATH = "dialog/oauth?"
VALID_API_VERSIONS = [
    "2.8",
    "2.9",
    "2.10",
    "2.11",
    "2.12",
    "3.0",
    "3.1",
    "3.2",
]
VALID_SEARCH_TYPES = ["place", "placetopic"]


class GraphAPI(object):

    def __init__(
        self,
        access_token=None,
        timeout=None,
        version=None,
        proxies=None,
        session=None,
    ):
        # The default version is only used if the version kwarg does not exist.
        default_version = VALID_API_VERSIONS[0]

        self.access_token = access_token
        self.timeout = timeout
        self.proxies = proxies
        self.session = session or requests.Session()

        if version:
            version_regex = re.compile("^\d\.\d{1,2}$")
            match = version_regex.search(str(version))
            if match is not None:
                if str(version) not in VALID_API_VERSIONS:
                    raise GraphAPIError(
                        "Valid API versions are "
                        + str(VALID_API_VERSIONS).strip("[]")
                    )
                else:
                    self.version = "v" + str(version)
            else:
                raise GraphAPIError(
                    "Version number should be in the"
                    " following format: #.# (e.g. 2.0)."
                )
        else:
            self.version = "v" + default_version

    def get_permissions(self, user_id):
        """Fetches the permissions object from the graph."""
        response = self.request(
            "{0}/{1}/permissions".format(self.version, user_id), {}
        )["data"]
        return {x["permission"] for x in response if x["status"] == "granted"}

    def get_object(self, id, **args):
        """Fetches the given object from the graph."""
        return self.request("{0}/{1}".format(self.version, id), args)

    def get_objects(self, ids, **args):
        """Fetches all of the given object from the graph.
        We return a map from ID to object. If any of the IDs are
        invalid, we raise an exception.
        """
        args["ids"] = ",".join(ids)
        return self.request(self.version + "/", args)

    def search(self, type, **args):
        """https://developers.facebook.com/docs/places/search"""
        if type not in VALID_SEARCH_TYPES:
            raise GraphAPIError(
                "Valid types are: %s" % ", ".join(VALID_SEARCH_TYPES)
            )

        args["type"] = type
        return self.request(self.version + "/search/", args)

    def get_connections(self, id, connection_name, **args):
        """Fetches the connections for given object."""
        return self.request(
            "{0}/{1}/{2}".format(self.version, id, connection_name), args
        )

    def get_all_connections(self, id, connection_name, **args):
        """Get all pages from a get_connections call
        This will iterate over all pages returned by a get_connections call
        and yield the individual items.
        """
        while True:
            page = self.get_connections(id, connection_name, **args)
            for post in page["data"]:
                yield post
            next = page.get("paging", {}).get("next")
            if not next:
                return
            args = parse_qs(urlparse(next).query)
            del args["access_token"]

    def put_object(self, parent_object, connection_name, **data):
        """Writes the given object to the graph, connected to the given parent.
        For example,
            graph.put_object("me", "feed", message="Hello, world")
        writes "Hello, world" to the active user's wall. Likewise, this
        will comment on the first post of the active user's feed:
            feed = graph.get_connections("me", "feed")
            post = feed["data"][0]
            graph.put_object(post["id"], "comments", message="First!")
        Certain operations require extended permissions. See
        https://developers.facebook.com/docs/facebook-login/permissions
        for details about permissions.
        """
        assert self.access_token, "Write operations require an access token"
        return self.request(
            "{0}/{1}/{2}".format(self.version, parent_object, connection_name),
            post_args=data,
            method="POST",
        )

    def put_comment(self, object_id, message):
        """Writes the given comment on the given post."""
        return self.put_object(object_id, "comments", message=message)
