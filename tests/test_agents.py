import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from guildkit import agents

REJECT = [".github/**", "AGENTS.md", "guild.toml", "conftest.py"]
PRICES = {
    "input_per_mtok": 4.0,
    "output_per_mtok": 20.0,
    "cache_read_per_mtok": 0.2,
    "cache_write_per_mtok": 5.0,
}


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".github").mkdir()
    (root / "src" / "a.py").write_text("x = 1\n", encoding="ascii")
    (root / "AGENTS.md").write_text("rules\n", encoding="ascii")
    return root


def pre(gate: agents.Gate, tool: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    hook_input: Any = {"tool_name": tool, "tool_input": tool_input}
    return dict(asyncio.run(gate.pre_tool_use(hook_input, None, {"signal": None})))


def decision(output: dict[str, Any]) -> str:
    return str(output["hookSpecificOutput"]["permissionDecision"])


@pytest.mark.parametrize(
    ("tool", "tool_input", "expected"),
    [
        ("Read", {"file_path": "src/a.py"}, None),
        ("Read", {"file_path": "AGENTS.md"}, "on the reject list"),
        ("Read", {"file_path": "/etc/passwd"}, "outside the checkout"),
        ("Read", {"file_path": "../other"}, "outside the checkout"),
        ("Read", {"file_path": ".git/config"}, "inside .git"),
        ("Glob", {"pattern": "**/*.py"}, None),
        ("Grep", {"pattern": "x", "path": "src"}, None),
        ("Edit", {"file_path": "src/a.py"}, None),
        ("Edit", {"file_path": ".github/workflows/ci.yml"}, "on the reject list"),
        ("Edit", {"file_path": "tests/conftest.py"}, "on the reject list"),
        ("Write", {"file_path": "src/new.py"}, None),
        ("Write", {}, "no path"),
        ("Bash", {"command": "uv run --no-sync pytest -q"}, None),
        ("Bash", {"command": "git push origin main"}, "command refused"),
        ("Bash", {"command": "curl https://example.com"}, "command refused"),
        ("Bash", {"command": "gh pr create"}, "command refused"),
        ("Bash", {"command": "pip install requests"}, "command refused"),
        ("Bash", {"command": "uv add anyascii"}, "command refused"),
        ("Bash", {"command": "sudo rm -rf /"}, "command refused"),
        ("Bash", {"command": "rm -rf /"}, "command refused"),
        ("Bash", {"command": "rm -rf build/"}, None),
        ("Bash", {"command": "python -c 'import socket'"}, "command refused"),
        ("Bash", {}, "no command"),
        ("WebFetch", {"url": "https://x"}, "tool not allowed for this role"),
        ("Agent", {"prompt": "x"}, "tool not allowed for this role"),
    ],
)
def test_builder_gate_reasons(
    checkout: Path, tool: str, tool_input: dict[str, Any], expected: str | None
) -> None:
    gate = agents.Gate(checkout, role="builder", reject=REJECT)
    assert gate.reason(tool, tool_input) == expected


def test_read_only_roles_cannot_write(checkout: Path) -> None:
    for role in ("planner", "reviewer"):
        gate = agents.Gate(checkout, role=role, reject=REJECT)
        assert gate.reason("Edit", {"file_path": "src/a.py"}) == "read-only role"
        assert gate.reason("Write", {"file_path": "src/b.py"}) == "read-only role"
        assert gate.reason("Read", {"file_path": "src/a.py"}) is None
    assert (
        agents.Gate(checkout, role="planner", reject=REJECT).reason(
            "Bash", {"command": "ls"}
        )
        == "tool not allowed for this role"
    )
    assert (
        agents.Gate(checkout, role="reviewer", reject=REJECT).reason(
            "Bash", {"command": "uv run --no-sync pytest"}
        )
        is None
    )


def test_symlink_out_of_the_checkout_is_outside(checkout: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (checkout / "link").symlink_to(outside)
    gate = agents.Gate(checkout, role="builder", reject=REJECT)
    assert gate.path_reason("link/secret") == "outside the checkout"


def test_hook_allows_denies_and_counts(checkout: Path) -> None:
    gate = agents.Gate(checkout, role="builder", reject=REJECT)
    assert decision(pre(gate, "Read", {"file_path": "src/a.py"})) == "allow"
    denied = pre(gate, "Edit", {"file_path": "AGENTS.md"})
    assert decision(denied) == "deny"
    assert "reject list" in denied["hookSpecificOutput"]["permissionDecisionReason"]
    assert gate.denied == ["Edit: on the reject list"]
    assert not gate.repeated


def test_the_same_call_repeated_ends_the_run(checkout: Path) -> None:
    gate = agents.Gate(checkout, role="builder", reject=REJECT)
    call = {"file_path": "src/a.py"}
    outputs = [pre(gate, "Read", call) for _ in range(agents.MAX_REPEATS)]
    assert all(decision(o) == "allow" for o in outputs[:-1])
    last = outputs[-1]
    assert decision(last) == "deny"
    assert last["continue_"] is False
    assert gate.repeated
    # A different call is still fine.
    assert decision(pre(gate, "Read", {"file_path": "src/b.py"})) == "allow"


def test_the_prompt_backstop_denies(checkout: Path) -> None:
    gate = agents.Gate(checkout, role="builder", reject=REJECT)
    result = asyncio.run(gate.can_use_tool("Bash", {"command": "ls"}, Any))  # type: ignore[arg-type]
    assert isinstance(result, PermissionResultDeny)
    assert gate.denied == ["Bash: reached the prompt"]


def stop(tests: agents.TestGate) -> dict[str, Any]:
    hook_input: Any = {"hook_event_name": "Stop", "stop_hook_active": False}
    return dict(asyncio.run(tests.stop(hook_input, None, {"signal": None})))


def test_stop_hook_blocks_while_the_tests_fail(checkout: Path) -> None:
    failing = f"{sys.executable} -c \"import sys; print('boom'); sys.exit(1)\""
    tests = agents.TestGate(checkout, failing, rounds=2)
    first = stop(tests)
    assert first["decision"] == "block"
    assert "boom" in first["reason"]
    assert tests.passed is False
    assert stop(tests)["decision"] == "block"
    # Past the rounds the agent may stop; the check fails the run instead.
    assert stop(tests) == {}
    assert tests.blocked == 3


def test_stop_hook_lets_a_green_suite_stop(checkout: Path) -> None:
    passing = f"{sys.executable} -c \"print('ok')\""
    tests = agents.TestGate(checkout, passing, rounds=2)
    assert stop(tests) == {}
    assert tests.passed is True
    assert tests.blocked == 0


def test_stop_hook_output_is_escaped_and_bounded(checkout: Path) -> None:
    script = "import sys; print(chr(0x430) * 10000); sys.exit(1)"
    tests = agents.TestGate(checkout, f'{sys.executable} -c "{script}"', rounds=1)
    reason = stop(tests)["reason"]
    assert reason.isascii()
    assert "U+0430" in reason
    assert len(reason) < agents.OUTPUT_TAIL + 300


def test_missing_test_command_fails_closed(checkout: Path) -> None:
    tests = agents.TestGate(checkout, "/no/such/command", rounds=1)
    passed, tail = tests.run()
    assert passed is False
    assert "could not run" in tail


def test_options_give_the_sdk_nothing_from_disk(checkout: Path, tmp_path: Path) -> None:
    gate = agents.Gate(checkout, role="builder", reject=REJECT)
    tests = agents.TestGate(checkout, "true", rounds=1)
    opts = agents.options(
        root=checkout,
        config_dir=tmp_path / "cfg",
        system_prompt="be good",
        role="builder",
        model="claude-opus-5-5",
        max_turns=10,
        cap_usd=4.0,
        effort="high",
        gate=gate,
        tests=tests,
    )
    assert opts.setting_sources == []
    assert opts.skills == []
    assert opts.strict_mcp_config is True
    assert opts.mcp_servers == {}
    assert opts.tools == ["Read", "Glob", "Grep", "Edit", "Write", "Bash"]
    assert "WebFetch" in opts.disallowed_tools
    assert opts.allowed_tools == []
    assert opts.permission_mode == "default"
    assert opts.can_use_tool == gate.can_use_tool
    assert opts.verbatim_prompts is True
    assert opts.max_turns == 10
    assert opts.max_budget_usd == 4.0
    assert opts.effort == "high"
    assert opts.model == "claude-opus-5-5"
    assert opts.cwd == checkout
    assert opts.env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "cfg")
    assert opts.env["DISABLE_TELEMETRY"] == "1"
    assert opts.hooks is not None
    assert set(opts.hooks) == {"PreToolUse", "Stop"}
    assert opts.hooks["Stop"][0].timeout == tests.timeout + 60
    assert opts.output_format is None
    with pytest.raises(ValueError, match="effort"):
        agents.options(
            root=checkout,
            config_dir=tmp_path,
            system_prompt="x",
            role="planner",
            model="m",
            max_turns=1,
            cap_usd=1.0,
            effort="extreme",
            gate=gate,
        )


def test_reader_roles_have_no_stop_hook(checkout: Path, tmp_path: Path) -> None:
    gate = agents.Gate(checkout, role="reviewer", reject=REJECT)
    opts = agents.options(
        root=checkout,
        config_dir=tmp_path,
        system_prompt="x",
        role="reviewer",
        model="m",
        max_turns=1,
        cap_usd=1.0,
        effort="low",
        gate=gate,
        output_format={"type": "json_schema", "schema": {"type": "object"}},
    )
    assert opts.hooks is not None
    assert set(opts.hooks) == {"PreToolUse"}
    assert opts.tools == ["Read", "Glob", "Grep", "Bash"]
    assert opts.output_format == {"type": "json_schema", "schema": {"type": "object"}}


def result(**overrides: Any) -> ResultMessage:
    base: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 12_000,
        "duration_api_ms": 9_000,
        "is_error": False,
        "num_turns": 3,
        "session_id": "s",
        "total_cost_usd": 0.1234567,
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_input_tokens": 3000,
            "cache_creation_input_tokens": 500,
        },
        "structured_output": {"findings": []},
    }
    base.update(overrides)
    return ResultMessage(**base)


