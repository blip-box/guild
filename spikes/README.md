# M0 spikes

Hand-run probes for `docs/ab-experiment-plan.md`, M0. Nothing here runs
in CI on its own, and nothing here is merged as a feature.

1. `sandbox_probe.py`, run by the Drills workflow's `sandbox` suite: does
   the Bash sandbox start on `ubuntu-latest` and block egress? The suite is
   there because a workflow is only dispatchable once it exists on the
   default branch, and this one runs from the spike branch. Dispatch it;
   the step summary shows the curl exit code. Pass: curl fails and the run
   ends with subtype `success`.

       gh workflow run drills.yml --ref spike/m0 -f suite=sandbox \
         -f federation_rule=fdrl_...

   The repository's federation rule is pinned to `refs/heads/main`, so the
   run needs a second rule on the Console's Workload identity page: the
   same issuer, service account and workspace, the subject
   `repo:blip-box@212885052/guild@1440301569:ref:refs/heads/spike/m0`
   (exact, from `gh api repos/blip-box/guild/actions/oidc/customization/sub`),
   scope `workspace:developer`. Its ID goes in `federation_rule`. Archive
   it when the spike branch is done.
2. `cloud-task/`: one Claude Code scheduled task fired by curl against a
   scratch repository. `README.md` there has the steps.
3. `systemone_probe.py`: one Jev call and one OpenAI Decisions call with a
   triage drill's text. Needs `TYPESAFE_API_KEY` or `OPENAI_API_KEY` in the
   environment; a vendor without a key is skipped.

   uv run --no-sync python spikes/systemone_probe.py bug-confirmed-paypal
