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
templates and the one model call), `config` (`guild.toml`), `agents` (the Agent
SDK driver with its hooks), `brief` (what the Builder reads), `builder` (the plain
check on a patch), `planner` and `reviewer` (their schemas, validation and
prompts). The `guildkit` command line chains them. The triage and build workflow
templates, the issue forms and the adopting guide exist (`docs/adopting.md`),
and so do `drills` (the runner, the graders and the scores) with the first
drills for confusable under `drills/confusable/` and the `Drills` workflow, and
the ledger's brakes, commit input and weekly report with the batch and report
workflow templates, the rubric grader (`grader`) as the build drills' second
judge, the weekly `Canary` workflow, the Builder's second attempt on an
escalated setting, and the Releaser with its workflow template. Nothing has
run against a live repository yet, and no drill has run with a model. Not
built: egress filtering of the agent jobs.

## Decisions

| Topic | Decision |
|---|---|
| Python | `>=3.13`, for `PurePosixPath.full_match`. The shell runs on CI runners, not on users' machines, so old interpreters do not matter. |
| Dependencies | `anthropic` for the model API and `confusable`, from git by commit, to find hidden characters. `claude-agent-sdk` in the `agents` extra only, pinned exactly, because its wheel carries the Claude Code CLI and the triage jobs do not need it; `roles.py` holds what `config` and `cli` need without it. GitHub and git are driven by `gh` and `git` in the workflows, not from Python, with two exceptions that hold no token: the Builder's Stop hook runs the adopter's test command, and the drill runner prepares its checkouts with `git`. |
| Installation | From git by commit SHA, never from PyPI. Adopters pin the SHA in their workflows. |
| Configuration | `guild.toml` in the adopting repository, parsed by `config.py` with plain validation. The plan called it `GUILD.md`; a TOML file is machine-readable and checkable, and the prose lives in the adopter's `CHARTER.md` and `AGENTS.md`. Changing it is tier 2, and it is on the reject list. |
| Untrusted text | Every string an outsider wrote passes through `text.prepare`: Markdown to plain text, HTML comments and tags dropped, entities decoded, then every character outside printable ASCII, newline and tab written as `U+XXXX`. JSON does not decode that notation, so it survives every hop. Hidden characters are listed with `confusable.find_invisible`. Lengths are capped. |
| Triage call | One `messages.create` on the pinned model with a system prompt, no tools, low effort and structured output in the record's schema. The reply is validated again in `triage.validate_output`, and `triage.apply_policy` decides what is actionable; the model only classifies. Comments come from `templates/comments/*.md` with enumerated placeholders. |
| Model IDs | Pinned in full in `guild.toml`, with a price table per ID for the ledger. The Anthropic IDs have no date suffix; partner platforms get their own entries. |
| Agent SDK | `claude-agent-sdk` 0.2.176, which bundles Claude Code 2.1.316 (`_cli_version.py`); `tests/test_package.py` checks the pin and this sentence agree. `agents.options` gives the SDK nothing from disk: `setting_sources=[]` (the default loads user, project and local settings, CLAUDE.md, agents, skills and `.mcp.json`), `skills=[]`, `strict_mcp_config=True` with no servers, a fresh `CLAUDE_CONFIG_DIR` per run, telemetry and the updater off, and `verbatim_prompts=True` so nothing in the brief expands a path or runs a command. The role prompt, handbook and charter are read from the base branch and passed as the system prompt. `tools` is a list per role; `disallowed_tools` names the web, subagents and skills as well. Every call goes through `agents.Gate.pre_tool_use`, a PreToolUse hook, and `Gate.can_use_tool` denies anything that reaches the permission prompt; the one call the gate always lets through is the SDK's `StructuredOutput` tool, which carries the structured answer and writes nothing. The Builder's Stop hook (`agents.TestGate`) runs the test command and blocks the stop while it fails, `max_test_rounds` times. `max_budget_usd` is the SDK's estimate and a brake; the ledger prices the tokens from `guild.toml`. The run record (`agents.Run`) holds counts and enumerations; the transcript is a separate artifact. |
| Agent roles | The Planner reads the feature form's fields (`planner.request`), the handbook, the charter and the repository, read-only, and returns structured output that `planner.validate_output` checks: a plan with checkable acceptance criteria, a request for clarification, or out of scope. The Builder reads a brief (`brief.from_triage`): the triage record, the bug form's structured fields cut to `FIELD_LIMIT`, or the approved plan; never the issue body, a comment or the web. The Reviewer runs on a fresh runner with the patch applied; `reviewer.prompt` takes five texts and nothing else, and a test plants a canary everywhere else to prove it. Its findings are validated again, and the verdict is computed in code: a verified finding is an objection, an unverified one a note. In shadow mode the Planner and the Builder start on a steward's `/guild plan` or `/guild build`, checked against `guild.toml` and live permissions, not on triage's acceptance. |
| Second attempt | A task gets at most two Builder attempts. When the plain check refuses the first and `guild.toml` has `[builder.second_attempt]` (a model, turns, cap and effort of its own; the template escalates effort, the strongest model being the first choice), `check` says so (`escalate`) and the `build-2` job runs the Builder again in a fresh checkout at the same base with `--second-attempt`: the same brief, then what the check and the first run reported in code's words (`builder.previous_attempt`), never the first patch or the agent's account. `check-2` grades it; the attempt that passed is reviewed and opened. Both fail: the `build_escalated` comment, the `needs steward` label, and the run marked failed. Ledger entries carry `attempt`, and the weekly report counts second attempts. In shadow mode the Reviewer's objections do not start a second attempt, because the verdict is not a gate; the drills run one attempt. |
| Releaser | A script, no model call: the plan gave it one bounded call for the release notes, but the change list is the merged pull request titles, which a steward wrote or approved and CI linted as Conventional Commits, the credits come from the ledger, and the version follows from the commit types, so a model would add phrasing and nothing else. `guild-release.yml` runs on every push to the default branch and weekly: the workflow writes `git log` since the last `v*` tag to a file, runs the adopter's test command, and `guildkit release` (`releaser.py`) decides whether a release is due (`[release]` in `guild.toml`: a `fix`, `feat` or breaking change touching `library` paths, or the oldest unreleased change older than `stale_days`), the version (`prerelease` keeps proposals in a pre-release series; pre-1.0 a breaking change bumps the minor), the change list, and the credits (authors of issues a released commit names whose Builder entry says `patched`). Due: the Triage App opens or rewrites the one open issue labelled `guild:release`, from `templates/release/`, with the steward's checklist and the earliest date the 72-hour notice allows; a `releaser` entry goes to the ledger. Not due: exit 4, nothing posted. The release itself, the version bump, the tag and publishing, is a steward's (tier 3). |
| Patch check | `builder.check_patch` reads the diff the workflow took against the base commit and refuses a patch that touches the reject list, removes a test function, adds a skip or an xfail, or changes a generated file without its generator (`[builder] generated` and `generators`); the rest is tiered by `tiers`. The Builder's own account of its work is not consulted. |
| Pull requests | The `open` job applies the patch and commits it through GitHub's `createCommitOnBranch` with the Builder App's token, so GitHub signs the commit as the App; `guildkit commit-input` builds the mutation's input. Title, body and commit message come from `templates/pr/` with enumerated placeholders; the message carries an `Assisted-by` trailer naming the model. The pull request is a draft, labelled `guild:<tier>`. The Gate App posts the Reviewer's verdict as the check run `guild/review`. Model text reaches stewards only in step summaries, check-run text and artifacts, escaped to ASCII and cut; comments, labels, titles and commit messages stay templated. |
| Drills | A drill is a TOML file under `drills/<repository>/<suite>/` (`drills.parse`): the inputs a role gets and the right outcome, with non-ASCII as TOML escapes so the file stays ASCII. Triage drills feed an issue to the triage call and grade the record's enumerations; review drills apply a patch at a base commit and grade the verdict and the file of a verified finding; build drills give the Builder a brief at a base commit, with a seed diff committed on top or a replayed history, and grade the diff with the plain check, the tier and a test command, with grading tests copied from a later commit only after the Builder is done. `drills.prepare_checkout` clones, detaches at the base, deletes every ref and the remote and prunes, so nothing after the base is reachable. Scores (`drills.score`) give pass@1 and pass^k per suite and for the fresh bucket of drills created on or after a cutoff, the candidate model's; `drills.compare` blocks a change only on a drop larger than the noise, and the `Drills` workflow compares with a committed `baseline-<suite>.json` when one exists. Seeded defects count as fresh; replayed public fixes do not decide. Every trial gets a fresh checkout. Base commits are written in full and checked by `parse`. |
| Rubric grader | A build drill may carry `[[rubric]]` tables: what a maintainer checks before accepting the patch, beyond the tests. When the plain check and the grading tests pass, the grader (`grader.py`, `roles/grader.md`) reads the brief, the rubric, the diff and the checkout and answers each criterion `met`, `not_met` or `unknown` as structured output, validated again in code. Only `not_met` fails the trial; `unknown` is a legitimate answer that leaves the tests deciding, and the score counts the undecided trials so a grader that abstains too often shows. It runs with the Reviewer's tools and, unless `guild.toml` has a `[grader]` table, the Reviewer's settings; its cost is added to the trial's. |
| Canary | `.github/workflows/canary.yml` runs five drills at one trial every Tuesday (three triage, the seeded review and the seeded build drill) against the pinned models, SDK, CLI and role prompts, and opens or comments on the issue "The weekly canary is failing" when any fails. The `scheduled` job in `ci.yml` fails while GitHub has disabled it; `GUILD_PAUSED` on this repository pauses it. `docs/operations.md` says what to check. |
| Plans | A plan is a run artifact named `plan-<issue number>`, kept 90 days; the build job fetches the latest one for a feature through the Actions API. The issue gets a templated comment pointing at the run. |
| Credentials | Workload Identity Federation from GitHub Actions, through the SDK's own resolution: `id-token: write`, an identity token file and the federation variables, with no `ANTHROPIC_API_KEY` in the job. The federation rule is pinned to the repository and to `refs/heads/main`, with GitHub's immutable subject prefix (`repo:ORG@ORGID/REPO@REPOID`), and allows every event, since nothing Guild does runs on push; `docs/adopting.md` step 3 has the details. The only hard cost cap is the workspace spend limit in the Console. |
| Oracle check | The adopter's script, run by the intake job from the base branch with no secrets, writes one of `confirms`, `disagrees`, `not_applicable`, `not_run`, `error` (`docs/adopting.md`). Policy: a bug is accepted only on `confirms`; `disagrees` goes to a steward with the citation; `not_run` and `error` escalate to a steward, because the harness failed, not the reporter; `not_applicable` asks the reporter for a reproducer. |
| Triggers | The triage and build workflows run on `issue_comment`, which zizmor flags, with a justification comment: the text never reaches a shell or a token, the intake job holds no secret, the triage model has no tools, and the agents never see the comment. Keep that true. |
| Ledger | One JSON line per run with sorted keys. Every field is a number, an enumerated value, an identifier or a hash; `ledger.validate` rejects anything else, so no model text can reach it. It lives as `ledger.jsonl` on the adopter's `guild-ledger` branch, appended by the `ledger` job that ends every workflow: the job downloads the run's `entry-*` artifacts, builds one `createCommitOnBranch` input with `guildkit ledger-input` and sends it with the Builder App's token, so the commit is signed and names the head it expects; a concurrent append makes it rebuild from the new head, five times. Without the branch the job warns and the entries stay in the artifacts. The weekly report audits that no commit removed a line. Entries carry the issue author's login, so the brakes can count by author. |
| Brakes | `ledger.brake` counts the day's triage entries, the author's against `per_author_per_day` and all against `daily_runs`, skipped ones included. The intake job queues an issue that hits a limit: label `guild:queued`, the `queued` comment, a `skipped` entry. `guild-batch.yml` dispatches `guild-triage.yml` for queued issues twice a day through its `workflow_dispatch` trigger, which reads the issue through the API; the brakes apply again, so a flood drains at the day's limit. |
| Reports | `guild-report.yml` runs weekly: fetches the ledger branch, fails if any commit removed a line, counts the week with `ledger.report` and comments the Markdown on the "Guild weekly report" issue through the Triage App. The two scheduled templates open an issue when they fail and must be listed in the adopter's `scheduled` CI job. `docs/operations.md` has the kill-switch rehearsal. |
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
- `src/guildkit/roles.py`: the role names and effort levels, without the SDK.
- `src/guildkit/agents.py`: the Agent SDK driver: options, the gate and the test
  hooks, one run, the run record.
