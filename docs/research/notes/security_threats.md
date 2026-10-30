# Security threats to AI coding agents on repositories, issues and CI (2025-2026), stress-tested against Guild

Conventions used below. "Guild" means the planned design: G1 outsiders only open issues/comments; G2 a plain script fetches issue text and escapes every non-ASCII character before any model sees it; G3 a read-only triage model with no write token emits a fixed-schema record; G4 a separate no-model job validates the record and posts labels/comments; G5 three GitHub Apps (triage: issues only; builder: contents + PRs, no `workflows`, cannot merge; gate: status checks + T0 merges); G6 agents cannot modify `.github/`, workflows, the charter or agent config (they draft, a human commits); G7 Claude Code CLI headless in Actions with short-lived OIDC credentials, egress allowlist, SHA-pinned actions, `permissions: {}` defaults; G8 PyPI publish only from a protected environment with required reviewers; G9 secret scanning and org 2FA. Verdicts: DEFENDED / PARTIAL / NOT DEFENDED. "Primary" = vendor advisory, researcher's own write-up or official docs; "secondary" = press, vendor blogs that summarise others, CSA research notes (one CSA note says it was AI-assisted and not formally reviewed, per [THN/CSA search summary](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-coding-agent-cicd-secrets-20260808-csa/)).

## 1. Prompt injection through issues, PR titles/bodies, comments, commits and repo files against coding agents and AI GitHub Actions

### Takeaway
Every 2025-2026 case of "AI agent in CI" compromise followed the same pattern: attacker-writable GitHub text (mostly plain ASCII, sometimes in hidden HTML or Unicode) reaches a model that shares a runtime with secrets, a shell, or a write path. The damage then comes through a side channel (issue edits, PR comments, image URLs, DNS, download counters on allowlisted domains, the Actions cache, repo config files). Guild's split between a model that can only read and a job with no model that writes addresses the most common version (PromptPwnd). It does not yet cover several channels: cache poisoning, config files the repo controls loading in headless mode, free text in the record, allowlisted-domain exfiltration, and injection that reaches the builder.

### Cited Findings

