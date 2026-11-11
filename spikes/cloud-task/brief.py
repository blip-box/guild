"""Render a build drill's brief as the text a scheduled task is fired with."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from guildkit import brief, drills

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    """Print the brief for the named build drill, plus the branch line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drill")
    parser.add_argument("--branch", required=True, help="the branch the task pushes")
    args = parser.parse_args()
    found = [
        d
        for d in drills.load(ROOT / "drills" / "confusable", "build")
        if d["name"] == args.drill
    ]
    if not found:
        print(f"no build drill named {args.drill}", file=sys.stderr)
        return 2
    text = brief.render(drills._drill_brief(found[0]))
    sys.stdout.write(text.rstrip("\n") + f"\n\nBranch: {args.branch}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
