import sys


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def main() -> None:
    from .cli import main as cli_main

    raise SystemExit(cli_main())


if __name__ == "__main__":
    main()
