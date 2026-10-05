"""建立员工账号。第一个 ADMIN 一定要用这个建；之后 ADMIN 可以在 Admin Platform 建其他账号。

用法（在 backend/ 里）：
    python -m app.db.create_staff amy "Amy Tan" --admin
    python -m app.db.create_staff ben "Ben Lim"
密码会问两次，打字时屏幕上不会显示。
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from ..auth import MIN_PASSWORD_LENGTH, hash_password
from .models import Staff, StaffRole
from .session import new_session


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.db.create_staff", description="Create a staff account")
    parser.add_argument("username")
    parser.add_argument("name")
    parser.add_argument("--admin", action="store_true", help="can change settings and staff accounts")
    args = parser.parse_args(argv)
    username = args.username.strip().lower()

    with new_session() as session:
        if session.scalars(select(Staff).where(Staff.username == username)).first() is not None:
            print(f"Username {username!r} already exists.")
            return 1
        password = getpass.getpass(f"Password (at least {MIN_PASSWORD_LENGTH} characters): ")
        if password != getpass.getpass("Password again: "):
            print("The two passwords are different.")
            return 1
        try:
            password_hash = hash_password(password)
        except ValueError as e:
            print(e)
            return 1
        role = StaffRole.ADMIN if args.admin else StaffRole.STAFF
        session.add(Staff(username=username, name=args.name.strip(), role=role, password_hash=password_hash))
        session.commit()
    print(f"Created {role} account {username!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
