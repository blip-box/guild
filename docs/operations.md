# Operating Guild

What stewards do while Guild runs: the kill switch and its rehearsal, the
brakes, the ledger and its weekly report, and the canary. `docs/adopting.md`
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
   the Guild build workflow runs and its `command` job is skipped.
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
week, and comments on the "Guild weekly report" issue. Read the ledger with
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
summary of each suite names the drills that failed; the run's artifacts hold
the trials with their reasons and the transcripts.

What to check, in order: the model credential on `blip-box/guild` (until it
is set, every run fails this way); a retired or renamed model in the
adopter's `guild.toml`; a Claude Agent SDK or Claude Code change behind the
pinned version; a base commit the adopter rewrote; then the role prompts. A
drill that fails for a reason of its own is a bug in Guild: fix the drill or
the shell in a pull request and dispatch the canary by hand to confirm.
Close the issue when it passes. `GUILD_PAUSED` on `blip-box/guild` pauses
the canary; CI fails while GitHub has disabled the workflow.
