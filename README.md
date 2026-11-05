# Guild

Agent-run maintenance for open-source libraries, under human stewards.

Guild runs the routine work of a library with agents: triage, planning,
building, review and release proposals. A small number of stewards own the
direction, approve every code change and run every release. Outside
contributors take part through issues and comments.

The rule every other control serves:

> Nothing a model wrote is executed or obeyed with more privilege than the
> model had, until a plain check or a steward has passed it.

This repository is the shell, a Python package named `guildkit`. An adopting
repository holds only what makes it different: a `CHARTER.md` with numbered
clauses, a `guild.toml` with its tiers, budgets and pinned models, and thin
workflows that call the shell. The first adopter is
[blip-box/confusable](https://github.com/blip-box/confusable).

> **Status: shadow mode is being built.** The shell exists and is tested:
> escaping untrusted text, issue snapshots, risk tiers, the ledger, steward
> commands, the triage call with its policy, the Planner, Builder and
> Reviewer on the Claude Agent SDK with the plain check on their patches, the
> drills that gate changes to any of it, and the ledger with its brakes and
> weekly report. Nothing has run against a live repository yet.

## How a piece of work moves

1. **Intake** (no model). A script fetches the issue or comment, turns the
   Markdown into plain text and writes every character outside printable
   ASCII as `U+XXXX`, a notation that JSON never decodes back. The hidden
   characters are listed, found with `confusable` itself.
2. **Oracle check** (no model). For a bug, the structured reproducer runs
   against the library's independent oracles before anyone spends time.
3. **Triage** (one model call, no tools). The model returns a record of closed
   enumerations. Plain code applies the rules: a bug needs a confirmed
   reproducer and a citation, a feature needs the charter clause it serves.
4. **Post** (no model). A job holding the Triage App's token validates the
   record and posts labels and a templated comment. No model text reaches the
   issue.
5. **Plan, build, review** (agents, through the Claude Agent SDK) produce a
   patch that a plain job opens as a pull request. Every tier needs a steward
   to merge. Releases are proposed by a script and run by a steward.

Every run writes one line to a public ledger: role, model, tokens, cost,
outcome, citation, who decided. No free text.

## Development

```bash
uv sync
uv run pre-commit install
uv run pytest
uv run pre-commit run --all-files
```

[AGENTS.md](AGENTS.md) has the conventions. [docs/plan.md](docs/plan.md) is
the design, with its decision log; [docs/research/](docs/research/) is the
research it rests on.

## License

MIT. See [LICENSE](LICENSE).
