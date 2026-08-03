"""Make an account an admin, from the machine that holds the database.

An admin is the only one who can take a card off the site, so the flag cannot
be something the site itself hands out, and it cannot be a name compared
against inside a request handler either — whoever joins under that name would
inherit it. It is a column on `account`, and this is the only thing that writes
it:

    flyctl ssh console -a cool-stuff -C "python scripts/admin.py poxagronka"

To take it back, or to see who has it:

    python scripts/admin.py --revoke poxagronka
    python scripts/admin.py --who
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tglinks import accounts, db  # noqa: E402
from tglinks.config import DB_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="grant admin to an account")
    parser.add_argument("name", nargs="?", default="", help="the login name")
    parser.add_argument("--revoke", action="store_true", help="take it back instead")
    parser.add_argument("--who", action="store_true", help="list the admins instead")
    args = parser.parse_args()

    conn = db.connect(DB_PATH)
    accounts.setup(conn)

    if args.who:
        rows = conn.execute(
            "SELECT name FROM account WHERE admin = 1 ORDER BY name"
        ).fetchall()
        print("\n".join(r["name"] for r in rows) or "no admins")
        return 0

    if not args.name:
        parser.error("give a name, or --who")
    if not accounts.set_admin(conn, args.name, not args.revoke):
        print(f"no account called {args.name!r}")
        return 1
    print(f"{args.name} is {'no longer an admin' if args.revoke else 'an admin now'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
