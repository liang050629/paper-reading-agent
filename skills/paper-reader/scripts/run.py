from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.pipeline import run_pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("analysis", "poster"), default="analysis")
    parser.add_argument("--no-browser-export", action="store_true")
    args = parser.parse_args()
    summary = run_pipeline(
        args.input,
        args.output,
        parser="mineru",
        mode=args.mode,
        export_browser=not args.no_browser_export,
    )
    print(summary["status"])
    return 0 if summary["status"] in {"passed", "passed_with_warnings"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
