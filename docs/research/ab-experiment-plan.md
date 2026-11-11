# A/B experiment: plan, logs and decision

A record, frozen on 2026-11-11 and committed as it was written, apart
from identifiers of things that no longer exist. Nobody keeps it current:
`docs/plan.md` holds the decisions (rows 76 to 78) and `AGENTS.md` the
roadmap. Prices and product behaviour are as read on the dates given.
Paths under `spikes/` and the cloud arm's code are on the branch
`spike/m0`, not on `main`.

Companion to the A/B section of `harness-options.md`, beside this file.
Written 2026-11-11. It says what to build, in what order, where in the
shell, and what each step must prove before the next starts. Every arm
keeps the two fixed rules: no model free text in an issue, label, ledger
line or commit; nothing merges without a steward.

## What the code already gives us

- Triage calls go through `triage.Caller`, a `(system, user) -> (text,
  usage)` protocol, and `drills.run_triage` takes any caller. A new arm is
  a new caller; `validate_output`, `apply_policy` and `grade_triage` do not
  change.
- `config._MODEL_ID` accepts `jev-1.14.0` and `gpt-6-luna`; `cost_usd`
  prices any model that has a `[models]` table.
- `drills.run_build` prepares a stripped checkout, runs the Builder through
  `_agent`, then grades with `builder.check_patch`, the grading tests and
  the rubric grader. Only the middle step differs per arm.
- `drills.score` and `drills.compare` give pass@1, pass^k, the fresh bucket
  and the noise threshold. The `Drills` workflow runs a suite by hand.
- The ledger validator wants exactly its field set, so the arm is encoded
  in two fields that exist: `model` and `harness`. No schema change.

## M0: three spikes, by hand, one day

Each spike closes an "unverified" in the memo. Nothing is merged.

1. Sandbox on `ubuntu-latest`: a canary run with `sandbox` set in
   `agents.options`, empty `allowedDomains`, `allowUnsandboxedCommands`
   false, `failIfUnavailable` true, after `apt-get install bubblewrap
   socat`. Pass: the build drill runs and a Bash `curl` to any host fails.
   If bubblewrap does not start, try the AppArmor sysctl, then stop and
   report.
2. One cloud scheduled task: create it at claude.ai/code/routines against a
   scratch repository, fire it with `curl` carrying a drill brief, and time
   how long the `claude/` branch takes to appear. Record the session URL.
   Pass: a branch with a diff within 60 minutes and no permission prompt
   left waiting.
3. One System One call each: Jev `POST /v1/systemone` and OpenAI
   `POST /v1/decisions` with the `bug-confirmed-paypal` drill text and the
   question set from M1. Record latency and the answers. Pass: the mapped
   record passes `grade_triage`.

## M1: triage arms, two to three days

Files: `src/guildkit/systemone.py` (new), `cli.py`, `drills.py`,
`roles/`, `drills/confusable/triage/`, `.github/workflows/drills.yml`,
`tests/test_systemone.py` (new), `AGENTS.md`.

- `systemone.py` holds the question set as ASCII constants: a choice for
  `kind` over `triage.KINDS`, a choice for `severity` over
  `triage.SEVERITIES`, one yes/no per entry of `triage.MISSING`, and a
  choice for `clause` over candidates. Candidates are every match of
  `triage._SPEC_CLAUSE` and `commands.CLAUSE` in the user text, plus
  `none`, capped at 255 so the model can only pick a string the issue
  holds or a charter ID. Instructions and criteria per answer come from the
  same text the role prompt uses, so T1 and T2/T3 judge by one rubric.
- Two callers, `typesafe_caller(transport)` and `openai_caller(transport)`,
  both returning the record as JSON text plus a `Usage` with the input
  tokens and zero elsewhere, so `triage.triage` runs unchanged. Thresholds:
  `missing` entries with probability above 0.7 are listed; a top `kind`
  probability under 0.5 maps to `other`, which the policy escalates. Both
  numbers are constants and the first thing the drills tune.
- The transport is stdlib `urllib` with one retry on 429 and 529; no new
  dependency. Tests use a fake transport with canned answers.
- The adapters put the top probabilities in the trial's `actual` as numbers
  under `probabilities`, so a failed trial's line can say how sure the
  model was. `drills.describe` stays enumerations only.
- `drill-run` gets `--caller anthropic|typesafe|openai` and
  `--triage-model`, and `CREDENTIALS` gains `TYPESAFE_API_KEY` and
  `OPENAI_API_KEY`, checked per caller. Prices for the two models go in
  `drills/models.toml`, read by the drills only, so confusable's
  `guild.toml` is untouched until a winner is chosen.
- `drills.yml` gets `caller` and `triage_model` inputs and passes the two
  secrets only for the matching caller.
- New triage drills, at least eleven, to reach twenty: three more
  injection shapes, a duplicate report, a report whose oracle says
  `not_run`, a feature that names a non-goal clause, a question posing as
  a bug, a security report with a public exploit, an empty body, a
  non-ASCII title only, and a report that quotes a steward command.
- Run: twenty drills, five trials, three arms, in the `Drills` workflow.
  Commit `baseline-triage.json` from T1 first; compare T2 and T3 against
  it. Cost is cents per arm.

## M2: arm A with the harness switched on, two to three days

Files: `agents.py`, `builder.py` (tool list), `roles/`, a new
`plugins/guild/` directory in this repository, `tests/test_agents.py`,
`guild-build.yml`, `drills.yml`, `canary.yml`, `AGENTS.md`.

