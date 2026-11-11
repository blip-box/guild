# M0 spike 2: one cloud scheduled task, fired by curl

Proves that a Claude Code scheduled task can take a drill brief, work in a
scratch repository and push a `claude/` branch without a human, and how
long that takes. Everything below is done by hand, once.

1. Create the scratch repository `blip-box/drill-confusable`, public, empty.
2. Push the drill's base:

       uv run --no-sync python spikes/cloud-task/push_base.py \
         --source ../confusable --drill seeded-bidi-fast-path \
         --remote git@github.com:blip-box/drill-confusable.git

   This clones confusable at the drill's base commit with nothing later
   reachable, applies the seed, and force-pushes the result as branch
   `base`. Make `base` the default branch in the repository settings.
3. At claude.ai/code/routines create a task: repository
   `blip-box/drill-confusable`; prompt: the text of `roles/builder.md`
   followed by `PROMPT.md`; environment: Limited with package managers
   allowed, no other hosts, setup script `uv sync --locked`; trigger: API.
   Copy the fire URL and the token into your shell as `ROUTINE_FIRE_URL`
   and `ROUTINE_FIRE_TOKEN`. Keep them out of every file.
4. Render the brief and fire:

       uv run --no-sync python spikes/cloud-task/brief.py seeded-bidi-fast-path \
         --branch claude/spike-1 > /tmp/brief.txt
       spikes/cloud-task/fire.sh /tmp/brief.txt claude/spike-1 \
         git@github.com:blip-box/drill-confusable.git

   `fire.sh` posts the brief, prints the session URL, then polls the
   remote every 30 seconds for the branch, up to 60 minutes.
5. Record: time to branch, the diff (`git diff base...claude/spike-1`),
   whether a permission prompt was left waiting in the session, and what
   the session did that the prompt did not ask for. Then delete the branch.

## Result, 2026-11-11

Run through the claude.ai trigger API (`/v1/code/triggers`, from the desktop
app) rather than a fire token: the brief went into the routine's prompt and
the routine was run by hand. Three fires, Opus 5.5, the Default cloud
environment:

1. 74 s. Test and fix committed in the container; no push, because the
   image's uv (0.11.32) is under confusable's 0.13.4 floor and the prompt
   allowed no install.
2. 162 s. uv upgraded with pip (`uv self update` does not work on the
   image), suite green; push refused with 403: a public repository gives
   the claude.ai GitHub connection read access only.
3. 170 s from fire to branch, after the Claude GitHub app was installed on
   the repository. `claude/spike-1` holds one commit, two files, 26 lines
   added and 5 removed; the suite passes on it here (382 passed), and
   Guild's own patch check accepts the diff at tier T2 (a line deleted
   under tests), so the drill's grade is `tier: T2 != T1`, as for one of
   arm A's five trials.

What the arm needs before M3, and what counts against it:

- The repository must be public or carry the Claude GitHub app for read,
  and must carry the app for write.
- A routine created through the API has every claude.ai connector of the
  account attached; `clear_mcp_connections` on every create and update.
- `allowed_tools` pre-approves and does not restrict: the session sent
  mobile push notifications.
- The commit is the session's own: author `Claude`, a model-written
  message that holds raw U+202E and U+202C, a session link trailer. Guild
  must discard it and commit the patch itself, as the memo said.
- The image needs uv upgraded on every run, or an environment with a
  setup script, which the claude.ai form sets and the API does not.
- The base carries confusable's `.github/`: public, it ran workflows and
  Dependabot opened five pull requests. Actions are disabled on the
  scratch repository; `push_base.py` should drop `.github/`.
