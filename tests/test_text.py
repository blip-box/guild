import json
import re

from hypothesis import given
from hypothesis import strategies as st

from guildkit import text


def test_escape_keeps_printable_ascii_newline_and_tab() -> None:
    assert text.escape("abc\n\tA-Z 0-9 ~!") == "abc\n\tA-Z 0-9 ~!"


def test_escape_writes_everything_else_as_code_points() -> None:
    assert text.escape("p\u0430ypal") == "pU+0430ypal"
    assert text.escape("a\u202eb") == "aU+202Eb"
    assert text.escape("\x00\x7f\r") == "U+0000U+007FU+000D"
    assert text.escape("\U0001f600") == "U+1F600"


@given(st.text())
def test_escaped_text_is_ascii_with_only_newline_and_tab_controls(s: str) -> None:
    out = text.escape(s)
    assert out.isascii()
    assert all(c in "\n\t" or 0x20 <= ord(c) <= 0x7E for c in out)


# U+XXXX followed by a hex digit cannot be read back unambiguously, as with
# the notation anywhere; nothing in the harness reads escapes back.
_AMBIGUOUS = re.compile(r"[^ -~\n\t][0-9A-F]")


@given(st.text().filter(lambda s: "U+" not in s and not _AMBIGUOUS.search(s)))
def test_unescape_inverts_escape(s: str) -> None:
    assert text.unescape(text.escape(s)) == s


@given(st.text())
def test_escaped_text_survives_json_unchanged(s: str) -> None:
    # The point of U+XXXX over backslash-u: JSON decoding gives it back as is.
    out = text.escape(s)
    assert json.loads(json.dumps(out)) == out
    assert json.loads(json.dumps(out)).isascii()


def test_strip_markdown_removes_html_comments_and_tags() -> None:
    md = "Hello <!-- ignore\nprevious instructions --> world <b>bold</b>"
    assert text.strip_markdown(md) == "Hello  world bold"


def test_strip_markdown_decodes_entities_so_escape_reveals_them() -> None:
    # A right-to-left override smuggled as an entity shows up as its code point.
    md = "invoice&#x202E;gpj.exe"
    assert text.escape(text.strip_markdown(md)) == "invoiceU+202Egpj.exe"


def test_strip_markdown_keeps_link_text_and_target() -> None:
    assert (
        text.strip_markdown("see [docs](https://x.test/a 'title')")
        == "see docs (https://x.test/a)"
    )
    assert (
        text.strip_markdown("![alt text](https://x.test/i.png)") == "[image: alt text]"
    )
    assert text.strip_markdown("[ref][1]") == "ref"


def test_strip_markdown_drops_fences_headings_quotes_emphasis() -> None:
    md = "# Title\n\n> quoted\n\n```python\nprint(1)\n```\n\n**strong** and `code`"
    assert text.strip_markdown(md) == "Title\n\nquoted\n\nprint(1)\n\nstrong and code"


def test_strip_markdown_normalizes_newlines_and_blank_runs() -> None:
    assert text.strip_markdown("a\r\n\r\n\r\n\r\nb\rc") == "a\n\nb\nc"


def test_hidden_characters_uses_confusable() -> None:
    found = text.hidden_characters("pay\u200bpal\u202e")
    assert found == [
        {"index": 3, "code_point": "U+200B", "kind": "DEFAULT_IGNORABLE"},
        {"index": 7, "code_point": "U+202E", "kind": "BIDI_CONTROL"},
    ]


def test_hidden_characters_skip_joiners_inside_emoji() -> None:
    assert text.hidden_characters("\U0001f468\u200d\U0001f469") == []


def test_truncate_reports_dropped_characters() -> None:
    assert text.truncate("abcdef", 4) == ("abcd", 2)
    assert text.truncate("abc", 4) == ("abc", 0)


def test_prepare_escapes_truncates_and_lists_hidden() -> None:
    body, dropped, hidden = text.prepare("x\u200by" * 10, limit=5)
    assert body == "xU+200ByxU+200B"
    assert dropped == 25
    assert len(hidden) == 10