- The sandbox from M0 becomes permanent in `agents.options`, with a test
  that the options carry it and that `failIfUnavailable` is forwarded.
- Skills and subagents arrive as a local plugin: `plugins=[{"type":
  "local", "path": <checkout of this repository at GUILDKIT_REF>}]` with
  `skills/` and `agents/` inside it, so nothing is read from the adopter's
  disk and the pin covers them. `TOOLS["builder"]` gains `Agent` and
  `Skill`; `NEVER` drops them for that role; each subagent definition
  lists the Builder's tools and nothing more.
- Verify in the canary that the PreToolUse hook fires for a subagent's
  calls. If it does not, subagents stay off and the plan says so.
- Two more seeded build drills, so the suite has three. Run five trials;
  commit `baseline-build.json`. This is the number arm B is compared with.

## M3: arm B drills, three to four days

Files: `drills.py` (`run_build_cloud`), `cli.py`, `drills.yml`,
`tests/test_drills.py`, a scratch repository `blip-box/drill-confusable`,
one scheduled task per scratch repository.

- Checkout: `prepare_checkout` as today, then push the detached head as
  branch `base` of the scratch repository, force. The scratch repository's
  default branch is `base`. Only the base and the seed are reachable; the
  fix is not. After grading, delete the `claude/` branch, so later clones
  cannot see earlier attempts.
- The task: prompt pinned in the task form, a copy of `roles/builder.md`
  plus "push branch `claude/<id>`, open no pull request, read the brief in
  the fire payload"; repository: the scratch one; environment: Limited with
  package managers, because `uv sync` needs PyPI. This is more egress than
  arm A has; the plan records it as a known asymmetry.
- `run_build_cloud`: fire the task with the rendered brief and the branch
  name as `text`; poll `git ls-remote` every 30 seconds for the branch, up
  to the drill's timeout; fetch, take `git diff base...claude/<id>`; apply
  it to the local checkout; then the same `check_patch`, grading tests and
  rubric grader as `run_build`. Model is `cloud-session`, cost 0, turns 0,
  duration the wall-clock from fire to branch; the session id goes in
  `actual`.
- Secrets `ROUTINE_FIRE_URL` and `ROUTINE_FIRE_TOKEN` in this repository;
  `drill-run --arm cloud`. The fire limit is 30 per task per hour and 100
  per account; subscription usage is the real bound (S20 in the memo).
- Run the same three drills at five trials. Compare with
  `baseline-build.json`.

## M4: decide, one retrospective

Apply the rule from the memo: a Builder arm wins on pass^k above the noise
threshold with no fixed rule broken, a tie keeps arm A; a triage arm wins
on the fresh negative drills first, then cost. Write the decision log row
and update the roadmap. Only then:

- If arm B won: a `push` trigger on `claude/*` in `guild-build.yml` that
  runs check, review and open; a `build-cloud` job that fires the task
  with the brief; `harness` set to `guildkit-<version>/cloud` on its
  ledger entries; a seat for the builder identity, terms checked with
  Anthropic first.
- If a System One arm won: its price table and model ID in confusable's
  `guild.toml` (tier 2, a steward commits), the API key as a secret in the
  adopter, the dependency row in `AGENTS.md`, and a decision log row that
  amends decision 32.

## Budget and order

M0 then M1 can run in one week; M2 and M3 the next. Arm A and the triage
arms spend from the drills reserve: at most three build drills times five
trials times the $4 cap, about $60 plus the grader; triage arms cost cents.
Arm B spends plan usage. The canary keeps running on the pinned
configuration throughout; nothing in M1 to M3 changes what confusable's
workflows run.

## Still unverified after the plan

- Whether the PreToolUse hook covers subagent calls in SDK 0.2.176.
- Whether a cloud environment with no network can run `uv sync` in its
  setup script; the plan allows package managers instead.
- Whether a plan seat may be used for an automated builder identity.
- The two System One vendors' behaviour under prompt injection; the drills
  measure it, nothing documents it.

## M0 log

- 2026-11-11. Branch `spike/m0` pushed (commits ee99cd9, 993719e and the
  federation input). `spike-sandbox.yml` could not be dispatched: GitHub
  only registers a workflow_dispatch workflow once it exists on the
  default branch, so the probe is the `sandbox` suite of `drills.yml`,
  which runs the file at the given ref.
- 2026-11-11. First probe run (actions/runs/42991205128): the runner
  steps all passed, including `apt-get install bubblewrap socat` and the
  AppArmor sysctl on ubuntu-latest, so spike 1's first question (does the
  sandbox's tooling exist on the image) is answered yes. The model turn
  never ran: the token exchange returned 401, because the federation
  rule is pinned to `refs/heads/main` by design (AGENTS.md, Credentials).
  Remedy chosen: a second rule pinned to `refs/heads/spike/m0`, named by
  the new `federation_rule` input; the alternative, widening the main
  rule, would let any branch mint a token. Every drill run off main
  during M1 to M3 needs the same input, and the rule is archived at M4.
