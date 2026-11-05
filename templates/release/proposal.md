Guild proposes releasing {version} from {head}, the last release being {previous}.

Why now: {reason}.

## Changes since {previous}

{changelog}
{credits}
## Before it ships

A release is a tier 3 change: a steward approves it and a steward runs it. While there is one steward, this issue is the public notice, and the release may run from {earliest} onwards with the Reviewer's no-objection.

- The test suite at {head}: {tests}.
- Bump the version to {version} in {version_files}; merge that as tier 2.
- Tag the merge commit `v{version}` and let the release workflow publish.
- Close this issue with the tag; Guild proposes the next release from there.

---
This proposal is from Guild, the stewards' automation. Its text comes from a template, the change list from the merged pull request titles and the credits from the ledger; no model wrote any of it. Decision record: {run_url}
