# Harness options for Guild's agent roles

A record, frozen on 2026-11-11 and committed as it was written. Nobody
keeps it current: `docs/plan.md` holds the decisions (rows 76 to 78) and
`AGENTS.md` the roadmap. Prices and product behaviour are as read on the
dates given.

For Atilla, steward of blip-box/guild and blip-box/confusable. Written
2026-11-10; every source was read that day. Fixed rules: no model free
text in an issue, label, ledger line or commit; nothing merges without a
steward. Smallest change wins.

## Today, and the gap stated precisely

The Planner, Builder, Reviewer and the drills' grader run the Claude Agent
SDK 0.2.176 (Claude Code 2.1.316) in GitHub Actions jobs on `ubuntu-latest`
(S1, S2), with the fresh checkout, per-role tools, gate, turn and budget
limits and Stop hook the handbook describes. Issue #61 cost $0.86 across plan, build and review (the ledger).

The gap, exactly: the checkout holds no token, but the job does. The OIDC
identity token file and GitHub's `ACTIONS_ID_TOKEN_REQUEST_TOKEN` sit in the
environment the Builder's Bash inherits, the gate has command patterns but
no path rule for Bash, and the Stop hook runs the adopter's tests, which the
Builder may have edited, outside any boundary. Nothing refuses the network.

## 1. Keep the SDK on hosted runners, add the SDK's own sandbox

