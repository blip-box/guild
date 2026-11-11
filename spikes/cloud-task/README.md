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
