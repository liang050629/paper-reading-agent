from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.ingest import ingest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paper_ir, report = ingest(args.input, args.output, "mineru")
    print(paper_ir)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