def fake_runner(messages: list[Any]) -> agents.Runner:
    seen: dict[str, Any] = {}

    async def runner(*, prompt: str, options: Any) -> AsyncIterator[Any]:
        seen["prompt"] = prompt
        seen["options"] = options
        for message in messages:
            yield message

    runner.seen = seen  # type: ignore[attr-defined]
    return runner


def test_run_records_counts_usage_and_cost(checkout: Path, tmp_path: Path) -> None:
    gate = agents.Gate(checkout, role="builder", reject=REJECT)
    opts = agents.options(
        root=checkout,
        config_dir=tmp_path,
        system_prompt="x",
        role="builder",
        model="claude-opus-5-5",
        max_turns=5,
        cap_usd=4.0,
        effort="high",
        gate=gate,
    )
    messages = [
        AssistantMessage(
            content=[
                TextBlock(text="reading"),
                ToolUseBlock(id="1", name="Read", input={"file_path": "src/a.py"}),
                ToolUseBlock(id="2", name="Bash", input={"command": "ls"}),
            ],
            model="claude-opus-5-5",
        ),
        AssistantMessage(
            content=[ToolUseBlock(id="3", name="Read", input={"file_path": "x"})],
            model="claude-opus-5-5",
        ),
        result(),
    ]
    transcript = tmp_path / "t.jsonl"
    runner = fake_runner(messages)
    record = asyncio.run(
        agents.run(
            "the brief",
            opts,
            role="builder",
            prices=PRICES,  # type: ignore[arg-type]
            gate=gate,
            transcript=transcript,
            runner=runner,
        )
    )
    assert runner.seen["prompt"] == "the brief"  # type: ignore[attr-defined]
    assert record["subtype"] == "success"
    assert record["is_error"] is False
    assert record["num_turns"] == 3
    assert record["tool_calls"] == {"Bash": 1, "Read": 2}
    assert record["usage"] == {
        "input_tokens": 1000,
        "output_tokens": 200,
        "cache_read_tokens": 3000,
        "cache_write_tokens": 500,
    }
    # 1000*4 + 200*20 + 3000*0.2 + 500*5 = 4000+4000+600+2500 = 11100 / 1e6
    assert record["cost_usd"] == 0.0111
    assert record["reported_cost_usd"] == 0.123457
    assert record["tests_passed"] is None
    assert record["structured_output"] == {"findings": []}
    assert agents.succeeded(record)
    lines = transcript.read_text(encoding="ascii").splitlines()
    assert len(lines) == 3
    assert '"name": "Bash"' in lines[0]


