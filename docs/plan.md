# Guild: the plan

Agent-run maintenance for open-source libraries, proven on `blip-box/confusable`.

Status: decisions final as of 2026-10-27, after four rounds of questions (Q1-Q49),
a research pass against 2025-2026 practice (`research/`) and a final review
that amended twelve decisions. Phase 0 (baseline) and phase 1 (the charter,
ratified 2026-10-30 as confusable PR #26) are done; phase 2 is being built.
Section 12 records what was verified on 2026-10-30 and what it changed.

## 1. What Guild is

Guild runs the routine maintenance of a library with agents, under a small
number of human stewards who own direction and accept risk. Outside
contributors take part through issues and comments. Agents triage, plan, build,
review and propose releases; stewards approve every code change and run every
release.

The one rule every other control serves:

> Nothing a model wrote is executed or obeyed with more privilege than the
> model had, until a plain check or a steward has passed it.

Every role and gate records the assumption it encodes and the drill that would
show it is no longer needed, so the harness can shrink as models improve.

Vocabulary: **stewards** (the humans), the **charter** (what the project is
for), **tiers** (how much human approval a change needs), **roles** (the agents
and scripts), the **ledger** (the public record of every run), **drills** (the
replay suite that gates changes to the harness).

## 2. Repositories and files

- `blip-box/guild` (MIT): the shell, a Python package named `guildkit`
  (`guild` on PyPI is taken). It holds the orchestration code, skills, role
  definitions, workflow templates, the drill runner and the ledger tools.
  Adopters install it from git by commit SHA, never from PyPI.
- Each adopting repository holds only what makes it different:
  - `CHARTER.md`: mission, scope, non-goals and principles as numbered clauses
    (`C-SPEC-1: follow UTS #39 exactly`). Changing it is T2.
  - `guild.toml`: the tier path map, budgets, pinned models and versions, roles.
    (The first draft called it `GUILD.md`; a TOML file is machine-readable and
    checkable, and the prose belongs in the charter and the handbook.)
  - `AGENTS.md`: the engineering handbook, as now. It points to the charter
    for the why.
  - thin workflows that call the shell.
- Build for `confusable` first with a clean split between shell and per-repo
  configuration. Generalise when a second repository adopts Guild, not before.
- Agents load the charter, `AGENTS.md` and role definitions from the base
  branch only, never from the checkout they are editing; the shell reads
  `guild.toml` from the base branch too.
- Interactive steward sessions (Claude Code) may use the same skills from the
  shell; `.claude/` in the repository is for stewards, not for the shell.
- Borrowed from Google's Elephant-Goldfish Model (Apache-2.0, kept as
  patterns, not as a dependency): fresh zero-context reviewers with a test that
  proves they saw no parent context; rubrics as versioned files; an
  implementation-readiness check before code; a scheduled drift report that
  the handbook and charter still match the code.

## 3. People

### Stewards

- At most three, enforced in repository settings. Today: one.
- Stewards own the charter, the budget and the agent configuration, approve by
  tier, run releases, and may push commits onto agent pull requests.
- Protecting steward attention: a cap on agent pull requests awaiting review;
  plan approval before the Builder spends on T2 and T3 work; the ledger tracks
  comments per review, time on review and approval drift; seeded-defect checks
  of stewards start when there are two of them.
- Recruiting a second steward is a roadmap item, because T3 cannot be met by
  one person (see section 5).

### Contributors

- Pull requests are limited to collaborators (GitHub setting, February 2026).
  Dependabot still counts as a collaborator; the Builder App must be tested
  against the setting.
- Issue forms: Bug (code points, the function called, expected and actual
  result, the specification clause, the library version, AI-use disclosure,
  a short human summary), Feature (the problem, the behaviour wanted, the
  charter clause it serves), Question. Security reports go through GitHub's
  private reporting.
- Every agent comment says it is from Guild and links its decision record.
- "Needs info" issues close after 21 days, name exactly what is missing, and
  reopen on any reply.
