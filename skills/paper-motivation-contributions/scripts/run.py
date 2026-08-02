from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.motivation_contributions import (  # noqa: E402
    build_motivation_contributions,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and audit Poster Motivation and Contributions."
    )
    parser.add_argument("--paper-ir", type=Path, required=True)
    parser.add_argument("--story", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--method-graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = build_motivation_contributions(
        args.paper_ir,
        args.story,
        args.evidence,
        args.method_graph,
        args.output,
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
