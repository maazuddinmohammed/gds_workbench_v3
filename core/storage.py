"""Azure storage for pulls and pushes: short-lived links the Bridge uses, and the server's own reads and writes
(docs/design.md, "Bridge"). As in v2, the MCP server reaches storage with its managed identity; it never holds an
account key. Python's own urllib, hmac and base64 do it, so no package is needed.

The app passes `where`: {"account_url": "https://<account>.blob.core.windows.net", "container": "...",
"token": a function giving the managed identity's bearer token for storage}, from v2's settings
GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL, GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER and
GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID (core/ never reads settings).

Not tried against Azure yet (Nov 28): there is no storage account locally.
"""

import base64
import hashlib
import hmac
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta, timezone

VERSION = "2022-11-02"
LINK_MINUTES = 15


def _call(where, method, path, data=None, query=""):
    url = f"{where['account_url'].rstrip('/')}/{path}{query}"
    headers = {"Authorization": f"Bearer {where['token']()}", "x-ms-version": VERSION}
    if method == "PUT" and data is not None:
        headers |= {"x-ms-blob-type": "BlockBlob", "Content-Type": "application/zip"}
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def put(where, name, data):
    """Write a blob with the server's own identity."""
    _call(where, "PUT", f"{where['container']}/{name}", data)


def get(where, name):
    """Read a blob with the server's own identity."""
    return _call(where, "GET", f"{where['container']}/{name}")


def link(where, name, write=False):
    """A short-lived link to one blob, signed with a user delegation key: read for a pull, create and write for a
    push. Returns (link, its end time)."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start, expiry = now - timedelta(minutes=5), now + timedelta(minutes=LINK_MINUTES)
    iso = lambda moment: moment.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    body = f"<?xml version=\"1.0\" encoding=\"utf-8\"?><KeyInfo><Start>{iso(start)}</Start><Expiry>{iso(expiry)}</Expiry></KeyInfo>"
    key = ElementTree.fromstring(_call(where, "POST", "", body.encode(), "?restype=service&comp=userdelegationkey"))
    k = {child.tag: child.text for child in key}
    account = urllib.parse.urlparse(where["account_url"]).hostname.split(".")[0]
    permissions = "cw" if write else "r"
    to_sign = "\n".join([permissions, iso(start), iso(expiry), f"/blob/{account}/{where['container']}/{name}",
                         k["SignedOid"], k["SignedTid"], k["SignedStart"], k["SignedExpiry"], k["SignedService"],
                         k["SignedVersion"], "", "", "", "", "https", VERSION, "b", "", "", "", "", "", "", ""])
    signature = base64.b64encode(hmac.new(base64.b64decode(k["Value"]), to_sign.encode(), hashlib.sha256).digest())
    query = urllib.parse.urlencode({"sp": permissions, "st": iso(start), "se": iso(expiry), "skoid": k["SignedOid"],
                                    "sktid": k["SignedTid"], "skt": k["SignedStart"], "ske": k["SignedExpiry"],
                                    "sks": k["SignedService"], "skv": k["SignedVersion"], "spr": "https",
                                    "sv": VERSION, "sr": "b", "sig": signature.decode()})
    return f"{where['account_url'].rstrip('/')}/{where['container']}/{urllib.parse.quote(name)}?{query}", expiry