- Reporters are credited in release notes for validated reports only.
- Floods: a playbook based on GitHub's temporary interaction limits. The
  all-or-nothing setting that restricts issue creation is never used.
- Provenance: agent commits are signed by the App, linked to their run log and
  carry an `Assisted-by` trailer. The merging steward is the accountable
  certifier. Agents may read ICU and Rust source to diagnose oracle
  disagreements and to patch the oracles under `tools/oracles/`, and must never
  reproduce it in `src/confusable/`.

## 4. Intake and triage

1. **Intake script** (no model). Fetches the issue or comment through the API,
   converts Markdown to plain text, drops HTML comments and entities, and
   escapes every non-ASCII character as `U+XXXX` (a notation JSON never
   decodes). It annotates which code points are invisible, bidirectional or
   Tag-block, using confusable itself. It records a content hash of the
   snapshot.
2. **Oracle check** (no model). For a bug report, a script turns the structured
   reproducer into a test and runs the claim against the committed ICU and
   Rust fixtures, or the oracles, before any model or steward spends time.
3. **Triage call** (one model call, no tools, no tokens, egress to the model
   API only). Reads the escaped text and the oracle result; returns a record
   of closed enums: kind, actionable or not, severity, the charter or spec
   clause, and what is missing. Comments are built from templates; no URLs,
   mentions, images or model free text.
4. **Poster job** (no model). Validates the record against its schema and
   posts labels and the templated comment through the Triage App.

Rules: a bug is accepted only with a reproducer the oracle check confirms and
a spec or oracle citation; without a reproducer the label is "needs info". When
the oracle agrees with the current output, triage labels "spec disagrees" and
posts the citation; a steward closes, because oracles are sometimes wrong
(seven ICU patches so far). Features are judged against charter clauses by ID.

Brakes: triage starts within minutes of a new issue or comment; at most three
triaged items per outside author per day; a daily cap on triage runs; batch
mode twice a day once the cap is hit.

## 5. Risk tiers

Computed by plain code from the paths a change touches and the kind of change.
The highest tier any rule gives wins. Diff size, deleted code, edited tests,
dependency or lockfile changes and build configuration can only raise a tier.
Agents and stewards can raise a tier, never lower it. CODEOWNERS and the
ruleset mirror the tiers (section 12, item 8), and a CI check fails when the
tier code and they disagree. Approvals are dismissed on a new push.

| Tier | Needs | Covers |
|---|---|---|
| T0 | Green CI and a Reviewer pass; a steward merges without review | Documentation that no agent reads as instructions, labels, generated data from pinned sources, Dependabot non-major updates (which keep their own auto-merge) |
| T1 | One steward approves | Every other code change: bug fixes with a confirmed reproducer, tests, refactors, performance work |
| T2 | Two stewards approve | Public API, departures from the spec, new data sources, `pyproject.toml`, `uv.lock`, `tools/**`, the charter, Guild configuration |
| T3 | Two stewards approve and a steward runs it | Releases to PyPI, security advisories |

Hard reject, for files that instruct or run the harness: `.github/**`,
`.claude/**`, `CLAUDE.md`, `AGENTS.md`, `CHARTER.md`, `guild.toml`,
`conftest.py`, `.pre-commit-config.yaml`. Agents draft such changes; a steward
commits them.

No tier merges without a human. There is no auto-merge of agent code.

While there is one steward: T2 passes with that steward's approval, a public
"merging in 24 hours" notice, a fresh read after the wait and a "no objection"
verdict from the Reviewer. A release passes with the steward plus a 72-hour
public notice and the Reviewer's no-objection. A security advisory needs the
steward alone, with no wait. All three are recorded in the ledger as
single-review. The rule switches off when a second steward joins. When the
only steward both starts a Builder run and approves its pull request, the
ledger records that too.

Every merge gets a decision record: tier, policy version, approvers, model and
harness versions, cost. A weekly sweep audits merged changes.

## 6. Roles and the harness

### Roles

