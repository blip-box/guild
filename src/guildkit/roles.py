"""The agent roles and the effort levels, named once, without the SDK.

`config` and `cli` import these; `agents` imports the SDK. Keeping them apart
lets the triage jobs install the shell without the agents extra.
"""

from __future__ import annotations

from typing import Literal

Role = Literal["planner", "builder", "reviewer", "grader"]
# The roles an adopter configures in guild.toml. The grader runs in the build
# drills only, as the second judge of a patch, and takes the Reviewer's
# settings unless guild.toml has a [grader] table of its own.
ROLES: tuple[Role, ...] = ("planner", "builder", "reviewer")
GRADER: Role = "grader"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
