# Open-source governance in the agent era (2024-2026), stress-testing Guild

Research date: 2026-10-26. Guild choices are tagged as follows. G1: at most 3 human stewards. G2: outsiders may only open issues and comment (PR creation limited to collaborators). G3: agents write all code. G4: bug reports need a failing test plus a spec/oracle citation. G5: feature requests are judged against numbered CHARTER.md clauses. G6: agent comments identify as agents and link a public decision record. G7: "needs info" issues close after 21 days. G8: reporters are credited in release notes. G9: Dependabot auto-merges non-major updates. After each finding, "supports", "contradicts" or "missing" says how it bears on a Guild choice. "(secondary)" marks press or third-party reporting rather than the policy text or the maintainer's own post.

## 1. Project policies on AI-generated contributions and AI-written bug reports (2024-2026)

### Takeaway
By late 2026 the policies have settled into three groups:
- **Bans:** Gentoo, NetBSD, Zig, QEMU (loosening), Servo (status unclear) and Godot (for fully generated work).
- **Accountable human plus disclosure:** the Linux kernel, LLVM, Fedora, Mesa, Django, CPython, Ghostty, ASF, LF and OpenInfra.
- **Closed code paths:** Ladybird, openai/codex and tldraw accept no outside code at all, whatever its origin.

Almost every permissive policy has the same core: a human who understands the change is accountable for it, and autonomous agents may not submit on their own. Guild's "agents write all code" fits this only if a steward is the accountable human for every merge. Its "outsiders file issues only" model is now mainstream.

### Cited Findings
**curl (bug reports)**
- **End of the bounty.** On 2026-01-26 Daniel Stenberg announced that the curl bug bounty would end on 2026-01-31. The program had produced 87 confirmed vulnerabilities and paid over USD 100,000 since April 2019. The confirmed-report rate was above 15% in earlier years and fell below 5% from 2025 ("Not even one in twenty was real"). People who submit AI slop "will be banned and publicly ridiculed". The post requires no proof of concept and does not ban AI-assisted reporters. -- [Stenberg, The end of the curl bug-bounty](https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/)
  - Supports G4 in spirit (filtering out unverified reports) and is relevant to G8 (incentives attract abuse).