- 2026-11-11. Spike 1 passes (run 43006920737): with the sandbox on,
  curl got a 403 from the sandbox proxy, a plain socket had no name
  resolution, the sandbox logged the violation, and the run ended with
  subtype `success`. Two findings on the way. ubuntu-latest is now Ubuntu
  26.04, and its stock AppArmor profile `bwrap-userns-restrict` confines
  bubblewrap's children so that the sandbox's seccomp helper cannot set
  up its own user namespace ("nested userns is capability-restricted"),
  whatever `kernel.apparmor_restrict_unprivileged_userns` says; the
  profile Claude Code's sandboxing page documents replaces it, and both
  the sysctl and the profile are needed. Every Sandbox dependencies step
  now applies both and fails the job if a nested namespace still does
  not work. And a probe must prove its command ran: the second run
  ended green with nothing proved, so the verdict now requires the
  command's own first line in the output.
- Open from spike 1: the gate refused one tool call in each passing run
  (`denials=1`); the probe does not say which. Harmless for the verdict,
  worth printing at M2. The AGENTS.md Decisions table needs a row for the
  sandbox and the AppArmor profile when this branch becomes the M2 pull
  request. Spikes 2 and 3 are untouched.
- 2026-11-11. Spike 3 done, raw answers in
  `spikes/results/systemone-2026-11-11.log`. Jev (jev-1.14.0) passed both
  triage drills: kind, severity and clause as the drills expect, no
  missing field on the confirmed bug, and on the injection drill a
  needs-info answer that ignored the injected instructions. Latency 0.2 s
  per drill, about 1,600 input tokens, so under a thousandth of a cent
  per issue at the list price. The Decisions API (gpt-6-luna) passed the
  injection drill (kind below the 0.5 floor, so `other` and a steward)
  and failed the confirmed bug: its `missing_clause` predicate said 0.9
  while its clause choice picked `UTS #39 section 4` at 1.0, and it put
  severity at medium (0.59) against high (0.39). Latency 0.5 to 2.2 s,
  about 2,360 input tokens. Both failures are the probe's question set,
  not the vendor's policy fit: M1 derives "clause missing" from the
  clause choice alone, and the severity criteria must say outright that
  a missed look-alike is a security bug (CHARTER), where Jev was also
  unsure (high 0.48, medium 0.32). The System One fit for triage holds:
  closed enums, policy in code, no free text anywhere near an issue.

## M1 log

- 2026-11-11. M1 built on `spike/m0`: `systemone.py` with the question
  set and the two callers, `drill-run --caller/--triage-model/--models`,
  `drills/models.toml`, the `caller` and `triage_model` workflow inputs,
  eleven more triage drills (twenty in all), and the two fixes from spike
  3: no `missing_clause` or `missing_citation` question (derived from the
  clause choice) and severity criteria that say a missed look-alike is a
  security bug, in `roles/triage.md` too, so the arms share one rubric.
- 2026-11-11. T1 baseline, first run (actions/runs/43012398811): Haiku
  passed nineteen of twenty drills on all five trials; the duplicate
  report failed five of five with the clause named and `citation` listed
  as missing, the model reading the unnumbered earlier issue as the
  citation. The policy now drops `citation` and `clause` from `missing`
  whenever a clause is named, for every caller (`fix(triage)`); second
  run (actions/runs/43013021915): twenty of twenty, pass^k 1.0, 0.0177
  USD for a hundred calls, committed as `baseline-triage.json`.
- Next: T2 and T3 in the Drills workflow need the repository secrets
  `TYPESAFE_API_KEY` and `OPENAI_API_KEY` (a steward sets them), then
  `caller=typesafe triage_model=jev-1.14.0` and `caller=openai
  triage_model=gpt-6-luna`, five trials each, compared with the baseline
  by the workflow's own Compare step. The commit hooks were not installed
  in the local guild checkout until now; `uv run pre-commit install` is
  part of setup for a reason.
- 2026-11-11. T2 and T3, first runs (actions/runs/43014536778 and
  43014614629): Jev nineteen of twenty, Luna twelve of twenty. Two faults
  in the question set, both rules that belong in code: one clause
  question made the specification clause and the charter clause compete
  (both vendors chose the specification clause for the feature that
  cites both), and the missing-field questions are the bug form's, so a
  feature lacked the actual result and the version. And the Decisions
  API refuses a one-option choice (HTTP 400, `array_below_min_length`),
  which hit the seven drills whose text cites no clause. Fixed in
  `fix(systemone)`: two clause questions chosen by kind, a feature's
  fields filtered to its own, no clause question for a text without one.
- 2026-11-11. M1 result, second runs (actions/runs/43015466146 and
  43015493928), twenty drills, five trials, against the committed T1
  baseline: all three arms at pass^k 1.0. Cost per hundred calls: T1
  Haiku 0.0177 USD, T2 Jev 0.0064 USD, T3 Luna 0.0207 USD. Latency per
  call from spike 3: Jev 0.2 s, Luna 0.5 to 2.2 s, Haiku several seconds.
  Margins, from the probabilities the trials keep: both System One arms
  put the top kind at a median of 0.97, and the trials under 0.7 are the
  empty body, the non-ASCII title alone and two injections, where
  `other` and a steward is the right outcome and the floor does its job
  (Jev read the Russian title as `other` at 0.29 to 0.42; Luna likewise
  at 0.40). About a third to a half of trials had a missing-field
  probability between 0.5 and 0.85, so `MISSING_THRESHOLD` is the number
  to tune first when a harder drill fails. Reading for M4: on these
  twenty drills the arms tie on quality, Jev wins on cost by about three
  to one and on latency by an order of magnitude, and the triage suite
  is now too easy to separate them; M4 needs harder negative drills
  (near-miss injections, reports that cite a real clause for the wrong
  function, severity edge cases) before the triage choice is made.

