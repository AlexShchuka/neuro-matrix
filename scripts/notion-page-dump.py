#!/usr/bin/env python3
"""Recursively dump a Notion page (title + all nested block children) as plain markdown.

Usage:
    NOTION_TOKEN=<integration-secret> notion-page-dump.py <page-id-or-url>

Auth: NOTION_TOKEN env var, passed as Bearer.
Output: markdown on stdout.
Exit codes:
    0 — success
    1 — Notion API / network error
    2 — argument / environment error

Uses only the Python standard library (urllib, json).

Supported block types:
    paragraph, heading_1, heading_2, heading_3,
    bulleted_list_item, numbered_list_item, to_do, toggle, callout,
    code, quote, divider, table, table_row, column_list, column,
    image, file, pdf, audio, video, bookmark, embed, link_preview,
    equation, link_to_page, synced_block (follows the original),
    child_page (recursive), child_database (shallow: title only).
Any other type is rendered as ``<!-- unsupported block: <type> -->``.

Page header: dumps ALL page properties (title, rich_text, select, multi_select,
status, date, people, url, email, phone, checkbox, number, created_by,
last_edited_by, created_time, last_edited_time, formula, relation, files) as a
metadata block above the body.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
REQUEST_SLEEP_SECONDS = 0.35  # Notion's documented rate ceiling is ~3 rps.


# --------------------------------------------------------------------------- #
# Arg / env parsing
# --------------------------------------------------------------------------- #

_PAGE_ID_32HEX_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_PAGE_ID_DASHED_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def extract_page_id(raw: str) -> str:
    """Accept a page id (dashed or undashed) or a full Notion URL; return dashed UUID."""
    candidate = raw.strip()
    if candidate.startswith("http://") or candidate.startswith("https://"):
        # Notion URLs look like https://www.notion.so/<workspace>/<slug>-<32hex>
        parsed = urllib.parse.urlparse(candidate)
        tail = parsed.path.rstrip("/").split("/")[-1]
        # the id is the last 32 hex chars; a hyphenated form is also possible
        m = re.search(r"([0-9a-fA-F]{32})$", tail)
        if m:
            candidate = m.group(1)
        elif _PAGE_ID_DASHED_RE.match(tail):
            candidate = tail
        else:
            raise ValueError(f"cannot find a Notion page id in URL: {raw}")

    candidate = candidate.replace("-", "")
    if not _PAGE_ID_32HEX_RE.match(candidate):
        raise ValueError(f"not a Notion page id: {raw}")
    # re-dash to 8-4-4-4-12
    return (
        f"{candidate[0:8]}-{candidate[8:12]}-{candidate[12:16]}-"
        f"{candidate[16:20]}-{candidate[20:32]}"
    ).lower()


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

class NotionError(Exception):
    pass


def _notion_get(path: str, token: str) -> dict:
    url = f"{NOTION_API}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        if exc.code == 401:
            raise NotionError(
                "401 Unauthorized — check NOTION_TOKEN (integration secret)"
            ) from exc
        if exc.code == 403:
            raise NotionError(
                f"403 Forbidden — the integration does not have access to this resource "
                f"(share the page with it). Detail: {detail[:200]}"
            ) from exc
        if exc.code == 404:
            raise NotionError(
                f"404 Not Found — wrong id, or page not shared with integration. "
                f"URL: {url}"
            ) from exc
        if exc.code == 429:
            raise NotionError(
                "429 Rate-limited by Notion — slow down and retry"
            ) from exc
        raise NotionError(
            f"HTTP {exc.code} for {url}: {detail[:200]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise NotionError(f"network error talking to Notion: {exc}") from exc
    time.sleep(REQUEST_SLEEP_SECONDS)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise NotionError(f"cannot decode Notion response as JSON: {exc}") from exc


def get_page(page_id: str, token: str) -> dict:
    return _notion_get(f"/pages/{page_id}", token)


def list_block_children(block_id: str, token: str) -> list[dict]:
    results: list[dict] = []
    cursor: str | None = None
    while True:
        q = f"?page_size=100"
        if cursor:
            q += f"&start_cursor={urllib.parse.quote(cursor)}"
        data = _notion_get(f"/blocks/{block_id}/children{q}", token)
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return results


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def rich_text_to_md(rt: list[dict]) -> str:
    """Convert Notion rich_text array to plain markdown inline text."""
    out: list[str] = []
    for item in rt or []:
        text = item.get("plain_text", "")
        if not text:
            continue
        ann = item.get("annotations") or {}
        link = (item.get("text") or {}).get("link") or item.get("href")
        if ann.get("code"):
            text = f"`{text}`"
        if ann.get("bold"):
            text = f"**{text}**"
        if ann.get("italic"):
            text = f"*{text}*"
        if ann.get("strikethrough"):
            text = f"~~{text}~~"
        if link:
            url = link.get("url") if isinstance(link, dict) else link
            if url:
                text = f"[{text}]({url})"
        out.append(text)
    return "".join(out)


def extract_page_title(page: dict) -> str:
    """Pull the title from a page object; fall back to untitled."""
    props = page.get("properties") or {}
    for _name, prop in props.items():
        if prop.get("type") == "title":
            return rich_text_to_md(prop.get("title") or []) or "(untitled)"
    return "(untitled)"


def _render_property_value(prop: dict) -> str:
    """Render a Notion page-property object into a single-line markdown value."""
    ptype = prop.get("type", "")
    payload = prop.get(ptype)
    if payload is None:
        return "—"

    if ptype == "title" or ptype == "rich_text":
        return rich_text_to_md(payload) or "—"
    if ptype == "number":
        return "—" if payload is None else str(payload)
    if ptype == "select":
        return payload.get("name", "—") if payload else "—"
    if ptype == "multi_select":
        names = [x.get("name", "?") for x in (payload or [])]
        return ", ".join(names) or "—"
    if ptype == "status":
        return payload.get("name", "—") if payload else "—"
    if ptype == "date":
        if not payload:
            return "—"
        start = payload.get("start", "")
        end = payload.get("end", "")
        return f"{start} → {end}" if end else (start or "—")
    if ptype == "people":
        people = [(p.get("name") or p.get("id", "?")) for p in (payload or [])]
        return ", ".join(people) or "—"
    if ptype == "files":
        names = []
        for f in payload or []:
            n = f.get("name") or "?"
            url = (f.get("external") or {}).get("url") or (f.get("file") or {}).get("url")
            names.append(f"[{n}]({url})" if url else n)
        return ", ".join(names) or "—"
    if ptype == "checkbox":
        return "✓" if payload else "✗"
    if ptype == "url":
        return payload or "—"
    if ptype == "email":
        return payload or "—"
    if ptype == "phone_number":
        return payload or "—"
    if ptype == "formula":
        inner_type = payload.get("type")
        return str(payload.get(inner_type, "—"))
    if ptype == "relation":
        ids = [r.get("id", "?") for r in (payload or [])]
        return ", ".join(ids) or "—"
    if ptype == "rollup":
        inner_type = payload.get("type")
        if inner_type == "array":
            arr = payload.get("array") or []
            return f"[{len(arr)} items]"
        return str(payload.get(inner_type, "—"))
    if ptype == "created_time" or ptype == "last_edited_time":
        return payload or "—"
    if ptype == "created_by" or ptype == "last_edited_by":
        if isinstance(payload, dict):
            return payload.get("name") or payload.get("id", "—")
        return "—"
    if ptype == "unique_id":
        prefix = payload.get("prefix") or ""
        number = payload.get("number")
        return f"{prefix}-{number}" if prefix else str(number)
    if ptype == "verification":
        return (payload or {}).get("state", "—")
    # Fallback — dump compact JSON
    try:
        return json.dumps(payload, ensure_ascii=False)[:200]
    except Exception:
        return "—"


def render_page_metadata(page: dict) -> str:
    """Render page-level metadata block: created/edited/url + all custom properties."""
    lines: list[str] = []
    url = page.get("url")
    if url:
        lines.append(f"- **URL:** {url}")
    if page.get("created_time"):
        author = page.get("created_by") or {}
        lines.append(
            f"- **Created:** {page.get('created_time', '—')} by "
            f"{author.get('name') or author.get('id', '—')}"
        )
    if page.get("last_edited_time"):
        editor = page.get("last_edited_by") or {}
        lines.append(
            f"- **Last edited:** {page.get('last_edited_time', '—')} by "
            f"{editor.get('name') or editor.get('id', '—')}"
        )
    if page.get("archived"):
        lines.append("- **Archived:** yes")

    props = page.get("properties") or {}
    # Keep order but skip the title (already used in the main heading).
    for name, prop in props.items():
        if prop.get("type") == "title":
            continue
        value = _render_property_value(prop)
        if value and value != "—":
            lines.append(f"- **{name}:** {value}")

    return "\n".join(lines) if lines else ""


def _indent(text: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" if line else "" for line in text.splitlines())


def render_block(block: dict, token: str, depth: int) -> str:
    btype = block.get("type", "")
    payload = block.get(btype) or {}
    rt = payload.get("rich_text") or []
    text = rich_text_to_md(rt)

    body: str
    if btype == "paragraph":
        body = text
    elif btype == "heading_1":
        body = f"# {text}"
    elif btype == "heading_2":
        body = f"## {text}"
    elif btype == "heading_3":
        body = f"### {text}"
    elif btype == "bulleted_list_item":
        body = f"- {text}"
    elif btype == "numbered_list_item":
        body = f"1. {text}"
    elif btype == "to_do":
        checked = "x" if payload.get("checked") else " "
        body = f"- [{checked}] {text}"
    elif btype == "toggle":
        body = f"- {text}"  # flatten; children render as nested list
    elif btype == "callout":
        emoji = (payload.get("icon") or {}).get("emoji") or ""
        prefix = f"{emoji} " if emoji else ""
        body = f"> {prefix}{text}"
    elif btype == "quote":
        body = f"> {text}"
    elif btype == "divider":
        body = "---"
    elif btype == "code":
        lang = payload.get("language", "") or ""
        body = f"```{lang}\n{text}\n```"
    elif btype == "table":
        # The table block only carries metadata; rows come as children.
        body = ""  # rendering happens via children traversal
    elif btype == "table_row":
        cells = payload.get("cells") or []
        rendered_cells = [rich_text_to_md(cell) for cell in cells]
        body = "| " + " | ".join(rendered_cells) + " |"
    elif btype == "column_list":
        body = ""  # columns are rendered sequentially via children
    elif btype == "column":
        body = ""  # ditto
    elif btype == "child_page":
        child_id = block.get("id")
        title = payload.get("title") or "(untitled child page)"
        body = f"## {title}"
        if child_id:
            try:
                child_blocks = list_block_children(child_id, token)
            except NotionError as exc:
                body += f"\n\n<!-- child_page error: {exc} -->"
                child_blocks = []
            rendered_children = render_blocks(child_blocks, token, depth)
            if rendered_children:
                body += "\n\n" + rendered_children
        return body  # children already folded in; do not recurse below
    elif btype == "child_database":
        title = payload.get("title") or "(untitled database)"
        body = f"**[Database]** {title}"
    elif btype in {"image", "file", "pdf", "audio", "video"}:
        source = payload.get("external") or payload.get("file") or {}
        url = source.get("url", "")
        caption = rich_text_to_md(payload.get("caption") or [])
        label = caption or btype
        if btype == "image" and url:
            body = f"![{caption or 'image'}]({url})"
        elif url:
            body = f"[{label}]({url}) _[{btype}]_"
        else:
            body = f"_[{btype}: no url]_"
    elif btype in {"bookmark", "embed", "link_preview"}:
        url = payload.get("url", "")
        caption = rich_text_to_md(payload.get("caption") or [])
        if url:
            body = f"[{caption or url}]({url}) _[{btype}]_"
        else:
            body = f"_[{btype}: no url]_"
    elif btype == "equation":
        expression = payload.get("expression", "")
        body = f"$${expression}$$" if expression else "_[equation: empty]_"
    elif btype == "link_to_page":
        ref_type = payload.get("type")
        ref_id = payload.get(ref_type) if ref_type else None
        body = f"_[link to {ref_type}: `{ref_id}`]_" if ref_id else "_[link_to_page]_"
    elif btype == "synced_block":
        synced_from = payload.get("synced_from") or {}
        if synced_from and synced_from.get("block_id"):
            # Duplicated synced block — follow the original.
            original_id = synced_from["block_id"]
            try:
                original_children = list_block_children(original_id, token)
            except NotionError as exc:
                body = f"<!-- synced_block error: {exc} -->"
            else:
                body = render_blocks(original_children, token, depth + 1) or "_[empty synced block]_"
            return body
        # Original synced block — its children render via the normal has_children path.
        body = ""
    elif btype == "table_of_contents":
        body = "_[Table of Contents]_"
    elif btype == "breadcrumb":
        body = "_[Breadcrumb]_"
    else:
        body = f"<!-- unsupported block: {btype} -->"

    # Recurse into children (non-child_page blocks) if any.
    if block.get("has_children") and btype not in {"child_page"}:
        try:
            children = list_block_children(block["id"], token)
        except NotionError as exc:
            body += f"\n<!-- children error: {exc} -->"
            children = []
        rendered = render_blocks(children, token, depth + 1)
        if rendered:
            if btype in {"bulleted_list_item", "numbered_list_item", "to_do", "toggle"}:
                body += "\n" + _indent(rendered, "    ")
            elif btype == "table":
                body = rendered  # the table body IS its rows
            elif btype in {"column_list", "column"}:
                body += rendered
            else:
                body += "\n\n" + rendered
    return body


def render_blocks(blocks: list[dict], token: str, depth: int) -> str:
    chunks: list[str] = []
    for b in blocks:
        chunk = render_block(b, token, depth)
        if chunk or chunk == "":
            chunks.append(chunk)
    # collapse empty chunks but keep separation between real content
    filtered = [c for c in chunks if c != ""]
    return "\n\n".join(filtered)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: NOTION_TOKEN=<secret> notion-page-dump.py <page-id-or-url>",
            file=sys.stderr,
        )
        return 2

    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        print("error: NOTION_TOKEN env var is required", file=sys.stderr)
        return 2

    try:
        page_id = extract_page_id(argv[1])
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        page = get_page(page_id, token)
        title = extract_page_title(page)
        blocks = list_block_children(page_id, token)
    except NotionError as exc:
        print(f"notion-error: {exc}", file=sys.stderr)
        return 1

    print(f"# {title}")
    print("")
    metadata = render_page_metadata(page)
    if metadata:
        print(metadata)
        print("")
    rendered = render_blocks(blocks, token, depth=0)
    if rendered:
        print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
