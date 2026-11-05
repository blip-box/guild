import re
from pathlib import Path

import pytest

from guildkit import config


def test_example_config_loads(example_config: Path) -> None:
    cfg = config.load(example_config)
    assert cfg["repo"] == "blip-box/confusable"
    assert cfg["stewards"] == ["atillaguzel"]
    assert cfg["paths"]["default"] == "t1"
    assert "CHARTER.md" in cfg["paths"]["reject"]
    assert cfg["shape"]["deleted_tests"] == "t2"
    assert cfg["tests"] == ["tests/**"]
    assert cfg["kinds"]["release"] == "t3"
    assert cfg["triage"]["model"] in cfg["prices"]
    assert cfg["prices"]["claude-haiku-5-5"]["output_per_mtok"] == 0.5


def _with(example_config: Path, old: str, new: str) -> str:
    text = example_config.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    return text.replace(old, new)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('repo = "blip-box/confusable"', 'repo = "confusable"', "guild.repo"),
        ('logins = ["atillaguzel"]', "logins = []", "stewards.logins"),
        (
            'logins = ["atillaguzel"]',
            'logins = ["a", "b", "c", "d"]',
            "stewards.logins",
        ),
        ('logins = ["atillaguzel"]', 'logins = ["not a login"]', "stewards.logins"),
        ('default = "t1"', 'default = "t9"', "tiers.paths.default"),
        ('deleted_tests = "t2"', "deleted_tests = 2", "tiers.shape.deleted_tests"),
        ("max_t0_lines = 50", 'max_t0_lines = "50"', "tiers.shape.max_t0_lines"),
        ('public_api = "t2"', 'public_api = "high"', "tiers.kinds.public_api"),
        ('model = "claude-haiku-5-5"', 'model = "Claude Haiku"', "triage.model"),
        ('model = "claude-haiku-5-5"', 'model = "claude-haiku-9"', "no prices"),
        ("cap_usd = 0.10", 'cap_usd = "cheap"', "triage.cap_usd"),
        ("input_per_mtok = 0.10", "input_per_mtok = true", "input_per_mtok"),
    ],
)
def test_bad_values_are_named(
    example_config: Path, old: str, new: str, message: str
) -> None:
    with pytest.raises(config.ConfigError, match=message):
        config.parse(_with(example_config, old, new))


def test_missing_table_is_named() -> None:
    with pytest.raises(config.ConfigError, match="guild: expected a table"):
        config.parse("[stewards]\nlogins = ['a']\nmax = 3\n")


def test_not_toml() -> None:
    with pytest.raises(config.ConfigError, match="not TOML"):
        config.parse("guild = [")


def test_example_config_has_the_agents(example_config: Path) -> None:
    cfg = config.load(example_config)
    assert set(cfg["agents"]) == {"planner", "builder", "reviewer", "grader"}
    assert cfg["agents"]["builder"]["cap_usd"] == 4.0
    assert cfg["agents"]["builder"]["effort"] == "high"
    assert cfg["build"]["test_command"].startswith("uv run --no-sync pytest")
    assert cfg["build"]["max_test_rounds"] == 3
    assert "tools/**" in cfg["build"]["generators"]
    for agent in cfg["agents"].values():
        assert agent["model"] in cfg["prices"]


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'effort = "high"\n\n[builder]',
            'effort = "extreme"\n\n[builder]',
            "planner.effort",
        ),
        ("max_turns = 80", "max_turns = 0", "builder.max_turns"),
        (
            'test_command = "uv run --no-sync pytest -q -x"',
            'test_command = " "',
            "builder.test_command",
        ),
        (
            '[reviewer]\nmodel = "claude-opus-5-5"',
            '[reviewer]\nmodel = "claude-opus-9"',
            "no prices for reviewer.model",
        ),
        ('generators = ["tools/**"]', "generators = [1]", "builder.generators"),
    ],
)
def test_agent_sections_are_validated(
    example_config: Path, old: str, new: str, message: str
) -> None:
    with pytest.raises(config.ConfigError, match=re.escape(message)):
        config.parse(_with(example_config, old, new))


def test_grader_takes_the_reviewer_settings_unless_set(example_config: Path) -> None:
    text = example_config.read_text(encoding="utf-8")
    cfg = config.parse(text)
    assert "\n[grader]\n" not in text
    assert cfg["agents"]["grader"] == cfg["agents"]["reviewer"]
    assert cfg["agents"]["grader"] is not cfg["agents"]["reviewer"]
    own = text + (
        '\n[grader]\nmodel = "claude-haiku-5-5"\nmax_turns = 10\n'
        'cap_usd = 0.5\neffort = "low"\n'
    )
    cfg = config.parse(own)
    assert cfg["agents"]["grader"] == {
        "model": "claude-haiku-5-5",
        "max_turns": 10,
        "cap_usd": 0.5,
        "effort": "low",
    }
    assert cfg["agents"]["reviewer"]["model"] == "claude-opus-5-5"
    with pytest.raises(
        config.ConfigError, match=re.escape("no prices for grader.model")
    ):
        config.parse(
            own.replace(
                'model = "claude-haiku-5-5"\nmax_turns = 10',
                'model = "x-9"\nmax_turns = 10',
            )
        )
    with pytest.raises(config.ConfigError, match=re.escape("grader.effort")):
        config.parse(own.replace('effort = "low"', 'effort = "most"'))