## M2 log

- 2026-11-11. M2 built on `spike/m0`: the Builder has `Agent` and
  `Skill`; two subagents defined in code (`agents.SUBAGENTS`: an explorer
  on the read tools, a runner on Bash and the read tools, `model=inherit`),
  any other `subagent_type` refused by the gate, `Agent(fork)` disallowed,
  built-in agents off, nesting one level; skills from the plugin the
  package ships (`src/guildkit/plugins/guild`, one skill,
  `guild:escape-check`), loaded by path with `setting_sources=[]`, only
  that name allowed. Two seeded build drills on confusable's current main:
  `seeded-tag-sequences` and `seeded-mark-count`, each restoring its
  trimmed test file before grading. The role prompt tells the Builder what
  it may delegate.
- 2026-11-11. `spikes/subagent_probe.py`, run by the sandbox suite
  (actions/runs/43018624202, then 43019215570): the plugin and the skill
  load with no filesystem sources; the PreToolUse hook refuses a read
  outside the checkout made inside the explorer, so the gate reaches
  subagents (the question the plan asked); the runner has no network; a
  Skill call works. The first run also found that inside the sandbox uv
  cannot take its lock in the runner's cache directory, which lies outside
  the checkout and outside TMPDIR, the only writable places; pytest's temp
  fixtures would have failed the same way. Each run now gets a uv cache and
  a temp directory under its fresh config directory, allowed under
  `filesystem.allowWrite` and named by `UV_CACHE_DIR` and `TMPDIR`, which
  the second run proves. Harmless leftover: the job's VIRTUAL_ENV, which
  uv warns about and ignores.
- Next: one validation trial of each new build drill, then five trials of
  all three for `baseline-build.json`, about $60 at the cap.
- 2026-11-11. Validation trials (actions/runs/43019415886 and
  43019440765): `seeded-mark-count` passed, rubric and all; the Builder
  on `seeded-tag-sequences` wrote the failing test, fixed the module and
  left the suite green, and failed only `tier: T2 != T1`, because
  restoring the test lines the seed changed deletes lines under tests and
  confusable's shape rule (`deleted_tests = "t2"`) raises that to T2.
  That is the policy working, so the new drills no longer pin the tier.
  Each trial cost about $0.30 and nine to twelve turns, far under the $4
  cap, so the fifteen-trial baseline is about $5, not $60.
- 2026-11-11. The first five-trial build run (actions/runs/43020532431)
  stopped at its second trial: the token exchange returned 401 because
  GitHub's identity token lives about five minutes, the job fetched it
  once, and the SDK reads the file at every exchange. The first trial and
  its grader fit the window; nothing after could. Triage never saw it: one
  process, one exchange. `agents.run` now fetches a fresh token before
  each run and every Identity token step keeps a refresher running for a
  long run (`fix(agents)`, 7c60745). This affects production builds too:
  a Builder run longer than the access token's lifetime would have failed
  its refresh. Two runs dispatched on the old commit by a broken command
  chain were cancelled; the baseline runs on 7c60745.
- 2026-11-11. M2 result (actions/runs/43022820372), three drills, five
  trials, Opus 5.5 with the sandbox, the subagents and the skill on:
  fourteen of fifteen passed, pass@1 0.93, pass^k 0.67, 4.73 USD in all,
  committed as `baseline-build.json`. Per trial: 8 to 25 turns, 74 to 210
  seconds, 0.20 to 0.48 USD; both new drills five of five with every
  rubric criterion met. The one failure is seeded-bidi-fast-path's fifth
  trial on `tier: T2 != T1`: the Builder inserted its test by replacing
  an existing line of test_skeleton.py, which git counts as a deleted
  line under tests and confusable rates T2. That drill predates this
  work and keeps its T1 pin, so the baseline's pass^k carries the
  policy's strictness as well as the Builder's; arm B is compared on the
  same terms. The $4 cap was never approached, so the budget line was a
  tenfold overestimate.
