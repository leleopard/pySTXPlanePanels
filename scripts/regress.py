"""Change-impact test selector.

Runs the tier that what-you-changed actually warrants, instead of making
you choose between "run everything every time" (slow, so it gets skipped)
and "run nothing" (fast, so it catches nothing).

    python scripts/regress.py              # vs the working tree
    python scripts/regress.py --base HEAD~3
    python scripts/regress.py --dry-run    # print the plan, run nothing
    python scripts/regress.py --all        # force the full suite

How a changed path picks a tier:

  docs, scripts, editor config       nothing — these cannot break a gauge
  gauge_designer/, gauge_test_harness/  smoke only: the designer cannot
                                     change how the runtime renders, but
                                     it can break a shared import
  gauge_core/                        smoke + the FULL render tier: almost
                                     anything here can move a pixel
  instruments/, panels/, assets/     smoke + only the render cases that
                                     depend on that file, via tests/depgraph

The bias throughout is toward running too much rather than too little: a
change that cannot be attributed to specific cases escalates to the full
render tier. A selector that silently skips the one case that mattered is
worse than one that occasionally spends an extra ten seconds.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.depgraph import build_graph, cases_affected_by  # noqa: E402
from tests.discovery import rel  # noqa: E402

# Paths that cannot affect behaviour under test.
_IGNORED_SUFFIXES = {".md", ".bat", ".sh", ".txt", ".xcf", ".sfd", ".svg", ".dxf"}
_IGNORED_NAMES = {".gitignore", ".gitattributes", "LICENSE"}
_IGNORED_PREFIXES = (".claude/", ".vscode/", ".idea/", ".githooks/", ".github/")

# gauge_core modules that provably cannot move a pixel.
_NON_RENDERING_CORE = {"mock_source.py", "aa_probe.py"}

# Directories whose contents are covered by the dependency graph.
_GRAPH_SCOPED_PREFIXES = ("instruments/", "panels/", "assets/", "tests/goldens/")

# Changing these changes how every case renders or is selected.
_FULL_RENDER_PATHS = {
    "config.yaml",
    "pyproject.toml",
    "tests/cases.yaml",
    "tests/conftest.py",
    "tests/depgraph.py",
    "tests/discovery.py",
    "tests/test_render.py",
}


class Plan:
    """What the selector decided, and why."""

    def __init__(self) -> None:
        self.run_smoke = False
        self.full_render = False
        self.render_cases: set[str] = set()
        self.reasons: list[tuple[str, str]] = []

    def note(self, path: str, reason: str) -> None:
        self.reasons.append((path, reason))

    @property
    def run_render(self) -> bool:
        return self.full_render or bool(self.render_cases)


def _git(args: list[str]) -> list[str]:
    """Run a git command with NUL-separated output and return the fields."""
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [field for field in result.stdout.split("\0") if field]


def changed_paths(base: str | None, staged: bool = False) -> list[str]:
    """Project-relative paths that changed, as forward-slash strings.

    With `--base`, everything that differs from that ref. With `staged`,
    only what is in the index — what a commit would actually contain.
    Otherwise the whole uncommitted working tree: staged, unstaged and
    untracked.
    """
    if staged:
        return sorted(set(_git(["diff", "--cached", "--name-only", "-z"])))

    if base:
        return sorted(set(_git(["diff", "--name-only", "-z", base])))

    paths: set[str] = set()
    # porcelain -z emits "XY path" per record; renames add a second path
    # record which is picked up on the next iteration as a bare path.
    for field in _git(["status", "--porcelain", "-z", "--untracked-files=all"]):
        paths.add(field[3:] if len(field) > 3 and field[2] == " " else field)
    return sorted(p for p in paths if p)


def classify(paths: list[str], graph: dict[str, set[Path]]) -> Plan:
    plan = Plan()

    for path in paths:
        normalized = path.replace("\\", "/")
        name = Path(normalized).name

        if (
            Path(normalized).suffix.lower() in _IGNORED_SUFFIXES
            or name in _IGNORED_NAMES
            or normalized.startswith(_IGNORED_PREFIXES)
        ):
            plan.note(normalized, "no tests")
            continue

        if normalized in _FULL_RENDER_PATHS:
            plan.run_smoke = True
            plan.full_render = True
            plan.note(normalized, "smoke + full render tier")
            continue

        if normalized.startswith("gauge_core/"):
            plan.run_smoke = True
            if name in _NON_RENDERING_CORE:
                plan.note(normalized, "smoke (non-rendering core module)")
            else:
                plan.full_render = True
                plan.note(normalized, "smoke + full render tier")
            continue

        if normalized.startswith(("gauge_designer/", "gauge_test_harness/")):
            plan.run_smoke = True
            plan.note(normalized, "smoke (cannot change runtime rendering)")
            continue

        if normalized.startswith("tests/") or normalized.startswith("scripts/"):
            plan.run_smoke = True
            plan.note(normalized, "smoke")
            continue

        if normalized.startswith(_GRAPH_SCOPED_PREFIXES):
            plan.run_smoke = True
            affected = cases_affected_by([normalized], graph)
            if affected:
                plan.render_cases |= affected
                plan.note(normalized, f"smoke + render: {', '.join(sorted(affected))}")
            else:
                # Not reachable from any case — e.g. an asset referenced
                # only by family name, or an instrument no golden covers.
                # Escalate rather than assume it is harmless.
                plan.full_render = True
                plan.note(normalized, "smoke + full render tier (no case owns it)")
            continue

        plan.run_smoke = True
        plan.full_render = True
        plan.note(normalized, "smoke + full render tier (unclassified)")

    return plan


def _print_plan(plan: Plan, paths: list[str], total_cases: int) -> None:
    if not paths:
        print("No changes detected.")
        return

    print(f"Changed files ({len(paths)}):")
    width = min(max((len(p) for p, _ in plan.reasons), default=0), 64)
    for path, reason in plan.reasons:
        # ASCII only: the Windows console's default cp1252 codepage cannot
        # encode arrows and raises rather than degrading.
        print(f"  {path:<{width}}  ->  {reason}")

    print()
    if plan.full_render:
        print(f"Plan: smoke + render (all {total_cases} cases)")
    elif plan.render_cases:
        print(
            f"Plan: smoke + render ({len(plan.render_cases)} of {total_cases} cases: "
            f"{', '.join(sorted(plan.render_cases))})"
        )
    elif plan.run_smoke:
        print("Plan: smoke only")
    else:
        print("Plan: nothing to run")


def _run(args: list[str], cwd: Path | None = None) -> int:
    print(f"\n$ {' '.join(args)}")
    # The child writes straight to the terminal while our own prints are
    # buffered when stdout is a pipe, so without this the plan and the
    # pytest output come out in the wrong order.
    sys.stdout.flush()
    return subprocess.run(args, cwd=cwd or PROJECT_ROOT).returncode


@contextmanager
def staged_snapshot() -> Iterator[Path]:
    """Materialise the index into a temp directory and yield its path.

    A pre-commit check should test the commit, not the working tree — and
    in this project the working tree is essentially always dirty with
    unrelated work in progress. Testing it would both pass on things the
    commit does not contain and fail on things it does not either.

    `git checkout-index` writes the staged content out without touching
    the working tree or the index, so unlike a stash-based approach there
    is nothing to restore and nothing to lose if the run is interrupted.
    Measured at ~0.3s for this repo, against a ~4s smoke tier.

    A useful side effect: the snapshot contains only tracked files, so a
    commit that references a file which was never `git add`ed fails here
    rather than on somebody else's clone.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="gauge-regress-"))
    try:
        # checkout-index wants a trailing separator on the prefix.
        subprocess.run(
            ["git", "checkout-index", "-a", "--prefix", f"{temp_dir}{os.sep}"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        yield temp_dir
    finally:
        # Copy any failure artifacts back where the user can actually look
        # at them before the snapshot is deleted.
        produced = temp_dir / "tests" / "_artifacts"
        if produced.is_dir():
            destination = PROJECT_ROOT / "tests" / "_artifacts"
            destination.mkdir(parents=True, exist_ok=True)
            for artifact in produced.iterdir():
                if artifact.is_file():
                    shutil.copy2(artifact, destination / artifact.name)
            print(
                f"\nFailure artifacts copied to "
                f"{destination.relative_to(PROJECT_ROOT).as_posix()}/"
            )
        shutil.rmtree(temp_dir, ignore_errors=True)


def _run_tiers(plan: Plan, cwd: Path | None = None) -> int:
    """Run the tiers the plan calls for, in *cwd* (default: the repo)."""
    # Keep the first failing tier's own exit code rather than combining
    # them — pytest's codes are meaningful (1 = failures, 2 = interrupted,
    # 5 = nothing collected) and OR-ing them together invents new ones.
    exit_code = 0

    if plan.run_smoke:
        exit_code = (
            _run([sys.executable, "-m", "pytest", "-m", "smoke", "-q"], cwd=cwd)
            or exit_code
        )

    if plan.run_render:
        render_args = [sys.executable, "-m", "pytest", "-m", "render", "-q"]
        if not plan.full_render:
            render_args += ["-k", " or ".join(sorted(plan.render_cases))]
        exit_code = _run(render_args, cwd=cwd) or exit_code

    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Compare against this git ref instead of the working tree.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without running anything.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ignore what changed and run the whole suite.",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help=(
            "Pre-commit mode: pick the tier from the staged changes, and "
            "run the tests against a snapshot of the index rather than the "
            "working tree — so the commit is what gets tested, not whatever "
            "else happens to be uncommitted. Used by the pre-commit hook."
        ),
    )
    args = parser.parse_args(argv)

    from tests.test_render import CASES

    graph = build_graph(CASES)

    if args.all:
        plan = Plan()
        plan.run_smoke = True
        plan.full_render = True
        paths = ["(--all)"]
        plan.note("(--all)", "smoke + full render tier")
    else:
        paths = changed_paths(args.base, staged=args.staged)
        plan = classify(paths, graph)

    _print_plan(plan, paths, len(CASES))

    if args.dry_run:
        return 0

    if args.staged and (plan.run_smoke or plan.run_render):
        with staged_snapshot() as snapshot:
            return _run_tiers(plan, cwd=snapshot)

    if not plan.run_smoke and not plan.run_render:
        print("\nNothing to run.")
        return 0

    return _run_tiers(plan)


if __name__ == "__main__":
    sys.exit(main())
