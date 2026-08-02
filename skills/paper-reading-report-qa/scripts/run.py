from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.common import read_json  # noqa: E402
from paperposter.reading_report import validate_reading_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a paper reading report.")
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    report_dir = args.run_dir.resolve() / "06-reading-report"
    qa_path = validate_reading_report(
        report_dir / "reading_report_spec.json",
        report_dir / "reading_report_render_bundle.json",
        report_dir,
    )
    qa = read_json(qa_path)
    print(qa_path)
    print(qa["status"])
    return 0 if qa["status"] in {"passed", "passed_with_warnings"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
