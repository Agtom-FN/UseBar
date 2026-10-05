"""Claude Code usage engine.

Primary (LIVE): the real /usage rate-limit percentages. Reads the Claude Code
OAuth token from the OS secret store, calls GET api.anthropic.com/api/oauth/usage,
and reads the `limits` array:
    kind="session"       -> Session (5h)   short "S"
    kind="weekly_all"    -> Weekly (7d)     short "W"
    kind="weekly_scoped" -> Fable (7d)      short "F"   (scope.model.display_name)

Fallback (LOCAL): token VOLUME from ~/.claude/projects/**/*.jsonl (no network).

Token store:
    macOS   : Keychain generic password, service "Claude Code-credentials"
    Windows : %USERPROFILE%\\.claude\\.credentials.json (Claude Code writes this on Windows)
    other   : ~/.claude/.credentials.json
"""
from __future__ import annotations
import glob
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

try:
    from .common import Metric, Result, fail
except ImportError:  # run as a loose script
    from common import Metric, Result, fail

SERVICE = "claude"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
BETA = "oauth-2025-04-20"
KEYCHAIN_SERVICE = "Claude Code-credentials"


# ---------- token ----------

def _find_key(obj, target):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == target and isinstance(v, str):
                return v
            r = _find_key(v, target)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_key(v, target)
            if r:
                return r
    return None


def _token_from_payload(raw: str):
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except Exception:
        return raw or None
    return _find_key(data, "accessToken") or _find_key(data, "access_token")


def read_token():
    if sys.platform == "darwin":
        try:
            r = subprocess.run(
                ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True, text=True, timeout=10)
        except Exception as e:
            return None, f"keychain read failed: {e}"
        if r.returncode != 0:
            return None, "not signed in to Claude Code (no Keychain item)"
        tok = _token_from_payload(r.stdout)
        return (tok, None) if tok else (None, "accessToken not found in Keychain")
    # Windows / Linux: Claude Code stores a credentials file
    path = os.path.expanduser("~/.claude/.credentials.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tok = _token_from_payload(fh.read())
        return (tok, None) if tok else (None, "accessToken not found in credentials file")
    except FileNotFoundError:
        return None, "not signed in to Claude Code (no credentials file)"
    except Exception as e:
        return None, f"credentials read failed: {e}"


# ---------- live ----------

def _fetch_usage(token):
    req = urllib.request.Request(USAGE_URL)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("anthropic-beta", BETA)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("User-Agent", "UseBar/1.0")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return None, "token expired — open Claude Code to refresh"
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"request failed: {e}"


def live() -> Result:
    token, e = read_token()
    if e:
        return fail(SERVICE, e)
    data, e = _fetch_usage(token)
    if e:
        return fail(SERVICE, e)
    limits = data.get("limits") if isinstance(data, dict) else None
    if not isinstance(limits, list) or not limits:
        return fail(SERVICE, "no limits in usage response")

    def find(kind):
        for lim in limits:
            if isinstance(lim, dict) and lim.get("kind") == kind:
                return lim
        return None

    metrics = []
    m = find("session")
    if m:
        metrics.append(Metric("session", "Session (5h)", "S", "pct",
                              m.get("percent"), None, m.get("resets_at"), m.get("severity")))
    m = find("weekly_all")
    if m:
        metrics.append(Metric("weekly", "Weekly (7d)", "W", "pct",
                              m.get("percent"), None, m.get("resets_at"), m.get("severity")))
    m = find("weekly_scoped")
    if m:
        scope = m.get("scope") or {}
        model = (scope.get("model") or {}) if isinstance(scope, dict) else {}
        name = model.get("display_name") or "Fable"
        metrics.append(Metric("fable", f"{name} (7d)", "F", "pct",
                              m.get("percent"), None, m.get("resets_at"), m.get("severity")))
    if not metrics:
        return fail(SERVICE, "no recognized limit windows")
    return Result(service=SERVICE, ok=True, metrics=metrics)


# ---------- local volume fallback ----------

PROJECTS = os.path.expanduser("~/.claude/projects")
SESSION_SECONDS = 5 * 3600
WEEK_SECONDS = 7 * 24 * 3600


def _parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _msg_tokens(u):
    if not isinstance(u, dict):
        return 0
    return (int(u.get("input_tokens", 0) or 0)
            + int(u.get("output_tokens", 0) or 0)
            + int(u.get("cache_creation_input_tokens", 0) or 0)
            + int(u.get("cache_read_input_tokens", 0) or 0))


def _family(model):
    m = (model or "").lower()
    for f in ("fable", "opus", "sonnet", "haiku"):
        if f in m:
            return f
    return "other"


def local_volume() -> Result:
    now = time.time()
    horizon = now - WEEK_SECONDS
    seen = set()
    session_total = weekly_total = fable_week = 0
    for path in glob.glob(os.path.join(PROJECTS, "**", "*.jsonl"), recursive=True):
        try:
            if os.path.getmtime(path) < horizon - 3600:
                continue
        except OSError:
            continue
        try:
            fh = open(path, "r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if not isinstance(d, dict) or d.get("type") != "assistant":
                    continue
                msg = d.get("message")
                if not isinstance(msg, dict):
                    continue
                tok = _msg_tokens(msg.get("usage"))
                if tok <= 0:
                    continue
                ts = _parse_ts(d.get("timestamp") or "")
                if ts is None or ts < horizon:
                    continue
                key = d.get("requestId") or d.get("uuid")
                if key is not None:
                    if key in seen:
                        continue
                    seen.add(key)
                fam = _family(msg.get("model"))
                weekly_total += tok
                if fam == "fable":
                    fable_week += tok
                if ts >= now - SESSION_SECONDS:
                    session_total += tok
    r = Result(service=SERVICE, ok=True,
               note="local token volume (live /usage unavailable)")
    r.metrics = [
        Metric("session", "Session 5h (tokens)", "S", "count", session_total),
        Metric("weekly", "Weekly 7d (tokens)", "W", "count", weekly_total),
        Metric("fable", "Fable 7d (tokens)", "F", "count", fable_week),
    ]
    return r


def fetch() -> Result:
    r = live()
    if r.ok:
        return r
    # fall back to local volume, but carry the live error as the note
    fb = local_volume()
    fb.note = f"{r.error} — showing local token volume"
    return fb


if __name__ == "__main__":
    from common import emit
    if "--raw" in sys.argv:
        tok, e = read_token()
        if e:
            print(json.dumps({"error": e})); sys.exit(0)
        data, e = _fetch_usage(tok)
        print(json.dumps(data if not e else {"error": e}, indent=2)); sys.exit(0)
    emit(fetch())
