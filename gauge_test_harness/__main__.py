"""Entry point: python -m gauge_test_harness <panel_or_instrument.yaml> [--port N]"""

import argparse
import sys

from PySide6.QtWidgets import QApplication

from gauge_core.mock_source import DEFAULT_MOCK_PORT
from gauge_test_harness.harness import TestHarnessWindow


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Test harness — drives gauge datarefs via a per-dataref spinbox form."
    )
    p.add_argument("yaml_path", help="Panel or instrument YAML to introspect")
    p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_MOCK_PORT,
        help=f"Port the running panel uses for --mock (default {DEFAULT_MOCK_PORT})",
    )
    args = p.parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv)
    win = TestHarnessWindow(args.yaml_path, port=args.port)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
