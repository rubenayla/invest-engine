"""The dashboard and its analysis pages are public.

Personal source notes remain in the vault; this server does not add a second
account or password layer around the rendered analysis pages.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from starlette.testclient import TestClient  # noqa: E402

import dashboard_server  # noqa: E402


@pytest.fixture(scope='module')
def client():
    return TestClient(dashboard_server.app, base_url='https://testserver',
                      raise_server_exceptions=False)


class TestPublicDashboard:
    @pytest.mark.parametrize('path', [
        '/', '/m', '/feed', '/api/stocks', '/api/health',
        '/api/notes/CRON', '/api/alarms', '/api/reminders',
    ])
    def test_reads_have_no_auth_boundary(self, client, path):
        assert client.get(path).status_code != 401

    def test_login_route_is_removed(self, client):
        assert client.post('/api/login', json={'password': 'anything'}).status_code == 404

    def test_notes_follow_browser_color_scheme(self, client, monkeypatch, tmp_path):
        (tmp_path / 'CRON.md').write_text('# Cronos Group', encoding='utf-8')
        monkeypatch.setattr(dashboard_server, 'NOTES_DIR', tmp_path)

        response = client.get('/api/notes/CRON')

        assert response.status_code == 200
        assert "color-scheme: light dark" in response.text
        assert "@media (prefers-color-scheme: dark)" in response.text
        assert "--background:#fff" in response.text
        assert "--background:#0d1117" in response.text
