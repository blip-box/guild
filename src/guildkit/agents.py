"""Agents through the Claude Agent SDK: the options, the hooks, one run.

The SDK drives the Claude Code CLI it bundles. The shell gives it nothing from
disk: `setting_sources=[]`, a fresh `CLAUDE_CONFIG_DIR`, no MCP servers, no
skills, and the role prompt, handbook and charter as text read from the base
branch. Every tool call passes `Gate.pre_tool_use` before it runs; the
Builder may not finish until `TestGate.stop` has seen the tests pass. A run
ends in a `Run` of numbers and enumerations; the transcript is a separate
file for stewards, never printed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shlex
import subprocess
from collections import Counter
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, TypedDict, cast

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    PermissionResultDeny,
    ResultMessage,
    ToolUseBlock,
    query,
)
from claude_agent_sdk.types import (
    EffortLevel,
    HookContext,
    HookInput,
    HookJSONOutput,
    PermissionResult,
    SyncHookJSONOutput,
    ToolPermissionContext,
)

from guildkit import text, tiers
from guildkit.roles import EFFORTS, Role
from guildkit.triage import Prices, Usage, cost_usd

# What each role may call. The Planner and the Reviewer read; the Builder
# edits and runs the tests. Nothing reaches the web or another agent.
TOOLS: dict[Role, list[str]] = {
    "planner": ["Read", "Glob", "Grep"],
    "builder": ["Read", "Glob", "Grep", "Edit", "Write", "Bash"],
    "reviewer": ["Read", "Glob", "Grep", "Bash"],
    "grader": ["Read", "Glob", "Grep", "Bash"],
}
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
# The SDK delivers `output_format` through a tool call the model makes; it
# writes nothing and is how the Planner, Reviewer and Grader hand in their
# answers, so the gate lets it through for every role.
STRUCTURED_OUTPUT = "StructuredOutput"
READ_TOOLS = ("Read", "Glob", "Grep")
# Removed from the model's context as well, in case `tools` ever widens.
NEVER = [
    "WebFetch",
    "WebSearch",
    "Agent",
    "Task",
    "Skill",
    "NotebookEdit",
    "MultiEdit",
    "TodoWrite",
    "AskUserQuestion",
    "EnterPlanMode",
    "ExitPlanMode",
    "KillShell",
    "TaskOutput",
]
# The same call this many times ends the run: a loop, not work.
MAX_REPEATS = 8
# How much of the test output the Builder is shown when it may not stop yet.
OUTPUT_TAIL = 4000

# Bash commands the gate refuses outright. The checkout holds no token and the
# apply job re-checks the whole diff, so this list is the obvious cases, not
# the defence.
_FORBIDDEN_BASH = (
    re.compile(r"\bgit\s+(push|fetch|pull|remote|clone|submodule)\b"),
    re.compile(r"\bgh\b"),
    re.compile(r"\b(curl|wget|ssh|scp|sftp|nc|ncat|netcat|telnet|rsync)\b"),
    re.compile(r"\bpip3?\s+(install|download)\b"),
    re.compile(r"\buv\s+(add|remove|pip|tool|publish)\b"),
    re.compile(r"\b(npm|npx|pnpm|yarn|cargo)\s+(install|add|run|exec)\b"),
    re.compile(r"\b(sudo|doas|su)\b"),
    re.compile(r"\b(chmod|chown)\b"),
    re.compile(r"\brm\s+(-[A-Za-z]+\s+)*/(\s|$)"),
    re.compile(r"\b(urllib|requests|httpx|socket)\b"),
)


class Run(TypedDict):
    """One agent run, as the ledger and the stewards see it. No model text."""

    role: Role
    model: str
    subtype: str
    is_error: bool
    num_turns: int
    duration_ms: int
    usage: Usage
    cost_usd: float
    reported_cost_usd: float
    tool_calls: dict[str, int]
    denials: int
    repeated: bool
    test_rounds_blocked: int
    tests_passed: bool | None
    structured_output: Any


def _allow() -> SyncHookJSONOutput:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }


def _deny(reason: str) -> SyncHookJSONOutput:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


class Gate:
    """The path and command rules, as a PreToolUse hook with a backstop.

    Reads stay inside the checkout. Writes stay inside it too, off the reject
    list and out of `.git`, and only for a role that may write. Bash commands
    that would reach the network, a package index or the system are refused.
    The same call repeated `MAX_REPEATS` times ends the run.
    """

    def __init__(self, root: Path, *, role: Role, reject: list[str]) -> None:
        """Guard the checkout at `root` for `role`, with the reject patterns."""
        self.root = root.resolve()
        self.role = role
        self.reject = list(reject)
        self.calls: Counter[str] = Counter()
        self.denied: list[str] = []
        self.repeated = False

    def path_reason(self, path: str) -> str | None:
        """Return why the path may not be touched, or None."""
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            relative = candidate.resolve().relative_to(self.root)
        except ValueError:
            return "outside the checkout"
        if ".git" in relative.parts:
            return "inside .git"
        posix = relative.as_posix()
        if any(tiers.matches(posix, pattern) for pattern in self.reject):
            return "on the reject list"
        return None

    def reason(self, tool: str, tool_input: dict[str, Any]) -> str | None:
        """Return why the call is refused, or None to let it run."""
        if tool == STRUCTURED_OUTPUT:
            return None
        if tool in NEVER:
            return "tool not allowed for this role"
        if tool in WRITE_TOOLS and self.role != "builder":
            return "read-only role"
        if tool not in TOOLS[self.role]:
            return "tool not allowed for this role"
        if tool in WRITE_TOOLS:
            path = tool_input.get("file_path") or tool_input.get("notebook_path")
            if not isinstance(path, str) or not path:
                return "no path"
            return self.path_reason(path)
        if tool in READ_TOOLS:
            path = tool_input.get("file_path") or tool_input.get("path")
            if isinstance(path, str) and path:
                return self.path_reason(path)
            return None
        if tool == "Bash":
            command = tool_input.get("command")
            if not isinstance(command, str):
                return "no command"
            if any(pattern.search(command) for pattern in _FORBIDDEN_BASH):
                return "command refused"
            return None
        return "tool not allowed for this role"

    def _repeat(self, tool: str, tool_input: dict[str, Any]) -> bool:
        key = hashlib.sha256(
            json.dumps([tool, tool_input], sort_keys=True, default=str).encode()
        ).hexdigest()
        self.calls[key] += 1
        return self.calls[key] >= MAX_REPEATS

    async def pre_tool_use(
        self, hook_input: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        """Decide one tool call."""
        data = cast(dict[str, Any], hook_input)
        tool = str(data.get("tool_name", ""))
        tool_input = data.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}
        if self._repeat(tool, tool_input):
            self.repeated = True
            self.denied.append(f"{tool}: repeated")
            stop = _deny("the same call repeated; the run ends")
            stop["continue_"] = False
            stop["stopReason"] = "the same tool call repeated"
            return stop
        reason = self.reason(tool, tool_input)
        if reason is not None:
            self.denied.append(f"{tool}: {reason}")
            return _deny(f"Guild refuses this call: {reason}.")
        return _allow()

    async def can_use_tool(
        self, tool: str, tool_input: dict[str, Any], context: ToolPermissionContext
    ) -> PermissionResult:
        """Refuse anything that reaches the permission prompt.

        The hook decides every call, so this runs only if it did not.
        """
        self.denied.append(f"{tool}: reached the prompt")
        return PermissionResultDeny(message="Guild allows tools through its hook only.")


class TestGate:
    """The Builder's Stop hook: the tests must pass before the agent may stop.

    The command runs in the checkout. While it fails, the hook blocks the stop
    and shows the agent the escaped tail of the output, up to `rounds` times;
    then the agent may stop and the run fails its check.
    """

    def __init__(
        self, root: Path, command: str, *, rounds: int, timeout: int = 900
    ) -> None:
        """Run `command` in `root`, blocking at most `rounds` stops."""
        self.root = root
        self.argv = shlex.split(command)
        self.rounds = rounds
        self.timeout = timeout
        self.blocked = 0
        self.passed: bool | None = None

    def run(self) -> tuple[bool, str]:
        """Run the tests once; return whether they passed and the output tail."""
        try:
            proc = subprocess.run(
                self.argv,
                cwd=self.root,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, f"the test command did not finish in {self.timeout} s"
        except OSError as error:
            return False, f"the test command could not run: {error}"
        output = text.escape(proc.stdout + proc.stderr)
        return proc.returncode == 0, output[-OUTPUT_TAIL:]

    async def stop(
        self, hook_input: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        """Let the agent stop only when the tests pass."""
        passed, tail = await asyncio.to_thread(self.run)
        self.passed = passed
        if passed:
            return {}
        self.blocked += 1
        if self.blocked > self.rounds:
            return {}
        return {
            "decision": "block",
            "reason": (
                "The test command failed, so the work is not done. Fix the cause"
                " and run the tests again. The end of the output:\n" + tail
            ),
        }


def options(
    *,
    root: Path,
    config_dir: Path,
    system_prompt: str,
    role: Role,
    model: str,
    max_turns: int,
    cap_usd: float,
    effort: str,
    gate: Gate,
    tests: TestGate | None = None,
    output_format: dict[str, Any] | None = None,
) -> ClaudeAgentOptions:
    """Return the SDK options for one run: nothing from disk, everything pinned.

    `verbatim_prompts` keeps the prompt as written: no `@path` expansion and
    no slash commands, because the brief holds text an outsider wrote.
    `max_budget_usd` is the SDK's own estimate and a brake, not the cap; the
    ledger prices the tokens itself.
    """
    if effort not in EFFORTS:
        raise ValueError(f"effort {effort!r}")
    hooks: dict[Any, list[HookMatcher]] = {
        "PreToolUse": [HookMatcher(hooks=[gate.pre_tool_use])],
    }
    if tests is not None:
        hooks["Stop"] = [HookMatcher(hooks=[tests.stop], timeout=tests.timeout + 60)]
    return ClaudeAgentOptions(
        tools=list(TOOLS[role]),
        allowed_tools=[],
        disallowed_tools=list(NEVER),
        system_prompt=system_prompt,
        mcp_servers={},
        strict_mcp_config=True,
        permission_mode="default",
        can_use_tool=gate.can_use_tool,
        hooks=hooks,
        max_turns=max_turns,
        max_budget_usd=cap_usd,
        model=model,
        effort=cast(EffortLevel, effort),
        cwd=root,
        setting_sources=[],
        skills=[],
        verbatim_prompts=True,
        output_format=output_format,
        env={
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_TELEMETRY": "1",
            "DISABLE_AUTOUPDATER": "1",
        },
    )


Runner = Callable[..., AsyncIterator[Any]]


def _usage(result: ResultMessage | None) -> Usage:
    raw = result.usage if result is not None and result.usage else {}

    def count(key: str) -> int:
        value = raw.get(key, 0)
        return int(value) if isinstance(value, int | float) else 0

    return {
        "input_tokens": count("input_tokens"),
        "output_tokens": count("output_tokens"),
        "cache_read_tokens": count("cache_read_input_tokens"),
        "cache_write_tokens": count("cache_creation_input_tokens"),
    }


def _jsonable(message: Any) -> Any:
    if is_dataclass(message) and not isinstance(message, type):
        return asdict(message)
    return {"type": type(message).__name__, "repr": repr(message)}


async def run(
    prompt: str,
    agent_options: ClaudeAgentOptions,
    *,
    role: Role,
    prices: Prices,
    gate: Gate,
    tests: TestGate | None = None,
    transcript: Path | None = None,
    runner: Runner = query,
) -> Run:
    """Run the agent once and return the record.

    Every message goes to the transcript file, as JSON lines, for stewards.
    The record holds counts, the usage priced by the ledger's table, and the
    structured output when the role asked for one.
    """
    result: ResultMessage | None = None
    tool_calls: Counter[str] = Counter()
    lines: list[str] = []
    async for message in runner(prompt=prompt, options=agent_options):
        lines.append(json.dumps(_jsonable(message), default=str, ensure_ascii=True))
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    tool_calls[block.name] += 1
        elif isinstance(message, ResultMessage):
            result = message
    if transcript is not None:
        transcript.write_text("\n".join(lines) + "\n", encoding="ascii")
    usage = _usage(result)
    model = agent_options.model or ""
    reported = result.total_cost_usd if result is not None else None
    return {
        "role": role,
        "model": model,
        "subtype": result.subtype if result is not None else "no_result",
        "is_error": result.is_error if result is not None else True,
        "num_turns": result.num_turns if result is not None else 0,
        "duration_ms": result.duration_ms if result is not None else 0,
        "usage": usage,
        "cost_usd": cost_usd(usage, prices),
        "reported_cost_usd": round(reported, 6) if reported is not None else 0.0,
        "tool_calls": dict(sorted(tool_calls.items())),
        "denials": len(gate.denied),
        "repeated": gate.repeated,
        "test_rounds_blocked": tests.blocked if tests is not None else 0,
        "tests_passed": tests.passed if tests is not None else None,
        "structured_output": result.structured_output if result is not None else None,
    }


def succeeded(record: Run) -> bool:
    """Return whether the run ended normally with its tests passing, if any."""
    if record["is_error"] or record["subtype"] != "success" or record["repeated"]:
        return False
    return record["tests_passed"] is not False
