"""Hand-off check: whether a Builder's session resumes on another host.

Two phases, run by two dispatches of the Drills workflow (suite `handoff`).

`first` runs one real build trial of a drill, set up as `drills.run_build`
sets it up, and keeps what a hand-off needs: the session files the SDK wrote
under the run's config directory, the working tree's diff and the session ID.

`resume` runs on a fresh runner: the same base, seed and setup, the first
phase's diff applied, the session files restored into a new config
directory, and the same options plus `resume`. The prompt is a steward's
comment asking for one more line. Pass: the run keeps the session ID, the
Builder names the files it changed before it uses any tool, the new line is
in the working tree, and the run ends well with the tests passing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from guildkit import agents, brief, builder, config, drills

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

MARK = "Hand-off probe: resumed on a second runner."
COMMENT = (
    "A steward read your change and commented on the pull request:\n\n"
    "Please add one comment line directly above the test you added. It must"
    f" read exactly: # {MARK}\n\n"
    "Before you use any tool, say from memory which files you changed in this"
    " session and the name of the test you added. Then make the edit and run"
    " the test command the brief names."
)


class Recorder:
    """The SDK's `query`, noting what the Builder said before its first tool."""

    def __init__(self) -> None:
        """Start with nothing seen."""
        self.before_tools: list[str] = []
        self.tool_seen = False
        self.session_id: str | None = None

    async def __call__(self, *, prompt: Any, options: Any) -> AsyncIterator[Any]:
        """Yield the run's messages unchanged."""
        async for message in query(prompt=prompt, options=options):
            own = getattr(message, "parent_tool_use_id", None) is None
            if own and isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        self.tool_seen = True
                    elif isinstance(block, TextBlock) and not self.tool_seen:
                        self.before_tools.append(block.text)
            elif isinstance(message, ResultMessage):
                self.session_id = message.session_id
            yield message


def prepare(args: argparse.Namespace) -> tuple[Any, str, Path, Path]:
    """Return the options, the brief's prompt, the checkout and the config dir."""
    cfg = config.load(args.config)
    drill = next(d for d in drills.load(args.dir, "build") if d["name"] == args.drill)
    inp = drill["input"]
    work = args.work / "checkout"
    config_dir = args.work / "cfg"
    if args.work.exists():
        shutil.rmtree(args.work)
    args.work.mkdir(parents=True)
    seed = Path(drill["directory"]) / inp["seed"] if "seed" in inp else None
    drills.prepare_checkout(args.source, inp["base"], work, seed=seed)
    if "setup" in inp:
        subprocess.run(shlex.split(inp["setup"]), cwd=work, check=True)
    system, user = builder.prompt(
        role=(args.roles / "builder.md").read_text(encoding="ascii"),
        handbook=(work / "AGENTS.md").read_text(encoding="utf-8"),
        charter=(work / cfg["charter"]).read_text(encoding="utf-8"),
        brief=brief.render(drills._drill_brief(drill)),
    )
    agent = cfg["agents"]["builder"]
    gate = agents.Gate(work, role="builder", reject=cfg["paths"]["reject"])
    tests = agents.TestGate(
        work, cfg["build"]["test_command"], rounds=cfg["build"]["max_test_rounds"]
    )
    config_dir.mkdir()
    options = agents.options(
        root=work,
        config_dir=config_dir,
        system_prompt=system,
        role="builder",
        model=agent["model"],
        max_turns=agent["max_turns"],
        cap_usd=agent["cap_usd"],
        effort=agent["effort"],
        gate=gate,
        tests=tests,
    )
    args.gate, args.tests, args.prices = gate, tests, cfg["prices"][agent["model"]]
    return options, user, work, config_dir


def run(args: argparse.Namespace, prompt: str, options: Any, name: str) -> Any:
    """Run the Builder once and return the record and the recorder."""
    recorder = Recorder()
    record = asyncio.run(
        agents.run(
            prompt,
            options,
            role="builder",
            prices=args.prices,
            gate=args.gate,
            tests=args.tests,
            transcript=args.out / f"{name}.transcript.jsonl",
            runner=recorder,
        )
    )
    usage = record["usage"]
    print(
        f"{name}: subtype={record['subtype']} turns={record['num_turns']}"
        f" cost_usd={record['cost_usd']} tests_passed={record['tests_passed']}"
        f" denials={record['denials']} tools={dict(record['tool_calls'])}"
    )
    print(f"{name}: usage={json.dumps(usage, sort_keys=True)}")
    return record, recorder


def ended_well(record: Any) -> bool:
    """Return whether the run succeeded with the tests not failing."""
    return (
        record["subtype"] == "success"
        and not record["is_error"]
        and record["tests_passed"] is not False
    )


def changed(work: Path) -> list[str]:
    """Return the paths the working tree changes against the seeded base."""
    drills.working_diff(work)
    return drills.git("diff", "--cached", "--name-only", "HEAD", cwd=work).split()


def first(args: argparse.Namespace) -> int:
    """Run the trial and keep the session files, the diff and the ID."""
    options, user, work, config_dir = prepare(args)
    record, recorder = run(args, user, options, "first")
    projects = config_dir / "projects"
    kept = sorted(p for p in projects.rglob("*") if p.is_file())
    for path in kept:
        print(f"session file: {path.relative_to(config_dir)} {path.stat().st_size} B")
    if kept:
        shutil.copytree(projects, args.out / "projects")
    (args.out / "patch.diff").write_text(drills.working_diff(work), encoding="utf-8")
    files = changed(work)
    state = {"session_id": recorder.session_id, "cwd": str(work), "files": files}
    (args.out / "first.json").write_text(json.dumps(state, indent=2) + "\n")
    print(f"session_id={recorder.session_id} cwd={work} files={files}")
    checks = {
        "the run ended well": ended_well(record),
        "the SDK wrote a session file named by the ID": any(
            p.name == f"{recorder.session_id}.jsonl" for p in kept
        ),
        "the Builder changed something": bool(files),
    }
    return report(checks)


def resume(args: argparse.Namespace) -> int:
    """Restore the first phase's state on this host and resume its session."""
    state = json.loads((args.inp / "first.json").read_text())
    options, _, work, config_dir = prepare(args)
    print(f"first cwd={state['cwd']} this cwd={work}")
    patch = (args.inp / "patch.diff").resolve()
    drills.git("apply", str(patch), cwd=work)
    shutil.copytree(args.inp / "projects", config_dir / "projects")
    options.resume = state["session_id"]
    record, recorder = run(args, COMMENT, options, "resume")
    said = "\n".join(recorder.before_tools)
    print("before any tool, the Builder said:")
    print(said.encode("ascii", "backslashreplace").decode("ascii"))
    added = [
        line
        for line in drills.working_diff(work).splitlines()
        if line.startswith("+") and MARK in line
    ]
    checks = {
        "the run ended well": ended_well(record),
        "the session ID is the first run's": recorder.session_id == state["session_id"],
        "the Builder named its files from memory": bool(said)
        and all(Path(name).name in said for name in state["files"]),
        "the steward's line is in the working tree": len(added) == 1,
    }
    return report(checks)


def report(checks: dict[str, bool]) -> int:
    """Print each check and return 0 when all passed."""
    for name, passed in checks.items():
        print(f"check {name}: {'ok' if passed else 'FAIL'}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    """Parse the phase and its paths, and run it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("first", "resume"))
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--drill", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--roles", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--in", dest="inp", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    return first(args) if args.phase == "first" else resume(args)


if __name__ == "__main__":
    sys.exit(main())
