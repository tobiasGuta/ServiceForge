"""Run ServiceForge with `python -m serviceforge`."""

import sys

from serviceforge.app import ServiceForgeApplication


def main() -> int:
    application = ServiceForgeApplication()
    return application.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
