from __future__ import annotations

import argparse
import json

from apps.api.app.db import Database, seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic Service Desk demo data")
    parser.add_argument("--reset", action="store_true", help="replace the local SQLite database")
    args = parser.parse_args()
    print(json.dumps(seed_database(Database(), reset=args.reset), indent=2))


if __name__ == "__main__":
    main()
