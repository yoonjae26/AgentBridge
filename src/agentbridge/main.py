"""Console entry point."""

from __future__ import annotations

import contextlib
import sys


def main() -> None:
    # Windows consoles may default to a legacy code page; make output UTF-8.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")
    from agentbridge.cli.app import app

    app()


if __name__ == "__main__":
    main()
