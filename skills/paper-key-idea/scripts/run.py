from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.key_idea import build_key_idea  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ir", type=Path, required=True)
    parser.add_argument("--story", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--method-graph", type=Path, required=True)
    parser.add_argument("--method-figure-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec, report = build_key_idea(
        args.paper_ir,
        args.story,
        args.evidence,
        args.method_graph,
        args.method_figure_map,
        args.output,
    )
    print(spec)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