def test_run_without_a_result_is_an_error(checkout: Path, tmp_path: Path) -> None:
    gate = agents.Gate(checkout, role="reviewer", reject=REJECT)
    opts = agents.options(
        root=checkout,
        config_dir=tmp_path,
        system_prompt="x",
        role="reviewer",
        model="m",
        max_turns=1,
        cap_usd=1.0,
        effort="low",
        gate=gate,
    )
    record = asyncio.run(
        agents.run(
            "p",
            opts,
            role="reviewer",
            prices=PRICES,  # type: ignore[arg-type]
            gate=gate,
            runner=fake_runner([]),
        )
    )
    assert record["subtype"] == "no_result"
    assert record["is_error"] is True
    assert record["cost_usd"] == 0.0
    assert not agents.succeeded(record)


def test_succeeded_needs_a_clean_end_and_green_tests(
    checkout: Path, tmp_path: Path
) -> None:
    gate = agents.Gate(checkout, role="builder", reject=REJECT)
    opts = agents.options(
        root=checkout,
        config_dir=tmp_path,
        system_prompt="x",
        role="builder",
        model="m",
        max_turns=1,
        cap_usd=1.0,
        effort="low",
        gate=gate,
    )

    def run_with(
        message: ResultMessage, tests: agents.TestGate | None = None
    ) -> agents.Run:
        return asyncio.run(
            agents.run(
                "p",
                opts,
                role="builder",
                prices=PRICES,  # type: ignore[arg-type]
                gate=gate,
                tests=tests,
                runner=fake_runner([message]),
            )
        )

    assert not agents.succeeded(
        run_with(result(subtype="error_max_turns", is_error=True))
    )
    failing = agents.TestGate(
        checkout, f"{sys.executable} -c 'raise SystemExit(1)'", rounds=1
    )
    stop(failing)
    record = run_with(result(), failing)
    assert record["tests_passed"] is False
    assert record["test_rounds_blocked"] == 1
    assert not agents.succeeded(record)
    gate.repeated = True
    assert not agents.succeeded(run_with(result()))
