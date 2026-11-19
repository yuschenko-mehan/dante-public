"""Allows running DANTE as `python -m dante`."""

import sys

# Always UTF-8 output (Ukrainian text must not turn into garbage when saved to a file on Windows).
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from dante.cli import main  # noqa: E402

sys.exit(main())