- `src/guildkit/brief.py`: the brief the Builder and the Reviewer read.
- `src/guildkit/builder.py`: the plain check on the Builder's diff.
- `src/guildkit/planner.py`: the Planner's request, schema and validation.
- `src/guildkit/reviewer.py`: the Reviewer's prompt, schema, validation and verdict.
- `src/guildkit/grader.py`: the rubric grader's prompt, schema, validation and
  verdict, for the build drills.
- `src/guildkit/releaser.py`: the Releaser: the unreleased commits, when a
  release is due, the version, the change list, the credits, the proposal.
- `src/guildkit/drills.py`: the drill files, the graders, the stripped
  checkouts, the runs and the scores.
- `src/guildkit/cli.py`: the `guildkit` command line, one subcommand per step.
- `drills/confusable/`: the drills for confusable, by suite, with their diffs.
- `roles/`: the role prompts, one file per role. ASCII.
- `templates/guild.toml`: the example configuration, the one the tests load.
- `templates/comments/`: the comment templates triage posts from.
- `templates/workflows/guild-triage.yml`, `guild-build.yml`, `guild-batch.yml`,
  `guild-report.yml` and `guild-release.yml`: the workflows an adopter copies. They are linted by
  hand with zizmor and actionlint, which only scan `.github/`;
  `tests/test_templates.py` checks the kill switch, the pins and the
  placeholders.
