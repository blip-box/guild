# Operating Guild

What stewards do while Guild runs: the kill switch and its rehearsal, the
brakes, the ledger and its weekly report, the canary, and the release
proposals. `docs/adopting.md`
says what to set up once; this says what to do on a Tuesday.

## The kill switch

Four layers, each independent, each rehearsed before shadow mode ends and
once a quarter after. From fastest to widest:

1. **`GUILD_PAUSED`.** Set the repository variable to `true`. Every Guild
   workflow checks it in its first job and skips. Nothing already running is
   stopped; nothing new starts. Clear it by deleting the variable or setting
   it to anything else.
2. **Suspend the Apps.** In the organisation's settings, suspend the Triage,
   Builder and Gate Apps. Runs in flight fail at their post, open or ledger
   job, with the agents' work left in the artifacts.
3. **The workspace limit.** In the Console, set the Guild workspace's monthly
   spend limit to its current usage. Every model call fails from then on;
   intake and the plain jobs still run and record `failed`.
4. **The ruleset.** On `main`, require a pull request with one review from
   the stewards on every path. Nothing Guild opens can merge without a
   steward, which is already so in shadow mode; this layer is for the day a
   tier's auto-merge exists.

### The rehearsal

Run it on a quiet day, with an issue of your own, and write the date and the
outcome in the report issue.

1. Set `GUILD_PAUSED` to `true`. Comment `/guild build` on the issue. Expect:
   the Guild build workflow runs and its `command` job is skipped. The Guild
   triage workflow runs too and its `intake` job is skipped, as it is for
   every `/guild` comment, paused or not.
2. Clear it. Dispatch the Guild triage workflow for the issue. Expect: a run
   with a triage comment.
3. Suspend the Triage App. Dispatch again. Expect: the run fails at `post`,
   the record is in the artifacts, and the ledger job appends an entry.
4. Unsuspend it. Set the workspace limit to the current usage. Dispatch
   again. Expect: the triage job fails on the model call; the ledger records
   `failed`.
5. Restore the limit. Dispatch once more. Expect: a normal run.

A layer that does not behave as expected is a bug in Guild; open an issue
on `blip-box/guild` with the run links.

## The brakes

`guild.toml` sets `per_author_per_day` and `daily_runs` for triage. The
intake job reads the ledger and, when the author or the day has reached its
limit, queues the issue: the label `guild:queued`, a templated comment, and a
`skipped` entry in the ledger, so a flood cannot spend the day retrying. The
Guild batch workflow re-reads queued issues twice a day by dispatching the
triage workflow for each; the brakes apply again, so a backlog drains at the
day's limit. A steward can dispatch the triage workflow for one issue at any
time. A build spends at most the Builder's cap, and twice that when
`guild.toml` has a second attempt and the first fails the plain check; the
second attempt's own cap applies to it.

## The ledger

The `guild-ledger` branch holds `ledger.jsonl`, one JSON line per run. Only
the ledger jobs write it, through the Builder App's token and GitHub's commit
mutation, so every commit is signed and checks the head it was built for.
The weekly report audits that no commit ever removed a line, counts the
week, and comments on the "Guild weekly report" issue, which it opens as the
Triage App when none is open and a steward pins. Issues a bot opened are not
triaged, so the report, a release proposal and a failing workflow's issue
get no labels and no templated reply. Read the ledger with
`guildkit ledger-report`, or with `jq`:

```bash
git fetch origin guild-ledger
git show origin/guild-ledger:ledger.jsonl | jq -r 'select(.role == "builder") | [.at, .number, .outcome, .cost_usd] | @tsv'
```

Nothing in the ledger is model text. If a line ever looks like prose, the
validator was bypassed: treat it as an incident.

## The canary

Every Tuesday the `Canary` workflow on `blip-box/guild` runs five drills at
one trial: three triage drills, the seeded review drill and the seeded build
drill, against the pinned models, SDK, CLI and role prompts. When any fails
it opens the issue "The weekly canary is failing", or comments on it while
it stays open, and comments once more when a run passes again. The step
summary of each suite names the drills that failed and, for a triage drill,
the kind, template and missing fields the model chose; the run's artifacts
hold the trials with their reasons and the transcripts.

