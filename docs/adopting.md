# Adopting Guild

What a repository adds to run under Guild, and what its stewards set up
outside the repository. The shell itself stays in `blip-box/guild`; the
adopter pins one commit of it.

## In the repository

- `CHARTER.md`: mission, scope, non-goals and principles as numbered clauses
  with stable IDs. Triage cites them; changing the file is tier 2.
- `guild.toml`: copied from `templates/guild.toml` and edited: the stewards,
  the tier rules, the agents' models, limits and test command (`[planner]`,
  `[builder]`, `[reviewer]`), the Builder's second attempt
  (`[builder.second_attempt]`, optional), the release rules (`[release]`:
  the library paths, the staleness, the version files, the pre-release
  series), the counts that end shadow mode (`[shadow]`: the steward grades
  per role and the canary passes in a row; remove the table when shadow
  ends), and the prices. Tier 2, and on the reject list.
- `.github/workflows/guild-triage.yml`, `guild-build.yml`, `guild-batch.yml`,
  `guild-report.yml` and `guild-release.yml`: copied from
  `templates/workflows/`. Workflows are on the reject list: agents draft them,
  a steward commits them. The build workflow runs on a steward's `/guild plan`
  or `/guild build` under an issue, checked against `guild.toml` and the
  steward's live permission; it installs the shell with its `agents` extra.
  The release workflow runs on every push to the default branch (set its
  branch name) and weekly, and proposes a release as an issue when one is due.
  The batch, report and release workflows are scheduled: add all three to the
  `scheduled` job of the repository's CI, which fails while a scheduled
  workflow is disabled, as they open an issue when they fail.
- `.github/ISSUE_TEMPLATE/`: copied from `templates/ISSUE_TEMPLATE/`. The bug
  form's fields are what the oracle check reads.
- `tools/guild_oracle_check.py`: the adopter's oracle check (below). Optional:
  without it every bug report is escalated to a steward.
- `.github/CODEOWNERS`: the stewards own every path, so "require review from
  code owners" in the branch ruleset mirrors tier 1 and above. Rulesets with
  path-restricted pushes are not available on public repositories, so the
  reject list is enforced by the tier check, not by GitHub.

## The oracle check

A script the intake job runs from the base branch, with no secrets and no
network beyond the adopter's own checkout:

    python -I tools/guild_oracle_check.py --snapshot snapshot.json --out oracle.txt

It reads the escaped snapshot (`guildkit.snapshot.Snapshot` as JSON), finds
the structured fields the bug form produces (Code points, Function called,
Expected result, Actual result), and writes one word to `oracle.txt`:

| Word | Meaning |
|---|---|
| `confirms` | An independent implementation gives the expected result, and the library does not: a real bug. |
| `disagrees` | The independent implementation gives the library's result. A steward reads the specification; oracles have been wrong before. |
| `not_applicable` | No structured reproducer in the text (a feature, a question, prose). |
| `not_run` | The reproducer is there but the check could not run it here. A steward looks. |
| `error` | The script failed. A steward looks. |

The script runs the adopter's code from the base branch. It never executes
anything from the issue: the fields are data (code points, a function name
from a fixed list, expected values) that the script turns into a call.

## Outside the repository

Stewards create these; agents cannot. Set the kill switch (item 5) before the
workflow lands and clear it when the rest exists: a run on an issue opened
before then fails at intake, which is noise, not harm.

0. **The shell's visibility.** The workflow checks `blip-box/guild` out with
   the adopting repository's own token, which reads no other private
   repository, so `blip-box/guild` is public. The adopter never grants the
   workflow a token for it.
1. **The Triage App.** A GitHub App owned by the organisation with the
   repository permission issues: write and nothing else, installed on the
   adopting repository only. Its Client ID, from the App's settings page,
   goes in the variable `GUILD_TRIAGE_CLIENT_ID` (the token action retired
   the numeric App ID), its private key in the secret `GUILD_TRIAGE_APP_KEY`.
   Agent comments are posted as the App, so they are visibly Guild's.
