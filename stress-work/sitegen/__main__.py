"""Allow ``python3 -m sitegen ...``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
