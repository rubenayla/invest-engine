"""Authentication for the dashboard server.

Why this exists rather than nginx `auth_basic`: the dashboard is deliberately
public to read — the point is that someone can be sent the link and just look at
it. But nginx's 401 carries a `WWW-Authenticate: Basic` header, and that header is
what makes a browser draw its own native sign-in dialog. Three of the page's
load-time fetches hit private endpoints, so **every anonymous visitor got a
credentials popup over a page they were supposed to read freely**. Moving the check
into the app lets a 401 be a plain 401, which JavaScript can handle quietly and
which no browser reacts to.

Cloudflare Access was evaluated for this and rejected (see history.md 2026-08-05):
its policies match on hostname and path but cannot distinguish HTTP methods, so it
cannot express "GET is public, POST needs auth", which is the whole requirement.

Configuration follows the same shape as `invest.data.db._resolve_db_url`: an
environment variable first, then a file in `$HOME`, and **raise if neither is set**.
Defaulting would mean silently serving with no protection at all, which is the one
outcome worse than crashing.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

# Paths that are private even for GET — someone else's alarms, notes and reminders
# are not public reading. Everything not listed here is readable by anyone; writes
# are handled separately, by method.
PRIVATE_PREFIXES = ('/api/alarms', '/api/notes', '/api/reminders')

# Without these exempt, nothing could ever authenticate.
AUTH_EXEMPT_PATHS = ('/api/login', '/api/logout')

SESSION_KEY = 'auth'
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 days

_PBKDF2_ROUNDS = 240_000


def _resolve_secret(env_var: str, filename: str, purpose: str) -> str:
    """Read a secret from the environment, else from a file in $HOME, else raise."""
    value = os.environ.get(env_var)
    if value:
        return value.strip()

    config_file = Path.home() / filename
    if config_file.exists():
        return config_file.read_text().strip()

    raise RuntimeError(
        f'No {purpose} configured. Set the {env_var} environment variable or write '
        f'it into {config_file}. Run `python scripts/set_dashboard_password.py` to '
        f'create both files. Refusing to start rather than serve unauthenticated.'
    )


def get_session_secret() -> str:
    """Signing key for the session cookie.

    Must be stable across restarts — generating one at boot would silently log
    everyone out on every deploy.
    """
    return _resolve_secret(
        'INVEST_DASHBOARD_SECRET', '.invest_dashboard_secret', 'session secret'
    )


def get_password_hash() -> str:
    """Stored password hash, in the `pbkdf2_sha256$rounds$salt$hash` format below."""
    return _resolve_secret(
        'INVEST_DASHBOARD_PASSWORD_HASH',
        '.invest_dashboard_password_hash',
        'dashboard password',
    )


def hash_password(password: str, *, salt: str | None = None,
                  rounds: int = _PBKDF2_ROUNDS) -> str:
    """PBKDF2-HMAC-SHA256, stdlib only.

    passlib/bcrypt would be a heavier dependency for a single-user login; the
    stdlib primitive is the same construction used by Django's default hasher.
    """
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), rounds)
    return f'pbkdf2_sha256${rounds}${salt}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a candidate password against a stored hash."""
    try:
        algorithm, rounds, salt, _ = stored.split('$', 3)
    except ValueError:
        return False
    if algorithm != 'pbkdf2_sha256':
        return False
    try:
        candidate = hash_password(password, salt=salt, rounds=int(rounds))
    except ValueError:
        return False
    # compare_digest, not ==, so a wrong password cannot be found byte by byte.
    return hmac.compare_digest(candidate, stored)


def requires_auth(method: str, path: str) -> bool:
    """Whether this request needs an authenticated session.

    Two rules, matching what nginx enforced before plus two agreed corrections:
      1. every write, on every path
      2. every method, including GET, on the private prefixes

    `/api/reminders` is in PRIVATE_PREFIXES deliberately. nginx left its GETs
    public while protecting `/api/alarms`, which was an oversight — reminders are
    equally personal.
    """
    if path in AUTH_EXEMPT_PATHS:
        return False
    if method not in ('GET', 'HEAD', 'OPTIONS'):
        return True
    return path.startswith(PRIVATE_PREFIXES)


def is_authenticated(request) -> bool:
    """True when the request carries a valid signed session cookie."""
    try:
        return bool(request.session.get(SESSION_KEY))
    except (AssertionError, AttributeError):
        # SessionMiddleware not installed — treat as anonymous rather than crash.
        return False
