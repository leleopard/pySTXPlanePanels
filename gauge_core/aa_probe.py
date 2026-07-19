"""Standalone probe: does this machine's GPU driver actually honor a
requested native-MSAA sample count, or silently drop it (the NVIDIA/Windows
per-application-driver-profile issue gauge_core.runner works around)?

Run as its own process (python -m gauge_core.aa_probe) rather than
in-process from the designer, since creating a real GL/pyglet window
inside a running Qt event loop is untested territory this project doesn't
otherwise rely on. Prints the actual GL_SAMPLES value to stdout and exits.
"""

from __future__ import annotations

import argparse
import ctypes
import sys


def probe(samples: int) -> int:
    import arcade
    from pyglet.gl import GL_SAMPLES, glGetIntegerv

    win = arcade.Window(200, 150, "aa probe", antialiasing=True, samples=samples, visible=False)
    try:
        actual = ctypes.c_int(0)
        glGetIntegerv(GL_SAMPLES, actual)
        return actual.value
    finally:
        win.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Probe whether this machine's GPU driver honors hardware MSAA at --samples.",
    )
    p.add_argument("--samples", type=int, default=4, choices=[2, 4, 8])
    args = p.parse_args(argv)
    print(probe(args.samples))
    return 0


if __name__ == "__main__":
    sys.exit(main())
