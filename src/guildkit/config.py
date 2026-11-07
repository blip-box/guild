"""guild.toml: what makes an adopting repository different from the shell.

Plain validation with plain errors, no schema library. Every value a workflow
or a role needs is read here once, so the rest of the shell takes typed data.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, TypedDict

from guildkit.builder import BuildRules
from guildkit.roles import EFFORTS, GRADER, ROLES, Role
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


class AgentConfig(TypedDict):
    """One agent role's model and limits."""

    model: str
    max_turns: int
    cap_usd: float
    effort: str


class ReleaseRules(TypedDict):
    """When a release is due and what the steward's checklist names."""

    library: list[str]
    stale_days: int
    version_files: list[str]
    prerelease: str


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
    agents: dict[Role, AgentConfig]
    build: BuildRules
    # The Builder's second attempt, on an escalated setting: None for one attempt.
    second_attempt: AgentConfig | None
    release: ReleaseRules
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


def _agent(table: dict[str, Any], where: str) -> AgentConfig:
    agent: AgentConfig = {
        "model": _get(table, "model", str, where),
        "max_turns": _get(table, "max_turns", int, where),
        "cap_usd": _get(table, "cap_usd", float, where),
        "effort": _get(table, "effort", str, where),
    }
    if not _MODEL_ID.match(agent["model"]):
        raise ConfigError(f"{where}.model: not a model ID")
    if agent["effort"] not in EFFORTS:
        raise ConfigError(f"{where}.effort: expected one of {list(EFFORTS)}")
    if agent["max_turns"] < 1:
        raise ConfigError(f"{where}.max_turns: expected at least 1")
    return agent


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

    agents: dict[Role, AgentConfig] = {}
    for role in (*ROLES, GRADER):
        if role == GRADER and role not in data:
            # The drills' second judge; the Reviewer's settings unless set.
            agents[role] = agents["reviewer"].copy()
            continue
        agents[role] = _agent(_table(data.get(role), role), role)
    builder_table = _table(data.get("builder"), "builder")
    second_attempt = None
    if "second_attempt" in builder_table:
        where = "builder.second_attempt"
        second_attempt = _agent(_table(builder_table["second_attempt"], where), where)
    build: BuildRules = {
        "test_command": _get(builder_table, "test_command", str, "builder"),
        "max_test_rounds": _get(builder_table, "max_test_rounds", int, "builder"),
        "generated": _strings(builder_table, "generated", "builder"),
        "generators": _strings(builder_table, "generators", "builder"),
    }
    if not build["test_command"].strip():
        raise ConfigError("builder.test_command: empty")

    release_table = _table(data.get("release", {}), "release")
    release: ReleaseRules = {
        "library": _strings(release_table, "library", "release")
        if "library" in release_table
        else ["src/**"],
        "stale_days": _get(release_table, "stale_days", int, "release")
        if "stale_days" in release_table
        else 28,
        "version_files": _strings(release_table, "version_files", "release")
        if "version_files" in release_table
        else ["pyproject.toml"],
        "prerelease": _get(release_table, "prerelease", str, "release")
        if "prerelease" in release_table
        else "",
    }
    if release["stale_days"] < 1:
        raise ConfigError("release.stale_days: expected at least 1")
    if release["prerelease"] not in ("", "a", "b", "rc"):
        raise ConfigError("release.prerelease: expected a, b, rc or nothing")

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
    for role, agent in agents.items():
        if agent["model"] not in prices:
            raise ConfigError(f"models: no prices for {role}.model {agent['model']}")
    if second_attempt is not None and second_attempt["model"] not in prices:
        raise ConfigError(
            f"models: no prices for builder.second_attempt.model"
            f" {second_attempt['model']}"
        )

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
        "agents": agents,
        "build": build,
        "second_attempt": second_attempt,
        "release": release,
        "prices": prices,
    }


def load(path: Path) -> Config:
    """Return the configuration in the file."""
    return parse(path.read_text(encoding="utf-8"))
