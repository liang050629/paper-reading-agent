from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.method_visual import compose_method_visual  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ir", type=Path, required=True)
    parser.add_argument("--method-graph", type=Path, required=True)
    parser.add_argument("--figure-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan, report = compose_method_visual(
        args.paper_ir,
        args.method_graph,
        args.figure_map,
        args.output,
    )
    print(plan)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
