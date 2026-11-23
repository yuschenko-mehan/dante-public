"""DANTE — Dynamic Autonomous Neural Tool for Engineering.

AI code builder: many free models + local model + external agents, plan → code → test → fix → commit.
"""

NAME = "DANTE"
FULL_NAME = "Dynamic Autonomous Neural Tool for Engineering"
__version__ = "0.4.2"
__build__ = "2026.11.23.2"  # date of the build + number of the build that day


def version_line() -> str:
    return f"{NAME} — {FULL_NAME} · v{__version__} (build {__build__})"