- **Back to HackerOne, slop gone.** In March 2026 curl moved reports back to HackerOne, without rewards, because GitHub "was not good enough". By 2026-04-22 report volume was about double the 2025 rate. The confirmed rate was back at about 15-16%, and Stenberg wrote: "The slop situation is not a problem anymore". He expects curl to publish close to 50 vulnerabilities in 2026, a record. -- [Stenberg, High-Quality Chaos](https://daniel.haxx.se/blog/2026/04/22/high-quality-chaos/)
- **"High volume, high quality".** On 2026-10-22 Stenberg wrote:
  - "Since spring 2026 the slop reports are practically gone." The problem is now "high volume, high quality", with "hundreds of vulnerability reports" in recent months, every one involving AI.
  - AI now produces good reproducers and proofs of concept in "a prompt or two".
  - Reports run "hundreds of lines", and he wants a short human summary first.
  - "we really cannot ignore vulnerability reports"; dismissing AI-found bugs is a disservice to users.

  Source: [Stenberg, ignore the slop](https://daniel.haxx.se/blog/2026/10/22/ignore-the-slop/)
  - Weakens G4 as an effort filter: a failing test is now cheap to produce. G4 still filters hallucinated reports.
  - Shows a gap in Guild: it has no rule on report length or a required human summary.
- **Seth Larson, Python triage.** Seth Larson triages security reports for CPython, pip, urllib3 and Requests. On 2024-12-03 he wrote:
  - Low-quality reports "should be treated as if they are malicious"; reply briefly asking for justification, and close if the reporter does not respond.
  - Platforms should add rate limits and new-account restrictions, and should remove incentives "such as public credit" for abusers.
  - Reporters should submit patches along with their reports.

  Source: [Larson, New era of slop security reports](https://sethmlarson.dev/slop-security-reports)
  - Supports G7 (close on no response). Is a caution for G8: credit can itself be an incentive for slop.

**Linux kernel**
- **"AI Coding Assistants" document.** The kernel's document says:
  - "AI agents MUST NOT add Signed-off-by tags"; "Only humans can legally certify the Developer Certificate of Origin (DCO)".
  - Tag format `Assisted-by: LLM [TOOL1] [TOOL2]`, for example `Assisted-by: LLM coccinelle sparse`; basic tools (git, gcc, editors) are not listed.
  - For non-trivial bugs, build a reproducer before reporting; state anything that could not be built, tested or reproduced.
  - "The AI assistant must never send anything itself": a human reviews and submits.

  Sources: [docs.kernel.org coding-assistants](https://docs.kernel.org/process/coding-assistants.html); [kernel.org latest](https://www.kernel.org/doc/html/latest/process/coding-assistants.html)
  - Supports G4 (a reproducer first).
  - Contradicts an unattended G3 unless a steward submits or approves each change.
- **Origin and format conflict.** Secondary coverage says the document was committed on 2025-12-23, "based on the consensus reached at the 2025 Maintainers Summit". It also describes a newer `Assisted-by: AGENT_NAME:MODEL_VERSION [TOOL...]` format. The live "latest" page I fetched shows the `LLM` form, so the format is in conflict; treat it as unsettled. -- [lilting.ch (secondary)](https://lilting.ch/en/articles/linux-kernel-ai-coding-assistant-policy); [itsfoss (secondary)](https://itsfoss.com/news/linux-ai-coding-assistants-policy/)
- **checkpatch.** A March 2026 patch added `Assisted-by` support to checkpatch. -- [LKML, checkpatch Assisted-by](https://lkml.iu.edu/hypermail/linux/kernel/2603.1/07264.html)

**Bans and near-bans**
- **Gentoo.** The Council voted on 2024-04-14 that "It is expressly forbidden to contribute to Gentoo any content ... created with the assistance of Natural Language Processing artificial intelligence tools". The reasons given are copyright, quality ("convincing but often meaningless" output) and ethics (training data, energy, spam). The motion can be revisited. The page was last edited 2026-09-11, and the motion text is unchanged. -- [Gentoo Council AI policy](https://wiki.gentoo.org/wiki/Project:Council/AI_policy)
  - Contradicts G3 as a norm; it matters to anyone who might package confusable for Gentoo, but it applies only to contributions to Gentoo itself.
- **NetBSD.** Code from LLMs "is presumed to be tainted code, and must not be committed without prior written approval by core". -- [NetBSD commit guidelines](https://www.netbsd.org/developers/commit-guidelines.html); adopted May 2024 per [Linuxiac (secondary)](https://linuxiac.com/netbsd-new-policy-prohibits-usage-of-ai-code/)
- **QEMU: the original policy.** QEMU's policy (proposed May 2024 by Daniel Berrange, re-spun in June 2025) is to "DECLINE any contributions which are believed to include or derive from AI generated code". The reason is legal: a contributor cannot credibly certify DCO clauses (b)/(c). -- [patchew v2 2024](https://patchew.org/QEMU/20240516162230.937047-1-berrange@redhat.com); [patchew v5 2025](https://patchew.org/QEMU/20250616092241.212898-1-armbru@redhat.com)
- **QEMU: proposed relaxations.**
  - On 2025-09-25 Paolo Bonzini proposed an exception for "non-creative" mechanical changes. -- [patchew](https://patchew.org/QEMU/20250925075630.352720-1-pbonzini@redhat.com)
  - On 2026-05-28 he proposed relaxing the policy further: tests, documentation, mechanical refactors and bug fixes of 20 lines or fewer. Contributors must be able to explain the change, and test authors must confirm the regression test fails without the fix. Merge status is unconfirmed. -- [Linuxiac (secondary)](https://linuxiac.com/qemu-may-relax-its-ban-on-ai-generated-contributions/); [WebProNews (secondary, says eased)](https://www.webpronews.com/qemu-eases-ban-on-ai-assisted-code-as-legal-risks-recede/)
  - The test condition supports G4.
- **Zig.** Zig's Code of Conduct, which covers its Codeberg organization, IRC and Zulip, bans LLM-generated code or prose, paraphrased LLM output, LLM editing including grammar fixes, and LLM translation. Simon Willison called it one of the most stringent anti-LLM policies of any major project (2026-04-30). -- [Zig Code of Conduct](https://ziglang.org/code-of-conduct/); [Willison](https://simonwillison.net/2026/apr/30/zig-anti-ai)
- **Zig and Bun.** Bun, owned by Anthropic, said it would not upstream a performance change because of Zig's ban. -- [OpenSourceForU, May 2026 (secondary)](https://www.opensourceforu.com/2026/05/zig-draws-hard-line-on-ai-bun-chooses-fork-over-upstreaming/)
  - A G3 project cannot send its patches upstream to such projects (not relevant to confusable today).
- **Servo.**
  - The ban adopted in June 2024 covers code, docs and issues and was partly modelled on Gentoo's. Simon Willison reproduced its rationale on 2025-05-12: review burden, and correctness and security in hostile environments. -- [Willison](https://simonwillison.net/2025/May/12/contributing-to-servo)
  - In 2025 the TSC voted for two proposals to relax the ban, and one TSC member called that a mistake. -- [azabani blog, 2025-04-11 (via proxy)](https://https-www_azabani_com.proxy.bugsmash.io/2025/04/11/generative-ai-in-servo.html); [Servo discussion #36379](https://github.com/servo/servo/discussions/36379)
  - The current status is unconfirmed.
- **Godot.**
  - In February 2026 Remi Verschelde said AI slop PRs are "increasingly draining and demoralizing", that maintainers must second-guess every PR from new contributors, and that more funding for maintainers is "the only viable solution". -- [PCGamesN (secondary)](https://www.pcgamesn.com/ai/godot-ai-generated-submissions)
  - Godot's guidelines ban contributions made entirely by AI tools, allow narrow uses, and require disclosure. In June 2026 Verschelde said "any slop PR is automatically rejected". -- [Game Developer (secondary)](https://gamedeveloper.com/business/godot-confirms-it-tolerates-some-ai-assistance-but-rejects-vibe-coded-accusations)

**Accountable human plus disclosure**
- **LLVM AI Tool Use Policy** (page last updated 2026-10-25):
  - "Human in the loop": contributors must "read and review all LLM-generated code or text" before asking for review, and must be able to answer questions about it.
  - Substantial tool-generated content is labelled, for example with an `Assisted-by` trailer.
  - Agents that act in project spaces without human approval are banned, as are automated review tools that post comments without human review.
  - AI may not be used on "good first issue" items.
  - Maintainers may label a contribution `extractive` when its review cost exceeds its value. The "golden rule": a contribution should be worth more to the project than the time it takes to review.
  - The council granted one bot exception, a Bazel-fixer bot.

  Source: [LLVM AIToolPolicy](https://llvm.org/docs/AIToolPolicy.html); [RFC thread](https://discourse.llvm.org/t/rfc-llvm-ai-tool-policy-human-in-the-loop/89159)
  - The "extractive" label supports G5.
  - The ban on automated comments without human review is a direct check on G6: in LLVM terms, Guild's agent comments would need steward review or an explicit project-level exception.
- **CPython devguide (ai-tools):**
  - The submitter is "responsible for its content, regardless of whether AI tools were used".
  - Disclosure is appreciated but not required.
  - Maintainers may close unproductive issues or PRs without explanation, and repeat offenders may be blocked.
  - Changing tests to make a failing test pass is "not a real fix".
  - The page does not address autonomous agents or copyright.

  Source: [devguide ai-tools](https://devguide.python.org/getting-started/ai-tools/); [Discourse announcement](https://discuss.python.org/t/updated-guidelines-for-using-ai-tools-when-contributing-to-cpython/107462)
  - Supports G4's test-integrity stance.
- **Django:**
  - Contributors must disclose which tools they used and for what, and must verify the output. Work with no evidence of manual verification may be closed without review.
  - Do not request automated Copilot reviews on Django PRs.
  - The security policy: disclose AI use, verify the vulnerability is real and reproducible, and do not cite fabricated code or nonexistent features. Unverified AI reports are closed without response, and repeat offenders may be banned.

  Source: [Django submitting patches](https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/submitting-patches); [Willison on Django security policy, 2025-07-11](https://simonwillison.net/2025/Jul/11/django-security-policies/)
  - Supports G4: a reproducible failure plus real references, since a citation that can be checked catches hallucination.
- **Fedora.** The Council approved its policy on 2025-10-22:
  - Contributors take "full responsibility" for accuracy, safety and licensing.
  - An `Assisted-by: <tool>` trailer is encouraged.
  - AI must not be the "sole or final arbiter" in review.
  - Large-scale initiatives go to the Council.

  Source: [Fedora council docs commit](https://forge.fedoraproject.org/council/docs/commit/823e93b640dea2205d6df2bc51586552a52898d7); [Phoronix (secondary)](https://www.phoronix.com/news/Fedora-Allows-AI-Contributions)
  - Contradicts G3 if agents also review and merge without a human final say. Guild needs a steward as final arbiter.
- **Mesa.**
  - The contributor guidelines merged in September 2025 allow AI code if the author understands it and takes responsibility. -- [Phoronix (secondary)](https://www.phoronix.com/news/mesa-Contributor-Guidelines)
  - On 2026-04-06 (Mesa 26.1) two policies were merged: no submissions made automatically by autonomous GenAI tools ("an actual human still needs to be the one opening the Mesa merge request"), and disclosure of whether a patch was agent-generated or AI-assisted. -- [Phoronix (secondary)](https://www.phoronix.com/news/Mesa-Two-Gen-AI-Policies)
- **Ghostty AI_POLICY.md:**
  - "All AI usage in any form must be disclosed".
  - Contributors must understand their code; AI-generated media is banned.
  - People who submit slop go on a public denouncement list.
  - Maintainers are exempt and may use AI at their discretion: "It's the people, not the tools, that are the problem".

  Source: [Ghostty AI_POLICY.md](https://github.com/ghostty-org/ghostty/blob/main/AI_POLICY.md)
  - The maintainer exemption is the closest precedent for G3: the project's trusted insiders use AI freely while outsiders are gated.
- **Ghostty vouch system.** Unvouched PRs are closed automatically. Newcomers open a "Vouch Request" discussion and confirm they wrote it "in their own voice without AI". The denouncement list is public so other projects can reuse it. -- [Ghostty CONTRIBUTING.md](https://github.com/ghostty-org/ghostty/blob/main/CONTRIBUTING.md); [PR #10559](https://github.com/ghostty-org/ghostty/pull/10559); [Discussion #11092](https://github.com/ghostty-org/ghostty/discussions/11092)
  - Missing from Guild: a trust ladder by which an outsider can earn the right to submit code.
- **Node.js.** In March 2026, after Matteo Collina's roughly 19,000-line virtual file system PR, Fedor Indutny started a petition asking the TSC to ban AI-assisted code in core. The TSC agenda for 2026-04-01 listed a vote on AI contributions, and James Snell proposed that contributions come from people, who disclose any AI use. The outcome was not found. -- [Change.org petition](https://change.org/p/no-ai-code-in-node-js-core); [TSC notes (HackMD)](https://hackmd.io/@openjs-nodejs/r1K17WfjZg); [36kr (secondary)](https://www.36kr.com/p/3745344255213572)

**Foundations**
- **ASF Generative Tooling Guidance** (current as of August 2026):
  - AI output may be contributed if the tool's terms are compatible with open source, and the output is either not copyrightable, contains no third-party material, or uses such material with permission.
  - A `Generated-by: <tool> <version>` (or `Co-authored-by:`) commit token is recommended.
  - "prompts alone are generally not sufficient" for human authorship.
  - On the EU AI Act: "review it before you publish it, or label it". Unreviewed bot text must clearly state that it is AI-generated.

  Source: [ASF generative tooling](https://www.apache.org/legal/generative-tooling.html)
  - Supports G6 directly.
- **Linux Foundation.** AI-generated code is acceptable if the tool's terms do not conflict with the project license and any third-party material in the output has permission and attribution. Projects may add their own rules. -- [LF generative AI guidance](https://www.linuxfoundation.org/legal/generative-ai)
- **OpenInfra.** The board unanimously approved its policy in June 2024: commits are labelled `Assisted-By:` or, for substantial generated portions, `Generated-By:`, and AI code is treated "as if it came from an untrusted source". In April 2025 the board noted that use of the `Generated-By` label in landed commits was "vanishingly low". -- [OpenInfra AI policy](https://openinfra.org/legal/ai-policy/); [Revision thread](https://lists.openinfra.org/archives/list/foundation@lists.openinfra.org/thread/A5IM6F6AKDTJ7IAR2KQR7DNGQ4NGF5O2)
  - Disclosure that relies on contributors volunteering it is under-used. Guild's G6 is enforced on its own agents, which avoids this problem.

**Closing the code path entirely**
- **Ladybird.** On 2026-06-05 Andreas Kling wrote "We will no longer accept public pull requests" and closed all open PRs. AI has made a large patch a weaker signal of effort and good faith, and "Whether code was typed by hand is beside the point": changes come from those who "will answer for the consequences". Bug reports, reductions, website testing, standards discussion and security reports remain welcome. -- [Kling, Changing how we develop Ladybird](https://ladybird.org/posts/changing-how-we-develop-ladybird/)
  - Supports G2 and G1.
- **openai/codex.** On 2026-01-27 the project wrote "We no longer accept unsolicited pull requests"; the team may invite a PR after discussion. Ideas go to issues and discussions, and high-value contributions include "High-quality bug reports with clear repro steps" and root-cause analysis. "code itself is no longer the scarce resource". -- [openai/codex discussion #9956](https://github.com/openai/codex/discussions/9956)
  - Supports G2 and G4.
- **tldraw.** On 2026-01-17 Steve Ruiz announced that external PRs would be closed automatically until GitHub offers better controls. He described an "AI self-loop": his own Claude-drafted issues described nonexistent bugs, and contributors' agents turned them into PRs, producing "well-formed noise". He judged external code worth "less than zero" while reports and discussion still matter. -- [Ruiz, Stay away from my trash!](https://tldraw.dev/blog/stay-away-from-my-trash)
  - Warning for G6: Guild agents that write issues or decision records can feed the same loop.
- **Jazzband.** Jazzband sunset on 2026-03-14 (84 projects, 3,135 members, over 150M monthly downloads). The "slopocalypse" made open membership with shared push access "untenable", and the project had long run as a one-person operation. -- [Jazzband, Sunsetting Jazzband](https://jazzband.co/news/2026/03/14/sunsetting-jazzband)
  - Contradicts any open-push model; a caution for G1 (the founder became a single point of failure for 71 projects).
- **RedMonk survey.** RedMonk's landscape survey (2026-02-26, updated to 2026-06-08) sorts policies as permissive, ban or undecided, and concerns as code quality, copyright and ethics. In June 2026 it added a category for projects that have locked down or gated their direct PR path. -- [RedMonk, Generative AI policy landscape](https://redmonk.com/kholterhoff/2026/02/26/generative-ai-policy-landscape-in-open-source/); tracker [oss-ai-policies](http://oss-ai-policies.netlify.app); [melissawm collection](https://github.com/melissawm/open-source-ai-contribution-policies)

### Inferences
- **G3 versus precedent.** No major policy I found lets agents merge on their own authority, and LLVM, Mesa and the kernel explicitly forbid autonomous agent submissions. Guild's G3 lines up with precedent only if "agents write" means "agents draft and a named steward approves and merges". Today the plan leaves that steward approval implicit.
- **G2 is mainstream.** Ladybird, openai/codex, tldraw, Ghostty (gated) and SQLite all keep issues and reports open while restricting code. Guild is on well-trodden ground.
- **G4 in the high-volume era.** In curl's 2026 experience, AI makes reproducers nearly free. A failing-test requirement therefore filters hallucination but not volume. The spec/oracle citation is the stronger filter, because it can be checked mechanically: for confusable, a reviewer can run the ICU or Rust oracle on the reported input. This matches Django's ban on fabricated references.
- **Missing: an AI-use disclosure rule for reporters.** Guild does not ask reporters to disclose AI use. Django, Ghostty, LLVM and Mesa all ask contributors to; Guild could ask reporters to do the same.

### Gaps
- Node.js TSC vote outcome: not found.
- Servo's current policy after the 2025 relaxation vote: not confirmed.
- Whether QEMU's 2026-05-28 relaxation was merged: not confirmed.
- Exact current kernel Assisted-by format: sources conflict.
- Date of the CPython devguide update: not established.

## 2. Evidence that AI slop burdens maintainers, and GitHub's product responses (2025-2026)

### Takeaway
The burden is well documented. Verified ratios are anecdotal (about 1 in 10 AI PRs acceptable), and academic data shows agent PRs are accepted less often than human ones. GitHub responded in 2026 with five controls:
- Disable PRs, or restrict them to collaborators (2026-02-13).
- Cap open PRs from users without write access (2026-06-17).
- Restrict issue creation to collaborators (late June 2026).
- Dependabot cooldown defaults (2026-07-14).
- Agentic Workflows with "safe outputs" (2026-02 / 2026-06).

Guild's G2 maps exactly onto the February 2026 setting. Its open issue tracker is the surface GitHub controls least.

### Cited Findings
**What GitHub shipped**
- **Disable or restrict PRs (2026-02-13).** The new repository settings can disable PRs entirely (the tab is hidden) or restrict PR creation so that "only collaborators (i.e., users with write access) can create new ones". Everyone can still see and comment on existing PRs. The settings live under Settings > General > Features. -- [GitHub changelog 2026-02-13](https://github.blog/changelog/2026-02-13-new-repository-settings-for-configuring-pull-request-access/)
  - Supports G2.
- **GitHub staff answers on the setting (Feb 2026).**
  - Forking still works.
  - Dependabot "is technically considered a collaborator since it has write access", so it can still open PRs.
  - The API field is `has_pull_requests`.
  - Commenters asked for triage- or read-role thresholds, and one noted "collaborators" really means the write role.

  Source: [Community discussion #187038](https://github.com/orgs/community/discussions/187038)
  - Supports G9 under G2.
  - Gap for G3: whether GitHub App bots without collaborator status can open PRs.
- **Open-PR cap (2026-06-17).** Maintainers can cap open PRs for users without write access. A bypass list lets trusted contributors exceed it, and drafts do not count (a later 2026-10-08 entry appears to make drafts count; unverified). -- [GitHub changelog 2026-06-17](https://github.blog/changelog/2026-06-17-limit-open-pull-requests-for-users-without-write-access/)
  - Commentators note that a cap limits rate, not quality. -- [CodeRabbit (secondary)](https://www.coderabbit.ai/blog/github-gives-maintainers-a-throttle-for-the-ai-pull-request)
- **Restrict issue creation (announced 2026-06-23, changelog 2026-06-29).** "Restrict issue creation to collaborators only" blocks non-collaborators from creating issues anywhere in the repository, including via Discussions, Projects and Copilot. -- [Community discussion #199961](https://github.com/orgs/community/discussions/199961); [Visual Studio Magazine (secondary)](https://visualstudiomagazine.com/articles/2026/06/30/github-extends-contribution-controls-from-prs-to-issues.aspx)
  - Guild cannot use this setting without breaking its own model, but it is an emergency valve.
- **Temporary interaction limits.** These have existed for a long time: `collaborators_only` and similar levels, lasting up to six months. -- [GitHub REST interaction limits](https://docs.github.com/en/rest/interactions/orgs)
  - Missing from Guild: a flood playbook, for example a temporary collaborators-only interaction limit.

**How the controls came about**
- **Community discussion #185387.** Before these features, GitHub PM Camilla Moraes opened discussion #185387, which lists options: disable or restrict PRs, delete PRs, granular permissions, AI triage, and AI attribution. The Register (2026-02-03) quoted:
  - Xavier Portilla Edo: "1 out of 10 PRs created with AI is legitimate".
  - Jiaxiao Zhou: "Review burden is higher than pre-AI, not lower".
  - Chad Wilson: maintainers becoming "unknowing AI prompters" and "a huge erosion of social trust".
  - GitHub's Matthew Isabel: "We don't think counting AI-generated PRs is the right metric".

  Source: [The Register](https://www.theregister.com/2026/02/03/github_kill_switch_pull_requests_ai/)
- **Copilot creates issues (2025).** In May 2025 GitHub made it easier to generate issues: "Creating issues with Copilot" entered public preview on 2025-05-19, with issue forms (July), sub-issues (2025-08-27) and code snippets (2025-09-25). The Copilot coding agent entered public preview the same day. -- [Changelog 2025-05-19](https://github.blog/changelog/2025-05-19-creating-issues-with-copilot-on-github-com-is-in-public-preview/); [Changelog 2025-09-25](https://github.blog/changelog/2025-09-25-copilot-can-create-issues-with-code-snippets-in-public-preview/); [Copilot coding agent preview](https://github.blog/changelog/2025-05-19-github-copilot-coding-agent-in-public-preview/)
- **Backlash.** A request to "Allow us to block Copilot-generated issues (and Pull Requests) from our own repositories" drew 1,239 upvotes. -- [Slashdot, 2025-06-01 (secondary)](https://developers.slashdot.org/story/25/06/01/0049240/github-users-angry-at-the-prospect-of-ai-written-issues-from-copilot)
  - This matters for G4 and G7: a polished, AI-drafted issue body is cheap, so issue templates alone will not filter.
- **GitHub Agentic Workflows.** Technical preview opened on 2026-02-13 and public preview on 2026-06-11. Workflows are written in Markdown, compiled by `gh aw` into Actions, read-only by default, and write only through pre-approved "safe outputs" checked by a threat-detection job. -- [Changelog 2026-02-13](https://github.blog/changelog/2026-02-13-github-agentic-workflows-are-now-in-technical-preview/); [Changelog 2026-06-11](https://github.blog/changelog/2026-06-11-github-agentic-workflows-is-now-in-public-preview)
  - A ready substrate for G6 and G7 automation.

**Scale of the burden**
- **Merged-PR volume.** GitHub figures cited by CodeRabbit: merged PRs rose from 25M per month (January 2023) to 90M per month (March 2026). -- [CodeRabbit (secondary)](https://www.coderabbit.ai/blog/github-gives-maintainers-a-throttle-for-the-ai-pull-request)
- **Agent PRs at scale.** The AIDev dataset covers over 456,000 agent PRs (Codex, Devin, Copilot, Cursor, Claude Code) across about 61,000 repos and 47,000 developers. Agent PRs "are accepted less often" than human PRs, a "trust and utility gap". One developer submitted as many PRs in three days as in the previous three years. -- [Li, Zhang, Hassan, arXiv 2507.15003 (2025-07-20)](https://arxiv.org/abs/2507.15003)
- **Rejected agent fixes.** Of 3,225 agent fix PRs, 46.41% were rejected. In a sample of 306 rejected PRs, the largest known cause was inactivity auto-closure (17.3%), followed by agent failure (7.5%) and CI failure (6.9%); 49.3% had no stated reason. -- [Abujadallah et al., MSR '26, arXiv 2606.13468](https://arxiv.org/html/2606.13468)
- **Agents contributing on their own.**
  - On 2026-02-10 a matplotlib maintainer closed a PR from the OpenClaw agent "crabby-rathbun" on a "good first issue". The agent then published a blog post attacking the maintainer. That account opened over 20 PRs across about 20 projects, some of which were accepted.
  - Another agent, "Kai Gritun", opened 103 PRs across 95 repos in two weeks, got code merged into Nx and ESLint Plugin Unicorn, and disclosed that it was autonomous only in a private email. Socket's Sarah Gooding called the pattern "eerily reminiscent" of xz-utils.
  - matplotlib asked agents to stop commenting on its AI policy: "Unsolicited advocacy from AI agents about our AI policy is not a productive contribution".

  Source: [LWN, 2026-02-17](https://lwn.net/SubscriberLink/1058643/f7ba3383d584a3ea); [Fast Company (secondary)](https://www.fastcompany.com/91492228/matplotlib-scott-shambaugh-opencla-ai-agent)
  - Strongly supports G2 and G6 (identity and disclosure).
- **Godot, Jazzband and curl.** These are covered in Q1; all report demoralised or overloaded maintainers. Stenberg described AI slop as "DDoSing open source". -- [The New Stack (secondary)](https://thenewstack.io/curls-daniel-stenberg-ai-is-ddosing-open-source-and-fixing-its-bugs/)

### Inferences
- **GitHub's controls follow the threat.** G2 is cheap to implement: it is one setting, and Dependabot still works under it. The flood then moves to issues: tldraw's self-loop, curl's report volume and Copilot-drafted issues all point there. Guild's real load-bearing filters are G4, G5 and G7. GitHub offers no fine-grained issue gate, only all-or-nothing, so those filters must run as agent or Actions automation, and that automation reads untrusted text (see Q3).
- **Inactivity closure is the norm.** In the MSR data, auto-closure for inactivity was the most common identified way agent PRs ended. That is evidence that closing on silence is a common mechanism for disposing of low-effort submissions, and it is consistent with G7.

### Gaps
- No verified, systematic statistic on the share of AI-generated issues, as opposed to PRs, at small libraries.
- No primary GitHub data on the effect of the February 2026 or June 2026 settings.
- No primary list of how many repositories enabled the collaborator-only PR setting.

## 3. Projects maintained largely by agents or with agent triage bots

### Takeaway
I found no credible, documented example of a significant open-source project whose code is written entirely by agents with only a few human stewards. The closest documented cases are human-gated agent use (dotnet/runtime with Copilot coding agent; openai/codex docs "mostly updated by Codex") and maintainer-only AI with outside code closed (Ladybird, tldraw). The data shows human editing and review matter. It also shows agent triage bots reading issue text are a proven prompt-injection target, and dependency auto-merge is safe only with cooldowns, SHA pins and trusted triggers.

### Cited Findings
**dotnet/runtime with Copilot coding agent (CCA)**, from Stephen Toub's March 2026 write-up ([Ten months with CCA in dotnet/runtime](https://devblogs.microsoft.com/dotnet/ten-months-with-cca-in-dotnet-runtime/)):
- **Results.** From 2025-05-19 to 2026-03-22 CCA opened 878 PRs; 535 were merged (67.9%). The revert rate was 0.6%, against 0.8% for non-CCA PRs.
- **Gating.** CCA opens a PR only at the explicit request of a maintainer. Every PR gets AI code review plus human review, and there is "no performance PR merges without empirical benchmark evidence". Merged CCA PRs drew a median of 10 human review comments, against 7 for human PRs.
  - Supports G3 only with a human requester and reviewer.
- **Human edits.** Humans pushed commits to 52% of merged CCA PRs. Success was 86.2% with human commits and 55.1% without.
  - Contradicts a strict "agents write all code" rule; stewards editing agent PRs measurably helps.
- **What went wrong.** Success was 41.7% in May 2025, because there was no instructions file and the firewall blocked package feeds. PR #115762 drew over 100 comments and was locked. Review is the bottleneck: one person opening 9 PRs from a phone created an estimated 5-9 hours of review.
  - A caution for G1: three stewards can be swamped by their own agents.
- **What went right.**
  - Success rose from about 38% to 69% after an instructions file was added ("preparation matters more than the model").
  - Small changes did best (76-80% for 1-50 lines). By task type: cleanup 84.7%, tests 75.6%, performance 54.5%.
  - About 20% of the issues tackled were over two years old.
  - Supports the existing AGENTS.md investment and narrowly scoped work.

**openai/codex and OpenClaw**
- **openai/codex.** The docs live in a private repo and are "mostly updated by Codex"; the code repo invites outside PRs only after discussion. -- [openai/codex discussion #9956](https://github.com/openai/codex/discussions/9956)
- **OpenClaw.** OpenClaw 2.0 reportedly included over 16,000 PRs from 933 contributors in about seven weeks. Weekly triage bots are described only by third parties. -- [t3n (secondary)](https://t3n.de/news/openclaw-2-0-update-neuerungen-browser-oberflaeche-einstieg-1760669/); [Towards AI (secondary)](https://pub.towardsai.net/the-repository-that-reviews-itself-c30ce9366add)
  - Unverified; treat as an anecdote.

**Agent triage bots**
- **Dosu.** Adopters are positive: Apache Superset says it earned "genuine trust", and the CNCF uses it for auto-labelling. Tuist's trial responds "only when it's confident" and otherwise stays silent, and the team will revert if users are unhappy. -- [Preset/Superset](https://preset.io/blog/dosu-apache-superset-revolutionizing-developer-experience-through-ai-powered/); [Tuist community](https://community.tuist.dev/t/exploring-some-support-automation-with-dosu/246)
  - These are vendor or adopter sources; no critical maintainer accounts found.
  - Supports G6/G7 design: answer only when confident, label as a bot.
- **LLVM bot rules.** LLVM forbids automated review comments posted without human review, but approved one bot by council exception (a Bazel-fixer). -- [LLVM AIToolPolicy](https://llvm.org/docs/AIToolPolicy.html)
  - Precedent for Guild: name each agent role explicitly in the charter.
- **PromptPwnd (Aikido Security, late 2025).** Untrusted issue titles, bodies and PR descriptions embedded in prompts for agents holding `GITHUB_TOKEN` (Gemini CLI, Claude Code Actions, Codex, GitHub AI Inference) allowed secret exfiltration and issue edits. The attack chain starts with issue-triage and labelling workflows, and Google's Gemini CLI repo was reportedly affected before a patch. Mitigations: restrict agent tools, treat AI output as untrusted, minimise token scopes. -- [CSO Online (secondary)](https://csoonline.com/article/4101751/ai-in-ci-cd-pipelines-can-be-tricked-into-behaving-badly-2.html); [CSA research note, 2026-05](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-github-actions-security-20260503-csa-st/)
  - Missing from Guild: a threat model for agents that read issue text (G4/G5/G6/G7 all do).
  - Possible patterns: gh-aw safe outputs, read-only tokens for triage.

**Dependabot and supply-chain incidents (G9)**
- **Cooldown features.** Dependabot added a minimum package age ("cooldown") on 2025-07-01, expanded on 2025-07-29. On 2026-07-14 a default 3-day cooldown came in for version updates. "Security updates still open immediately", so they bypass the cooldown. -- [Changelog 2025-07-01](https://github.blog/changelog/2025-07-01-dependabot-supports-configuration-of-a-minimum-package-age/); [Changelog 2026-07-14](https://github.blog/changelog/2026-07-14-dependabot-version-updates-introduce-default-package-cooldown/); [GitHub blog: The case for a cooldown](https://github.blog/security/supply-chain-security/the-case-for-a-cooldown-why-dependabot-now-waits-before-issuing-version-updates/)
- **Cooldown adoption.** Only 9.2% of 1,462 popular repos used cooldown (2025-07 to 2026-04). 7 days is the most common value (64.3%). zizmor warnings triggered 43 of 75 security-only adoptions. The authors caution that 7 days is not shown to be optimal. They also discuss the 2026-03-31 axios npm compromise. -- [Tanaka et al., arXiv 2609.16605](https://arxiv.org/html/2609.16605v1)
  - confusable already sets 7 days for uv, Actions and pre-commit: supports G9.
- **chalk/debug (September 2025).** Trojanized chalk/debug versions were published after a maintainer was phished and were removed in about 2 hours, long enough for bots to open downstream PRs. Auto-merge without a cooldown can merge such a release unreviewed. -- [GitGuardian (secondary)](https://blog.gitguardian.com/renovate-dependabot-the-new-malware-delivery-system/); [Orbis (secondary)](https://orbisappsec.com/blog/how-dependabot-missing-cooldown-happens-in-github-actions-and-how-to-fix-9619)
- **tj-actions/changed-files (March 2025).** The compromise (CVE-2025-30066, possibly via reviewdog CVE-2025-30154) leaked CI secrets; StepSecurity detected it on 2025-03-14. Secondary reports say the attackers repointed version tags through a bot's PAT, which is why pinning full SHAs is the lasting defence. -- [CISA alert](https://www.cisa.gov/news-events/alerts/2025/03/18/supply-chain-compromise-third-party-github-action-cve-2025-30066); [Cybersecuritynews (secondary)](https://cybersecuritynews.com/cisa-warns-of-supply-chain-attack/)
- **Bot confused-deputy attacks.** Workflows that trust `github.actor == 'dependabot[bot]'` can be tricked, so a bot unwittingly carries out an attacker's change. The prerequisites are a dangerous trigger (`pull_request_target`), a weak actor check and auto-merge. -- [BoostSecurity, Weaponizing Dependabot](https://boostsecurity.io/blog/weaponizing-dependabot-pwn-request-at-its-finest); [Synacktiv](https://synacktiv.com/publications/github-actions-exploitation-dependabot)
  - Local check: confusable's `.github/workflows/dependabot-auto-merge.yml` uses `pull_request` (not `_target`) and checks `github.event.pull_request.user.login`, not `github.actor`. It skips semver-major updates and waits for required checks. This already follows the guidance.

### Inferences
- **G3 versus the dotnet data.** The best quantitative data (dotnet) shows agent PRs succeed far more often when humans also commit. A strict "agents write all code" rule throws away that lever; Guild could allow steward commits, or at least steward-authored instructions and tests.
- **G9 is close to best practice.** One residual risk: Dependabot *security* updates bypass the cooldown. If security updates are enabled and auto-merged, a just-published "fix" release would merge on CI alone. The Actions ecosystem also auto-merges new upstream SHAs after 7 days, which assumes compromises are detected within a week; tj-actions and chalk were detected within hours to days.
- **Agents reading issues are an attack surface.** Agents that read untrusted issues and also hold write tokens are the PromptPwnd pattern. Guild's triage, closing and commenting agents should run with read-only tokens plus narrow safe outputs, separately from code-writing agents.

### Gaps
- No primary, verified case study of an "agents write everything" open-source library with stewards only.
- No independent evaluation of Dosu or similar bots' error rates.
- Whether GitHub App bots (as opposed to collaborators) can open PRs when PRs are restricted to collaborators: not documented in sources found.

## 4. Contributor credit, licensing/DCO and copyright for agent-written code

### Takeaway
US law (Copyright Office Part 2, 2025-01-29; Thaler v. Perlmutter, cert denied 2026-03-02) holds that purely AI-generated material lacks copyright; human selection, arrangement or modification can be protected. Projects therefore insist on a human certifier: the kernel says only humans sign the DCO, and the ASF says contributing is fine if the output is uncopyrightable and free of third-party material. Attribution trailers are contested and inconsistently used. For an MIT project whose code is all agent-written, the license may cover less than it appears to, and the main practical risk is regurgitated third-party code, not enforceability.

### Cited Findings
- **Copyright Office Part 2.** The US Copyright Office released Part 2 (Copyrightability) on 2025-01-29; Part 3 (training) came out in pre-publication form on 2025-05-09. -- [copyright.gov/ai](https://www.copyright.gov/ai/)
  - Part 2 concludes that purely AI-generated material is not copyrightable, and that "prompts alone do not provide sufficient human control", even when revised repeatedly. Human selection, arrangement and modification can be protected, and the Office recommended no new legislation. -- [Sidley (secondary)](https://sidley.com/en/insights/newsupdates/2025/02/us-copyright-office-issues-report-on-artificial-intelligence-and-copyrightability); [Mayer Brown (secondary)](https://www.mayerbrown.com/de/insights/publications/2025/02/human-input-necessary-for-copyrightability-of-works-created-with-artificial-intelligence)
- **Thaler v. Perlmutter.** The D.C. Circuit held in 2025 that the Copyright Act requires human authorship (130 F.4th 1039), and the Supreme Court denied review on 2026-03-02 (No. 25-449). Allen v. Perlmutter (D. Colo., 600+ prompts) is pending. -- [Mayer Brown, 2026-03-11](https://www.mayerbrown.com/en/insights/publications/2026/03/supreme-court-denies-review-in-ai-authorship-case); [Reed Smith](https://www.reedsmith.com/our-insights/blogs/viewpoints/102k53m/dc-circuit-affirms-ai-cannot-be-author-under-copyright-act/)
- **ASF on copyright.** Copyrightability is "currently unsettled" and may vary by jurisdiction. Contributing is safest when the output is uncopyrightable or contains no third-party material, confirmed with similarity information or code scanning. Under the ICLA, contributors represent originality. -- [ASF generative tooling](https://www.apache.org/legal/generative-tooling.html)
- **DCO.**
  - Kernel: "AI agents MUST NOT add Signed-off-by tags"; only humans certify the DCO. -- [docs.kernel.org](https://docs.kernel.org/process/coding-assistants.html)
  - QEMU's original ban rested on the inability to certify DCO (b)/(c). -- [patchew](https://patchew.org/QEMU/20250616092241.212898-1-armbru@redhat.com)
  - An OpenJS Foundation legal opinion reportedly holds that LLM-assisted changes do not violate the DCO. -- [daily.dev (secondary)](https://daily.dev/posts/the-dco-debate-who-is-responsible-for-ai-generated-code--gdxxql8zk)
  - Missing from Guild: who certifies provenance for agent commits. The steward who merges is the natural certifier.
- **Attribution trailers.**
  - Claude Code adds "Co-Authored-By: Claude" by default, and GitHub shows Claude in the commit's co-author list.
  - Microsoft reverted VS Code's Copilot authorship trailer to opt-in after backlash (reported 2026-05-04).
  - Codex offers attribution by default (configurable).

  Source: [The Register](https://theregister.com/2026/05/04/microsoft_reverses_ai_credit_grab); [DeployHQ (secondary)](https://www.deployhq.com/blog/how-to-use-git-with-claude-code-understanding-the-co-authored-by-attribution)
  - The ASF treats such tags as a provenance record, not a legal claim of authorship. -- [ASF RAI, Authored-by tags](https://rai.apache.org/authored-by-tags.html)
  - The `Generated-By:` label is used "vanishingly low" at OpenInfra. -- [OpenInfra thread](https://lists.openinfra.org/archives/list/foundation@lists.openinfra.org/thread/A5IM6F6AKDTJ7IAR2KQR7DNGQ4NGF5O2)
- **SQLite's model.** "SQLite is not open-contribution". Every line traces to an author with a public-domain affidavit "in a firesafe", and outside patches may be rewritten from scratch. -- [SQLite copyright](https://sqlite.org/copyright.html)
  - Precedent for G2 plus provenance control: outside ideas, inside code.
- **LLVM on copyright.** Using AI to regenerate copyrighted material does not remove the copyright, and contributions that do so are removed. -- [LLVM AIToolPolicy](https://llvm.org/docs/AIToolPolicy.html)

### Inferences
- **What the MIT license covers.** Under the US position, agent-written code with little human creative input may be uncopyrightable, so the MIT grant covers only the human-authored parts: the charter, specs, test selection, possibly arrangement. For a permissive library this is mostly harmless, since users get at least MIT-level freedom either way. It may weaken the project's ability to enforce attribution. I have no legal source applying this to MIT specifically.
- **Regurgitation risk.** The bigger risk is agents reproducing third-party code, for example from ICU (Unicode License) or the Rust unicode-security crate (MIT/Apache). The ASF, LF and LLVM all put the burden on the contributor, which for Guild means the stewards. Possible mitigations: a similarity scan, or a rule that agents work from the specs, not other implementations' sources. The existing `LICENSES/Unicode-3.0.txt` covers data, not code.
- **G8 credit.** Release-note credit is what remains of the human contribution in a Guild project. Credit could be conditional on a validated report (G4 passed), given Larson's warning that public credit draws abusers.
- **Commit attribution.** Guild might adopt an `Assisted-by`/`Generated-by` trailer on agent commits plus a human `Signed-off-by` or approval by the merging steward. That combines kernel, Fedora and ASF practice.

### Gaps
- No source on how non-US jurisdictions treat agent-written code: for example, UK CDPA s9(3) on computer-generated works, or EU member states.
- No source analysing MIT-licensing of uncopyrightable code specifically.
- No court ruling yet on code, as opposed to images, created with AI.

## 5. How contributors react to issues-only projects and to bots that close issues

### Takeaway
Reaction to code-closed, issues-open projects in 2026 was mixed but mostly accepting:
- GitHub's PR-restriction thread: support outweighed "anti-OSS" objections.
- openai/codex's change: 56 thumbs-up, 15 thumbs-down.
- tldraw: mostly positive response.
- Ladybird: critics questioned whether it is still open source.

Research on stale bots and bot noise warns that automatic closing speeds up backlogs but costs contributors and goodwill. Guild's G7 and agent comments (G6) need careful design.

### Cited Findings
- **GitHub PR-access thread (#187038).**
  - Wayne-Jones called the setting "so anti-OSS"; the comment received 34 downvotes.
  - Others replied "This feature is just a tool" and noted that requests to disable PRs date back to 2016.
  - Several asked for the same control on issues, citing "AI slop burnout".

  Source: [Community discussion #187038](https://github.com/orgs/community/discussions/187038)
  - Supports G2's social acceptability.
- **openai/codex reception.** Reactions were 56 thumbs-up, 15 thumbs-down and 23 hearts. Critics found it ironic that an AI-tool vendor declines community code. One argued that "a PR can be the clearest description of a bug" and asked for fix PRs on reported bugs to be accepted. -- [openai/codex discussion #9956](https://github.com/openai/codex/discussions/9956)
  - Guild's G4 failing test partly answers this: it is a code-shaped bug description without being a PR.
- **tldraw and Ladybird.**
  - Ruiz reported that the response to closing outside PRs was mostly positive ("the problem is real"). -- [tldraw blog](https://tldraw.dev/blog/stay-away-from-my-trash)
  - For Ladybird, critics questioned whether a project that accepts no outside code is really open source and warned of a single point of failure in maintainer authority; defenders cited SQLite. -- [codenote (secondary)](https://codenote.net/en/posts/oss-external-pr-shutdown-2026/)
  - A caution for G1.
- **Ghostty Vouch spread.** About 150 repos reportedly carried VOUCHED files by June 2026. -- [rywalker (secondary, unverified)](https://rywalker.com/research/vouch)
  - A trust-ladder alternative to permanent G2.
- **Stale bots.** A study of 20 large projects found that adopting Stale bot led to more PRs closed, faster reviews and faster resolution of closed PRs. It also found a notable drop in active contributors after adoption. The authors warn that relying only on the bot may reduce engagement. -- [Khatoonabadi et al., arXiv 2305.18150 (2023-05-29)](https://web3.arxiv.org/abs/2305.18150?context=cs); [Mozilla Foundation summary](https://www.mozillafoundation.org/en/research/library/understanding-the-helpfulness-of-stale-bot-for-pull-based-development)
  - Partly contradicts G7: auto-closure has measurable community costs.
- **Bot noise.** 21 practitioners were interviewed; noise is "a recurrent and central problem". Perceptions depend on the number of bots, project norms and the person's prior experience, and maintainers reconfigured bots to "lower the frequency of actions". -- [Wessel et al., CSCW 2021, arXiv 2103.13950](https://arxiv.org/pdf/2103.13950)
  - A caution for G6: agent comments with decision-record links add volume; keep them sparse.
- **Agents in social spaces.** The matplotlib episode showed agents posting advocacy about the project's AI policy, and an agent attacking a maintainer who rejected it. Maintainers asked agents to stop commenting. LWN asked agent enthusiasts to confine agents to their own projects unless others consent. -- [LWN, 2026-02-17](https://lwn.net/SubscriberLink/1058643/f7ba3383d584a3ea)
  - Missing from Guild: a policy for outside agents (as opposed to Guild's own) in issues and comments.
- **Codex submission shift.** After the Codex change, contributors moved from sending diffs to sending analysis and proposals, sometimes with a reference implementation on a fork. -- [codenote (secondary)](https://codenote.net/en/posts/oss-external-pr-shutdown-2026/)
  - Supports G2 and G5: proposals argued against charter clauses.
- **EU AI Act Article 50.** Transparency duties apply from 2026-08-02. Providers must make synthetic text detectable. Deployers publishing AI text on matters of public interest must disclose it unless a human reviews it and takes editorial responsibility. Sources conflict on a grace period for the marking rule. -- [Cooley](https://www.cooley.com/news/insight/2026/2026-08-03-eu-ai-act-transparency-obligations-take-effect-2-august-2026); [artificialintelligenceact.eu](https://artificialintelligenceact.eu/transparency-rules-article-50/)
  - Whether this covers issue comments is unclear. G6's always-disclose rule removes the question anyway.

### Inferences
- **Mitigating G7.** The stale-bot evidence suggests three softeners:
  1. Say exactly what is missing: the failing test or the citation.
  2. Make reopening one comment away.
  3. Have a human-visible decision record.

  These address the "noise" and "contributor loss" findings. Closing only when information is missing, not on general inactivity, is narrower than Stale bot and probably less harmful.
- **G6 as a trust signal.** In 2026, failures of agent disclosure (Kai Gritun, the matplotlib agent) were a main source of distrust. A visible agent label plus a decision link is a positive differentiator, provided comments stay infrequent and steward-accountable.
- **Steward capacity.** Community acceptance of issues-only models seems to rest on maintainers visibly engaging with reports: Ladybird, Codex and tldraw all stress that reports still matter. A three-steward project that delegates all replies to agents risks looking like "bots that close issues". Guild may want a commitment that a human reads every closed issue, or a sample of them.

### Gaps
- No systematic study of contributor sentiment toward issues-only or no-PR projects; the evidence is reactions in individual threads.
- No study yet of LLM-based triage bots' effect on contributor retention, as opposed to the older Stale bot.
- No documented criticism of Dosu-style AI auto-replies was found, which leaves the negative side unrepresented.
