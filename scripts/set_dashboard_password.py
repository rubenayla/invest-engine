#!/usr/bin/env python3
"""Set the dashboard login password and session secret.

Writes two files in $HOME with mode 600:
  ~/.invest_dashboard_password_hash   PBKDF2 hash of the password you type
  ~/.invest_dashboard_secret          random key for signing session cookies

Neither the password nor the secret ever goes in git — the repo was made private
on 2026-07-30 after a Telegram token was committed and abused (AGENTS.md), and
this follows the same $HOME-file convention as ~/.invest_db_url.

Usage:
    uv run python scripts/set_dashboard_password.py
    uv run python scripts/set_dashboard_password.py --show-hash   # print, don't write

The session secret is only regenerated if it does not already exist — rotating it
logs you out of every browser, so it is not something to do by accident.
"""

import argparse
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from invest.dashboard_auth import hash_password  # noqa: E402

PASSWORD_FILE = Path.home() / '.invest_dashboard_password_hash'
SECRET_FILE = Path.home() / '.invest_dashboard_secret'


def write_private(path: Path, content: str) -> None:
    """Write mode-600 so the secret is not world-readable on a shared box."""
    path.write_text(content + '\n')
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--show-hash', action='store_true',
                        help='Print the hash instead of writing it, e.g. to paste into a systemd unit')
    args = parser.parse_args()

    password = getpass.getpass('Dashboard password: ')
    if not password:
        print('Empty password, aborting.', file=sys.stderr)
        return 1
    if password != getpass.getpass('Confirm: '):
        print('Passwords do not match.', file=sys.stderr)
        return 1

    hashed = hash_password(password)

    if args.show_hash:
        print(hashed)
        return 0

    write_private(PASSWORD_FILE, hashed)
    print(f'password hash -> {PASSWORD_FILE}')

    if SECRET_FILE.exists():
        print(f'session secret -> {SECRET_FILE} (kept; rotating it signs you out everywhere)')
    else:
        write_private(SECRET_FILE, secrets.token_urlsafe(48))
        print(f'session secret -> {SECRET_FILE} (generated)')

    print('\nRestart the dashboard for this to take effect:')
    print('  systemctl --user restart invest-dashboard')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