| Role | Kind | Model (baseline) | Reads | Produces |
|---|---|---|---|---|
| Triage | Script plus one tool-less call | Haiku 5.5 | Escaped text, oracle result | Enum record |
| Planner | Agent | Opus 5.5 | Validated record, repository, charter | Plan with checkable acceptance criteria, or "needs clarification" |
| Builder | Agent | Opus 5.5 | Approved plan or confirmed reproducer, repository | A patch |
| Reviewer | Agent, fresh context | Opus 5.5 | Patch, base-branch rules, the contract | Findings on correctness and charter violations only, each verified |
| Releaser | Script plus one bounded call | Haiku 5.5 | Merged changes, ledger | Release proposal: version, changelog with credits, conformance summary |

- Every role starts on the strongest model; a role moves down only when the
  drills show no loss. Model IDs are pinned in full, per provider.
- The Planner is skipped for T1 bug fixes with a confirmed reproducer: the
  failing test is the acceptance criterion. It runs for features and T2/T3
  work, where the Planner and Reviewer fix the acceptance checks in a short
  contract before the Builder starts, and a steward approves the plan.
- The Builder never reads raw issue text, outsider comments or the web.
- A task gets at most two Builder attempts, one review round each; the second
  attempt escalates the model. After that it goes to the stewards with a
  summary and the cost so far. A patch leaves the sandbox only when the stop
  hook's tests and conformance suite pass.
- A plain check fails on deleted tests, new skips or xfails, and fixture or
  `_data` changes without a generator change.
- A different Reviewer model is optional, chosen by the drills.

### The harness

- Everything runs in GitHub Actions on fresh runners, driven by the shell.
- The shell drives agents through the Claude Agent SDK for Python: it passes
  `setting_sources=[]`, because the SDK otherwise loads settings, CLAUDE.md,
  agents and skills from disk (section 12, item 3), and hands it the charter,
  settings and role definitions from the base branch explicitly; path and
  command rules run as a PreToolUse hook inside the shell, with a permission
  callback that denies whatever reaches the prompt; cost and usage arrive as
  typed results. The SDK and Claude Code versions are pinned.
- No agent holds a write token. Agent steps produce a patch or a record. Plain
  jobs holding the App tokens apply it after checks.
- The agent sandbox has no tokens. A networked setup step installs
  dependencies and caches the Unicode sources; the agent step's network
  allowlist is the model endpoint and nothing else, in block mode, DNS
  included.
- Before every run, agent configuration is restored from the base branch.
- The model credential is the shortest-lived token available, kept out of the
  agent's environment where possible (see section 12).
- Three GitHub Apps, held by the apply jobs: Triage (issues: write), Builder
  (contents and pull requests: write, no workflows permission, cannot merge),
  Gate (checks: write, for the tier status check and the Reviewer verdict).
- Not used: Claude's ready-made GitHub Action (it runs the agent beside the
  token and reports no cost). Its input sanitising and base-branch restore are
  copied as patterns.

## 7. Charter and roadmap

- `CHARTER.md` is drafted from the decisions table in `AGENTS.md`, the v1
  scope and the README, as numbered clauses; the steward ratifies it. Agents
  cite a clause by ID when they accept or reject a feature.
- GitHub issues are the roadmap's source of truth: issue types Bug, Feature
  and Task, sub-issues for breakdowns, maintainer-only labels for priority
  overrides. The Planner reads issues only.
- The generated roadmap is a pinned issue, refreshed weekly, ordered by
  expected value (severity, charter priority, how many distinct people asked)
  per expected cost (past ledger costs for similar work). It is never a file
  on `main`, and no agent reads it. The ordering is calibrated against actual
  costs and outcomes before it is trusted.
- Releases: the Releaser proposes one when an unreleased fix to library
  behaviour has landed, or after four weeks of other unreleased changes. A
  steward approves and runs it (T3).

## 8. Cost

- A dedicated Anthropic Console workspace for Guild with a monthly spend limit
  enforced by Anthropic: the only hard cap. Alerts at 50% and 80%.
