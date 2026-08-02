from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.render import render_poster  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--paper-ir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-browser-export", action="store_true")
    args = parser.parse_args()
    html_path, report = render_poster(
        args.spec,
        args.paper_ir,
        args.output,
        export_browser=not args.no_browser_export,
    )
    print(html_path)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

