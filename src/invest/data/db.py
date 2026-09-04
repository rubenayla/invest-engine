"""
Central database connection factory.

All database access goes through this module. The connection string is read from
the DB_URL environment variable, falling back to the ~/.invest_db_url file. There
is no built-in default: a missing configuration raises rather than silently
attempting a guessed host, user and password.

Set one of the two, using your own credentials:

    export DB_URL=postgresql://USER:PASSWORD@localhost:5432/invest   # direct
    export DB_URL=postgresql://USER:PASSWORD@localhost:5433/invest   # via SSH tunnel

or write the same URL into a mode-600 ~/.invest_db_url, which keeps it out of the
repository and process environment. See README.md for creating the database and
loading scripts/create_postgres_schema.sql.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import psycopg2
import psycopg2.extras


def _resolve_db_url() -> str:
    """Resolve the database URL from the environment or the config file."""
    url = os.environ.get('DB_URL')
    if url:
        return url

    config_file = Path.home() / '.invest_db_url'
    if config_file.exists():
        return config_file.read_text().strip()

    raise RuntimeError(
        'No database configuration found. Set the DB_URL environment variable or '
        f'write a connection URL into {config_file}, for example '
        'postgresql://USER:PASSWORD@localhost:5432/invest . '
        'See the Database Setup section of README.md to create the database first.'
    )


@lru_cache(maxsize=1)
def get_db_url() -> str:
    """Get the database URL (cached)."""
    return _resolve_db_url()


def get_connection(dict_cursor: bool = False):
    """
    Get a new psycopg2 connection.

    Parameters
    ----------
    dict_cursor : bool
        If True, use RealDictCursor so rows behave like dicts.

    Returns
    -------
    psycopg2.extensions.connection
    """
    kwargs = {}
    if dict_cursor:
        kwargs['cursor_factory'] = psycopg2.extras.RealDictCursor
    return psycopg2.connect(get_db_url(), **kwargs)


def get_engine():
    """Get a SQLAlchemy engine for pandas read_sql / to_sql."""
    from sqlalchemy import create_engine
    return create_engine(get_db_url())