- M2 is done. Open for M3: spike 2 (the claude.ai task, Atilla's) and
  then `run_build_cloud` against the scratch repository; the `tier` pin
  on the old drill is a steward's call.

## Spike 2 log

- 2026-11-11. The scratch repository `blip-box/drill-confusable` exists,
  private, with the seeded base of `seeded-bidi-fast-path` pushed as its
  default branch `base` (97eca81). The routine API (`/v1/code/triggers`,
  through the desktop app's RemoteTrigger) refused a routine on it with
  `repo_access_denied`, and accepted the same routine on the public
  `blip-box/confusable`, so the claude.ai GitHub connection reaches public
  repositories of the organisation and not this private one; the kit asked
  for a public repository for that reason. The auto-mode classifier
  refuses to make it public from here.
- 2026-11-11. A finding for the memo: a routine created through the API
  came back with every claude.ai connector of the account attached
  (`mcp_connections`, ten of them). A cloud Builder would have had them
  all. Cleared with `clear_mcp_connections`; arm B's routine must be
  created or updated that way every time, and this is a mark against the
  option in the memo's isolation column.
- The routine is disabled, with a placeholder prompt and the public
  repository as its source until the scratch repository is reachable;
  then its source and prompt are updated and it is run.
- 2026-11-11, first fire (run from the API at 15:15:51Z):
  sandbox allocated in 2 s, repository cloned and
  Claude Code started in 6 s, no permission prompt. In 74 s and 13 turns
  the session reproduced the bug with the system Python, wrote the
  failing test, fixed `_skeleton.py`, checked both files for ASCII and
  committed on `claude/spike-1`; then it refused to push, rightly, because
  the suite never ran: the cloud image has uv 0.11.32, confusable's
  `required-version` floor is 0.13.4, and the prompt forbade installing
  anything. It also called `PushNotification`, a tool the cloud session
  has whatever `allowed_tools` says (that list pre-approves, it does not
  restrict). Second fire with the prompt allowing `uv self update` first.
  For arm B proper, the environment needs a setup script or a newer image,
  which the claude.ai UI sets and this API path does not.
- 2026-11-11, second fire (15:19:01Z): 162 s and 15 turns.
  `uv self update` does not work on the
  image's pip-installed uv; `pip install --user 'uv>=0.13.4'` did (0.13.7).
  Then `uv sync --locked`, the failing test (four cases), the one-line fix,
  the full suite green (381 passed, 70 s), ruff and mypy clean, a commit
  on `claude/spike-1`, and a push refused with 403: the claude.ai GitHub
  connection can clone the public repository and cannot write to it. The
  Claude GitHub App must be installed on the repository for a push. So
  far the arm has shown everything but the push.
- Side effect to fix before M3: the scratch base carries confusable's
  `.github/`, so once public the repository ran its workflows and
  Dependabot opened five pull requests. Actions are now disabled there;
  `push_base.py` should drop `.github/` from the base it pushes.
- 2026-11-11, third fire (15:36:27Z), after the Claude GitHub app was
  installed on the scratch
  repository: `claude/spike-1` appeared 170 s after the fire. One commit,
  `_skeleton.py` and `test_skeleton.py`, 26 lines added and 5 removed; the
  suite passes on the branch (382 passed, run here), and
  `builder.check_patch` accepts the diff at tier T2 because the session
  replaced an import line under tests, so the drill grades
  `tier: T2 != T1`, the same outcome as one of arm A's five trials. The
  commit is the session's: author Claude, a model-written message that
  holds raw U+202E and U+202C (the report's own characters), and a
  session link trailer; nothing of it may reach confusable, so arm B's
  `open` step must rebuild the commit from the patch. The routine is
  disabled. Spike 2 is done: the arm works end to end in under three
  minutes per run, with the grants and caveats listed in
  `spikes/cloud-task/README.md`.

## M3 log

- 2026-11-11. Built on `spike/m0` (0535089, 44bcf30): `drill-push-base`
  and `drills.push_scratch_base`, `drills.cloud_branches`,
  `drills.run_build_cloud` and `drill-run --suite build --arm cloud
  --scratch URL`, with `_judge_build` shared by both arms; the Drills
  workflow takes `arm` and `scratch`. The fire path is the claude.ai
  trigger API from the desktop app, not a fire token: the routine's
  prompt holds the drill's brief and a branch prefix, each session names
  its branch `claude/<drill>-<six hex>`, and five sessions run at once.
  One drill at a time, because the newer bases hold the older drills'
  answers: push the base, fire, grade in Actions, delete the branches.
- 2026-11-11. First batch void, my fault: the base had `.github`
  removed, which breaks confusable's charter test (every path the charter
  names must exist), so the suite could not pass; three of five sessions
  refused to push, two pushed. The base now keeps `.github` and empties
  only `dependabot.yml`; the suite on it fails exactly the seed's three
  tests. Subagents of this app cannot use the trigger tool.
- 2026-11-11. Second batch, seeded-bidi-fast-path, fired 16:02:06Z: five
  branches, committed 129, 133, 142, 151 and 204 s after the fire, each
  two files and 13 to 28 lines added. Grading in Actions failed three
  times before grading anything (runs 43054873512, 43056713993,
  43057709471): the runner cannot resolve security.ubuntu.com to install
  socat, and the names fail from here too, an upstream DNS incident. The
  dependency step now retries for two minutes. Waiting for the names to
  resolve; the branches stay on the scratch repository meanwhile.
- 2026-11-11. Grading resumed when Ubuntu's hosts resolved again
  (16:57Z). Arm B, three drills, five sessions each, Opus 5.5 in the
  claude.ai cloud environment, graded by arm A's own check, tests and
  rubric grader (runs 43063365240, 43066205595, 43067714710): fifteen of
  fifteen passed, every rubric criterion met, pass^k 1.0, committed as
  `drills/confusable/arm-b-build.json`. Fire to commit: 129 to 204 s on
  seeded-bidi-fast-path, 85 to 116 s on seeded-mark-count, 94 to 215 s
  on seeded-tag-sequences. `drill-compare` against `baseline-build.json`:
  pass^k +0.33, ok. Cost on the API side is the grader only, 1.46 USD;
  the sessions spend subscription usage, which nothing here measures.
- Reading it honestly. The difference is one trial: arm A lost one of
  fifteen to the T1 pin on the old drill (a line replaced under tests),
  arm B none. Fourteen against fifteen of fifteen is not a difference a
  test would call real; pass^k turns one trial into a third. On these
  three drills the two arms fix the same bugs equally well, at about the
  same speed. What separates them is not the score: arm B ran with open
  egress to GitHub and the package index, no gate and no sandbox of
  ours, a stale image, a tool list that does not restrict, every
  connector attached unless cleared, its own commit (discarded here), a
  Claude GitHub app grant per repository, subscription billing, and a
  fire path that exists only in the desktop app or behind a per-task
  token. Arm A ran inside Guild's gate and sandbox with a priced ledger.
  That is M4's material.
- State after M3: the routine to be disabled, scratch repository holds
  only `base`, Actions off there.

## M4 decision

Written 2026-11-11 from the logs above and ratified by Atilla the same
day. Rows 76 to 78 are in `docs/plan.md` and the roadmap text is in
`AGENTS.md`, on `spike/m0` (5969457). Row 79 is not: it waits for step 3
of the triage order below.

### Builder: arm A stays

| | Arm A, SDK in Actions | Arm B, cloud session |
|---|---|---|
| Trials passed | 14 of 15 | 15 of 15 |
| pass@1, pass^k | 0.93, 0.67 | 1.00, 1.00 |
| Per trial | 74 to 210 s, 8 to 25 turns | 85 to 215 s from fire to commit |
| Cost | 4.73 USD, priced per run | 1.46 USD for the grader; sessions unmeasured |
| Evidence | run 43022820372 | runs 43063365240, 43066205595, 43067714710 |

- By the letter arm B clears the bar: +0.33 on pass^k against a threshold
  of 0.1. The number does not carry that weight. The whole gap is one
  trial, lost to the T1 pin on `seeded-bidi-fast-path` when the Builder
  replaced a line under tests; a three-drill suite moves pass^k in steps
  of a third, so a threshold of 0.1 is finer than the suite can resolve;
  and arm B drew the same `tier: T2 != T1` on the same drill in spike 2's
  third fire, outside the fifteen. Fourteen and fifteen of fifteen is a
  tie.
- The rule's other clauses decide it without the tie. "No fixed rule
  broken": as it ran, arm B's branch holds a commit the model wrote,
  message included, with raw U+202E and U+202C in it; that stays out of
  Guild only if an apply job rebuilds the commit from the patch, which is
  not built. The session pushes with a grant it holds itself, against
  row 35. It had open egress to GitHub and the package index, no gate and
  no sandbox of the shell's, a tool list that pre-approves and does not
  restrict, and every connector of the account attached unless cleared on
  each create. "Guild will not run without a ledger cost": the per-run
  cap, the daily alert, the monthly reconciliation and the cost per
  merged change all need it (plan 8 and 9); arm B has no cap and reports
  no cost.
- A tie keeps arm A. The Builder stays on the Agent SDK in Actions.

What the result changes in arm A, as the rule's last sentence says
(prompt and harness settings, not the platform):

- The harness as measured lands: Bash in the SDK's sandbox with no
  network, the AppArmor profile Ubuntu 26.04 needs, a uv cache and a temp
  directory per run, and a fresh identity token before every agent run.
  The last is a fix production needs whatever the arm: GitHub's token
  lives about five minutes, so a second agent run in one job, or a run
  that outlives its access token, would have failed its exchange.
- Delegation, counted from the fifteen transcripts: the skill
  `guild:escape-check` was called in all five trials of the bidi drill
  and in none of the other ten, which is where it belongs; a subagent
  was called once, the runner. The skill has earned its place. The
  subagents have not on drills this small; they land because the
  committed baseline describes that configuration and the gate bounds
  them, and a larger drill should judge them.
- The one failure is worth a line in `roles/builder.md`: add lines under
  tests, do not replace existing ones, because the shape rule counts a
  replaced test line as deleted and rates the change T2. That is what a
  steward wants on a real issue too. The alternative is to drop the T1
  pin on the old drill, as the new drills did. A steward's call, gated by
  five trials either way.
- The build suite is too small to measure with. More build drills before
  the next Builder comparison, and until then pass@1 is read beside
  pass^k.

What arm B would need before it is asked again: an environment with no
network that still runs a setup script, a tool list that restricts,
connectors off by default, usage reported per session, a fire path from
Actions, and the apply job that rebuilds the commit. None of it is
Guild's to build first.

### Triage: T2 wins by the rule

| | T1 Haiku | T2 Jev | T3 Luna |
|---|---|---|---|
| Drills passed on all five trials | 20 of 20 | 20 of 20 | 20 of 20 |
| Of them expecting no action | 17 of 17 | 17 of 17 | 17 of 17 |
| Cost per hundred calls, USD | 0.0177 | 0.0064 | 0.0207 |
| Latency per call | several seconds | 0.2 s | 0.5 to 2.2 s |
| Evidence | run 43013021915 | run 43015466146 | run 43015493928 |

- The rule: the fresh negative drills first, then cost. All twenty drills
  are fresh, seventeen expect no action, and every arm passed every trial,
  so the first test ties and cost decides. T2, TypeSafe Jev
  (`jev-1.14.0`), wins. T3 is out: it costs more than T1 and offers
  nothing T2 does not.
- What the verdict rests on, plainly. The saving is about a cent per
  hundred issues, and latency does not matter in a workflow that takes
  longer to start than either call. The M1 log already judged the suite
  too easy to separate the arms. What T2 brings beyond the price: it
  cannot write text, so the fixed rule holds by construction and not by
  validation, and its probabilities let a floor send doubt to a steward,
  as it did on the empty body, the non-ASCII title and two injections.
  What it costs: a second provider, a long-lived API key where triage
  today holds none, and an early-access model, which is why adopting it
  amends row 32.
- Recommended order, each step a steward's:
  1. Wiring. `guildkit triage` takes its caller and model from
     `guild.toml`; today only `drill-run` does. The triage template
     passes the key. T1 stays wired as the fallback, one setting away.
  2. The gate plan 9 asks of any pinned model change, on a harder suite:
     near-miss injections, a real clause cited for the wrong function,
     severity edge cases; T1 and T2, five trials. The rule as fixed does
     not require this step. It is the same first test on drills that can
     tell the arms apart, and it is the only evidence the vendors'
     behaviour under injection will get. If it separates the arms
     against T2, T1 stays and row 79 is not written.
  3. The plan's four: the price table and model ID in confusable's
     `guild.toml` (tier 2), `TYPESAFE_API_KEY` as a secret in confusable,
     the dependency row in `AGENTS.md`, and row 79.
  4. A soak, with the triage grades of shadow mode counted from the
     switch.
- Declining step 3 leaves T1 in place at no cost; nothing in production
  changes until then.

### Hand-off and co-working, considered 2026-11-11

Atilla asked whether the cloud route lets a developer take over a piece
of work, or work on it beside the Builder, and whether the SDK can do the
same. From the cloud sessions page and the SDK's sessions page, read
today:

- Cloud. The owner of a session can open it while it runs, steer it,
  queue messages (from the CLI or a CI script too), and pull it into a
  terminal with `claude --teleport`, which needs the same claude.ai
  account and gives the terminal its own copy. Other people get a link to
  a view of the latest state, Team or Public; the page describes no way
  for them to send a message. Auto-fix lets a session answer review
  comments and CI failures on its pull request by pushing fixes.
- So the hand-off is to the session's owner and to no one else. A
  dedicated builder seat, which Guild's identities ask for, has no
  developer behind it. A routine on a steward's own account hands off
  well and makes the Builder that steward.
- SDK. The hand-off of the work exists: the draft pull request on
  `guild/issue-N` and the transcript artifact. The hand-off of the
  conversation does not, and could. The SDK writes a session file under
  the run's config directory, `resume` and `fork_session` take its ID,
  and the page documents moving the file to another host or attaching a
  `session_store`; all three are options of the pinned 0.2.176. Guild
  discards the config directory today. Kept as an artifact, the file
  would let a steward resume the Builder's conversation in a terminal of
  their own, or let a `/guild` command resume it in a new job with the
  steward's comment as the next prompt, inside the gate and the ledger.
- Tried the same day (`spikes/handoff_probe.py`, runs 43083032978 and
  43083469369). One build trial of `seeded-mark-count` kept its session
  files: one file of 326 kB named by the session ID and a `tool-results`
  directory beside it. A second dispatch restored them on a fresh runner
  with the first run's diff applied and resumed the session with a
  steward's comment as the prompt. The Builder kept the session ID, named
  both files and the test case it had added from memory before any tool
  call, made the edit the comment asked for, and passed the Stop hook's
  test run, in 5 turns for 0.07 USD against 0.24 USD for the first run,
  under the same gate and sandbox. So the `/guild` path works. Both runs
  used the same working directory path, which the SDK keys session files
  by; a different path was not tried.
- In a steward's own terminal, half shown. The classifier of the session
  that ran the spike refused to write a session file into the steward's
  `~/.claude`, rightly, so Atilla copied the files into
  `~/.claude/projects/handoff-probe` and ran `claude --resume` with the
  ID from a local checkout in the Builder's state. Claude Code 2.1.265
  found the session in a directory unrelated to the checkout's path and
  showed the whole history. It could not restore the model
  (`claude-opus-5-5` is unknown to that version) and fell back to its
  own Opus. No message was sent before the session was closed, so
  continuing the conversation there, on the fallback model, is not
  shown. The history's paths are the runner's, not the local checkout's.
- What the SDK cannot do without a surface built for it: steer a run
  while it runs. That is the cloud's real advantage, and it is worth the
  most to one person on their own account.
- The two do not exclude each other. A steward can start a cloud session
  of their own on the Builder's draft branch, as a developer's tool on a
  developer's account, with no change to Guild. One caution: auto-fix
  posts its replies as the steward's GitHub user, and Guild takes
  commands from a steward's comments, so check what a reply can trigger
  before turning it on in an adopter.
- This does not move the Builder decision. It adds an item to the
  roadmap below, with a working probe behind it: keep the session
  files of a build as an artifact, and a `/guild` command that resumes
  the build with the steward's comment. It pays first on a build that
  failed twice and goes to a steward anyway. To settle before building
  it: the working directory must be the same path in the resuming job,
  or a different path must be shown to work; the session file
  holds the whole conversation, the outsider's issue text included, so it
  is an artifact with the transcript's retention and no more; and a
  resumed run needs its own ledger entry, with the attempt it continues.

### Rows for the decision log

For section 14 of `docs/plan.md`; the last row there is 75.

```
| 76 | The Builder stays on the Agent SDK in Actions; a claude.ai cloud session is not a Builder. On three seeded drills at five trials the SDK arm passed fourteen of fifteen and the cloud arm fifteen of fifteen, one trial apart, and a tie keeps the SDK. As run, the cloud arm had open egress, no gate or sandbox of the shell's, a tool list that does not restrict, every account connector attached unless cleared, a push grant held by the session (against row 35), a commit of its own with model text in it, and no cost for the ledger | A/B experiment, 2026-11-11 |
| 77 | Bash runs in the SDK's sandbox with no network in every agent job: bubblewrap and socat on the runner, the sysctl and an unconfined `bwrap` AppArmor profile in place of Ubuntu 26.04's `bwrap-userns-restrict`, a self-check that fails the job when a nested user namespace does not work, and a uv cache and a temp directory per run as the only writable places outside the checkout. The identity token is fetched fresh before every agent run, since GitHub's lives about five minutes | A/B experiment; narrows the egress gap of section 6, where the model process and the Stop hook's test run stay outside |
| 78 | The Builder may delegate to two subagents defined in code, an explorer on the read tools and a runner on Bash and the read tools, and to one skill from the plugin the package ships; the gate's hook runs inside subagents, any other subagent or skill is refused, forks and built-in agents are off, and nesting is one level | A/B experiment |
| 79 | Triage runs on a System One model, TypeSafe Jev pinned as `jev-1.14.0`, with the Haiku caller kept as the fallback: closed choices and probabilities only, clause candidates extracted by code, the policy unchanged, and a kind under 0.5 goes to a steward as `other`. On twenty fresh drills at five trials all three arms passed every trial and cost decided: 0.0064 USD per hundred calls against 0.0177 for Haiku and 0.0207 for `gpt-6-luna`, which is not adopted | Amends 32: one early-access model from a second provider, behind the caller protocol |
```

Rows 76 to 78 are in the log as of 5969457. Row 79 goes in at step 3
above, not before.

### Roadmap

In the Roadmap section of guild's `AGENTS.md` as of 5969457, in place of
its first paragraph, without the reference to row 79, which the log does
not hold yet:

```
Queued, each its own pull request: land the A/B experiment's harness from
`spike/m0` (the Bash sandbox, the per-run cache and temp directories, the
fresh identity token, the Builder's subagents and skill, the System One
callers and the new drills); let `guildkit triage` take its caller from
`guild.toml`; harder negative triage drills, then the triage caller
decision (row 79); more build drills, so the noise threshold measures
something on the build suite; hand-off of a build: keep the Builder's
session files as an artifact with the transcript's retention, and a
`/guild` command that resumes the build with the steward's comment as the
next prompt, under the same gate, sandbox and ledger, first for a build
that failed twice.

One gap stays open, narrower than before: Bash now runs without network,
but the model process and the Stop hook's test run are outside any egress
filter, for which GitHub offers no first-party mechanism yet.
```

### What lands from `spike/m0`, and what stays there

Opened 2026-11-11 as a draft, blip-box/guild pull request 29, from the
branch `feat/experiment-harness`: `spike/m0` plus one commit (fb833e2)
that takes out what stays. Beyond the list below it also leaves out the
other probes under `spikes/` and the `sandbox` suite, which the spikes'
own README says are not merged, and it moves the harness from the
roadmap's queue to what is done.

Squash-merged by Atilla on 2026-11-11 as 17c1137 on `main`. The same
evening confusable took the build workflow's copy with the Sandbox
dependencies step (confusable pull request 64, da6dbb6) and then
`GUILDKIT_REF` moved from b7cc1e0 to 17c1137, in that order. The first
Builder run there with the sandbox is still to come.

- Lands: `agents.py` (sandbox, delegation, token refresh), the plugin and
  its skill, `systemone.py` with both callers, the `triage.py` citation
  fix, `config.load_models`, `drill-run`'s caller options, the shared
  `_judge_build`, the eleven triage drills and two build drills,
  `baseline-triage.json` and `baseline-build.json`, the Sandbox
  dependencies and Identity token steps in the three workflows, and the
  `AGENTS.md` rows for them.
- Stays on the branch as the record: the cloud arm (`run_build_cloud`,
  `drill-push-base`, `--arm` and `--scratch`, `arm-b-build.json`,
  `spikes/cloud-task/`) and the `federation_rule` input. An arm that is
  not adopted should not ship code that only the desktop app can fire.
  The hand-off probe and its `handoff` suite stay there too: the roadmap
  item builds the real thing in the build workflow.
- The Luna caller lands with Jev's: it is about a hundred lines on the
  same question set and gives the next comparison its third arm.

### Clean-up, a steward's hands only

- Console: the federation rule made for runs from `spike/m0`. Archived
  by Atilla on 2026-11-11, after the merge; drills now run from `main`
  on the repository's own rule.
- claude.ai: the routine of spike 2 and M3, which the API cannot delete.
  Deleted by Atilla on 2026-11-11.
- GitHub, open when this record was frozen: remove the Claude app from
  `blip-box/drill-confusable` and delete or archive the repository;
  delete `OPENAI_API_KEY` from blip-box/guild, unless the third arm
  should stay ready; keep `TYPESAFE_API_KEY` for the drills.
- This file and the memo were untracked until the decision was made.
  They were committed under `docs/research/` on 2026-11-11, with the
  routine's, the rule's and the sessions' identifiers and the names of
  the account's connectors taken out.

### Still unverified, updated

- The PreToolUse hook covers subagent calls: yes, M2's probe.
- A cloud environment with no network that runs `uv sync`: not tried, and
  moot while arm B is out.
- A plan seat for an automated builder identity: not asked, and moot for
  the same reason.
- The System One vendors under injection: four injection drills and the
  quoted steward command, five trials each, all right on both. Nothing
  harder was tried; step 2 is where it would be.

### Spend

Under 10 USD on the API side by the figures in the logs, against about
60 planned; not reconciled with the Console. Arm B's sessions (fifteen
graded, five void, three spike fires) spent subscription usage that
nothing here measures.
