"""Tests for the canonical database URL resolution path."""

from pathlib import Path

import pytest

from invest.data import db


def test_environment_url_takes_precedence(monkeypatch, tmp_path: Path):
    config_file = tmp_path / ".invest_db_url"
    config_file.write_text("postgresql://file@example/invest")
    monkeypatch.setattr(db.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("DB_URL", "postgresql://environment@example/invest")

    assert db._resolve_db_url() == "postgresql://environment@example/invest"


def test_file_url_is_used_when_environment_is_unset(monkeypatch, tmp_path: Path):
    config_file = tmp_path / ".invest_db_url"
    config_file.write_text("postgresql://file@example/invest\n")
    monkeypatch.setattr(db.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("DB_URL", raising=False)

    assert db._resolve_db_url() == "postgresql://file@example/invest"


def test_missing_url_explains_both_configuration_options(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(db.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("DB_URL", raising=False)

    with pytest.raises(RuntimeError, match="DB_URL.*invest_db_url"):
        db._resolve_db_url()