The pinned SDK already has `ClaudeAgentOptions.sandbox` (S3). On Linux,
bubblewrap puts each Bash command in its own network namespace behind a
proxy with a domain allowlist (S4). Guild's Bash needs no network, so the
list is empty, with `allowUnsandboxedCommands=False`, `failIfUnavailable`
(S5; not declared in 0.2.176's TypedDict, forwarding unverified) and
`autoAllowBashIfSandboxed=False` so the gate still decides. The Stop hook's test run is not
covered. Step 1b: `srt` from `@anthropic-ai/sandbox-runtime` (beta research
preview) wraps the whole `guildkit build` process, tests included, with
`api.anthropic.com` the only allowed host (S6, S7).

- Isolation: 1a closes Bash egress; 1b closes the step except the model
  endpoint. The proxy does not terminate TLS, so an allowed host can be
  fronted (S4, S7); with no host, or only the API, that is moot.
- Credential: unchanged; a process that reaches the federated token can
  only spend inside the workspace limit.
- Cost, latency, ledger, grading, drills, lock-in: unchanged.
- Shell: 1a is about twenty lines in `agents.options` plus
  `apt-get install bubblewrap socat` in the agent jobs; 1b adds an npm global
  install, a settings file and a wrapper. Both need one run to prove
  bubblewrap starts on `ubuntu-latest` (an AppArmor sysctl may be needed,
  S4). Not verified today.

## 2. Self-hosted or larger runners behind an allowlist

A self-hosted runner behind a firewall is infrastructure to patch, and the
plan's research rules them out after Shai-Hulud registered rogue ones
(docs/research/notes/security_threats.md).
GitHub's larger runners with Azure private networking put the runner's NIC
in your VNet, so NSG outbound rules apply (S8), but they draw on Team or
Enterprise Cloud compute and bill public-repository minutes (S9); blip-box
is on the Free plan (plan 12.8). Harden-Runner's block mode filters egress
on hosted runners, but it is a third-party agent with two 2026 bypasses,
one through DNS over HTTPS to allowed hosts (S10).

github.com on the list reopens the exfiltration channel the research
names. Credential, ledger, grading and
drills are unchanged; only the workflows change. Cost: a paid GitHub plan
plus Azure, or a StepSecurity tier, which is also the lock-in. More money
and more surface than option 1 for the same boundary. No.

## 3. Claude Managed Agents

Anthropic runs the agent loop and a fresh Linux container per session; the
GitHub job becomes a thin client that creates a session, streams events and
applies the result (S11). Beta header `managed-agents-2026-04-01`; not
ZDR-eligible, transcripts persist until deleted (S12).

- Fresh checkout: a `github_repository` resource pinned to a commit. A token
  is injected by an Anthropic-side proxy and never enters the container; a
  public repository clones with no token, and push then fails (S13). The patch comes back as a file under
  `/mnt/session/outputs/`, listed by the Files API with `scope_id` (S14);
  the `check`, `review` and `open` jobs run unchanged.
- Tool list per role: per-tool `enabled` on the eight built-in tools (S15).
- Gate: `permission_policy: always_ask` pauses the session on every call and
  the job answers allow or deny with a reason, so `Gate.reason` runs
  unchanged, one round trip per call. The server's `auto` policy is a
  classifier, not a plain check (S15).
- Stop hook: none. The job downloads the patch at each idle, runs the tests
  on the runner and sends the escaped tail back, `max_test_rounds` times.
- Caps: no `max_turns`; the job counts calls. The session `budget` is a hard
  platform-enforced cap at list price (S16).
- Egress: `limited` networking with no hosts. A request that omits
  `networking` gets `unrestricted`, so the shell must always set it, and
  `allow_package_managers` opens github.com and PyPI, so the adopter's
  environment stays out of the sandbox (S12).
- Credential: the job holds it; the container never does, since the model
  calls are Anthropic's. Whether a federated token is accepted on
  `/v1/agents` and `/v1/sessions` is not verified.
- Cost: tokens at list plus $0.08 per session-hour of `running` time, idle
  free (S17); #61's three runs would add under $0.10. Latency: container
  start time is undocumented; each gated call adds a round trip.
- Ledger: `session.usage` carries cumulative tokens, `list_cost` and
  `active_seconds`; the event list is the transcript (S18).
- Shell: `agents.py` and the three agent jobs rewritten against the events
  protocol. The drills' stripped checkouts cannot come from
  `github_repository`, which clones with refs intact; they would be uploaded
  as file resources. Grading is GitHub-side and unchanged.
- Lock-in: Anthropic objects in a beta API, on the Claude API, Claude
  Platform on AWS and Claude Models on Google Cloud (Anthropic managed);
  not Bedrock or Vertex (S12).

Keeps both rules. The only option where the agent's runtime holds no
Anthropic credential and the cap is the platform's, at the price of a
rewrite and a beta. A phase 4 candidate, not a phase 3 change.

## 4. Cloud sessions, scheduled tasks, Remote Control

Scheduled tasks run without a human: an API trigger with a per-task bearer
token, GitHub triggers on issue, pull request and release events, or a
schedule (S19, S20). They belong to one person's
claude.ai account and spend its subscription usage, so no token counts
reach the ledger and no Console cap applies (S20). Runs push branches and
open pull requests as that person's GitHub user with the agent's own commit
messages: model free text in a commit (S19). The session loads the
repository's `.claude/` settings and skills, the opposite of
`setting_sources=[]`; permissions are a classifier, and undecidable calls
wait for a human (S19). I found no documented API that reads a session's
result; the fire endpoint returns a URL and does not stream (S20). Remote
Control is a window into a `claude` process on a machine that stays on,
subscription only, no API (S21). Out.

## 5. Bedrock, Vertex or Claude Platform on AWS behind option 1 or 2

Credential and cap change, not the harness. Bedrock has no
provider-enforced cap (plan 12.6, checked 2026-10-30, not re-verified).
Claude Platform on AWS is Anthropic-operated with API parity: tier spend
caps plus self-set organisation and workspace limits, computed at list price
with about two hours of lag and billed overshoot; SigV4 through the AWS
credential chain, which includes web identity for GitHub Actions; Managed
Agents available (S22). Claude Models on Google Cloud (Anthropic managed)
bills through the Marketplace with ADC credentials and no API keys, and has
Managed Agents with session budgets; I found no spend-cap statement on its
page (S23). Each needs a cloud account, per-provider model IDs and prices
in `guild.toml`, and per-provider drills (plan 11). Not now.

## Recommendation for phase 3

Do 1a now: the SDK's own sandbox with an empty allowlist, bubblewrap in the
agent jobs, proven in the canary first. It is the smallest change that
closes the Bash channel and touches neither ledger, grading nor drills. Then
1b, `srt` around the whole agent step with `api.anthropic.com` alone, once a
run shows it starts on `ubuntu-latest` and the tests pass inside it; that
puts the Stop hook's test run behind the boundary too. Keep option 3 for phase 4. Options 2, 4 and
5: no.

## Questions only you can answer

1. May phase 3 go live with 1a alone, with the test run still outside the
   boundary, or must 1b land first?
2. Would blip-box hold a paid GitHub plan, an Azure subscription or an AWS
   account? If not, options 2 and 5 stay off the table whatever their merit.
3. Is a Managed Agents spike worth a slice of the drills reserve now, given
   that Anthropic retains session transcripts and the API is beta?

## A/B experiment: two Builder arms, three triage arms

Added 2026-11-11 at Atilla's request: see both paths in action and pick the
one the rest of Guild is built on, with the decision rule written before
the first trial.

### What is compared

One variable per comparison. The Planner and Reviewer stay on the SDK in
every arm.

Builder arms:

- A: the Agent SDK in Actions with the Bash sandbox of option 1a, and the
  harness features switched on per role from the base branch: skills and
  subagents handed in as options, nothing read from disk. Without this the
  test measures harness features, not platforms.
- B: a Claude Code scheduled task on the claude.ai plan. The command job
  fires its API trigger with the brief as `text`; the saved prompt says to
  push a `claude/` branch and open no pull request; a `push` trigger on
  `claude/*` runs the existing check, review and open jobs, so the Builder
  App still opens the templated draft PR and squash-merge drops the agent's
  commit messages (S19, S20).

Triage arms, through the `Caller` protocol that `drills.run_triage`
already takes:

- T1: `claude-haiku-5-5` with structured output, as today.
- T2: TypeSafe Jev, `jev-1.14.0` pinned by version, a System One model: it
  returns typed answers and probabilities and writes no text (S24).
- T3: OpenAI's Decisions API on `gpt-6-luna`: predicate, choice and score
  questions, up to 400 per request (S25).

### System One models and where they fit

A System One model is a closed-enumeration classifier with calibrated
probabilities. That is the shape Guild's triage already has: the model
classifies, the policy decides. The mapping is direct: a choice question
for `kind` and one for `severity`, one yes/no question per `missing`
field, and `clause` chosen from candidates that code extracts with the
existing regexes, plus "none", so a clause can only be a string the issue
contains or a charter ID. The adapter turns the answers into the JSON
record; `validate_output` and `apply_policy` run unchanged. Two things
improve. A model that cannot write cannot be talked into text, only into a
wrong label, which the oracle check and the policy already bound (decision
70). And probabilities are numbers, so the ledger can carry the top
probability per run, and the negative drills can score the mass on safe
outcomes instead of one draw.

Costs and caveats. Jev bills $0.042 per million input tokens, output free,
with 64k tokens per request (S24); Luna $0.10 per million, output not
charged (S25); both are under a cent per triage. Jev is early access, and
neither vendor documents prompt-injection behaviour, so the injection drill
decides. Both need an API key as a repository secret, where triage today
holds none, and a second provider dependency: a decisions-table change and
a departure from decision 32, no beta-only features. ZDR: TypeSafe for
enterprise customers, OpenAI for eligible customers; issue text is public
anyway. Beyond triage, the rubric grader's per-criterion `met` question and
the roadmap's expected-value ordering (plan 7) are System One shapes; the
Planner, Builder and Reviewer need tools and text and are not.

### Measurement and decision rule

- Drills, not live issues. Builder arms: the build drill plus two new
  seeded drills. Triage arms: the nine triage drills plus enough new ones to
  reach the plan's 20 to 50, with more injection and negative cases.
- Three to five trials per drill per arm; pass@1 and pass^k;
  `drills.compare` with the noise threshold; a difference inside it is a tie
  (plan 9).
- Per run: wall-clock, denials, test rounds, steward grades, and cost where
  it exists. Arm B has no token counts; it records a `subscription` marker
  and no cost.
- The rule, fixed before the first trial: a Builder arm wins on pass^k
  above the threshold with no fixed rule broken; a tie keeps arm A, which
  holds the ledger cost. A triage arm wins on the fresh negative drills
  first, then cost. If B wins on quality but Guild will not run without a
  ledger cost, the result changes the Builder's prompt and harness
  settings, not the platform.

### To build

- Arm B: a grader that waits for the `claude/` branch and grades its diff;
  the push-triggered workflow; the task and an environment with no network
  (whether the setup script then runs is unverified); a `runner`
  enumeration in ledger entries; a dedicated seat for the builder identity,
  whose terms are a question for Anthropic.
- Arms T2 and T3: two caller adapters, the candidate-clause extractor,
  `[models]` price entries, the secrets, the new drills.
- Nothing merges without a steward in any arm.

### Budget

Arm A and the triage arms draw on the drills reserve; arm B on the plan
allowance, under the task fire limit of thirty per hour (S20). Shell work:
a few days. Managed Agents is not an arm; it shares arm A's billing world
and gate logic and is tested later with the same drills.

### Outcome, 2026-11-11

The experiment ran in a day; the logs and the decision are in
`ab-experiment-plan.md`, beside this file (M0 to M3 logs, M4 decision). Builder: the
arms tie, fourteen and fifteen of fifteen trials, and a tie keeps arm A,
which also keeps every fixed rule and the ledger cost; arm B as it ran
kept neither. Triage: all three arms passed every trial of twenty fresh
drills, so cost decides and T2 (Jev) wins by the rule, on a margin of
about a cent per hundred issues; adoption waits on production wiring and
is a steward's, with a harder negative suite recommended first. The
recommendation above stands: 1a is built and proven on `spike/m0`, 1b is
next, option 4 is now a measured no.

## Sources (S1 to S23 read 2026-11-10, S24 and S25 on 2026-11-11)

S1 guild AGENTS.md. S2 templates/workflows/guild-build.yml.
S3 .venv claude_agent_sdk/types.py (0.2.176, CLI 2.1.316).
S4 https://code.claude.com/docs/en/sandboxing
S5 https://code.claude.com/docs/en/agent-sdk/python (Sandbox settings)
S6 https://code.claude.com/docs/en/sandbox-environments
S7 https://code.claude.com/docs/en/agent-sdk/secure-deployment
S8 https://docs.github.com/en/organizations/managing-organization-settings/about-azure-private-networking-for-github-hosted-runners-in-your-organization
S9 https://docs.github.com/en/actions/concepts/runners/larger-runners
S10 GHSA-46g3-37rh-v698, CVE-2026-32946, CVE-2026-32947 (found by search)
S11 claude-api skill, shared/managed-agents-overview.md
S12 https://platform.claude.com/docs/en/managed-agents/environments
S13 https://platform.claude.com/docs/en/managed-agents/github
S14 claude-api skill, shared/managed-agents-environments.md, Session outputs
S15 claude-api skill, shared/managed-agents-tools.md, Permission Policies
S16 claude-api skill, shared/managed-agents-core.md, Session budgets
S17 https://platform.claude.com/docs/en/about-claude/pricing
S18 claude-api skill, shared/managed-agents-events.md
S19 https://code.claude.com/docs/en/routines
S20 https://platform.claude.com/docs/en/api/claude-code/routines-fire
S21 https://code.claude.com/docs/en/remote-control
S22 https://platform.claude.com/docs/en/build-with-claude/claude-platform-on-aws
S23 https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/anthropic-managed
S24 https://docs.typesafe.ai/concepts/system-one, /api, /models, /api/errors, /legal; the early-access launch date (2026-09-15) is from third-party reports
S25 https://developers.openai.com/api/docs/guides/decisions; openai.com's announcement page returned 403, so the GA date (2026-10-22) is from third-party reports
