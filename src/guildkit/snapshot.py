"""An issue or comment, as a record safe to hand to the triage call.

The snapshot holds only escaped text, numbers, identifiers and a hash of the
raw fields it was made from, so a later run can tell whether the issue has
changed since.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal, TypedDict

from guildkit.text import Hidden, escape, prepare

TITLE_LIMIT = 256
BODY_LIMIT = 20_000


class Snapshot(TypedDict):
    """What triage sees of an issue or a comment."""

    repo: str
    number: int
    kind: Literal["issue", "comment"]
    comment_id: int | None
    author: str
    author_association: str
    created_at: str
    labels: list[str]
    title: str
    body: str
    dropped: int
    hidden: list[Hidden]
    content_hash: str


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def content_hash(*fields: Any) -> str:
    """Return the SHA-256 of the fields, as JSON with sorted keys."""
    raw = json.dumps(fields, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def snapshot(
    repo: str,
    issue: Mapping[str, Any],
    comment: Mapping[str, Any] | None = None,
    *,
    title_limit: int = TITLE_LIMIT,
    body_limit: int = BODY_LIMIT,
) -> Snapshot:
    """Return the snapshot of an issue, or of one comment on it.

    `issue` and `comment` are the objects GitHub's API returns (the `issue`
    and `comment` members of an event payload). Every string they hold is
    untrusted and leaves here escaped.
    """
    source = comment if comment is not None else issue
    user = source.get("user") or {}
    raw_title = _text(issue.get("title"))
    raw_body = _text(source.get("body"))
    body, dropped, hidden = prepare(raw_body, limit=body_limit)
    title = escape(raw_title[:title_limit])
    return {
        "repo": repo,
        "number": int(issue["number"]),
        "kind": "comment" if comment is not None else "issue",
        "comment_id": int(comment["id"]) if comment is not None else None,
        "author": escape(_text(user.get("login"))),
        "author_association": escape(_text(source.get("author_association"))),
        "created_at": escape(_text(source.get("created_at"))),
        "labels": sorted(
            escape(_text(label.get("name"))) for label in issue.get("labels") or []
        ),
        "title": title,
        "body": body,
        "dropped": dropped,
        "hidden": hidden,
        "content_hash": content_hash(
            repo,
            issue.get("number"),
            source.get("id"),
            raw_title,
            raw_body,
            user.get("login"),
            source.get("created_at"),
            source.get("updated_at"),
        ),
    }


def render(snap: Snapshot) -> str:
    """Return the snapshot as the text the triage call reads.

    Labelled fields, nothing else: no instructions, no Markdown.
    """
    hidden = ", ".join(
        f"{h['code_point']} ({h['kind']}) at {h['index']}" for h in snap["hidden"]
    )
    lines = [
        f"Repository: {snap['repo']}",
        f"Number: {snap['number']}",
        f"Kind: {snap['kind']}",
        f"Author association: {snap['author_association']}",
        f"Labels: {', '.join(snap['labels']) or '(none)'}",
        f"Hidden characters: {hidden or '(none)'}",
        f"Characters dropped by the length limit: {snap['dropped']}",
        f"Title: {snap['title']}",
        "Body:",
        snap["body"],
    ]
    return "\n".join(lines)
