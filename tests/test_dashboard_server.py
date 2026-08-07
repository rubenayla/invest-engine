"""Auth rules for the dashboard server.

The dashboard is public to read on purpose — the link gets sent to people. What
must not be public is writing, or reading the owner's alarms, notes and reminders.

The specific bug these tests pin: nginx used to enforce that with `auth_basic`,
whose 401 carries a `WWW-Authenticate: Basic` header. Three of the page's
load-time fetches hit private endpoints, so **every anonymous visitor got a
browser credentials popup over a page they were meant to just read**. The fix
moved the check into the app so a 401 is a plain 401. `test_401_has_no_www_authenticate_header`
is the test that would catch a regression back to that behaviour — everything else
here could pass while the popup returned.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from invest.dashboard_auth import hash_password, requires_auth, verify_password  # noqa: E402

TEST_PASSWORD = 'correct horse battery staple'


@pytest.fixture(scope='module')
def client():
    """TestClient over the real app.

    The secrets go in the environment before importing dashboard_server, because
    it resolves them at import time — deliberately, so a misconfigured deploy
    crashes instead of silently serving with no auth.
    """
    os.environ['INVEST_DASHBOARD_SECRET'] = 'test-secret-not-used-in-production'
    os.environ['INVEST_DASHBOARD_PASSWORD_HASH'] = hash_password(TEST_PASSWORD, rounds=1000)

    from starlette.testclient import TestClient

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
    import dashboard_server

    # base_url must be https: the session cookie is set with https_only=True
    # (correct in production, where Cloudflare terminates TLS and the browser
    # always sees https), so over plain http it is never sent back and every
    # post-login request would look anonymous.
    return TestClient(dashboard_server.app, base_url='https://testserver')


# ── The rule itself, no HTTP involved ────────────────────────────────────

class TestRequiresAuth:
    @pytest.mark.parametrize('path', ['/', '/m', '/feed', '/api/stocks', '/api/health',
                                      '/api/update/status', '/api/insider/AAPL'])
    def test_public_reads(self, path):
        assert not requires_auth('GET', path)

    @pytest.mark.parametrize('path', ['/api/alarms', '/api/alarms/triggered',
                                      '/api/notes/AAPL', '/api/reminders',
                                      '/api/reminders/due'])
    def test_private_even_for_get(self, path):
        """Alarms, notes and reminders are the owner's own data.

        Reminders are included deliberately: nginx left their GETs public while
        protecting alarms, which was an oversight, not a decision.
        """
        assert requires_auth('GET', path)

    @pytest.mark.parametrize('method', ['POST', 'PUT', 'DELETE', 'PATCH'])
    def test_writes_always_need_auth(self, method):
        assert requires_auth(method, '/')
        assert requires_auth(method, '/api/update')

    def test_login_endpoints_are_exempt(self):
        """Otherwise nothing could ever authenticate."""
        assert not requires_auth('POST', '/api/login')
        assert not requires_auth('POST', '/api/logout')


class TestPasswordHashing:
    def test_round_trip(self):
        stored = hash_password(TEST_PASSWORD, rounds=1000)
        assert verify_password(TEST_PASSWORD, stored)

    def test_wrong_password_rejected(self):
        stored = hash_password(TEST_PASSWORD, rounds=1000)
        assert not verify_password('wrong', stored)

    def test_salt_differs_between_hashes(self):
        assert hash_password('x', rounds=1000) != hash_password('x', rounds=1000)

    @pytest.mark.parametrize('junk', ['', 'garbage', 'md5$1$a$b', 'pbkdf2_sha256$notanint$s$h'])
    def test_malformed_stored_hash_rejected(self, junk):
        assert not verify_password('anything', junk)


# ── Through the app ──────────────────────────────────────────────────────

class TestAnonymousAccess:
    @pytest.mark.parametrize('path', ['/api/alarms', '/api/notes/AAPL', '/api/reminders'])
    def test_private_endpoints_401(self, client, path):
        assert client.get(path).status_code == 401

    def test_writes_401(self, client):
        assert client.post('/api/update', json={}).status_code == 401
        assert client.post('/api/alarms', json={}).status_code == 401

    def test_401_has_no_www_authenticate_header(self, client):
        """The whole point of moving auth out of nginx.

        That header is what makes a browser draw its own sign-in dialog. If it
        comes back, the popup comes back, and every other test here still passes.
        """
        for path in ('/api/alarms', '/api/notes/AAPL', '/api/reminders'):
            response = client.get(path)
            assert response.status_code == 401
            assert 'www-authenticate' not in {k.lower() for k in response.headers}


class TestLoginFlow:
    def test_wrong_password_401(self, client):
        assert client.post('/api/login', json={'password': 'nope'}).status_code == 401

    def test_missing_password_401(self, client):
        assert client.post('/api/login', json={}).status_code == 401

    def test_login_then_access_then_logout(self, client):
        assert client.get('/api/alarms').status_code == 401

        assert client.post('/api/login', json={'password': TEST_PASSWORD}).status_code == 200
        # TestClient keeps the session cookie, so this is now the owner.
        assert client.get('/api/alarms').status_code != 401

        assert client.post('/api/logout').status_code == 200
        assert client.get('/api/alarms').status_code == 401
