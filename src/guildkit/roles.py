"""The agent roles and the effort levels, named once, without the SDK.

`config` and `cli` import these; `agents` imports the SDK. Keeping them apart
lets the triage jobs install the shell without the agents extra.
"""

from __future__ import annotations

from typing import Literal

Role = Literal["planner", "builder", "reviewer"]
ROLES: tuple[Role, ...] = ("planner", "builder", "reviewer")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
