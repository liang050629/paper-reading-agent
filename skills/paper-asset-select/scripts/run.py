from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.assets import select_assets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    outputs = select_assets(args.paper_ir, args.evidence, args.output)
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

