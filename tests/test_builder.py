from typing import Any

from guildkit import builder, tiers

PATHS: tiers.PathRules = {
    "reject": [".github/**", "AGENTS.md", "guild.toml", "conftest.py"],
    "t0": ["*.md", "src/confusable/_data/**"],
    "t1": [],
    "t2": ["pyproject.toml", "tools/**"],
    "t3": [],
    "default": "t1",
}
SHAPE: tiers.ShapeRules = {
    "max_t0_lines": 50,
    "deleted_tests": "t2",
    "deleted_files": "t1",
    "changed_tests": "t1",
}
RULES: builder.BuildRules = {
    "test_command": "true",
    "max_test_rounds": 1,
    "generated": ["src/confusable/_data/**", "tests/conformance/fixtures/**"],
    "generators": ["tools/**"],
}
FLOORS = {"public_api": "t2", "release": "t3"}


def diff(*files: tuple[str, list[str], list[str]], deleted: str | None = None) -> str:
    out = []
    for path, removed, added in files:
        out.append(f"diff --git a/{path} b/{path}")
        out.append(f"--- a/{path}")
        out.append(f"+++ b/{path}")
        out.append("@@ -1,3 +1,3 @@")
        out.append(" context")
        out.extend(f"-{line}" for line in removed)
        out.extend(f"+{line}" for line in added)
    if deleted:
        out.append(f"diff --git a/{deleted} b/{deleted}")
        out.append("deleted file mode 100644")
        out.append(f"--- a/{deleted}")
        out.append("+++ /dev/null")
        out.append("@@ -1 +0,0 @@")
        out.append("-gone")
    return "\n".join(out) + "\n"


def check(text: str, kinds: list[str] | None = None) -> builder.Check:
    return builder.check_patch(
        text,
        paths=PATHS,
        shape=SHAPE,
        tests=["tests/**"],
        rules=RULES,
        kinds=kinds or [],
        floors=FLOORS,
    )


def test_parse_diff_reads_paths_lines_and_deletions() -> None:
    patch = builder.parse_diff(
        diff(
            ("src/x.py", ["a"], ["b", "c"]),
            ("tests/test_x.py", [], ["d"]),
            deleted="old.py",
        )
    )
    assert patch["paths"] == ["src/x.py", "tests/test_x.py", "old.py"]
    assert patch["deleted_files"] == ["old.py"]
    assert patch["lines_changed"] == 5
    assert patch["added"]["src/x.py"] == ["b", "c"]
    assert patch["removed"]["old.py"] == ["gone"]


def test_parse_diff_handles_binary_and_headers() -> None:
    text = (
        "diff --git a/img.png b/img.png\n"
        "new file mode 100644\n"
        "Binary files /dev/null and b/img.png differ\n"
        "diff --git a/src/y.py b/src/y.py\n"
        "--- a/src/y.py\n+++ b/src/y.py\n@@ -1 +1 @@\n"
        "-+++ not a header\n+--- not a header\n"
    )
    patch = builder.parse_diff(text)
    assert patch["paths"] == ["img.png", "src/y.py"]
    assert patch["added"]["img.png"] == []
    assert patch["added"]["src/y.py"] == ["--- not a header"]
    assert patch["removed"]["src/y.py"] == ["+++ not a header"]
    assert builder.parse_diff("")["paths"] == []


def test_a_good_fix_passes_and_is_tiered() -> None:
    text = diff(
        ("src/confusable/_skeleton.py", ["old"], ["new"]),
        ("tests/test_skeleton.py", [], ["def test_more(): ..."]),
    )
    result = check(text)
    assert result["ok"] is True
    assert result["failures"] == []
    assert result["tier"] == "T1"
    assert result["rejected"] == []


def test_failures_are_named() -> None:
    text = diff(
        ("AGENTS.md", ["a"], ["b"]),
        (
            "tests/test_a.py",
            ["def test_gone(): ...", "def test_kept(): ..."],
            [
                "def test_kept(): ...",
                "@pytest.mark.skip(reason='later')",
                "x = pytest.xfail('no')",
            ],
        ),
        ("src/confusable/_data/scripts.py", ["1"], ["2"]),
    )
    result = check(text)
    assert result["ok"] is False
    assert result["rejected"] == ["AGENTS.md"]
    assert "reject list: AGENTS.md" in result["failures"]
    assert "deleted test: tests/test_a.py: test_gone" in result["failures"]
    assert any(
        f.startswith("new skip or xfail: tests/test_a.py: @pytest.mark.skip")
        for f in result["failures"]
    )
    assert any(
        f.startswith("new skip or xfail: tests/test_a.py: x = pytest.xfail")
        for f in result["failures"]
    )
    assert (
        "generated without its generator: src/confusable/_data/scripts.py"
        in result["failures"]
    )


def test_generated_with_its_generator_is_fine_and_t2() -> None:
    text = diff(
        ("src/confusable/_data/scripts.py", ["1"], ["2"]),
        ("tools/generate_tables.py", ["a"], ["b"]),
    )
    result = check(text)
    assert result["ok"] is True
    assert result["tier"] == "T2"


def test_empty_patch_and_kinds() -> None:
    assert check("")["failures"] == ["no change"]
    result = check(
        diff(("src/confusable/__init__.py", [], ["x = 1"])), kinds=["public_api"]
    )
    assert result["ok"] is True
    assert result["tier"] == "T2"
    assert any("kind public_api" in r for r in result["reasons"])


def test_renamed_test_counts_as_kept() -> None:
    text = diff(
        ("tests/test_a.py", ["def test_old(): ..."], ["async def test_old(): ..."])
    )
    assert builder.deleted_tests(builder.parse_diff(text), ["tests/**"]) == []


def test_prompt_is_role_rules_and_brief() -> None:
    system, user = builder.prompt(
        role="ROLE", handbook="HAND", charter="CHART", brief="BRIEF"
    )
    assert system.startswith("ROLE\n\n# The handbook\n\nHAND\n\n# The charter\n\nCHART")
    assert user == "BRIEF"


def test_check_is_a_plain_dict() -> None:
    result: Any = check(diff(("src/a.py", [], ["x"])))
    assert set(result) == {"ok", "tier", "paths", "rejected", "failures", "reasons"}
