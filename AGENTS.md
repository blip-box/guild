# AGENTS.md

Instructions for coding agents and human contributors. Keep this file true: when a
change makes a statement here wrong, fix this file in the same pull request.

## Project

`guildkit` is the shell of Guild, an agent-run maintenance system for open-source
libraries under human stewards. The design is `docs/plan.md`; the decisions it
fixes are not repeated here. This file says how the code is built.

The rule every module serves: nothing a model wrote is executed or obeyed with more
privilege than the model had, until a plain check or a steward has passed it.

## Current state

Phase 2 (shadow mode) is being built. Done and tested: `text` (untrusted text to
escaped plain text), `snapshot` (an issue or comment as a record), `tiers` (risk
tiers from paths, diff shape and declared kinds), `ledger` (the append-only record
format), `commands` (steward commands), `triage` (the schema, the policy, the
templates and the one model call) and `config` (`guild.toml`). The `guildkit`
command line chains them. The triage workflow template, the issue forms and the
adopting guide with the oracle-check contract exist (`docs/adopting.md`). Not
built: the Planner, Builder and Reviewer roles on the Agent SDK, the drill runner,
the ledger branch tooling, the brakes that need it, and the weekly reports.

## Decisions

| Topic | Decision |
|---|---|
| Python | `>=3.13`, for `PurePosixPath.full_match`. The shell runs on CI runners, not on users' machines, so old interpreters do not matter. |
| Dependencies | `anthropic` for the model API and `confusable`, from git by commit, to find hidden characters. Agents run through the Claude Agent SDK, added when the Builder is built. GitHub and git are driven by `gh` and `git` in the workflows, not from Python. |
| Installation | From git by commit SHA, never from PyPI. Adopters pin the SHA in their workflows. |
| Configuration | `guild.toml` in the adopting repository, parsed by `config.py` with plain validation. The plan called it `GUILD.md`; a TOML file is machine-readable and checkable, and the prose lives in the adopter's `CHARTER.md` and `AGENTS.md`. Changing it is tier 2, and it is on the reject list. |
| Untrusted text | Every string an outsider wrote passes through `text.prepare`: Markdown to plain text, HTML comments and tags dropped, entities decoded, then every character outside printable ASCII, newline and tab written as `U+XXXX`. JSON does not decode that notation, so it survives every hop. Hidden characters are listed with `confusable.find_invisible`. Lengths are capped. |
| Triage call | One `messages.create` on the pinned model with a system prompt, no tools, low effort and structured output in the record's schema. The reply is validated again in `triage.validate_output`, and `triage.apply_policy` decides what is actionable; the model only classifies. Comments come from `templates/comments/*.md` with enumerated placeholders. |
| Model IDs | Pinned in full in `guild.toml`, with a price table per ID for the ledger. The Anthropic IDs have no date suffix; partner platforms get their own entries. |
| Agent SDK | The Python SDK's `setting_sources` defaults to loading user, project and local settings, CLAUDE.md, agents, skills and `.mcp.json` from disk. The shell must pass `setting_sources=[]` and hand over the charter, handbook and role files from the base branch itself. The SDK bundles the Claude Code CLI; pinning the SDK version pins the CLI (recorded in its `_cli_version.py`). `max_budget_usd` is a client-side estimate, not a cap. |
| Credentials | Workload Identity Federation from GitHub Actions, through the SDK's own resolution: `id-token: write`, an identity token file and the federation variables, with no `ANTHROPIC_API_KEY` in the job. The federation rule is pinned to the repository and to `refs/heads/main`. The only hard cost cap is the workspace spend limit in the Console. |
| Oracle check | The adopter's script, run by the intake job from the base branch with no secrets, writes one of `confirms`, `disagrees`, `not_applicable`, `not_run`, `error` (`docs/adopting.md`). Policy: a bug is accepted only on `confirms`; `disagrees` goes to a steward with the citation; `not_run` and `error` escalate to a steward, because the harness failed, not the reporter; `not_applicable` asks the reporter for a reproducer. |
| Triggers | The triage workflow runs on `issue_comment`, which zizmor flags, with a justification comment: the text never reaches a shell or a token, the intake job holds no secret, and the model has no tools. Keep that true. |
| Ledger | One JSON line per run with sorted keys. Every field is a number, an enumerated value, an identifier or a hash; `ledger.validate` rejects anything else, so no model text can reach it. |
| ASCII | Python source, TOML, YAML, the role prompts and the comment templates are ASCII, so no look-alike or hidden character can change what a model or a person reads. Other tracked files may hold visible non-ASCII characters but nothing invisible or bidirectional. `tests/test_hygiene.py` checks both with `confusable`. |