- `templates/pr/`: the pull request body and the commit message.
- `templates/release/`: the release proposal's title and body.
- `templates/ISSUE_TEMPLATE/`: the issue forms; the bug form's fields are what the
  oracle check reads.
- `docs/plan.md`: the design and its decision log. `docs/adopting.md`: what an
  adopter adds and what stewards set up. `docs/operations.md`: the kill switch
  and its rehearsal, the brakes, the ledger. `docs/research/`: the research.
- `.github/workflows/drills.yml`: runs a suite of drills against confusable by
  hand and scores it, with the model credential this repository holds.
  `.github/workflows/canary.yml`: the weekly canary, five drills at one trial,
  with an issue on failure; `ci.yml`'s `scheduled` job fails while it is
  disabled. `.github/workflows/dependabot-auto-merge.yml`: auto-merge for
  Dependabot's non-major updates, except Anthropic or Claude tooling, which a
  human reviews. Branch protection on `main` requires only `ci.yml`'s
  `required` job, so the jobs can change without touching repository settings.
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
  protocol and the agents behind `agents.Runner`; tests use fakes, the command
  line takes `--reply` for triage and `cli.RUNNER` for the agents.
- Mirror `blip-box/confusable`'s tooling: ruff, mypy strict, zizmor, actionlint,
  pre-commit, Conventional Commits, squash merges. The maintainer merges; agents do
  not merge and do not work around tooling that blocks a merge. Dependabot's
  non-major updates merge on green CI, except the Agent SDK, the CLI and any
  other Anthropic or Claude tooling, which a human reviews first. Keep
  Dependabot security updates off while that runs: they skip the cooldown, so
  a just-published release would merge on CI alone.

