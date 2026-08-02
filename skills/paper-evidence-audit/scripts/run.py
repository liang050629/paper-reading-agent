from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.evidence import audit_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-ir", type=Path, required=True)
    parser.add_argument("--story", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    matrix, report = audit_evidence(args.paper_ir, args.story, args.output)
    print(matrix)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

