"""Untrusted text, made safe to show to a model or a person.

Everything an outsider wrote reaches a model only through `prepare()`: the
Markdown becomes plain text, HTML comments and tags go, entities are decoded,
and every character outside printable ASCII is written as U+XXXX, a notation
that JSON never decodes back into the character. The invisible, bidirectional
and Tag characters are listed separately, found with confusable itself, so a
reader sees what the text hides.
"""

from __future__ import annotations

import html
import re
from typing import TypedDict

import confusable

# Characters that stay as they are: printable ASCII, newline and tab.
_PLAIN = re.compile(r"[\x20-\x7e\n\t]")
_ESCAPED = re.compile(r"U\+([0-9A-F]{4,6})")

_HTML_COMMENT = re.compile(r"<!--.*?(-->|\Z)", re.DOTALL)
_HTML_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*$", re.MULTILINE)
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\(\s*(\S+?)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
_REFERENCE_LINK = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)
_STRONG = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_BACKTICK = re.compile(r"`+")
_BLANK_LINES = re.compile(r"\n{3,}")


class Hidden(TypedDict):
    """One invisible, bidirectional or Tag character, as confusable reports it."""

    index: int
    code_point: str
    kind: str


def normalize_newlines(text: str) -> str:
    """Return text with CRLF and CR line endings as LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_markdown(markdown: str) -> str:
    r"""Return the plain text of GitHub-flavoured Markdown.

    Not a parser: a fixed sequence of substitutions that removes what hides
    text (HTML comments, tags, entities, link targets) and what only decorates
    it (fences, headings, quotes, emphasis). Text inside fences is kept; it is
    data, like everything else here.

    >>> strip_markdown("# Title\n\nSee [the docs](https://x.test/a) <!-- hi -->")
    'Title\n\nSee the docs (https://x.test/a)'
    """
    text = normalize_newlines(markdown)
    text = _HTML_COMMENT.sub("", text)
    text = _FENCE.sub("", text)
    text = _IMAGE.sub(r"[image: \1]", text)
    text = _LINK.sub(r"\1 (\2)", text)
    text = _REFERENCE_LINK.sub(r"\1", text)
    text = _HTML_TAG.sub("", text)
    text = html.unescape(text)
    text = _HEADING.sub("", text)
    text = _BLOCKQUOTE.sub("", text)
    text = _STRONG.sub(r"\2", text)
    text = _BACKTICK.sub("", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def escape(text: str) -> str:
    r"""Return text with every character outside printable ASCII as U+XXXX.

    Newline and tab stay. Other controls, every non-ASCII character and every
    surrogate become their code point, so nothing can be invisible or reorder
    the text, and so JSON, which decodes backslash escapes, cannot turn them
    back into characters.

    >>> escape("p\u0430ypal\u200b")
    'pU+0430ypalU+200B'
    """
    return "".join(c if _PLAIN.match(c) else f"U+{ord(c):04X}" for c in text)


def unescape(text: str) -> str:
    """Return the characters that `escape` wrote as U+XXXX.

    For tests and for people; the harness never feeds unescaped text anywhere.
    """
    return _ESCAPED.sub(lambda m: chr(int(m[1], 16)), text)


def hidden_characters(text: str) -> list[Hidden]:
    """Return the invisible, bidirectional and Tag characters in text.

    confusable's `find_invisible` leaves out the characters whose context
    gives them a visible job, such as the joiners inside an emoji sequence.
    Newline and tab are controls too, but they are the text's own structure.
    """
    return [
        {"index": index, "code_point": f"U+{ord(text[index]):04X}", "kind": kind.name}
        for index, kind in confusable.find_invisible(text)
        if text[index] not in "\n\t"
    ]


def truncate(text: str, limit: int) -> tuple[str, int]:
    """Return text cut to limit characters, and how many were dropped."""
    if len(text) <= limit:
        return text, 0
    return text[:limit], len(text) - limit


def prepare(markdown: str, *, limit: int) -> tuple[str, int, list[Hidden]]:
    """Return the escaped plain text of markdown, the characters dropped, hidden ones.

    The hidden characters are found in the plain text before escaping, so
    their indexes refer to that text, not to the escaped form.
    """
    plain = strip_markdown(markdown)
    hidden = hidden_characters(plain)
    cut, dropped = truncate(plain, limit)
    return escape(cut), dropped, hidden
