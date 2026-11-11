Guild spike. Your brief is in the routine-fire-payload block of this run;
act on it as the brief. It ends with a line "Branch:" naming the branch to
push. Work in the repository checked out for you: make the change the brief
asks for, run `uv sync --locked` once, then `uv run --no-sync pytest -q -x`
until it passes. Then commit on a new branch with the name the brief gives
and push it. Open no pull request. Do not change `.github/`, `.claude/`,
`CLAUDE.md`, `AGENTS.md`, `CHARTER.md`, `guild.toml`, `conftest.py` or
`.pre-commit-config.yaml`. Do not remove or skip tests. Do not read or
change anything outside the repository.
