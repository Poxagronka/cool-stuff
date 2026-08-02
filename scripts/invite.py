"""Mint an invite from the command line.

The site is invite-only and invites come from accounts, which leaves the first
account with no way in. This is that way in: run it on the machine that holds
the database and open the link it prints.

    flyctl ssh console -a tg-links-collector -C "python scripts/invite.py"

It can also list who is already inside:

    python scripts/invite.py --who
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tglinks import accounts, db  # noqa: E402
from tglinks.config import DB_PATH  # noqa: E402

DEFAULT_SITE = "https://tg-links-collector.fly.dev"


def main() -> int:
    parser = argparse.ArgumentParser(description="invite people to the portal")
    parser.add_argument("--site", default=DEFAULT_SITE, help="public origin of the portal")
    parser.add_argument("--who", action="store_true", help="list accounts instead")
    args = parser.parse_args()

    conn = db.connect(DB_PATH)
    accounts.setup(conn)

    if args.who:
        rows = conn.execute(
            "SELECT a.name, a.created_at, i.name AS host FROM account a"
            " LEFT JOIN account i ON i.id = a.invited_by ORDER BY a.created_at"
        ).fetchall()
        if not rows:
            print("nobody yet")
        for row in rows:
            host = f" (invited by {row['host']})" if row["host"] else ""
            print(f"{row['created_at'][:10]}  {row['name']}{host}")
        return 0

    code = accounts.mint(conn, None)
    print(f"{args.site.rstrip('/')}/join/{code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
