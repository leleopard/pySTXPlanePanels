"""Tier 2 — golden-image render regression.

Rasterises each case in `tests/cases.yaml` offscreen at fixed dataref
values and compares it pixel-by-pixel against a committed baseline under
`tests/goldens/`. This is the tier that answers "does the needle still
point where it used to", which no amount of config validation can.

It needs a GPU and takes seconds rather than milliseconds, so it is
deselected by default (see `addopts` in pyproject.toml). Run it with:

    python -m pytest -m render

To accept an intended visual change, regenerate the baselines and then
*look at them* before committing:

    python -m pytest -m render --update-goldens

When a case fails, the rendered frame and an amplified difference map are
written to `tests/_artifacts/` so the change can be seen rather than
inferred from a pixel count.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from PIL import Image

from gauge_core.offscreen import render_yaml

from tests.discovery import PROJECT_ROOT

pytestmark = pytest.mark.render

CASES_FILE = Path(__file__).parent / "cases.yaml"
GOLDENS_DIR = Path(__file__).parent / "goldens"
ARTIFACTS_DIR = Path(__file__).parent / "_artifacts"


def _load_cases() -> list[dict[str, Any]]:
    with open(CASES_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    defaults = data.get("defaults", {}) or {}
    cases = []
    for case in data.get("cases", []) or []:
        merged = {**defaults, **case}
        merged["values"] = case.get("values") or {}
        cases.append(merged)
    return cases


CASES = _load_cases()
CASE_IDS = [c["name"] for c in CASES]


def _write_artifact(name: str, image: Image.Image) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / name
    image.save(path)
    return path


def _difference_map(actual: np.ndarray, golden: np.ndarray) -> Image.Image:
    """Amplified per-pixel difference, for eyeballing what actually moved.

    Differences in gauge rendering are often a few pixels of needle edge,
    which is invisible in a raw subtraction — so the delta is scaled up
    until it is obvious, and rendered as greyscale over black.
    """
    delta = np.abs(actual.astype(np.int16) - golden.astype(np.int16))
    intensity = delta[:, :, :3].max(axis=2)
    amplified = np.clip(intensity.astype(np.int16) * 8, 0, 255).astype(np.uint8)
    return Image.fromarray(amplified, mode="L")


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_render_matches_golden(case: dict[str, Any], update_goldens: bool, gl_context) -> None:
    name = case["name"]
    yaml_path = PROJECT_ROOT / case["yaml"]
    assert yaml_path.exists(), f"case {name!r} points at a missing file: {case['yaml']}"

    image = render_yaml(
        yaml_path,
        values=case["values"],
        supersample=int(case.get("supersample", 1)),
        # One discarded frame: the first frame after construction can differ
        # by a level or two on antialiased edges while arcade lazily packs
        # its texture atlas. Cheap, and removes the variance entirely.
        warmup=1,
    )

    golden_path = GOLDENS_DIR / f"{name}.png"

    if update_goldens:
        GOLDENS_DIR.mkdir(parents=True, exist_ok=True)
        image.save(golden_path)
        pytest.skip(f"golden written: {golden_path.relative_to(PROJECT_ROOT)}")

    if not golden_path.exists():
        actual_path = _write_artifact(f"{name}.actual.png", image)
        pytest.fail(
            f"no golden image for case {name!r}.\n"
            f"Rendered output saved to: {actual_path.relative_to(PROJECT_ROOT)}\n"
            f"If it looks right, create the baseline with:\n"
            f"    python -m pytest -m render --update-goldens"
        )

    golden = Image.open(golden_path).convert("RGBA")
    if golden.size != image.size:
        pytest.fail(
            f"{name}: rendered size {image.size} != golden size {golden.size}. "
            f"The panel's declared size changed; regenerate the golden if intended."
        )

    actual_array = np.array(image)
    golden_array = np.array(golden)

    tolerance = int(case.get("channel_tolerance", 0))
    budget = int(case.get("max_differing_pixels", 0))

    delta = np.abs(actual_array.astype(np.int16) - golden_array.astype(np.int16))
    beyond_tolerance = (delta > tolerance).any(axis=2)
    differing = int(beyond_tolerance.sum())

    if differing > budget:
        actual_path = _write_artifact(f"{name}.actual.png", image)
        diff_path = _write_artifact(
            f"{name}.diff.png", _difference_map(actual_array, golden_array)
        )
        total = beyond_tolerance.size
        pytest.fail(
            f"{name}: {differing} of {total} pixels ({100 * differing / total:.2f}%) "
            f"differ from the golden by more than {tolerance}/255 "
            f"(budget {budget}); largest channel delta {int(delta.max())}.\n"
            f"  rendered:   {actual_path.relative_to(PROJECT_ROOT)}\n"
            f"  difference: {diff_path.relative_to(PROJECT_ROOT)}\n"
            f"  golden:     {golden_path.relative_to(PROJECT_ROOT)}\n"
            f"If the change is intended: python -m pytest -m render --update-goldens"
        )


def test_cases_file_is_consistent() -> None:
    """Case names are unique and every case names a file that exists."""
    names = [c["name"] for c in CASES]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, f"duplicate case names in cases.yaml: {duplicates}"

    missing = [c["yaml"] for c in CASES if not (PROJECT_ROOT / c["yaml"]).exists()]
    assert not missing, f"cases.yaml references missing files: {missing}"