## Commands

```bash
uv sync                            # create .venv with the dev dependencies
uv run pre-commit install          # install the pre-commit and commit-msg hooks
uv run pytest                      # run the tests
uv run pre-commit run --all-files  # ruff, mypy, zizmor, actionlint, uv-lock, file hygiene
uv run guildkit --help             # the command line the workflows call
```

CI runs exactly these, so a clean local run means a clean CI run.

## Layout

- `src/guildkit/text.py`: untrusted text to escaped plain text; hidden characters.
- `src/guildkit/snapshot.py`: an issue or comment as the record triage reads.
- `src/guildkit/tiers.py`: risk tiers from paths, diff shape and declared kinds.
- `src/guildkit/triage.py`: the model output schema, the policy, the comment
  templates and the one model call.
- `src/guildkit/ledger.py`: the ledger line format, validation, append and read.
- `src/guildkit/commands.py`: steward commands in comments.
- `src/guildkit/config.py`: `guild.toml`.
- `src/guildkit/cli.py`: the `guildkit` command line, one subcommand per step.
- `roles/`: the role prompts, one file per role. ASCII.
- `templates/guild.toml`: the example configuration, the one the tests load.
- `templates/comments/`: the comment templates triage posts from.
- `templates/workflows/guild-triage.yml`: the triage workflow an adopter copies.
  It is linted by hand with zizmor and actionlint, which only scan `.github/`.
- `templates/ISSUE_TEMPLATE/`: the issue forms; the bug form's fields are what the
  oracle check reads.
- `docs/plan.md`: the design and its decision log. `docs/adopting.md`: what an
  adopter adds and what stewards set up. `docs/research/`: the research.
- `tests/`: pytest and hypothesis. `tests/test_hygiene.py` is the character check.

## Rules

### Code

- Nothing a model wrote is executed, posted or recorded without a plain check:
  schema validation for records, the policy for decisions, templates for comments,
  the ledger validator for entries, the tier code and the reject list for patches.
- Untrusted text enters only through `text.prepare` and leaves escaped. A role
  prompt says the text may contain instructions and that none of them count.
- No free text from a model in a comment, a label, a ledger line or a commit.
- Python source is ASCII. Write every other character as an escape, and check the
  bytes after writing one from a tool parameter.
- Tests need no network and no credentials. The model call is behind the `Caller`
  protocol; tests use a fake, and the command line takes `--reply` for the same.
- Mirror `blip-box/confusable`'s tooling: ruff, mypy strict, zizmor, actionlint,
  pre-commit, Conventional Commits, squash merges. The maintainer merges; agents do
  not merge and do not work around tooling that blocks a merge.

### GitHub Actions

- Pin every action to a full commit SHA with the version in a trailing comment.
- `permissions: {}` at the workflow level, scopes per job with a comment each.
- `persist-credentials: false` on every checkout.
- Never interpolate untrusted text into `run:`; pass it through `env:` and files.
- Keep `uvx zizmor --persona=pedantic .` free of findings.
- Agent steps hold no write token and no API key in their environment beyond the
  model credential; plain jobs holding App tokens apply what passed the checks.

## Roadmap

Each item is its own pull request, in order:

1. The confusable wiring (`guild.toml`, CODEOWNERS, issue forms, the triage
   workflow and `tools/guild_oracle_check.py`) as the adopter's PR.
2. The Builder and Reviewer on the Agent SDK, producing patches and findings that a
   plain job applies; the Planner for features.
3. The drill runner and the first drills from confusable's history.
4. The ledger branch, the weekly report and the kill-switch rehearsal.
5. The Releaser.