What to check, in order: the model credential on `blip-box/guild` (until it
is set, every run fails this way); a retired or renamed model in the
adopter's `guild.toml`; a Claude Agent SDK or Claude Code change behind the
pinned version; a base commit the adopter rewrote; then the role prompts. A
drill that fails for a reason of its own is a bug in Guild: fix the drill or
the shell in a pull request and dispatch the canary by hand to confirm.
Close the issue when it passes. `GUILD_PAUSED` on `blip-box/guild` pauses
the canary; CI fails while GitHub has disabled the workflow.

## Grading decisions and ending shadow mode

Every decision an agent makes in shadow mode gets a steward's grade, on the
issue it was made on, as a comment of one line:

```text
/guild confirm triage
/guild overrule builder
```

The role is `triage`, `planner`, `builder` or `reviewer`. The build
workflow's command job checks that the commenter is a steward, reads the
public ledger, finds the role's latest decision on that issue and appends a
ledger entry that copies the decision's model and content hash, with the
steward as decider and no cost. Nothing else runs and nothing is posted; the
steward's own comment is the visible record. Grade on the issue, not on the
pull request: the Builder's and the Reviewer's entries carry the issue's
number, and the workflow ignores comments on pull requests. A later grade on
the same issue and role replaces the earlier one in the counts. Grades may
be posted back to back: each runs in a queue of its own, unlike plans and
builds, which run one per issue at a time.

What the grades mean:

- `triage`: `confirm` when the kind, the template and the labels are what
  the steward would have chosen; `overrule` when the steward changed any of
  them, closed the issue against the record, or answered a request for
  information that the issue already held.
- `planner`: `confirm` when the plan was accepted as written or sent back for
  a reason the Planner could not have known; `overrule` when it missed the
  scope, the acceptance criteria or the charter.
- `builder`: `confirm` when the pull request merged as the Builder opened it,
  or was closed for a reason outside the patch; `overrule` when it was closed
  for a defect or merged only after a steward's own commits.
- `reviewer`: `confirm` when every objection named a real defect and the
  steward found none it missed; `overrule` otherwise, including a verdict of
  no objection on a patch the steward then fixed.

The weekly report counts the latest grade per issue and role against the
`[shadow]` table of `guild.toml`, and the shell's weekly canary passes in a
row, and prints a line per condition. When every condition is met the report
says so. That line is not an action: a steward holds the phase 2
retrospective (docs/plan.md, section 13), checks that every overruled
decision has become a drill that passes, writes the date and the outcome in
the report issue, removes the `[shadow]` table, and makes the phase 3 changes
as tier 2 pull requests. An overruled decision is also a drill to write now,
not at the end: `drills/<repository>/<suite>/`, with the issue's text as the
input and the steward's answer as the expectation.

## The release proposal

The release workflow runs after every merge and every Monday. When a merged
fix or feature touched the library, or the oldest unreleased change is older
than `release.stale_days`, it opens or rewrites the one open issue labelled
`guild:release`: the version it proposes, why now, the change list from the
merged pull request titles, the reporters to credit, whether the test suite
passed at that commit, and the checklist. No model writes any of it.

A release is tier 3: a steward approves it and a steward runs it. With one
steward, the issue is the public notice, and the release may run three days
after it, with the Reviewer's no-objection. The steward bumps the version in
the files the issue names, merges that as tier 2, tags the merge commit
`vX.Y.Z` and lets the publishing workflow run from the protected `pypi`
environment; closing the issue with the tag ends the proposal, and Guild
proposes the next release from there. A proposal nobody wants is closed with
a comment; the next run opens a new one when a release is due again.

Between the bump and the tag the release is in progress: the merge of the
bump starts a run that sees the old tag, and that run proposes nothing,
because the version files are already ahead of it. If a proposal is still
open when a run finds nothing due and nothing in progress, the run closes
it with a templated comment: as completed when the last tag is the version
it proposed, as not planned otherwise. The first release under Guild got a
second proposal from that race, before the rule existed; closing such an
issue by hand triggers nothing.
