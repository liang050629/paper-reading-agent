from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.compose import compose_poster  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ir", type=Path, required=True)
    parser.add_argument("--story", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--method-graph", type=Path, required=True)
    parser.add_argument("--method-visual", type=Path, required=True)
    parser.add_argument("--key-idea", type=Path, required=True)
    parser.add_argument("--experimental-results", type=Path, required=True)
    parser.add_argument("--highlights", type=Path, required=True)
    parser.add_argument("--motivation", type=Path, required=True)
    parser.add_argument("--contributions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compact-level", type=int, default=0)
    args = parser.parse_args()
    spec, report = compose_poster(
        args.paper_ir,
        args.story,
        args.evidence,
        args.assets,
        args.method_graph,
        args.method_visual,
        args.key_idea,
        args.experimental_results,
        args.highlights,
        args.motivation,
        args.contributions,
        args.output,
        args.compact_level,
    )
    print(spec)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
