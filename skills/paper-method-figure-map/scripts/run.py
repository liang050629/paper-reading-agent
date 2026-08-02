from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.method_figures import map_method_figures  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ir", type=Path, required=True)
    parser.add_argument("--method-graph", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    figure_map, report = map_method_figures(
        args.paper_ir,
        args.method_graph,
        args.catalog,
        args.output,
    )
    print(figure_map)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