- Operations budget: $150 a month to start. Drills: a separate reserve of about
  $300 a quarter, spent only when a pinned component changes.
- Per-run caps, to be tuned after a month of ledger data: triage $0.10,
  Planner $1, Builder $4, Reviewer $2. Each run also has a budget with one
  maximal turn of headroom, a turn limit and a job timeout.
- A hook stops a run after repeated identical tool calls.
- Daily: an alert computed from the ledger. Monthly: the ledger is reconciled
  against billed usage.
- The ledger reports cache reads and writes separately, since a skill or tool
  edit can move cost without moving quality.
- The caps are Anthropic-only: Bedrock has no provider-enforced cap and
  Vertex's new one is unverified for Claude (section 12, item 6).

## 9. Quality, drills and pinning

- Quality signals in the ledger: how often stewards overrule triage; the
  Reviewer's catch rate and false-veto rate; escaped defects (reverted or fixed
  later); time to first response; cost per merged change; pull request size;
  the stewards' own review effort.
- A monthly retrospective reads transcripts, not only counts, and proposes
  changes to prompts, model choice or caps as drafts a steward commits.
- Drills: a replay set of past issues and pull requests with known right
  outcomes, including negative drills where the right answer is "needs info"
  or "do nothing", and some kept private. Each drill strips later commits,
  tags and refs; a bucket created after each candidate model's training cutoff
  carries the deciding weight; grading uses the original tests plus a
  maintainer-style rubric; each drill runs 3-5 times on fixed runner sizes,
  scored as pass^k, compared in pairs against the current setup. "No quality
  drop" is a threshold above measured noise.
- Pinned, each gated by drills and followed by a soak period: model IDs per
  provider, the Claude Agent SDK and Claude Code versions, effort level,
  settings, the shell version. A weekly canary of 3-5 drills at one trial runs
  between changes.
