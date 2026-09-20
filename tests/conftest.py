"""Pytest configuration for the gauge regression suite.

Tiers are expressed as markers:

    smoke   — pure-Python, no GL context. Parses and builds every config.
              Fast enough (~2s) to run on every change.
    render  — opens a hidden OpenGL context and rasterises frames, then
              compares them against committed golden PNGs. Slower and
              GPU-dependent, so it is deselected by default (see the
              `addopts` in pyproject.toml) and opted into with `-m render`.

`scripts/regress.py` picks the tier automatically from what changed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The suite imports gauge_core directly from the working tree so it tests
# the code you are editing, not whatever happens to be pip-installed.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help=(
            "Rewrite the render tier's golden PNGs from the current code "
            "instead of comparing against them. Review the resulting image "
            "diff before committing — this is how an intended visual change "
            "is accepted, and it is also how an unintended one gets baked in."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "smoke: fast, no-GL config validation — runs on every change"
    )
    config.addinivalue_line(
        "markers", "render: opens a GL context and compares rendered frames to goldens"
    )


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def update_goldens(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--update-goldens"))


@pytest.fixture(scope="session")
def gl_context():
    """Session-scoped hidden GL context for the render tier.

    Created once for the whole session and torn down at the end, so a run
    of forty render cases pays for one context rather than forty.
    """
    from gauge_core import offscreen

    yield
    offscreen.close_host_window()
