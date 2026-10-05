"""Cursor usage engine.

Cursor meters a MONTHLY fast-request quota (no weekly window), so this reports a
single metric:  Usage (month)  short "U"  -> e.g. "123/500" or percent.

Auth: Cursor stores a session token in its local SQLite state DB (key
`cursorAuth/accessToken`, a JWT whose `sub` is the user id). The usage endpoint
is called with the Workos session cookie.

  macOS   : ~/Library/Application Support/Cursor/User/globalStorage/state.vscdb
  Windows : %APPDATA%\\Cursor\\User\\globalStorage\\state.vscdb
  Linux   : ~/.config/Cursor/User/globalStorage/state.vscdb

NOTE: the exact usage endpoint/shape is confirmed against a live account during
setup; `USAGE_URL`/parsing below are the current best-known form and are easy to
adjust in one place.
"""
from __future__ import annotations
import base64
import json
import os
import sqlite3
import sys
import urllib.request
import urllib.error

try:
    from .common import Metric, Result, fail
except ImportError:
    from common import Metric, Result, fail

SERVICE = "cursor"
USAGE_URL = "https://www.cursor.com/api/usage"      # ?user=<id>
TOKEN_KEY = "cursorAuth/accessToken"


def state_db_path():
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Cursor")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Cursor")
    else:
        base = os.path.expanduser("~/.config/Cursor")
    return os.path.join(base, "User", "globalStorage", "state.vscdb")


def read_token():
    db = state_db_path()
    if not os.path.exists(db):
        return None, None, "Cursor not found (no state DB) — sign in to Cursor"
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            cur = con.execute("SELECT value FROM ItemTable WHERE key=?", (TOKEN_KEY,))
            row = cur.fetchone()
        finally:
            con.close()
    except Exception as e:
        return None, None, f"state DB read failed: {e}"
    if not row or not row[0]:
        return None, None, "not signed in to Cursor (no access token)"
    token = row[0]
    if isinstance(token, bytes):
        token = token.decode("utf-8", "replace")
    token = token.strip().strip('"')
    user_id = _jwt_sub(token)
    return token, user_id, None


def _jwt_sub(jwt):
    try:
        payload = jwt.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        sub = data.get("sub") or ""
        # sub is often "auth0|user_XXns..." — the usage API wants the part after "|"
        return sub.split("|")[-1] if sub else None
    except Exception:
        return None


def _fetch_usage(token, user_id):
    url = USAGE_URL + (f"?user={user_id}" if user_id else "")
    req = urllib.request.Request(url)
    # Cursor authenticates the dashboard API via the Workos session cookie.
    cookie = f"WorkosCursorSessionToken={user_id}%3A%3A{token}" if user_id else f"WorkosCursorSessionToken={token}"
    req.add_header("Cookie", cookie)
    req.add_header("User-Agent", "UseBar/1.0")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None, "Cursor auth rejected — reopen Cursor to refresh"
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"request failed: {e}"


def _extract_usage(data):
    """Pull (used, limit, resets_at) from Cursor's usage JSON, defensively.

    Known shape: {"gpt-4": {"numRequests": N, "maxRequestUsage": M}, "startOfMonth": "..."}
    """
    if not isinstance(data, dict):
        return None, None, None
    resets = data.get("startOfMonth") or data.get("resetDate")
    # Preferred: the premium/gpt-4 fast-request bucket
    for k in ("gpt-4", "gpt4", "premium", "fast"):
        b = data.get(k)
        if isinstance(b, dict):
            used = b.get("numRequests", b.get("used"))
            limit = b.get("maxRequestUsage", b.get("limit"))
            if used is not None:
                return used, limit, resets
    # Fallbacks for alternate shapes
    for used_k, lim_k in (("numRequests", "maxRequestUsage"), ("used", "limit"),
                          ("usage", "quota")):
        if used_k in data:
            return data.get(used_k), data.get(lim_k), resets
    return None, None, resets


def fetch() -> Result:
    token, user_id, e = read_token()
    if e:
        return fail(SERVICE, e)
    data, e = _fetch_usage(token, user_id)
    if e:
        return fail(SERVICE, e)
    used, limit, resets = _extract_usage(data)
    if used is None:
        return fail(SERVICE, "could not parse Cursor usage response")
    if limit:
        m = Metric("usage", "Usage (month)", "U", "ratio", float(used), float(limit), resets)
    else:
        m = Metric("usage", "Usage (month)", "U", "count", float(used), None, resets)
    return Result(service=SERVICE, ok=True, metrics=[m],
                  note="beta — Cursor API shape may change")


if __name__ == "__main__":
    from common import emit
    if "--raw" in sys.argv:
        tok, uid, e = read_token()
        if e:
            print(json.dumps({"error": e})); sys.exit(0)
        data, e = _fetch_usage(tok, uid)
        print(json.dumps({"user_id": uid, "usage": data} if not e else {"error": e}, indent=2))
        sys.exit(0)
    emit(fetch())