- Dependabot never auto-merges Anthropic or Claude tooling (PR #24). A weekly
  workflow opens an issue when a pinned model is deprecated, listed in the
  `scheduled` CI job as `AGENTS.md` requires.

## 10. Operations

- One orchestrator job chains the roles for an issue. Each issue has its own
  concurrency group, so a run is never silently dropped. Every run rebuilds its
  state from the issue.
- Steward commands in comments: `/guild build`, `/guild reject <clause>`,
  `/guild retry`, `/guild pause`. A plain script parses them and acts only for
  stewards, checked against live permissions.
- Kill switch, four independent layers, each rehearsed: a repository variable
  (`GUILD_PAUSED`) every workflow checks first; suspending the Apps; the
  workspace spend cap; a ruleset switch that requires a human on every path.
- Ledger: an append-only file on a `guild-ledger` branch, protected by
  ruleset, written by the poster job. One line per run: role, model, tokens,
  cost, issue or pull request, outcome, decision and citation, who decided. No
  model free text. A Markdown summary on the same branch and a weekly report
  issue; a Pages dashboard only if the summary proves insufficient.
- Public repositories have public logs: no run prints model output or
  secrets.

## 11. Security baseline and release path

Before any agent runs:

- Organisation: require two-factor authentication; remove or confine the
  third-party apps with write access to code and workflows (`tembo`,
  `chatgpt-codex-connector`).
- Repository: secret scanning and push protection on; pull requests from
  collaborators only; actions required to be pinned to full commit SHAs
  (already true of every workflow); Dependabot security updates stay off (they
  skip the cooldown).
- Release: a protected `pypi` environment with a required reviewer, tag
  pattern `v*` and no administrator bypass; a tag ruleset on `v*`; PyPI Trusted
  Publishing from a job that only uploads an artifact another job built; no
  Actions cache in any workflow that publishes or holds secrets; no package
  installs in jobs triggered by issues.
- CI on agent branches runs with no secrets.
- Security reports stay private. Agents may reproduce, draft a fix and a test,
  and draft the advisory; stewards run, publish and release (T3). Nothing is
  public until the advisory is.
- Dependencies of Guild itself are stable, documented features only: no
  beta-only features. The same configuration must run on Anthropic, Bedrock
  and Vertex with per-provider pinned IDs and per-provider drills.

## 12. Verified before building on them

Checked against current documentation on 2026-10-30. Each item says what was
found and what it changed.

1. **Workload identity federation: yes.** Anthropic documents OIDC token
   exchange from GitHub Actions for the plain API client, and the WIF reference
   says the Agent SDK follows the same credential order (not yet run). The job
   needs `id-token: write`, an identity token file and the federation
   variables, and no `ANTHROPIC_API_KEY`, which would shadow federation. The
   rule is pinned to the repository and to `refs/heads/main`. Tokens live
   about ten minutes and are single-use, so long jobs re-mint.
2. **Builder App under collaborators-only pull requests: not documented.** The
   docs define collaborators as users with a role and say nothing about Apps
   or Dependabot. Test it with the App in shadow mode before relying on it.
3. **SDK settings: the opposite of the expectation.** `setting_sources=None`
   loads user, project and local settings, CLAUDE.md, agents, skills and
   `.mcp.json`. The shell passes `setting_sources=[]`. Managed policy
   settings, `~/.claude.json` and auto memory load regardless, so the runner
   must be fresh.
4. **The `workflows` permission covers `.github/workflows` only.**
   `.github/actions/`, `CODEOWNERS` and `dependabot.yml` are writable with
   `contents: write`. The reject list (`.github/**`) and the tier check before
   any apply job protect them, not the App's permissions.
5. **Required status checks can name their app**: `integration_id` in rulesets,
   `app_id` in branch protection. The Gate App can be the only valid source.
6. **Spending caps.** Bedrock has none: Budgets actions lag by hours and need a
   customer-written deny policy. Vertex gained spend-cap budgets in October
   2026, but whether Claude partner SKUs fall under the capped service is
   undocumented. The Console workspace limit stays the only hard cap.
7. **The Python Agent SDK bundles the Claude Code CLI** and records the version
   in `_cli_version.py` (0.2.175 bundles 2.1.314, both released 2026-10-30;
   the shell pins 0.2.176 with 2.1.316, installed and read on 2026-11-02).
   Pinning the SDK pins the CLI. `max_budget_usd` is a client-side estimate.
   The bundled CLI reads the federation variables and the identity token
   file, so the agents use the same credential path as the plain client.
8. **Rulesets on a Free-plan public repository.** Branch rulesets, code owners
   and required code-owner review are available. Push rulesets that restrict
   file paths are for private and internal repositories only. Tiers are
   mirrored with CODEOWNERS plus "require review from code owners", and, once
   a team of stewards exists, the "required reviewers" rule (teams, N
   approvals per path; generally available since February 2026, plan
   availability undocumented). The drift check compares `guild.toml` with
   CODEOWNERS and the ruleset.

## 13. Rollout

- **Phase 0, baseline.** The settings and workflow changes in section 11.
  Started: PR #24.
- **Phase 1, charter.** Draft `CHARTER.md`; the steward ratifies it. Done
  2026-10-30 (confusable PR #26).
- **Phase 2, shadow.** Create `blip-box/guild` and the shell. Triage posts
  records; the Builder opens draft pull requests; nothing merges without a
  steward; outcomes are graded and seed the first drills. Shadow ends on a
  count of clean decisions and passing drills, not on a date.
- **Phase 3, live.** T1 through steward approval; T2 and T3 rules live;
  the first alpha on PyPI.
- Each phase ends with a short retrospective before the next begins.

## 14. Decision log

| Q | Decision | Amended by |
|---|---|---|
| 1 | Reusable system, proven on confusable | Review: confusable first, generalise at the second adopter |
| 2 | Outside contributors open issues and comments only | Round 2: enforced by the collaborators-only PR setting |
| 3 | Quarantined triage | Q35: a tool-less API call |
| 4 | Risk tiers T0-T3 | Q37, review: no auto-merge; T0 is "merge without review" |
| 5 | Bugs need a failing test and a spec or oracle citation | Q40: structured reproducer, oracle check; review: stewards close |
| 6 | A numbered charter decides features | |
| 7 | Separate roles with least privilege | Q35: Triage and Releaser are scripts; review: Planner skipped for T1 fixes |
| 8 | Cost as a first-class metric | Q42: cap hierarchy |
| 9 | Every decision public, with a ledger | Q26: ledger branch |
| 10 | Stewards steer; limit of three enforced | Q44: attention protected |
| 11 | Runs in GitHub Actions via Claude Code headless | Q48: the Agent SDK, driven by the shell |
| 12 | Agents only draft changes to the machinery | Q36, review: hard-reject list; `pyproject.toml`, `uv.lock`, `tools/**` are T2 |
| 13 | Three GitHub Apps | Q35: held by apply jobs; Gate never merges |
| 14 | Escape untrusted text before any model | Q35, Q38, Q40: `U+XXXX`, Markdown to plain text |
| 15 | Reactive triage with brakes | |
| 16 | Dedicated workspace, $150 a month, per-run caps | Q42; review: drills funded separately; strongest model as baseline |
| 17 | Reviewer on a different model; two attempts | Q43: different model optional; second attempt escalates |
| 18 | GitHub issues are the roadmap | Review: roadmap as a pinned issue, never read by agents |
| 19 | Security reports stay private and human | Q45 |
| 20 | T2 with one steward: approval plus 24 hours plus Reviewer | Q37: public notice |
| 21 | Security baseline first | Q38 |
| 22 | Name: Guild | Review: package `guildkit` |
| 23 | `blip-box/guild` plus per-repo charter, config and role files | Q48: role files handed to the SDK from the base branch |
| 24 | Tier computed by plain code, highest wins | Q37: diff shape only raises |
| 25 | Steward commands and `GUILD_PAUSED` | Q46 |
| 26 | Ledger on a branch, weekly report, dashboard | Review: dashboard deferred |
| 27 | Quality metrics and a monthly retrospective | Q44: steward metrics |
| 28 | Drills gate every harness change | Q39, Q41 |
| 29 | Rollout in phases | Q37: shadow ends on a count |
| 30 | Draft the charter from existing decisions | |
| 31 | Issue forms, private reporting, agent self-identification, 21-day close, credit | Q40, Q47 |
| 32 | No beta-only features; portable across providers | |
| 33 | Releases proposed by the Releaser, approved as T3 | Q45 |
| 34 | The governing rule | |
| 35 | No agent holds a write token | |
| 36 | Agent code never runs near secrets | Review: narrower hard-reject list |
| 37 | T0 documentation only, shadow by count | Review: no auto-merge at all |
| 38 | Trusted Publishing, no caches near secrets, per-job egress | Review: "offline" means model API only |
| 39 | Pin the whole harness | |
| 40 | Reproducers as data, checked by machine | |
| 41 | Statistically real drills | Review: separate budget |
| 42 | Hierarchy of cost caps | |
| 43 | Bounded Builder-Reviewer loop | |
| 44 | Protect steward attention | Review: seeded checks of stewards wait for a second steward |
| 45 | T3 with one steward | |
| 46 | Orchestration and a tested kill switch | |
| 47 | Provenance, licensing, floods | Review: agents may read oracle source, never copy it |
| 48 | The Agent SDK rather than the bare CLI | |
| 49 | Borrow EGM's patterns, not the plugin | |
| 50 | `guild.toml`, not `GUILD.md`, holds the per-repository configuration | Phase 2 |
| 51 | The shell passes `setting_sources=[]` to the Agent SDK | Section 12, item 3 |
| 52 | Tiers mirrored with CODEOWNERS and the required-reviewers rule, not push rulesets | Section 12, item 8 |
| 53 | The triage call uses structured output in the record's schema, validated again in code | Phase 2 |
| 54 | In shadow mode a steward starts every plan and build with `/guild plan` or `/guild build`; triage's acceptance starts nothing | Phase 2 |
| 55 | Plans are run artifacts named by issue, found by the build job; the issue gets a templated pointer to the run | Phase 2 |
| 56 | Agent commits are made with `createCommitOnBranch` by the Builder App, so GitHub signs them; an `Assisted-by` trailer names the model | Phase 2 |
| 57 | Model text reaches stewards only in step summaries, check-run text and artifacts, escaped to ASCII and cut; comments, labels, titles and commit messages stay templated | Phase 2 |
| 58 | The Reviewer's verdict is computed in code: a verified finding objects, an unverified one is a note; the verdict is a check run, not a gate, in shadow mode | Phase 2 |
| 59 | Drills are TOML files per suite with the role's inputs and the right outcome; seeded defects from the project's known traps count as fresh, replayed public fixes do not decide | Phase 2 |
| 60 | Drill checkouts are clones detached at the base with every ref, the remote and unreachable objects removed, one per trial; grading tests from later commits arrive after the Builder is done | Phase 2 |
| 61 | Scores report pass@1 and pass^k, with the fresh bucket deciding; a committed baseline per suite and a noise threshold make the gate | Phase 2 |
| 62 | The ledger is appended by a `ledger` job at the end of every workflow through `createCommitOnBranch` with the Builder App's token, from the run's entry artifacts; the branch is a steward's to create and protect | Phase 2 |
| 63 | Entries carry the issue author's login; the brakes count the day's triage entries by author and in total, and a queued issue gets a label, a comment and a skipped entry; a twice-daily batch dispatches the triage workflow for queued issues | Phase 2 |
| 64 | The weekly report is a comment on one pinned issue, from counts only, after an audit that the ledger never lost a line; the kill-switch rehearsal is a written procedure in `docs/operations.md` | Phase 2 |
| 65 | A build drill's rubric is graded by a second model as the second judge, after the tests pass: `met`, `not_met` or `unknown` per criterion, validated in code; only `not_met` fails, and the score counts undecided trials so an abstaining grader shows | Phase 2 |
| 66 | A weekly canary runs five drills at one trial on the shell's own repository and opens or comments on an issue when any fails; CI fails while it is disabled, and `GUILD_PAUSED` pauses it | Phase 2 |
| 67 | The second Builder attempt runs on `[builder.second_attempt]` when the plain check refuses the first: a fresh checkout at the same base, the check's and the run's reasons after the brief, never the first patch; the attempt that passes is reviewed and opened, two failures go to a steward; entries carry the attempt number. In shadow mode the Reviewer's objections do not start it, since the verdict is not a gate | Phase 2 |
| 68 | The Releaser makes no model call: the change list is the merged pull request titles, the credits the ledger's, the version the commit types'; a release is due on a fix or feature to the library or after `stale_days`, proposed as one open issue the Triage App rewrites, and run by a steward as tier 3 | Phase 2; amends row 7's "one bounded call" |
| 69 | The shell's own repository mirrors the adopter's merge policy: branch protection on `main` requires only CI's `required` job, and Dependabot's non-major updates auto-merge except Anthropic or Claude tooling, which a human reviews first | Phase 2 |
| 70 | The oracle's verdict outranks the model's reading of the reproducer: when the check ran, the triage policy drops the fields it needed from the model's `missing` list, so a classifier's doubt cannot turn a confirmed bug into a request for information. A negative drill pins what must not happen, as a list of acceptable kinds and templates, not one classification; the first shadow runs showed `claude-haiku-5-5` classing an injection attempt as a bug, spam or other from run to run, all of them safe | Phase 2; from the canary runs of 2026-11-08 |
| 71 | Nothing a bot opens or writes starts triage: the intake condition tests the issue's author as well as the comment's, so Guild's own issues (the weekly report, a release proposal, a failing scheduled workflow) and Dependabot's are never submissions, whoever comments on them; a dispatched run is a steward's or the batch's choice and skips nothing | Phase 2; the first scheduled weekly report, 2026-11-09, opened its issue as the Triage App and triage classified it |