### GitHub Actions

- Pin every action to a full commit SHA with the version in a trailing comment.
- `permissions: {}` at the workflow level, scopes per job with a comment each.
- `persist-credentials: false` on every checkout.
- Never interpolate untrusted text into `run:`; pass it through `env:` and files.
- Keep `uvx zizmor --persona=pedantic .` free of findings.
- Agent steps hold no write token and no API key in their environment beyond the
  model credential; plain jobs holding App tokens apply what passed the checks.
- Do not add a scheduled workflow unless failures reach a human, by opening or
  commenting on an issue. Add every scheduled workflow to the `scheduled` job in
  `ci.yml`, which fails while GitHub has disabled one, and give its first job
  the `GUILD_PAUSED` check; `tests/test_templates.py` checks both.

## Roadmap

From the first shadow runs (2026-11-08): two of the canary's three triage
drills fail against `claude-haiku-5-5`. `bug-confirmed-paypal` is answered
`needs_info` instead of `bug_accepted`, and `injection-in-a-bug-report` is
classed `other` rather than `bug` and sent to a steward. Decide whether the
triage role prompt or the drills' expectations move, then make the canary
green. One gap stays open: egress filtering of the agent jobs, for which
GitHub offers no first-party mechanism yet.

Done: the shell, the triage workflow template, the issue forms, the adopting
guide, the confusable wiring (`guild.toml`, CODEOWNERS, issue forms, the
triage workflow and `tools/guild_oracle_check.py`; confusable PR #27), and the
Planner, Builder and Reviewer on the Agent SDK with the build workflow template,
the drill runner with the first drills (nine triage, two review, one build),
the ledger branch tooling with the brakes, the batch, the weekly report and
the kill-switch rehearsal (`docs/operations.md`), the rubric grader with the
weekly canary, the second Builder attempt, and the Releaser.
