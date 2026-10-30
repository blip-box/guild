from typing import Any

from guildkit import snapshot, text

ISSUE: dict[str, Any] = {
    "number": 7,
    "id": 1001,
    "title": "skeleton() misses p\u0430ypal",
    "body": "Hi <!-- hidden -->\n\n`skeleton('p\u0430ypal')`"
    " returns the wrong thing &#x202E;",
    "user": {"login": "someone"},
    "author_association": "NONE",
    "created_at": "2026-10-30T00:00:00Z",
    "updated_at": "2026-10-30T00:00:00Z",
    "labels": [{"name": "bug"}, {"name": "needs info"}],
}
COMMENT: dict[str, Any] = {
    "id": 5005,
    "body": "Any news?\u200b",
    "user": {"login": "someone-else"},
    "author_association": "CONTRIBUTOR",
    "created_at": "2026-10-30T01:00:00Z",
    "updated_at": "2026-10-30T01:00:00Z",
}


def test_issue_snapshot_is_escaped_and_hashed() -> None:
    snap = snapshot.snapshot("blip-box/confusable", ISSUE)
    assert snap["kind"] == "issue"
    assert snap["comment_id"] is None
    assert snap["title"] == "skeleton() misses pU+0430ypal"
    assert (
        snap["body"] == "Hi \n\nskeleton('pU+0430ypal') returns the wrong thing U+202E"
    )
    assert snap["labels"] == ["bug", "needs info"]
    # The index refers to the plain text before escaping.
    where = text.unescape(snap["body"]).index("\u202e")
    assert snap["hidden"] == [
        {"index": where, "code_point": "U+202E", "kind": "BIDI_CONTROL"}
    ]
    assert len(snap["content_hash"]) == 64
    # The whole record is ASCII: nothing in it can hide or reorder.
    assert str(snap).isascii()


def test_comment_snapshot_takes_the_comment_body_and_author() -> None:
    snap = snapshot.snapshot("blip-box/confusable", ISSUE, COMMENT)
    assert snap["kind"] == "comment"
    assert snap["comment_id"] == 5005
    assert snap["author"] == "someone-else"
    assert snap["body"] == "Any news?U+200B"
    assert snap["title"] == "skeleton() misses pU+0430ypal"


def test_content_hash_changes_with_the_body() -> None:
    a = snapshot.snapshot("r/r", ISSUE)
    b = snapshot.snapshot("r/r", {**ISSUE, "body": ISSUE["body"] + "."})
    assert a["content_hash"] != b["content_hash"]
    assert snapshot.snapshot("r/r", ISSUE)["content_hash"] == a["content_hash"]


def test_limits_apply() -> None:
    snap = snapshot.snapshot(
        "r/r", {**ISSUE, "title": "t" * 300}, title_limit=10, body_limit=5
    )
    assert snap["title"] == "t" * 10
    assert snap["dropped"] > 0


def test_render_is_labelled_plain_text() -> None:
    rendered = snapshot.render(snapshot.snapshot("r/r", ISSUE))
    assert rendered.startswith("Repository: r/r\nNumber: 7\nKind: issue\n")
    assert "Hidden characters: U+202E (BIDI_CONTROL) at 48" in rendered
    assert rendered.endswith(
        "Body:\n" + "Hi \n\nskeleton('pU+0430ypal') returns the wrong thing U+202E"
    )
