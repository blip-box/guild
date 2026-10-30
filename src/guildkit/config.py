"""guild.toml: what makes an adopting repository different from the shell.

Plain validation with plain errors, no schema library. Every value a workflow
or a role needs is read here once, so the rest of the shell takes typed data.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, TypedDict

from guildkit.tiers import PathRules, ShapeRules, Tier
from guildkit.triage import Prices

_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9.:-]*$")
_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
TIER_NAMES = tuple(t.name.lower() for t in Tier)


class TriageConfig(TypedDict):
    """The triage role's model and limits."""

    model: str
    max_tokens: int
    cap_usd: float
    per_author_per_day: int
    daily_runs: int


class Config(TypedDict):
    """Everything in guild.toml."""

    repo: str
    charter: str
    stewards: list[str]
    max_stewards: int
    paths: PathRules
    shape: ShapeRules
    tests: list[str]
    kinds: dict[str, str]
    triage: TriageConfig
    prices: dict[str, Prices]


class ConfigError(ValueError):
    """guild.toml says something the shell cannot use."""


def _table(data: Any, where: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: expected a table")
    return data


def _get(table: dict[str, Any], key: str, kind: type, where: str) -> Any:
    if key not in table:
        raise ConfigError(f"{where}.{key}: missing")
    value = table[key]
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise ConfigError(f"{where}.{key}: expected {kind.__name__}")
    return value


def _strings(table: dict[str, Any], key: str, where: str) -> list[str]:
    value = _get(table, key, list, where)
    if not all(isinstance(v, str) and v for v in value):
        raise ConfigError(f"{where}.{key}: expected a list of strings")
    return list(value)


def _tier(table: dict[str, Any], key: str, where: str) -> str:
    value = _get(table, key, str, where)
    if value not in TIER_NAMES:
        raise ConfigError(f"{where}.{key}: expected one of {list(TIER_NAMES)}")
    return str(value)


def parse(text: str) -> Config:
    """Return the configuration in the TOML text, or raise ConfigError."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"not TOML: {e}") from e

    guild = _table(data.get("guild"), "guild")
    repo = _get(guild, "repo", str, "guild")
    if not re.match(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", repo):
        raise ConfigError("guild.repo: expected owner/name")
    charter = _get(guild, "charter", str, "guild")

    stewards = _table(data.get("stewards"), "stewards")
    logins = _strings(stewards, "logins", "stewards")
    max_stewards = _get(stewards, "max", int, "stewards")
    if not logins or len(logins) > max_stewards or len(set(logins)) != len(logins):
        raise ConfigError(
            f"stewards.logins: between 1 and {max_stewards} distinct logins"
        )
    if not all(_LOGIN.match(login) for login in logins):
        raise ConfigError("stewards.logins: not GitHub logins")

    tiers = _table(data.get("tiers"), "tiers")
    paths_table = _table(tiers.get("paths"), "tiers.paths")
    paths: PathRules = {
        "reject": _strings(paths_table, "reject", "tiers.paths"),
        "t0": _strings(paths_table, "t0", "tiers.paths"),
        "t1": _strings(paths_table, "t1", "tiers.paths"),
        "t2": _strings(paths_table, "t2", "tiers.paths"),
        "t3": _strings(paths_table, "t3", "tiers.paths"),
        "default": _tier(paths_table, "default", "tiers.paths"),
    }
    shape_table = _table(tiers.get("shape"), "tiers.shape")
    shape: ShapeRules = {
        "max_t0_lines": _get(shape_table, "max_t0_lines", int, "tiers.shape"),
        "deleted_tests": _tier(shape_table, "deleted_tests", "tiers.shape"),
        "deleted_files": _tier(shape_table, "deleted_files", "tiers.shape"),
        "changed_tests": _tier(shape_table, "changed_tests", "tiers.shape"),
    }
    tests = _strings(shape_table, "tests", "tiers.shape")
    kinds_table = _table(tiers.get("kinds"), "tiers.kinds")
    kinds = {key: _tier(kinds_table, key, "tiers.kinds") for key in kinds_table}

    triage_table = _table(data.get("triage"), "triage")
    triage: TriageConfig = {
        "model": _get(triage_table, "model", str, "triage"),
        "max_tokens": _get(triage_table, "max_tokens", int, "triage"),
        "cap_usd": _get(triage_table, "cap_usd", float, "triage"),
        "per_author_per_day": _get(triage_table, "per_author_per_day", int, "triage"),
        "daily_runs": _get(triage_table, "daily_runs", int, "triage"),
    }
    if not _MODEL_ID.match(triage["model"]):
        raise ConfigError("triage.model: not a model ID")

    models = _table(data.get("models"), "models")
    prices: dict[str, Prices] = {}
    for model_id, table in models.items():
        where = f"models.{model_id}"
        if not _MODEL_ID.match(model_id):
            raise ConfigError(f"{where}: not a model ID")
        price_table = _table(table, where)
        prices[model_id] = {
            "input_per_mtok": _get(price_table, "input_per_mtok", float, where),
            "output_per_mtok": _get(price_table, "output_per_mtok", float, where),
            "cache_read_per_mtok": _get(
                price_table, "cache_read_per_mtok", float, where
            ),
            "cache_write_per_mtok": _get(
                price_table, "cache_write_per_mtok", float, where
            ),
        }
    if triage["model"] not in prices:
        raise ConfigError(f"models: no prices for triage.model {triage['model']}")

    return {
        "repo": repo,
        "charter": charter,
        "stewards": logins,
        "max_stewards": max_stewards,
        "paths": paths,
        "shape": shape,
        "tests": tests,
        "kinds": kinds,
        "triage": triage,
        "prices": prices,
    }


def load(path: Path) -> Config:
    """Return the configuration in the file."""
    return parse(path.read_text(encoding="utf-8"))
