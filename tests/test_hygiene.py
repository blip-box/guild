"""No hidden characters anywhere, and ASCII where a model reads instructions."""

import subprocess
from pathlib import Path

import confusable
import pytest

ROOT = Path(__file__).resolve().parents[1]


def tracked_text_files() -> list[Path]:
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    files = []
    for name in listing.decode("utf-8").split("\0"):
        if not name:
            continue
        path = ROOT / name
        try:
            path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        files.append(path)
    return files


def test_no_tracked_file_holds_invisible_or_bidi_characters() -> None:
    found = []
    for path in tracked_text_files():
        text = path.read_text(encoding="utf-8")
        for index, kind in confusable.find_invisible(text):
            if text[index] in "\t\n":
                continue
            found.append(
                f"{path.relative_to(ROOT)}: U+{ord(text[index]):04X} {kind.name}"
            )
    assert found == []


def test_source_roles_and_templates_are_ascii() -> None:
    not_ascii = [
        str(path.relative_to(ROOT))
        for path in tracked_text_files()
        if (
            path.suffix in (".py", ".toml", ".yml", ".yaml")
            or path.parts[len(ROOT.parts)] in ("roles", "templates")
        )
        and not path.read_text(encoding="utf-8").isascii()
    ]
    assert not_ascii == []
