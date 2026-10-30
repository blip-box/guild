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
