import argparse

from .db import get_database
from .system import Catalog


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m catalog")
    parser.add_argument("command", choices=["rebuild"])
    args = parser.parse_args()
    if args.command == "rebuild":
        print(Catalog(get_database()).index_manager.rebuild())


if __name__ == "__main__":
    main()
