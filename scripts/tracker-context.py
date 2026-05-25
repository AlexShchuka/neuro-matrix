#!/usr/bin/env python3
"""
tracker-context.py — fetch a Yandex Tracker task with maximally complete
context and print it as markdown on stdout.

What it pulls for <TASK-KEY>:
  * Full issue metadata + description (no truncation)
  * Full comments (every comment, full body, no truncation)
  * All links + for each linked issue: its summary, status, description
  * Parent issue + its summary/status/description
  * Checklist items
  * Attachments metadata (filename, size, author, uploadedAt)

Goal: replace a flurry of MCP tool calls (issue_get + issue_get_comments +
issue_get_links + issue_get_checklist + N × issue_get for related/parent) with
a single Bash invocation that returns a full-picture brief. Saves tokens and
avoids the round-trip cost of resolving each linked task separately.

Auth via environment variables:
  TRACKER_TOKEN        — OAuth token, required.
  TRACKER_CLOUD_ORG_ID — Yandex Cloud organization ID (preferred for cloud orgs).
  TRACKER_ORG_ID       — classic organization ID (used if CLOUD_ORG_ID is unset).

Usage:
  python3 tracker-context.py <TASK-KEY>

Exit codes:
  0 — success (markdown printed to stdout)
  1 — HTTP or network error on the primary issue fetch
  2 — argument or env-var error
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

API_BASE = "https://api.tracker.yandex.net/v3"


def _die(msg: str, code: int) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _auth_headers() -> Dict[str, str]:
    token = os.environ.get("TRACKER_TOKEN")
    if not token:
        _die("TRACKER_TOKEN env var is required", 2)

    cloud_org = os.environ.get("TRACKER_CLOUD_ORG_ID")
    classic_org = os.environ.get("TRACKER_ORG_ID")
    if not (cloud_org or classic_org):
        _die("TRACKER_CLOUD_ORG_ID or TRACKER_ORG_ID env var is required", 2)

    headers = {
        "Authorization": f"OAuth {token}",
        "Content-Type": "application/json",
    }
    if cloud_org:
        headers["X-Cloud-Org-ID"] = cloud_org
    else:
        headers["X-Org-ID"] = classic_org  # type: ignore[assignment]
    return headers


def _http_get(path: str, tolerant: bool = False) -> Any:
    url = API_BASE + path
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data) if data else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        if tolerant:
            print(f"WARN: HTTP {e.code} on {path}: {body}", file=sys.stderr)
            return None
        _die(f"HTTP {e.code} on {path}: {body}", 1)
    except urllib.error.URLError as e:
        if tolerant:
            print(f"WARN: network error on {path}: {e}", file=sys.stderr)
            return None
        _die(f"network error on {path}: {e}", 1)


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #

def _display(user_obj: Optional[Dict[str, Any]]) -> str:
    if not user_obj:
        return "—"
    return user_obj.get("display") or user_obj.get("id") or "—"


def _field(obj: Optional[Dict[str, Any]], key: str = "display") -> str:
    if not obj:
        return "—"
    return obj.get(key, "—")


def _body(raw: Optional[str]) -> str:
    return raw.rstrip() if raw else "_(empty)_"


def _fmt_bytes(n: Optional[int]) -> str:
    if not isinstance(n, (int, float)):
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# --------------------------------------------------------------------------- #
# Fetchers
# --------------------------------------------------------------------------- #

def fetch_issue(key: str, tolerant: bool = False) -> Optional[Dict[str, Any]]:
    return _http_get(f"/issues/{urllib.parse.quote(key)}", tolerant=tolerant)


def fetch_comments(key: str) -> List[Dict[str, Any]]:
    out = _http_get(f"/issues/{urllib.parse.quote(key)}/comments", tolerant=True)
    return out or []


def fetch_links(key: str) -> List[Dict[str, Any]]:
    out = _http_get(f"/issues/{urllib.parse.quote(key)}/links", tolerant=True)
    return out or []


def fetch_checklist(key: str) -> List[Dict[str, Any]]:
    out = _http_get(f"/issues/{urllib.parse.quote(key)}/checklistItems", tolerant=True)
    return out or []


def fetch_attachments(key: str) -> List[Dict[str, Any]]:
    out = _http_get(f"/issues/{urllib.parse.quote(key)}/attachments", tolerant=True)
    return out or []


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def render_metadata(task: Dict[str, Any]) -> str:
    lines = [
        f"- **Status:** {_field(task.get('status'))}  |  **Priority:** {_field(task.get('priority'))}  |  **Type:** {_field(task.get('type'))}",
        f"- **Assignee:** {_display(task.get('assignee'))}  |  **Author:** {_display(task.get('createdBy'))}",
        f"- **Created:** {task.get('createdAt', '—')[:10]}  |  **Updated:** {task.get('updatedAt', '—')[:10]}",
        f"- **Deadline:** {task.get('deadline') or task.get('dueDate') or '—'}  |  **Start:** {task.get('start', '—')}",
        f"- **Tags:** {', '.join(task.get('tags') or []) or '—'}",
        f"- **Original estimation:** {task.get('originalEstimation', '—')}  |  **Spent:** {task.get('spent', '—')}",
    ]
    queue = task.get("queue") or {}
    if queue.get("key"):
        lines.append(f"- **Queue:** {queue.get('key')} — {queue.get('display', '')}")
    components = task.get("components") or []
    if components:
        names = [c.get("display", c.get("id", "?")) for c in components]
        lines.append(f"- **Components:** {', '.join(names)}")
    versions = task.get("fixVersions") or []
    if versions:
        names = [v.get("display", v.get("id", "?")) for v in versions]
        lines.append(f"- **Fix versions:** {', '.join(names)}")
    return "\n".join(lines)


def render_parent(task: Dict[str, Any]) -> str:
    parent_obj = task.get("parent") or {}
    parent_key = parent_obj.get("key")
    if not parent_key:
        return "_(no parent)_"
    parent_full = fetch_issue(parent_key, tolerant=True) or {}
    status = _field(parent_full.get("status"))
    summary = parent_full.get("summary") or parent_obj.get("display", "")
    desc = parent_full.get("description") or ""
    out = [f"### {parent_key} — {summary} [{status}]"]
    if desc.strip():
        out.append("")
        out.append(_body(desc))
    return "\n".join(out)


def render_links(key: str, links: List[Dict[str, Any]]) -> str:
    if not links:
        return "_(none)_"
    out = []
    for link in links:
        ltype = link.get("type") or {}
        rel = ltype.get("inward") or ltype.get("outward") or ltype.get("id") or "—"
        obj = link.get("object") or {}
        target_key = obj.get("key")
        if not target_key:
            out.append(f"- {rel} → _(no target key)_")
            continue
        target_full = fetch_issue(target_key, tolerant=True) or {}
        status = _field(target_full.get("status")) or _field(obj.get("status"))
        summary = target_full.get("summary") or obj.get("display", "")
        desc = target_full.get("description") or ""
        out.append(f"#### {rel} → **{target_key}** [{status}] — {summary}")
        if desc.strip():
            out.append("")
            out.append(_body(desc))
        out.append("")
    return "\n".join(out).rstrip()


def render_comments(comments: List[Dict[str, Any]]) -> str:
    if not comments:
        return "_(none)_"
    out = []
    for c in comments:
        author = _display(c.get("createdBy"))
        when = c.get("createdAt", "")[:16].replace("T", " ")
        text = c.get("text", "").rstrip()
        out.append(f"### `{when}` {author}")
        out.append("")
        out.append(text if text else "_(empty)_")
        out.append("")
    return "\n".join(out).rstrip()


def render_checklist(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "_(none)_"
    out = []
    for item in items:
        mark = "x" if item.get("checked") else " "
        text = (item.get("text") or "").strip()
        out.append(f"- [{mark}] {text}")
    return "\n".join(out)


def render_attachments(atts: List[Dict[str, Any]]) -> str:
    if not atts:
        return "_(none)_"
    out = []
    for a in atts:
        name = a.get("name") or a.get("filename") or "?"
        size = _fmt_bytes(a.get("size"))
        when = a.get("createdAt", "")[:10]
        author = _display(a.get("createdBy"))
        out.append(f"- `{when}` {author} — **{name}** ({size})")
    return "\n".join(out)


def render_brief(key: str, task: Dict[str, Any]) -> str:
    comments = fetch_comments(key)
    links = fetch_links(key)
    checklist = fetch_checklist(key)
    attachments = fetch_attachments(key)

    summary = task.get("summary", "—")
    sections = [
        f"# {key} — {summary}",
        "",
        render_metadata(task),
        "",
        "## Description",
        _body(task.get("description")),
        "",
        "## Parent",
        render_parent(task),
        "",
        "## Links",
        render_links(key, links),
        "",
        "## Checklist",
        render_checklist(checklist),
        "",
        "## Attachments",
        render_attachments(attachments),
        "",
        f"## Comments ({len(comments)})",
        render_comments(comments),
    ]
    return "\n".join(sections)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__, file=sys.stderr)
        sys.exit(2)

    key = sys.argv[1].strip()
    if not re.match(r"^[A-Z][A-Z0-9]+-\d+$", key, re.IGNORECASE):
        _die(f"invalid task key format: {key!r} (expected 'PROJECT-123')", 2)

    task = fetch_issue(key)
    if not task:
        _die(f"task {key} returned empty body", 1)

    print(render_brief(key, task))


if __name__ == "__main__":
    main()