2. **The Builder App and the Gate App.** Two more GitHub Apps, installed on
   the adopting repository only: the Builder App with contents: write and
   pull requests: write (variable `GUILD_BUILDER_CLIENT_ID`, secret
   `GUILD_BUILDER_APP_KEY`), which commits the patch through
   `createCommitOnBranch`, so the commit is signed, and opens the draft pull
   request; the Gate App with checks: write (variable `GUILD_GATE_CLIENT_ID`,
   secret `GUILD_GATE_APP_KEY`), which posts the Reviewer's verdict as the
   check run `guild/review`. Whether an App may open pull requests under the
   collaborators-only setting is undocumented; the first shadow build shows it.
3. **The model credential.** A Console workspace for Guild with a monthly
   spend limit (the only hard cap). Then workload identity federation: on the
   Console's Workload identity page, connect GitHub Actions, and pin the rule
   to this repository and `refs/heads/main`. GitHub issues an immutable
   subject by default, `repo:ORG@ORGID/REPO@REPOID:ref:refs/heads/main`;
   read the prefix with `gh api repos/ORG/REPO/actions/oidc/customization/sub`
   and put it in the rule's subject pattern, because the wizard writes the
   older `repo:ORG/REPO:...` form, which never matches (the Console's
   authentication events then say `match_subject_prefix`). The rule's
   allowed events must include every event, not only push: Guild runs on
   issues, comments, schedules and dispatches. The rule, organisation and
   service account IDs go in the variables `ANTHROPIC_FEDERATION_RULE_ID`,
   `ANTHROPIC_ORGANIZATION_ID` and `ANTHROPIC_SERVICE_ACCOUNT_ID`
   (`ANTHROPIC_WORKSPACE_ID` only for a rule over several workspaces). Until
   federation exists, a workspace-scoped service account key in the secret
   `ANTHROPIC_API_KEY`; the workflow never sets both.
4. **The pin.** The variable `GUILDKIT_REF`: the commit of `blip-box/guild`
   the workflows check out. Bumping it is how the shell changes for this
   repository, after the drills pass.
5. **The kill switch.** The variable `GUILD_PAUSED`; set it to `true` and every
   workflow skips its first job. Rehearse it.
6. **Labels.** The workflow creates the labels it uses (`guild:*`, `needs
   info`, `needs steward`, `spec disagrees`, `severity:*`) on first use.
7. **The ledger branch.** An orphan branch `guild-ledger` with an empty
   `ledger.jsonl`, created once by a steward:

       git checkout --orphan guild-ledger && git rm -rfq . && : > ledger.jsonl
       git add ledger.jsonl && git commit -m "ledger: start" && git push origin guild-ledger
       git checkout main

   Then a branch ruleset on `guild-ledger`: block force pushes and deletion,
   require linear history, and restrict updates with the Builder App as the
   only bypass, so only the ledger jobs append. Without the branch the ledger
   jobs warn and keep the entries in the run's artifacts, and the brakes see
   an empty ledger. The weekly report posts to an issue named "Guild weekly
   report", which a steward pins; `docs/operations.md` has the rest.

## Shadow mode

While Guild is in shadow, nothing merges without a steward, and nothing is
automatic beyond triage comments: a steward starts every plan and every build
with a command, the pull requests are drafts, and the Reviewer's verdict is a
check run, not a gate. Every decision is graded afterwards and
seeds the drills: a steward comments `/guild confirm <role>` or
`/guild overrule <role>` on the issue (`triage`, `planner`, `builder` or
`reviewer`), and the ledger records the grade. Shadow ends on a count of
clean decisions and passing drills, not on a date (docs/plan.md, section 13
and decision 73): the `[shadow]` table of `guild.toml` holds the targets, and
the weekly report shows the progress and says when every condition is met.
`docs/operations.md` says what each grade means and how shadow ends.
