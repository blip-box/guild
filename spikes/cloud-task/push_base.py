"""Push a build drill's stripped, seeded checkout as branch `base` of a remote.

The clone has nothing after the base commit reachable, as the drills do it,
so the scratch repository never holds the fix.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from guildkit import drills

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    """Prepare the checkout and force-push it as `base`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="a confusable clone")
    parser.add_argument("--drill", required=True)
    parser.add_argument("--remote", required=True, help="the scratch repository")
    args = parser.parse_args()
    found = [
        d
        for d in drills.load(ROOT / "drills" / "confusable", "build")
        if d["name"] == args.drill
    ]
    if not found:
        print(f"no build drill named {args.drill}", file=sys.stderr)
        return 2
    drill = found[0]
    inp = drill["input"]
    seed = Path(drill["directory"]) / inp["seed"] if "seed" in inp else None
    with tempfile.TemporaryDirectory(prefix="spike-base-") as tmp:
        work = Path(tmp) / "work"
        head = drills.prepare_checkout(
            args.source.resolve(), inp["base"], work, seed=seed
        )
        subprocess.run(
            ["git", "push", "--force", args.remote, "HEAD:refs/heads/base"],
            cwd=work,
            check=True,
        )
    print(f"pushed {head} as base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
