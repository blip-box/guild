# Adopting Guild

What a repository adds to run under Guild, and what its stewards set up
outside the repository. The shell itself stays in `blip-box/guild`; the
adopter pins one commit of it.

## In the repository

- `CHARTER.md`: mission, scope, non-goals and principles as numbered clauses
  with stable IDs. Triage cites them; changing the file is tier 2.
- `guild.toml`: copied from `templates/guild.toml` and edited: the stewards,
  the tier rules, the pinned models and their prices. Tier 2, and on the
  reject list.
- `.github/workflows/guild-triage.yml`: copied from `templates/workflows/`.
  Workflows are on the reject list: agents draft them, a steward commits them.
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

Stewards create these; agents cannot. Set the kill switch (item 4) before the
workflow lands and clear it when the rest exists: a run on an issue opened
before then fails at intake, which is noise, not harm.

0. **The shell's visibility.** The workflow checks `blip-box/guild` out with
   the adopting repository's own token, which reads no other private
   repository, so `blip-box/guild` is public. The adopter never grants the
   workflow a token for it.
1. **The Triage App.** A GitHub App owned by the organisation with the
   repository permission issues: write and nothing else, installed on the
   adopting repository only. Its ID goes in the variable
   `GUILD_TRIAGE_APP_ID`, its private key in the secret `GUILD_TRIAGE_APP_KEY`.
   Agent comments are posted as the App, so they are visibly Guild's.
2. **The model credential.** A Console workspace for Guild with a monthly
   spend limit (the only hard cap). Then workload identity federation: on the
   Console's Workload identity page, connect GitHub Actions, and pin the rule
   to this repository and `refs/heads/main`. The rule, organisation and
   service account IDs go in the variables `ANTHROPIC_FEDERATION_RULE_ID`,
   `ANTHROPIC_ORGANIZATION_ID` and `ANTHROPIC_SERVICE_ACCOUNT_ID`
   (`ANTHROPIC_WORKSPACE_ID` only for a rule over several workspaces). Until
   federation exists, a workspace-scoped service account key in the secret
   `ANTHROPIC_API_KEY`; the workflow never sets both.
3. **The pin.** The variable `GUILDKIT_REF`: the commit of `blip-box/guild`
   the workflows check out. Bumping it is how the shell changes for this
   repository, after the drills pass.
4. **The kill switch.** The variable `GUILD_PAUSED`; set it to `true` and every
   workflow skips its first job. Rehearse it.
5. **Labels.** The workflow creates the labels it uses (`guild:*`, `needs
   info`, `needs steward`, `spec disagrees`, `severity:*`) on first use.

## Shadow mode

While Guild is in shadow, nothing merges without a steward, and nothing is
automatic beyond triage comments. Every decision is graded afterwards and
seeds the drills. Shadow ends on a count of clean decisions and passing
drills, not on a date (docs/plan.md, section 13).