**Invariant Labs, GitHub MCP "toxic agent flow" (May 2025)**
- An attacker files an issue in a public repo. When the owner asks their agent (connected to the official GitHub MCP server) to look at open issues, the agent is coerced into pulling private-repo data into context and leaking it in an autonomously created PR on the public repo. Invariant calls it an architectural issue, not a bug in the MCP server code, and notes users often pick "always allow" — [Invariant Labs](https://invariantlabs.ai/blog/mcp-github-vulnerability).
- The practical fix proposed by others is scoping the token to one repository per session, since the attack needs a token spanning public and private repos (secondary) — [Repello](https://repello.ai/blog/github-mcp-server-security).

**Aikido "PromptPwnd" (published 4 Dec 2025, updated 17 Mar 2026; author Rein Daelman)**
- The pattern: `${{ github.event.issue.title }}`, `issue.body`, `pull_request.body` or commit messages go into the agent prompt. The agent holds `GITHUB_TOKEN` with write access, cloud tokens or AI API keys, plus tools such as shell and `gh issue edit` — [Aikido](https://www.aikido.dev/blog/promptpwnd-github-actions-ai-agents).
- Google's own `gemini-cli` repo used `run-gemini-cli` for issue triage. The workflow passed title and body via env vars, which stops shell injection but not prompt injection. The exposed secrets were `GEMINI_API_KEY`, `GOOGLE_CLOUD_ACCESS_TOKEN` and a read/write `GITHUB_TOKEN`. In the PoC, the hidden instructions made the agent run `gh issue edit` with the secrets in `--body`. Google patched within 4 days of disclosure — [Aikido](https://www.aikido.dev/blog/promptpwnd-github-actions-ai-agents).
- Claude Code Action runs only for users with write permission by default. Setting `allowed_non_write_users: "*"` removes that boundary ("extremely dangerous"). When an attacker could trigger such a workflow, leaking a privileged `GITHUB_TOKEN` was "almost always possible". Codex Action is vulnerable only with `allow-users: "*"` plus a weakened `safety-strategy`. GitHub AI Inference is risky with `enable-github-mcp: true` — [Aikido](https://www.aikido.dev/blog/promptpwnd-github-actions-ai-agents).
- Aikido recommends: restrict agent tools (especially writing to issues/PRs), avoid untrusted input in prompts, treat AI output as untrusted, and limit the blast radius of leaked tokens (e.g. IP restrictions). It also open-sourced Opengrep rules. No CVE or GHSA was assigned — [Aikido](https://www.aikido.dev/blog/promptpwnd-github-actions-ai-agents).
- Secondary reporting says at least five Fortune 500 companies were affected — [eSecurity Planet](https://www.esecurityplanet.com/threats/ai-agents-create-critical-supply-chain-risk-in-github-actions/). Unverified against Aikido.

**"Comment and Control" (reported Oct 2025, public 15 Apr 2026; Aonan Guan with Johns Hopkins collaborators)**
- Payloads in PR titles, issue bodies, issue comments and hidden HTML comments made Anthropic's Claude Code Security Review action, Google's Gemini CLI Action and the GitHub Copilot coding agent leak `ANTHROPIC_API_KEY`, `GITHUB_TOKEN` and `GEMINI_API_KEY` into PR comments or Actions logs. The trigger was automatic except for Copilot, where the victim had to assign the issue — [SecurityWeek](https://www.securityweek.com/claude-code-gemini-cli-github-copilot-agents-vulnerable-to-prompt-injection-via-comments/); [CSA note](https://labs.cloudsecurityalliance.org/research/csa-research-note-comment-control-github-prompt-injection-20/).
- In the Claude case, the PR title was interpolated into the system prompt. Secondary reports give it CVSS 9.4. The Copilot payload was base64-encoded to evade secret scanning and pushed with `git push`. Bounties were $100 (Anthropic), $1,337 (Google) and $500 (GitHub). No broad advisories or CVEs were published. The CSA says Anthropic's fix blocked only `ps`, which the researchers said could be bypassed — [CSA Aug 2026 note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-coding-agent-ci-prompt-injection-202608/) (secondary; the researcher's own post was not retrieved).

**Novee Security, Black Hat USA (5 Aug 2026): one unprivileged issue reaches CI credentials in vendor-default configs**
- **Claude Code:**
  - A command-validator bypass via `git push --receive-pack` hid a shell payload in single-quoted text that the validator stripped before checking. It was fixed with a `git push` flag allowlist.
  - CVE-2026-54316 used the pre-approved `huggingface.co` WebFetch domain. Download counters on 64 attacker model repos served as a side channel to leak an API key one character at a time. Affected 0.2.54-2.1.162, fixed in 2.1.163 — [CSA Aug 2026 note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-coding-agent-ci-prompt-injection-202608/); [The Hacker News](https://thehackernews.com/2026/08/claude-code-and-gemini-cli-flaws-let.html).
  - The primary advisory is GHSA-fg94-h982-f3mm / CVE-2026-54316, "Out-of-Band Data Exfiltration via Pre-Approved HuggingFace Domain in WebFetch" (published 13 Jun 2026) — [anthropics/claude-code advisories](https://github.com/anthropics/claude-code/security/advisories/GHSA-fg94-h982-f3mm).
- **Gemini CLI:** CVE-2026-12537 (CVSS v4 10.0). A crafted `.gemini/.env` in a PR ran OS commands before the sandbox started. A chained flaw read a sibling process's environment via `/proc/[PID]/environ`, and a dispatched second workflow pushed a backdoored commit — [CSA Aug 2026 note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-coding-agent-ci-prompt-injection-202608/).
- **Gemini CLI, primary advisory:** GHSA-wpqr-6v78-jr5g (critical, 24 Apr 2026) says headless mode used to auto-trust workspace folders and load `.gemini/` config and `.env`. Under `--yolo` it also ignored the fine-grained tool allowlist: `run_shell_command(echo)` allowed any command. Fixed in gemini-cli 0.39.1 and run-gemini-cli 0.1.22. Credited to Elad Meged (Novee) and Dan Lisichkin (Pillar) — [GHSA-wpqr-6v78-jr5g](https://github.com/google-github-actions/run-gemini-cli/security/advisories/GHSA-wpqr-6v78-jr5g).
- **OpenAI Codex (no CVE):** In a two-pass agent pattern, the first pass wrote attacker issue content into `AGENTS.md`. Invalid JSON from that pass forced a second pass, which loaded the poisoned file as instructions. OpenAI split the passes into separate jobs in its own repo but said the sandbox worked as documented — [CSA Aug 2026 note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-coding-agent-ci-prompt-injection-202608/).

**Clinejection (introduced 21 Dec 2025; reported 1 Jan 2026; disclosed 9 Feb 2026; exploited 17 Feb 2026)**
- Cline's `claude-issue-triage.yml` ran `anthropics/claude-code-action` on the `issues` event with `allowed_non_write_users: "*"` and `--allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch"`. The raw issue title was in the prompt. `GITHUB_TOKEN` permissions were restricted, and the only direct secret was the Anthropic API key — [Adnan Khan](https://adnanthekhan.com/posts/clinejection/).
- The chain:
  1. The injection makes Claude `npm install` an attacker commit, whose preinstall drops Cacheract.
  2. Cacheract fills the Actions cache past 10 GB so LRU eviction removes legitimate entries.
  3. It writes poisoned entries matching the nightly release workflow's `node_modules` key (`${{ runner.os }}-npm-${{ hashFiles('package-lock.json') }}`).
  4. The nightly publish restores the poisoned cache, exposing `VSCE_PAT`, `OVSX_PAT` and `NPM_RELEASE_TOKEN`.
  Khan: "any workflow can read from and write to the cache with full control of cache keys/versions" — [Adnan Khan](https://adnanthekhan.com/posts/clinejection/).
- An unknown actor published `cline@2.3.0`, which ran a postinstall that installed OpenClaw. Cline later said one npm token had not been revoked during the 9 Feb rotation — [Adnan Khan](https://adnanthekhan.com/posts/clinejection/); [Simon Willison](https://simonwillison.net/2026/Mar/6/clinejection/).
- Khan's fixes: no `Bash`/`Write`/`Edit` for triage; "Do not consume caches in workflows with access to production publication secrets"; separate nightly namespaces and credentials — [Adnan Khan](https://adnanthekhan.com/posts/clinejection/).
- Snyk: the chain composes known bugs (indirect prompt injection, cache poisoning, credential model) rather than one novel technique — [Snyk](https://snyk.io/fr/blog/cline-supply-chain-attack-prompt-injection-github-actions/).

**claude-code-action GHSA-8q5r-mmjf-575q / CVE-2026-47751 (published 20 May 2026; CVSS v4 5.3; fixed in 1.0.74)**
- The action checked out the PR head, read `.mcp.json` from the working directory, and unconditionally set `enableAllProjectMcpServers`. A PR adding a malicious `.mcp.json` therefore got arbitrary code execution on the runner and could exfiltrate workflow secrets once a privileged user or automatic trigger invoked the action — [GHSA-8q5r-mmjf-575q](https://github.com/anthropics/claude-code-action/security/advisories/GHSA-8q5r-mmjf-575q).

**Claude Code CLI: recurring "repo files run before or around trust" advisories (all primary, [anthropics/claude-code advisories](https://github.com/anthropics/claude-code/security/advisories))**
- **Code execution and data leakage before or around the trust check:**
  - CVE-2025-59536 and CVE-2025-65099: command execution before the startup trust dialog (Oct and Nov 2025).
  - CVE-2026-21852: repo config can leak data via environment configuration before trust (20 Jan 2026).
  - CVE-2026-33068: workspace-trust bypass via a repo-controlled settings file (18 Mar 2026).
  - CVE-2026-40068: trust-dialog bypass via git worktree spoofing (24 Apr 2026).
  - CVE-2026-25725: sandbox escape via persistent configuration injection in `settings.json` (6 Feb 2026).
  - CVE-2026-88066: code execution via a malicious `git` executable on the search path (13 Oct 2026).
  - CVE-2026-86063: plugin commit-SHA pin bypass (9 Oct 2026).
- **Command-validation and approval bypasses:** `echo` (CVE-2025-54795), `rg` (CVE-2025-58764), `sed` (CVE-2025-64755), `find` (CVE-2026-24887), piped `sed` (CVE-2026-25723), directory change (CVE-2026-25722), and a general validation bypass (CVE-2025-66032).
- **Network:** a domain-validation bypass allowed automatic requests to attacker domains (CVE-2026-24052, 3 Feb 2026).
- Claude Code's docs say a `-p` (headless) session shows neither the workspace-trust prompt nor the `.mcp.json` approval prompt — [Claude Code security docs](https://code.claude.com/docs/en/security).

**CamoLeak, GitHub Copilot Chat (found June 2025; GitHub's interim fix 14 Aug 2025; published 30 Sep 2025; CVSS 9.6)**
- A prompt hidden in a PR description via GitHub's invisible-comment syntax ran with the permissions of whoever viewed the page with Copilot Chat. It bypassed CSP using a pre-generated dictionary of valid signed Camo image-proxy URLs, one per character. Copilot rendered the stolen private-repo code and secrets as "ASCII art" made of those images, including an unpatched zero-day description from a private issue — [Legit Security](https://www.legitsecurity.com/blog/camoleak-critical-github-copilot-vulnerability-leaks-private-source-code).
- GitHub's fix was to disable image rendering in Copilot Chat entirely — [Legit Security](https://www.legitsecurity.com/blog/camoleak-critical-github-copilot-vulnerability-leaks-private-source-code); [The Register](https://theregister.com/2025/10/09/github_copilot_chat_vulnerability/).
- A CVE (CVE-2025-59145) is claimed only by [BlackFog](https://www.blackfog.com/camoleak-how-github-copilot-became-an-exfiltration-channel/). Legit's post lists none; treat it as unconfirmed.

**Rules File Backdoor (Pillar Security, March 2025)**
- Hidden instructions in Cursor and Copilot rules files, concealed with Unicode obfuscation or semantic manipulation, steer the assistant into generating malicious code. The demo injected a script that sent data to an external server. Poisoned rules persist across forks. Cursor's position was that this is the user's responsibility and not a vulnerability on its side — [Security Affairs](https://securityaffairs.com/175593/hacking/rules-file-backdoor-ai-code-editors-silent-supply-chain-attacks.html); [The Hacker News](https://thehackernews.com/2025/03/new-rules-file-backdoor-attack-lets.html) (both secondary; Pillar's own post was not retrieved).

**Johann Rehberger, "Month of AI Bugs" (Aug 2025)**
- Daily disclosures across coding agents ([Simon Willison summary](https://simonwillison.net/2025/Aug/15/the-summer-of-johann/); [Rehberger slides](https://media.defcon.org/DEF%20CON%20SG%201/DEF%20CON%20SG%201%20main%20stage%20presentations/Johann%20Rehberger%20-%20The%20Month%20of%20AI%20Bugs%20Lessons%20Learned%20Exploiting%20AI%20Computer-Use%20and%20Coding%20Agents.pdf)):
  - Claude Code (11 Aug): data exfiltration over DNS through the pre-approved `ping`/`nslookup`/`host`/`dig`.
  - GitHub Copilot (12 Aug): the injection edits `settings.json` to set `chat.tools.autoApprove: true`, giving RCE (CVE-2025-53773).
  - Amp (5 Aug): the agent edits its own settings to enable new Bash commands and MCP servers.
  - Cursor (4 Aug): Mermaid diagrams allow image exfiltration (CVE-2025-54132).
  - Codex web (2 Aug): abuse of `azure.net` on the "Common Dependencies Allowlist".
  - Google Jules (15 Aug): "hidden Unicode tricks" let invisible instructions in issues subvert the agent.
  - Devin and OpenHands: assorted command execution and exfiltration.
- Primary advisory for the Claude Code item: GHSA-x5gv-jw7f-j6xj / CVE-2025-55284, "Permissive Default Allowlist Enables Unauthorized File Read and Network Exfiltration" (15 Aug 2025) — [advisory](https://github.com/anthropics/claude-code/security/advisories/GHSA-x5gv-jw7f-j6xj).
- Willison's conclusions:
  - Every attack starts with prompt injection, and avoiding untrusted input is unrealistic.
  - Over-broad domain allowlists are exfiltration vectors.
  - Writing an agent's own config escalates privileges and defeats approval prompts.
  - "There may be systems that should not be built at all" — [Simon Willison](https://simonwillison.net/2025/Aug/15/the-summer-of-johann/).

**Other 2026 items (secondary, CSA-only, unverified)**
- "GuardFall" (June 2026, Adversa AI): 10 of 11 open-source agents were vulnerable to a mismatch between text inspection and shell execution.
- "Agentjacking" (15 Jun 2026): Sentry-DSN-based MCP injection at an 85% success rate across three agents — [CSA Aug 2026 note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-coding-agent-ci-prompt-injection-202608/).

### Inferences
**Guild verdicts per finding**

| Finding | Verdict | Why / what to add |
|---|---|---|
| PromptPwnd: agent with write token edits the issue to leak secrets | DEFENDED (mostly) | G3/G4 remove the write token and tools from the model job. Residual risk: the record itself is an output channel. Keep the schema to closed enums (label IDs from a fixed set, integer issue refs, booleans) and post no model free text verbatim. Build comments from fixed templates in the no-model job. Reject records with URLs, `@mentions` or text over a length cap. This mirrors GitHub's "safe outputs": an operation allowlist, volume limits, URL stripping and secret removal (see Q4). |
| Comment and Control: model reads secrets via shell (`ps`, `env`, `/proc`) and posts them | PARTIAL | G3 has no write token, but the model job still holds the model credential (OIDC-derived or API key) and possibly `ACTIONS_RUNTIME_TOKEN`, and the CLI may have shell tools. Add: run triage with no tools at all (no Bash/Read/WebFetch; ideally a plain API call, not the agentic CLI). Keep the model credential outside the model process via a credential-injecting proxy, as in GitHub Agentic Workflows and Claude Code cloud sessions (Q4). G9 secret scanning is not enough on its own: the Copilot PoC base64-encoded the secret to dodge it. |
| Clinejection: triage injection leads to cache poisoning and publish secrets | NOT DEFENDED by G2/G3 alone; PARTIAL via G8 | The title payload was plain ASCII, so G2 does nothing. A job with no write token can still write the Actions cache, because cache access is not governed by `permissions:`. Issue-triggered jobs run in the default-branch cache scope shared with release jobs. G8's reviewer approval does not help when the approved publish job restores a poisoned cache. Add: no `actions/cache` or setup-* caching in any publish or secret-bearing workflow (zizmor `cache-poisoning`); no package installs or code execution in the triage job; PyPI Trusted Publishing (no long-lived token); a separate, minimal publish workflow. |
| Novee / CVE-2026-54316: exfiltration via an allowlisted domain (HF counters) | PARTIAL | G7's egress allowlist is necessary but not sufficient. Any allowlisted host with attacker-observable state (huggingface.co, github.com, gist, PyPI/npm, `*.azure.net`) is a channel. Add: an allowlist for model jobs containing only the model API endpoint (and GitHub API via proxy if needed). Block DNS to arbitrary resolvers. Run Harden-Runner or equivalent in block mode, not audit. |
| Novee / Gemini `.gemini/.env`; claude-code-action `.mcp.json` CVE-2026-47751; Claude Code pre-trust CVEs | NOT DEFENDED unless enforced | Headless `-p` shows no trust or MCP prompts, so any repo-controlled `.claude/settings.json`, hooks, `.mcp.json`, `CLAUDE.md`/`AGENTS.md` or `.env` in the checkout is loaded. G6 is a policy and must become a control. (1) The builder must not be able to push changes to agent config: use push rulesets with file-path restrictions or a gate-enforced path check, plus CODEOWNERS. The `workflows` permission only protects `.github/workflows/` (verify). (2) Every CLI run should restore agent config from the trusted base ref before starting, as claude-code-action does for `.claude/`, `.mcp.json`, `CLAUDE.md`, `.husky/` etc. (Q4). Pass explicit flags that ignore project settings and project MCP. Flag names such as `--setting-sources` and `--strict-mcp-config` should be verified against current CLI docs. (3) Pin the CLI version and track the advisory feed. Advisories arrive roughly monthly. |
| Codex two-pass AGENTS.md poisoning | PARTIAL | The same class applies to any Guild pipeline where one agent run writes files that a later run loads as instructions, such as builder notes, plan files or memory. Treat every file an agent wrote as untrusted input to the next stage. Load agent instructions only from human-committed paths on the base branch. |
| Invariant toxic agent flow (cross-repo token) | DEFENDED if Apps are installed on a single repo | Install each App only on the repo(s) it serves and mint per-job tokens scoped to one repository and a permission subset. Never let one installation span public and private repos. Make sure the builder never reads raw issue text (see Q5). |
| CamoLeak (image-URL exfiltration through rendered markdown) | PARTIAL | Guild posts comments publicly anyway. The risk is model-authored markdown whose image or link URLs encode data, fetched when rendered. Add: the posting job strips all markdown images, links and HTML from any model-derived text, or uses templates only. |
| Rules File Backdoor / Jules hidden Unicode in repo files | PARTIAL | G2 covers issue text only. Repo files the model reads (CLAUDE.md, docs, code comments, vendored READMEs, dependency source) are not escaped. Add a CI check that rejects invisible, bidi, Tag-block, variation-selector and PUA characters in agent config and agent-authored diffs. This is the same idea as this repo's `tests/test_source_hygiene.py` for Python source. |
| Rehberger config self-modification (Amp, CVE-2025-53773) | PARTIAL | This is the same as the G6 enforcement point above. Also make the runner's home and config directories read-only to the agent process, or recreate them from a known template each run (ephemeral hosted runners help here). |

- The builder is the highest-risk component in Guild. It holds contents and PR write access, so it is "untrusted content + state change" in Meta's Rule of Two terms. If it ever reads raw issue text, linked pages, dependency READMEs or PR review comments from outsiders, it has all three trifecta legs. Its secrets (model credential, App token) are the "private data" leg even in a public repo.
- Status checks and "T0 merges" by the gate are an injection target: an attacker will try to make a malicious change look like T0. T0 should be decided by deterministic rules over the diff (path globs, size, no dependency or lockfile changes, no build-config changes), never by a model. Required checks should be bound to the gate App as the expected source, so another actor cannot post a check with the same name. Verify the exact ruleset option in GitHub docs.

### Gaps
- Aonan Guan's original "Comment and Control" write-up and Novee's primary blog were not retrieved. Details come from CSA notes, SecurityWeek and The Hacker News.
- CVE-2026-12537 was not found as a standalone primary record. The Gemini GHSA lists no CVE.
- No primary source was found for a "CVSS 9.4" rating of the Claude Code Security Review issue.
- Pillar's and Rehberger's own posts on the Unicode techniques (Rules File Backdoor; the Jules invisible-instructions bug) were not fetched. Only secondary summaries were used.
- Whether the builder App's lack of `workflows` permission also blocks edits to `.github/actions/*` composite actions, `CODEOWNERS` or `dependabot.yml` was not verified. The assumption is that it covers only `.github/workflows/`.

## 2. Supply-chain attacks that weaponised or targeted AI coding tools, and which controls would have stopped them

### Takeaway
In 2025-2026, AI tools became both a target (credential files, MCP servers, skills registries, IDE extensions) and a weapon: malware invoked locally installed agents with permission-bypass flags, and wiper prompts were planted in an assistant. The root causes were mostly classic CI and credential failures: `pull_request_target` plus template injection, over-scoped tokens, mutable tags, long-lived publish tokens, and caches shared with release jobs. Guild's SHA pinning, protected publish environment, App split and no-`workflows` builder stop several of them. The biggest additions are Trusted Publishing for PyPI, no caches in release workflows, pinned tools inside workflows, and enforced immutability of agent config.

### Cited Findings

**tj-actions/changed-files (CVE-2025-30066, March 2025) and reviewdog/action-setup (CVE-2025-30154)**
- Version tags were retroactively repointed to a payload that dumped Runner.Worker memory (including secrets) into public logs. About 23,000 repos used the action. Both CVEs were added to CISA KEV. The compromise chained from reviewdog — [CSA May 2026 note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-github-actions-security-20260503-csa-st/).
- StepSecurity's Harden-Runner flagged it through an anomalous outbound call (to `gist.githubusercontent.com`) absent from the job's baseline. StepSecurity says it was credited in the CVE (vendor claim) — [StepSecurity](https://www.stepsecurity.io/cicd-security); [Harden-Runner detections docs](https://docs.stepsecurity.io/github-actions/harden-runner/detections).

**Nx "s1ngularity" (21-27 Aug 2025, EDT; GHSA-cxm3-wv7p-598c)**
- **Root cause:**
  - A `pull_request_target` workflow interpolated the PR title into a `run:` block, so `$(...)` executed.
  - Outdated branches still carried the vulnerable workflow after the revert on master.
  - The injected workflow triggered `publish.yml`, and an attacker commit sent the npm token to a webhook.
  - Malicious nx 20.9.0-21.8.0 and others were published on 26 Aug. The postinstall collected credentials into `s1ngularity-repository` repos and appended `sudo shutdown -h 0` to shell rc files — [Nx GHSA](https://github.com/nrwl/nx/security/advisories/GHSA-cxm3-wv7p-598c).
- **Nx's fixes:** Trusted Publishing with npm tokens removed, mandatory 2FA, approval required for external-contributor workflows, outdated branches rebased, CodeQL, and `SECURITY.md` — [Nx GHSA](https://github.com/nrwl/nx/security/advisories/GHSA-cxm3-wv7p-598c).
- **AI weaponisation:** The malware invoked local `claude --dangerously-skip-permissions`, `gemini --yolo` and `q --trust-all-tools --no-interactive` to inventory secrets.
  - About 50% of victims had at least one AI CLI.
  - Almost a quarter of Claude interactions were refused, and Gemini was often blocked by workspace-directory limits.
  - AI-driven exfiltration succeeded in under a quarter of cases.
- **Impact:** Over 2,000 verified secrets leaked. About 90% of leaked GitHub tokens were still valid two days later. Phase 2 made over 6,700 private repos public across at least 480 accounts — [Wiz](https://www.wiz.io/blog/s1ngularitys-aftermath).

**Amazon Q Developer for VS Code 1.84.0 (CVE-2025-8217; AWS-2025-015, 23 Jul 2025, updated 25 Jul)**
- An inappropriately scoped GitHub token in the CodeBuild configuration let an attacker push code that was automatically included in a release. The release shipped a prompt telling the agent to wipe file systems and cloud resources. It failed to execute because of a syntax error. 1.85.0 removed it, and all 1.84.0 installs should be removed — [AWS-2025-015](https://aws.amazon.com/security/security-bulletins/AWS-2025-015/); [AWS Insider](https://awsinsider.net/articles/2025/07/25/formatting-flaw-foils-attempted-prompt-injection-on-amazon-q.aspx) (secondary).
- Reports conflict on whether the code arrived via a PR. The AWS bulletin's wording should be preferred — [AWS-2025-015](https://aws.amazon.com/security/security-bulletins/AWS-2025-015/).

**Shai-Hulud, npm worm**
- **Wave 1 (mid-Sep 2025; CISA alert 23 Sep 2025):** Over 500 npm packages were compromised. The worm stole GitHub PATs and AWS/GCP/Azure keys and uploaded them to public "Shai-Hulud" repos. CISA advises pinning to releases before 16 Sep 2025, rotating credentials and using phishing-resistant MFA — [CISA](https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem).
- The worm committed `.github/workflows/shai-hulud-workflow.yml` to repos to exfiltrate CI secrets — [Intel 471](https://go.intel471.com/hubfs/Emerging%20Threats/2025%20Emerging%20Threats/Emerging%20Threat%20-%20NPM%20-%20Shai-Hulud%20Worm.pdf) (secondary).
- **Wave 2 ("Sha1-Hulud", Nov 2025):**
  - Preinstall `setup_bun.js` / `bun_environment.js` and TruffleHog secret sweeps.
  - It registered the host as a self-hosted runner named `SHA1HULUD` and injected workflows (e.g. `discussion.yaml`) for remote command execution.
  - Wiping the home directory was the fallback.
  - About 600-800 packages and more than 25,000 repos were affected, per [Invicti](https://www.invicti.com/blog/web-security/shai-hulud-2-worm-supply-chain-attack-on-npm-dependencies).
  - Datadog gives a lower bound of over 500 exfiltrated GitHub users and saw the last package on 24 Nov — [Datadog Security Labs](https://securitylabs.datadoghq.com/articles/shai-hulud-2.0-npm-worm/).

**GhostAction (malicious commit 2 Sep 2025; disclosed 5 Sep 2025 by GitGuardian)**
- Compromised maintainer accounts pushed a workflow titled "Add Github Actions Security workflow". It triggered on `push`/`workflow_dispatch` and POSTed secrets to an attacker host. The campaign hit 327 users and 817 repos and stole 3,325 secrets (DockerHub, GitHub, npm, PyPI, AWS, Cloudflare). A second wave came on 9 Sep — [GitGuardian](https://blog.gitguardian.com/ghostaction-campaign-3-325-secrets-stolen/).
- PyPI invalidated the affected publishing tokens and found no compromised PyPI accounts. It recommended Trusted Publishers, which issue short-lived, repo-scoped tokens. A GitGuardian report email landing in spam delayed the response from 5 to 10 Sep — [BleepingComputer](https://www.bleepingcomputer.com/news/security/pypi-invalidates-tokens-stolen-in-ghostaction-supply-chain-attack/); [PyPI blog draft in warehouse PR](https://github.com/pypi/warehouse/pull/18705/files).

**postmark-mcp (first known malicious MCP server; malicious v1.0.16 released 17 Sep 2025)**
- After 15 clean versions, one added line BCC'd every outgoing email to `phan@giftshop.club`. The package had 1,643 downloads before the author deleted it — [Koi Security](https://koi.ai/blog/postmark-mcp-npm-malicious-backdoor-email-theft); [The Hacker News](https://thehackernews.com/2025/09/first-malicious-mcp-server-found.html).

**Slopsquatting (USENIX Security 2025, Spracklen et al., "We Have a Package for You!")**
- 16 code models generated 576,000 code samples. About 1 in 5 recommended packages did not exist (205,474 unique hallucinated names). Open models hallucinated about 21.7% of the time and GPT-4 about 5.2%. Names repeat across re-runs (43%/58%; sources disagree on the exact definition) — [Xygeni](https://xygeni.io/blog/what-is-slopsquatting-how-attackers-weponize-ai-hallucinations/); [agentpatterns.ai](https://agentpatterns.ai/security/slopsquatting-hallucinated-package-names/) (secondary).
- The paper won a best-paper award — [UW-Madison seminar](https://madsp.cs.wisc.edu/sp-seminar/20250922-package_hallucinations).
- An earlier real case: the hallucinated name `huggingface-cli`, registered as a benign placeholder, got over 30,000 downloads in three months — [agentpatterns.ai](https://agentpatterns.ai/security/slopsquatting-hallucinated-package-names/).

**GlassWorm (Oct 2025 onward)**
- Self-spreading malware in OpenVSX and VS Code extensions hid JavaScript in invisible Unicode (variation selectors and PUA) that renders blank. It stole developer credentials and wallets, used Solana-based C2, and returned after Open VSX's cleanup. Reports say it also hid payloads in AI-generated-looking commits in GitHub repos — [BleepingComputer](https://www.bleepingcomputer.com/news/security/self-spreading-glassworm-malware-hits-openvsx-vs-code-registries/); [Endor Labs](https://www.endorlabs.com/learn/invisible-threats-glassworm-unicode-vscode); [Veracode](https://www.veracode.com/blog/glassworm-vs-code-extension).

**TeamPCP: Trivy, then LiteLLM (late Feb to Mar 2026)**
- A misconfiguration in Trivy's Actions gave the attackers a privileged token. Existing `trivy-action` tags were rewritten (76 of 77 tags, plus all 7 `setup-trivy` tags, on 19 Mar). LiteLLM's CI ran Trivy unpinned, so the poisoned scanner harvested the PyPI publish token.
- Malicious litellm 1.82.7/1.82.8 went to PyPI on 24 Mar 2026. One version shipped a `.pth` file that runs at every Python startup. Checkmarx KICS action and extensions followed on 23 Mar. Targets included OpenAI, Anthropic, Azure, AWS and Kubernetes credentials — [The Register](https://www.theregister.com/2026/03/24/trivy_compromise_litellm/); [BoostSecurity](https://labs.boostsecurity.io/articles/teampcp-litellm-supply-chain-compromise/); [CSA note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-github-actions-security-20260503-csa-st/) (secondary; sources disagree on PyPI takedown time, about 40-46 minutes).

**ClawHub / OpenClaw skills (Feb 2026 onward)**
- Koi audited 2,857 skills and flagged 341 as malicious, 335 of them in one "ClawHavoc" campaign that used fake prerequisites to install the AMOS macOS stealer. Skills get the agent's privileges. Unit 42 (23 Jun 2026) reported skills engineered to pass ClawHub's scanning — [CSA note](https://labs.cloudsecurityalliance.org/research/csa-research-note-openclaw-clawhub-supply-chain-risk-2026070/); [eSecurity Planet](https://esecurityplanet.com/threats/hundreds-of-malicious-skills-found-in-openclaws-clawhub) (secondary).

### Inferences
**What would have stopped each incident, and Guild's coverage**

| Incident | Control that would have stopped it | Guild verdict / add |
|---|---|---|
| tj-actions / reviewdog / Trivy tag rewrites | SHA pinning; enforced by GitHub's SHA-pinning policy (Aug 2025); egress anomaly detection | DEFENDED for direct `uses:` (G7). PARTIAL for transitive pins inside composite actions and for tools fetched by `curl`/`pip`/`docker` inside steps (LiteLLM ran Trivy unpinned). Add: the org-level "require SHA pinning" policy, zizmor `unpinned-uses`/`unpinned-tools`/`unpinned-images`/`impostor-commit`, and hash-locked tool installs. |
| Nx (PR-title injection in `run:` under `pull_request_target`) | No `${{ }}` of untrusted text in `run:` (zizmor `template-injection`); no `pull_request_target`; Trusted Publishing | DEFENDED if G2 passes text via file or env and never via `${{ }}`, and Guild has no `pull_request_target` workflows. Note that G2's non-ASCII escaping is irrelevant here: `$(...)` is ASCII. |
| Nx malware driving local AI CLIs with `--dangerously-skip-permissions` | No long-lived secrets on developer machines; agent CLIs not installed where credentials live | OUT OF GUILD SCOPE for CI. Relevant to maintainers' laptops. G9 2FA does not stop token theft. Use short-lived, fine-grained tokens and keep the publish credential off laptops (Trusted Publishing). |
| Amazon Q (over-scoped CI token pushes into a release) | Least-privilege per-job tokens; human review before release; protected branches | DEFENDED in spirit by G5 (builder cannot merge) and G8. Residual: gate "T0 merges" must never include code paths that reach a release artifact without human review. |
| Shai-Hulud workflow injection and self-hosted runner registration | Tokens without `workflow` scope; no self-hosted runners; dependency cooldown and lockfiles | DEFENDED for the builder App (no `workflows`). NOT DEFENDED for human PATs: require fine-grained PATs without workflow scope or none at all, and disable self-hosted runners at the org level (zizmor `self-hosted-runner`). Keep a dependency cooldown. This repo's Dependabot already has a 7-day cooldown. |
| GhostAction (pushed workflow exfiltrates repo secrets) | Secrets only in environments with required reviewers and branch restrictions; Trusted Publishing | DEFENDED for secrets placed only in the G8 environment, if the environment restricts deployment branches to `main`/tags and forbids self-review. NOT DEFENDED for any repo- or org-level secret, such as a model API key or App private key stored as a repo secret: any workflow pushed by a compromised human can read those. Move them into environments or OIDC. |
| postmark-mcp / ClawHub skills / Claude Code plugin pin bypass (CVE-2026-86063) | No third-party MCP servers, skills or plugins in CI; vendor and review them | Unknown: Guild does not say whether MCP or skills are used. Add: CI agents run with an explicit, empty or vendored MCP and plugin set (project MCP disabled), versions pinned, nothing installed from a marketplace at runtime. |
| Slopsquatting | Human review of any dependency change; registry allowlist; lockfile with hashes; cooldown | PARTIAL. Treat any diff touching `pyproject.toml`/`uv.lock` as never-T0. This project's "no runtime dependencies" rule helps, and dev-dependency additions should also need human review. |
| GlassWorm (invisible-Unicode code in commits and extensions) | Byte-level checks for invisible and bidi characters on every diff | PARTIAL. G2 covers issues, not code. Add a repo-wide hygiene check like `tests/test_source_hygiene.py` extended to all agent-authored files. |
| Clinejection (cache to publish) | No cache restore in publish jobs; separate credentials for nightly and prod | See Q1: NOT DEFENDED unless Guild bans caches in publish and secret-bearing workflows. |

- PyPI publish via G8 should use Trusted Publishing (OIDC) with no stored token. A protected environment with required reviewers gates secret release, but a stored token can still be exfiltrated by whatever code the approved job runs (Clinejection, LiteLLM). Trusted Publishing removes the stealable long-lived secret; the OIDC token is short-lived and repo-scoped per PyPI. zizmor has a `use-trusted-publishing` audit.
- The publish job should run nothing but build-and-upload of an artifact built in a separate job: no scanners, no linters, no caches, no agent. The TeamPCP chain shows scanners running next to the publish token are a vector.

### Gaps
- No primary Shai-Hulud 2.0 advisory from GitHub/npm was retrieved. GitHub's npm hardening plan after Shai-Hulud (token lifetimes, trusted publishing) was not fetched.
- The slopsquatting statistics come from secondary summaries; the USENIX paper itself was not read.
- Amazon Q: the exact attacker access path is disputed between sources.
- I found no evidence of a 2025-2026 incident in which a CI-hosted coding agent itself was the initial access vector into a PyPI release. Clinejection (npm) is the closest.

## 3. GitHub Actions hardening specific to agents

### Takeaway
Agents add three twists to classic Actions hardening. (1) Jobs that read untrusted text must hold no reachable secrets: env vars, `/proc`, cache tokens and the model credential all count. (2) Agent-authored branches in the base repo are "trusted" by GitHub's event model, so CI on them gets secrets unless designed otherwise. (3) Egress allowlists must account for attacker-writable allowlisted hosts. GitHub's 2025 changes (default-branch `pull_request_target`, SHA-pin enforcement) and its own agent products (Copilot coding agent, Agentic Workflows) show the reference pattern. Guild already matches several pieces of it.

### Cited Findings
- **`pull_request_target` change (effective 8 Dec 2025):** The workflow file and checkout commit always come from the default branch, with `GITHUB_REF`/`GITHUB_SHA` set to the default branch. Environment branch-protection rules now evaluate against the execution ref (`refs/pull/N/merge` for `pull_request*`; the default branch for `pull_request_target`), closing a path where PR head refs could reach environment secrets. GitHub still warns that `pull_request_target` with fork PRs is elevated-risk because it runs with secrets — [GitHub changelog 2025-11-07](https://github.blog/changelog/2025-11-07-actions-pull_request_target-and-environment-branch-protections-changes/).
- **claude-code-action on `pull_request_target`/`workflow_run`:** These run with base-repo secrets. "Do not check out an untrusted ref into the workspace root before this action." Check out the head into a subdirectory and pass `--add-dir`. On PRs the action restores `.claude/`, `.mcp.json`, `.claude.json`, `.gitmodules`, `.ripgreprc`, `CLAUDE.md`, `CLAUDE.local.md` and `.husky/` from the base branch, but `package.json`, lockfiles, `Makefile` and linter config stay at the PR head — [claude-code-action security.md](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md).
- **claude-code-action defaults:**
  - Write-access users only, with bots blocked by default. Allowed bots are not permission-checked.
  - `allowed_non_write_users` is "RISKY"; it requires the auto-generated `GITHUB_TOKEN` ("Do not use a personal access token") and minimal tools (e.g. `Bash(gh issue view:*)`). It does a best-effort secret scrub of subprocess env, plus PID-namespace isolation with bubblewrap on Linux, and "reduces but does not eliminate prompt injection risk".
  - `show_full_output` can publish tool outputs to public logs.
  - Claude does not open PRs itself; a human clicks the link — [claude-code-action security.md](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md).
- **`GITHUB_TOKEN` and OIDC:** `GITHUB_TOKEN` defaults to read-write unless `permissions` is declared. AWS IAM roles trusting GitHub OIDC without a `sub` condition could be assumed by any repo's workflow. AWS blocked new such roles in June 2025, but existing ones remain (Datadog research, via CSA) — [CSA May 2026 note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-github-actions-security-20260503-csa-st/).
- **Cache poisoning:** "Any workflow can read from and write to the cache with full control of cache keys/versions." Default-branch workflows (including `issues`-triggered ones) share the default-branch cache scope. Without `actions: write` a job can't delete entries, but can force LRU eviction by exceeding 10 GB — [Adnan Khan](https://adnanthekhan.com/posts/clinejection/). zizmor's `cache-poisoning` audit flags cache reads in release workflows and cache writes from privileged triggers — [zizmor audits](https://docs.zizmor.sh/audits/).
- **zizmor audits relevant to agent workflows:** `template-injection`, `dangerous-triggers` (`pull_request_target`, `workflow_run`, `issue_comment`), `excessive-permissions`, `artipacked` (persisted checkout credentials), `cache-poisoning`, `github-app` (unrevoked or over-broad App tokens), `secrets-outside-env`, `overprovisioned-secrets`, `secrets-inherit`, `bot-conditions` (spoofable actor checks), `self-hosted-runner`, `unpinned-uses`, `impostor-commit`, `ref-confusion`, `typosquat-uses`, `adhoc-packages`, `unpinned-tools`, `unpinned-images`, `use-trusted-publishing`, `dependabot-cooldown`. No AI- or LLM-specific audit was visible on the audits page as fetched (the page was partly truncated) — [zizmor audits](https://docs.zizmor.sh/audits/).
- **SHA-pinning enforcement (15 Aug 2025):** The allowed-actions policy can require full commit SHAs (unpinned actions fail) and block actions or versions with a `!` prefix — [GitHub changelog](https://github.blog/changelog/2025-08-15-github-actions-policy-now-supports-blocking-and-sha-pinning-actions/).
- **Egress monitoring:** Harden-Runner's "Anomalous Outbound Network Calls" detection compares against a per-workflow baseline. It needs a stable baseline before it alerts — [StepSecurity docs](https://docs.stepsecurity.io/github-actions/harden-runner/detections).
- **Copilot coding agent security model (GA 25 Sep 2025, per CSA):**
  - Only write-access users can trigger it. It pushes only to `copilot/` branches and cannot run `git push` itself.
  - It cannot approve or merge, and the requester cannot approve its PR.
  - Workflows on its PRs need a write-access user to click "Approve and run workflows".
  - It gets no Actions repo or org secrets, only the `copilot` environment.
  - A firewall limits egress.
  - "Hidden characters are filtered before user input reaches the agent", and HTML comments are not passed.
  - Commits are signed and co-authored, with session logs.
  - Automations ignore events from non-write users by default — [GitHub Docs](https://docs.github.com/en/enterprise-cloud@latest/copilot/concepts/agents/cloud-agent/risks-and-mitigations).
- **GitHub Agentic Workflows (tech preview 13 Feb 2026; security post 9 Mar 2026, Landon Cox and Jiaxiao Zhou):**
  - Agents are untrusted by default, and Actions is "a single shared trust domain".
  - The agent runs in its own container behind an egress firewall with an allowlist.
  - The MCP gateway "has exclusive access to MCP authentication material", and LLM tokens sit in an API proxy outside the agent.
  - The host filesystem is mounted read-only with tmpfs overlays in a chroot.
  - The agent "can only stage its updates through the safe outputs MCP server". Staged writes go through deterministic checks: operation allowlists, volume limits ("at most three pull requests in a given run"), URL removal, secret removal and moderation.
  - Firewall, proxy and gateway all log — [GitHub blog](https://github.blog/ai-and-ml/generative-ai/under-the-hood-security-architecture-of-github-agentic-workflows/).
- **Claude Code cloud sessions:** GitHub credentials "never enter the session VM". The VM holds a short-lived, session-scoped credential, and a proxy attaches the real credential server-side and rejects tag pushes and branch deletions — [Claude Code security docs](https://code.claude.com/docs/en/security).

### Inferences
**Guild verdicts**

| Hardening item | Verdict | Add |
|---|---|---|
| `permissions: {}` default, per-job scopes | DEFENDED | Keep zizmor pedantic in CI. Also note that `permissions: {}` does not remove `ACTIONS_RUNTIME_TOKEN` (cache and artifact access) or OIDC if `id-token: write` is granted. |
| `pull_request_target` / `workflow_run` | DEFENDED if absent | Ban both via zizmor `dangerous-triggers`. If `workflow_run` is used to chain triage, then poster, never execute artifacts from the first run. Treat the record artifact as data, validated against a strict JSON schema with no code paths. |
| Secrets in jobs that read untrusted text | PARTIAL | The triage job needs a model credential. Prefer a credential-injecting egress proxy so the token is not in the process env or `/proc`. If that's impossible, use the shortest-lived OIDC-minted token, a separate OS user and PID namespace for the model process, and no shell tools. |
| Builder branches trigger CI with secrets | NOT DEFENDED (not addressed) | The builder pushes branches in the base repo, and App-token pushes trigger workflows, unlike pushes made with `GITHUB_TOKEN` (verify for Guild's event set). Tests and build hooks the builder wrote (conftest.py, build backends) then run with whatever secrets those workflows hold. Add: CI for agent branches has no secrets and no environments, and runs with read-only token. Or copy Copilot's "Approve and run workflows" gate. |
| Cache poisoning | NOT DEFENDED | No caching in publish or secret-bearing workflows. No issue-triggered job runs package installs. Consider separate cache keys per trust level. |
| Self-hosted runners | Not stated | Use GitHub-hosted ephemeral runners only, disable self-hosted at org level (Shai-Hulud 2 registered rogue runners), and monitor runner registrations in the audit log. |
| OIDC trust policies | PARTIAL (G7 uses OIDC) | Pin `sub` to repo + environment (and `job_workflow_ref` where the provider supports it) for every cloud and model-provider trust. Never use a wildcard org-wide trust. |
| Egress allowlist | PARTIAL | Use block mode, not audit. Include DNS. Allowlist per job (triage: model API only; builder: model API, GitHub API, PyPI index read-only via a pinned mirror). Remember that GitHub, gist and HF content are attacker-writable. |
| Action pinning | DEFENDED (direct) | Turn on GitHub's enforce-SHA-pinning policy at the org level, and scan for transitive and unpinned tools. |
| App private keys | Not stated | If App private keys live in repo secrets, any workflow can mint full-permission tokens. Store them in environment-scoped secrets, mint per-job tokens with `repositories` and `permissions` narrowed (zizmor `github-app`), and revoke at job end. |
| Agent config immutability (G6) | PARTIAL | Enforce with push rulesets or file-path restrictions and CODEOWNERS, and restore config from the base ref before every CLI run (see Q1). |
| Logs | Not stated | Public repos have public logs. Never enable verbose or `show_full_output`-style logging for agent runs. Base64 and other encodings evade secret masking. |

- Copilot's model and GitHub Agentic Workflows independently converge on what Guild is doing: a read-only agent, writes staged through a deterministic gate, credentials outside the agent boundary, and egress firewalling. The main places Guild falls short of that reference are credential placement (proxy rather than env), sanitizing staged outputs (URLs, mentions, secrets, volume caps), and the human "approve and run workflows" step for agent PRs.

### Gaps
- I did not re-fetch GitHub's "Security hardening for GitHub Actions" doc for its exact current wording on self-hosted runners and public repos.
- I did not verify whether GitHub-App-authored pushes and PRs in the same repo trigger `pull_request` and `push` workflows with repo secrets in every case. This is commonly understood, but should be checked against GitHub docs for Guild's exact event set.
- No primary source found on GitHub changing cache-scope or eviction semantics in response to Clinejection.
- Whether a ruleset can require that a status check come from a specific GitHub App was not re-verified in this session.

## 4. Authoritative guidance (OWASP, OpenSSF, SLSA, NIST/CISA, Anthropic, GitHub, Google, Willison, Meta)

### Takeaway
The guidance converges on architecture over filtering. Assume injection succeeds, then limit what a compromised session can reach: no more than two of untrusted input, sensitive access and outbound state change (Meta), never the full lethal trifecta (Willison), least agency (OWASP ASI), and deterministic gates on writes (GitHub's safe outputs). Vendor docs explicitly say their sanitizers are best-effort. SLSA and OpenSSF have little agent-specific material yet.

### Cited Findings
- **OWASP Top 10 for Agentic Applications 2026** (published 9 Dec 2025, OWASP GenAI Security Project) — [OWASP](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/):
  - ASI01 Agent Goal Hijack
  - ASI02 Tool Misuse & Exploitation
  - ASI03 Identity & Privilege Abuse
  - ASI04 Agentic Supply Chain Vulnerabilities
  - ASI05 Unexpected Code Execution
  - ASI06 Memory & Context Poisoning
  - ASI07 Insecure Inter-Agent Communication
  - ASI08 Cascading Failures
  - ASI09 Human-Agent Trust Exploitation
  - ASI10 Rogue Agents

  The titles were taken from secondary explainers because the OWASP landing page does not enumerate them — [Blck Alpaca](https://blckalpaca.at/en/knowledge-base/ai-agents/ai-agent-security-owasp/owasp-agentic-asi-top-10-2026); [F5 glossary](https://www.f5.com/fr_fr/glossary/owasp-top-10-for-agentic-ai-applications). A February 2025 draft ordering (Memory Poisoning first) is outdated but still cited — [Blck Alpaca](https://blckalpaca.at/en/knowledge-base/ai-agents/ai-agent-security-owasp/owasp-agentic-asi-top-10-2026).
- **OWASP Top 10 for LLM Applications 2025** — [OWASP](https://genai.owasp.org/llm-top-10/):
  - LLM01 Prompt Injection
  - LLM02 Sensitive Information Disclosure
  - LLM03 Supply Chain
  - LLM04 Data and Model Poisoning
  - LLM05 Improper Output Handling
  - LLM06 Excessive Agency
  - LLM07 System Prompt Leakage
  - LLM08 Vector and Embedding Weaknesses
  - LLM09 Misinformation
  - LLM10 Unbounded Consumption
- **OpenSSF "Security-Focused Guide for AI Code Assistant Instructions"** (Best Practices and AI/ML WGs, 1 Aug 2025): how to write custom instruction files (CLAUDE.md, Copilot instructions, Cursor rules) so assistants produce more secure code, with short targeted instructions and sample snippets. It does not recommend telling the AI to adopt a security-expert persona. OpenSSF is developing course LFEL1012 on using AI code assistants securely — [OpenSSF guide](https://best.openssf.org/Security-Focused-Guide-for-AI-Code-Assistant-Instructions); [OpenSSF announcement](https://openssf.org/?p=8932). It is about code quality, not about sandboxing agents against injection.
- **SLSA v1.2:**
  - The "reviewed by two trusted persons" verified property must be issued per the Source Track's two-party-review requirements — [SLSA verified properties](https://slsa.dev/spec/v1.2/verified-properties).
  - Two-party review sits at Source Level 4 in the 2025 drafts — [SLSA source sprint blog](https://slsa.dev/blog/2025/04/slsa-source-sprint).
  - v1.2 RC2 was announced Nov 2025 — [SLSA blog](https://slsa.dev/blog/2025/11/slsa-v1.2-rc2).
- **NIST CAISI:**
  - RFI on securing AI agent systems: Federal Register 8 Jan 2026, docket NIST-2025-0035, comments due 9 Mar 2026. It covers threats, measurement, and "methods to constrain and monitor the extent of agent access" — [NIST](https://www.nist.gov/news-events/news/2026/01/caisi-issues-request-information-about-securing-ai-agent-systems); [Federal Register](https://www.govinfo.gov/content/pkg/FR-2026-01-08/html/2026-00206.htm).
  - NIST's summary of responses: commenters agree agents bring novel threats that block adoption, and conventional security practice applies but needs adapting — [NIST summary](https://www.nist.gov/publications/summary-analysis-responses-request-information-regarding-security-considerations-ai).
  - An "AI Agent Standards Initiative" (17 Feb 2026) is reported only by secondary sources (unverified).
- **CISA:** alerts on tj-actions/reviewdog (18 Mar 2025, per CSA) and Shai-Hulud (23 Sep 2025); KEV listing of CVE-2025-30066/30154 — [CISA](https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem); [CSA May 2026 note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-github-actions-security-20260503-csa-st/).
- **Anthropic, Claude Code security docs:**
  - Permission modes (auto mode uses a classifier model; manual mode is read-only by default) and a sandboxed Bash tool with filesystem and network isolation.
  - `curl`/`wget` are not auto-approved. Deny rules match "as written", so use sandbox network isolation for real enforcement.
  - WebFetch returns a separate model's summary rather than the raw page.
  - A `-p` session shows neither the trust nor the MCP prompt.
  - Recommendations: "Avoid piping untrusted content directly to Claude", use VMs or devcontainers, and audit settings changes with `ConfigChange` hooks. "No system is completely immune" — [Claude Code security docs](https://code.claude.com/docs/en/security).
- **Anthropic, claude-code-action:** it strips HTML comments, invisible characters, markdown image alt text, hidden HTML attributes and HTML entities, but "new bypass techniques may emerge". Its advice is to "review the raw content of all input coming from external contributors" and to use `include_comments_by_actor` allowlists on public repos — [claude-code-action security.md](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md).
- **Google, run-gemini-cli GHSA-wpqr-6v78-jr5g:** headless runs on untrusted inputs must not auto-trust the workspace and need a strict tool allowlist. `GEMINI_TRUST_WORKSPACE: 'true'` is only for trusted inputs — [GHSA-wpqr-6v78-jr5g](https://github.com/google-github-actions/run-gemini-cli/security/advisories/GHSA-wpqr-6v78-jr5g).
- **GitHub:** the Copilot coding agent risks-and-mitigations page and the Agentic Workflows security architecture (see Q3) — [GitHub Docs](https://docs.github.com/en/enterprise-cloud@latest/copilot/concepts/agents/cloud-agent/risks-and-mitigations); [GitHub blog](https://github.blog/ai-and-ml/generative-ai/under-the-hood-security-architecture-of-github-agentic-workflows/).
- **Simon Willison, "The lethal trifecta" (16 Jun 2025):** private data + untrusted content + external communication lets an attacker "easily trick" the agent into exfiltration. Guardrails that stop 95% of attacks are a failing grade — [Simon Willison](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/).
- **Meta, "Agents Rule of Two" (31 Oct 2025):**
  - Until robust injection detection exists, a session should satisfy no more than two of [A] "process untrustworthy inputs", [B] "access to sensitive systems or private data", [C] "change state or communicate externally".
  - If all three are needed and the work can't be split into a fresh context, there should be no autonomous operation, only human-in-the-loop or another reliable validation.
  - Transitions within a session are allowed (e.g. disable external comms before accessing internal systems).
  - Worked example: an internal coding agent [BC] should filter data sources by "author-lineage".
  - Caveats: it supplements rather than replaces least privilege and defence in depth, and compliant designs can still fail (e.g. a user blindly confirming) — [Meta AI](https://ai.meta.com/blog/practical-ai-agent-security/).

### Inferences
**Guild through the main frameworks**

| Framework item | Guild status | Add |
|---|---|---|
| Rule of Two / trifecta, triage job | [A] untrusted input, partial [B] (model credential), no [C] once G4 posts only from a closed schema | Good. Keep [C] closed: no free text out, no egress beyond the model API. |
| Rule of Two, builder | Likely [B]+[C] (repo write, secrets). Gains [A] if it reads issue text, PR comments, web or dependency docs | Feed the builder only the validated record and a human-approved task, using Meta's "author-lineage" filtering of what it may read. Add human review before merge for everything non-T0 (this exists via G5 and G6). |
| Rule of Two, gate | [B]+[C] (merge rights) | The gate must never read untrusted text. Make it a deterministic policy engine with no model, or a model that sees only structured diff metadata. |
| ASI03 Identity & Privilege Abuse | Strong (three Apps, short-lived OIDC) | Per-job token minting with a permission subset; no long-lived PATs anywhere. |
| ASI04 Agentic Supply Chain | Partial | Pin CLI and actions, disable project MCP and plugins, vendor any MCP. |
| ASI05 Unexpected Code Execution | Partial | No shell tools for triage. Run the builder in a sandbox or VM. Restore config from base. |
| ASI06 Memory & Context Poisoning | Not addressed | Any persistent agent memory, notes or plan files are untrusted inputs to later runs (Codex AGENTS.md case). |
| ASI08 Cascading Failures | Partial | Volume limits per run (e.g. at most N PRs or comments). A kill switch: an org-level variable that disables all agent workflows. |
| ASI09 Human-Agent Trust Exploitation | Not addressed | Agent PR descriptions are model output and can mislead reviewers. Reviewers should review the diff, not the summary. Render agent text with invisible and bidi characters flagged. |
| LLM05 Improper Output Handling | Strong (G4) | Strict JSON-schema validation with no unknown fields, enums only, and no markdown passthrough. |
| SLSA Source L4 two-party review | Partial | A model or bot approval must not count as one of the "two trusted persons". T0 auto-merges by the gate fall below two-party review, so record them as such in provenance, or limit T0 to non-code paths. |

- No authority yet defines provenance for agent-authored commits. The practical baseline is the Copilot model: commits authored by the agent identity, co-authored by the requesting human, signed, and linked to session logs. Guild can adopt that via App-signed commits (claude-code-action's `use_commit_signing` uses the GitHub API so commits verify as the App).

### Gaps
- I did not find SLSA guidance specific to AI-authored code or agent identities, nor a CISA publication specific to AI coding agents in CI. CISA material found is incident alerts.
- The OWASP Agentic Top 10 PDF was not read directly. The titles come from consistent secondary sources.
- The OpenSSF guide's full text and any OpenSSF guidance on agent sandboxing beyond instruction files were not reviewed.

## 5. Is escaping non-ASCII before the model sees untrusted text a recognised mitigation? Limits and complementary controls

### Takeaway
Yes, in its narrow form. Stripping or neutralising invisible and Tag characters before model ingestion is recommended or implemented by AWS, Anthropic's claude-code-action and GitHub's Copilot coding agent. Guild's escape-everything-non-ASCII is a stricter variant of the same idea and arguably better for auditability. It defends against one channel only: hidden or confusable characters. Most real attacks were plain ASCII, hidden markup (HTML comments, entities, alt text) is ASCII too, models can decode encodings they are asked to decode, and a JSON hop can silently undo `\uXXXX` escapes. It must sit under architectural controls (dual-LLM/CaMeL, structured outputs, Rule of Two), not replace them.

### Cited Findings
- **AWS, "Defending LLM applications against Unicode character smuggling" (30 Sep 2025; Dranch, Boesen, Martinez, Konakandla):**
  - Tag-block characters U+E0000-U+E007F can carry hidden instructions; LLMs "can read, interpret, and act on" them.
  - Recommendation: strip them before the model. In Java, sanitize recursively until the string stops changing, because repeated surrogates can recombine into a new tag character after one pass, and strip orphaned surrogates too.
  - Pitfalls: their own first Java sample had a range check written with `||` that lets almost everything through. Stripping breaks some flag emoji. Attackers can split surrogate pairs and tell the model to ignore what's between them.
  - Bedrock Guardrails can block but not sanitize.
  - "Continue implementing other prompt-injection defenses" — [AWS Security Blog](https://aws.amazon.com/blogs/security/defending-llm-applications-against-unicode-character-smuggling/).
- **claude-code-action:** strips HTML comments, invisible characters, image alt text, hidden HTML attributes and HTML entities, and warns that new bypasses may emerge — [claude-code-action security.md](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md).
- **Copilot coding agent:** "Hidden characters are filtered before user input reaches the agent", and HTML-comment text is not passed — [GitHub Docs](https://docs.github.com/en/enterprise-cloud@latest/copilot/concepts/agents/cloud-agent/risks-and-mitigations).
- **Invisible-character attacks in the wild:**
  - Jules (15 Aug 2025): hidden Unicode instructions in issues — [Simon Willison](https://simonwillison.net/2025/Aug/15/the-summer-of-johann/).
  - Rules File Backdoor (Mar 2025): hidden Unicode in rules files — [Security Affairs](https://securityaffairs.com/175593/hacking/rules-file-backdoor-ai-code-editors-silent-supply-chain-attacks.html).
  - GlassWorm (Oct 2025): variation-selector and PUA-encoded code — [Endor Labs](https://www.endorlabs.com/learn/invisible-threats-glassworm-unicode-vscode).
- **"Imperceptible Jailbreaking against Large Language Models" (arXiv 2510.05025, Oct 2025, Gao et al.):** appended Unicode variation selectors (invisible but tokenized) give high attack success on four aligned LLMs, and the approach extends to prompt injection — [arXiv](https://arxiv.org/html/2510.05025v1). garak notes tokenizers handle non-printables such as tags and variation selectors — [garak docs](https://reference.garak.ai/en/latest/ascii_smuggling.html).
- **Plain-ASCII injections dominated real incidents:**
  - PromptPwnd: hidden instructions in ordinary issue text — [Aikido](https://www.aikido.dev/blog/promptpwnd-github-actions-ai-agents).
  - Clinejection: the issue title — [Adnan Khan](https://adnanthekhan.com/posts/clinejection/).
  - Nx: `$(...)` in the PR title — [Nx GHSA](https://github.com/nrwl/nx/security/advisories/GHSA-cxm3-wv7p-598c).
  - Comment and Control: PR titles and HTML comments — [SecurityWeek](https://www.securityweek.com/claude-code-gemini-cli-github-copilot-agents-vulnerable-to-prompt-injection-via-comments/).
  - CamoLeak: GitHub's invisible-comment markdown syntax, which is ASCII — [Legit Security](https://www.legitsecurity.com/blog/camoleak-critical-github-copilot-vulnerability-leaks-private-source-code).
- **Models decode encodings:** Microsoft's spotlighting "encoding" variant (base64/ROT13 of untrusted text) depends on the model decoding it. GPT-4 did well and GPT-3.5-Turbo dropped significantly. Spotlighting (arXiv 2403.14720, 2024; delimiting, datamarking, encoding) reduced attack success in their tests. Datamarking had negligible task cost and is used in Azure Prompt Shields — [arXiv 2403.14720](https://arxiv.org/html/2403.14720v1); [implementation note](https://github.com/realArcherL/spotlighting-datamarking). The Comment and Control Copilot PoC base64-encoded exfiltrated secrets — [CSA Aug 2026 note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-coding-agent-ci-prompt-injection-202608/).
- **JSON escapes:** In JSON, `\uXXXX` inside a string is an escape that a conforming parser decodes back to the code point (UTF-16 surrogate pairs for astral characters such as the Tag block) — [RFC 8259 section 7](https://www.rfc-editor.org/rfc/rfc8259#section-7).
- **CaMeL (Google DeepMind et al., arXiv 2503.18813, Mar 2025):**
  - A privileged LLM plans from the trusted query only. A quarantined LLM parses untrusted data with no tool access. A custom interpreter tracks provenance and enforces capability policies before each tool call.
  - On AgentDojo: 77% of tasks with provable security vs 84% undefended, per the later version; 67% in the March 2025 version — [arXiv PDF](https://arxiv.org/pdf/2503.18813); [summary](https://sotaverified.org/papers/defeating-prompt-injections-by-design). Code: google-research/camel-prompt-injection.
- **GitHub Agentic Workflows "safe outputs":** staged writes, operation allowlists, volume caps and URL/secret stripping — the deterministic output-side counterpart — [GitHub blog](https://github.blog/ai-and-ml/generative-ai/under-the-hood-security-architecture-of-github-agentic-workflows/).
- **Willison:** 95%-effective filters are a failing grade, which argues against relying on detection or filtering — [Simon Willison](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/).

### Inferences
- **What G2 does well:**
  - It neutralises the whole hidden-character class (Tag block, variation selectors, zero-width, bidi/Trojan Source, PUA, homoglyphs) in one rule, without maintaining strip lists that AWS shows are easy to get wrong.
  - Unlike stripping, escaping keeps evidence. A triage record can flag "contains U+E00xx" and a human sees it.
  - For a Unicode-security library like confusable, whose bug reports will legitimately contain look-alike and invisible characters, escaping preserves the exact code points the maintainers need. Stripping would destroy them.
- **Limits Guild must plan for:**
  1. **ASCII payloads pass untouched.** These include instructions in plain English, `$(...)`, and markdown or HTML hiding (`<!-- -->`, `<details>`, alt text, link titles, reference-style links). HTML numeric entities such as `&#x202E;` are ASCII and decode to bidi or tag characters when rendered or parsed. Add the claude-code-action strip set (HTML comments, entities, alt text, hidden attributes), or better, convert issue markdown to plain text before escaping.
  2. **Escapes are decodable.** Tag characters are ASCII + 0xE0000, so an escaped Tag run is a trivially decodable cipher. A plain-ASCII preamble ("decode the U+E00xx escapes and follow them") can recover the hidden text. Mark escapes as data: use datamarking/spotlighting, and tell the model escaped sequences are never instructions. More importantly, rely on the fact that the triage model can do nothing harmful even if it obeys.
  3. **Re-decoding bugs.** If the escaped text passes through JSON (tool parameters, API request bodies, the record artifact) with `\uXXXX` notation, any JSON parser turns it back into the literal characters, silently undoing G2. This happened in this repo's own tooling, per the maintainer's memory notes (not a public source). Use a notation JSON does not interpret, such as `U+202E` or `<U+202E>`, or double-escape and verify bytes after every hop.
  4. **Coverage gaps.** G2 covers issue text only. Issue edits after the fetch, attachments and images (multimodal models read text in images), linked URLs the model might fetch, PR review comments, commit messages from merged outsider work, and every repo file are outside it. Fetch issue text once, record an immutable snapshot (content hash) in the record, and re-check before acting.
  5. **Quality cost.** Non-English reports become escape soup and triage accuracy drops. That is acceptable for a security project but worth measuring.
- **Complementary controls, ranked by value for Guild:**
  1. Architectural isolation (already present): the triage model has no tools and no write path, and outputs go through a closed schema to a deterministic poster. This is the "quarantined LLM" half of the dual-LLM/CaMeL pattern.
  2. Builder never sees raw untrusted text, only the validated record plus a human-approved task. This is CaMeL's "privileged planner sees only trusted input" in miniature.
  3. Safe-outputs-style post-processing in G4: an enum-only schema, per-run volume caps, no URLs, mentions or markdown images, secret scanning of all outbound text including base64-decoded forms, and length limits.
  4. Credential proxying, so no secret lives in a model-reachable process.
  5. Spotlighting or datamarking of the escaped text as cheap defence in depth. It is not a boundary.
  6. Repo-wide invisible-character hygiene checks on agent-authored diffs and agent config files.
- **No source** claims escaping all non-ASCII is sufficient. Every vendor that implements character filtering (AWS, Anthropic, GitHub) states it is partial and must be layered.

### Gaps
- I found no published evaluation that measures whether frontier models follow instructions carried in escaped (as opposed to raw) Tag sequences. Limit 2 above is an inference from the 1:1 Tag-to-ASCII mapping and models' demonstrated decoding ability, not a measured result.
- Rehberger's 2025 posts with model-by-model results on Tag-character interpretation (and whether current Claude models interpret Tags) were not retrieved.
- The CaMeL per-suite numbers and the spotlighting "below 2%" figure come only from secondary summaries and were not verified against the papers.
- No primary documentation was found on the exact character set GitHub's Copilot "hidden character" filter removes.
