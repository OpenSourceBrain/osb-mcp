"""Unit tests for the OSB Keycloak access-token helper.

These tests drive the helper through ``httpx.MockTransport`` so they never
touch the network.
"""

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from osb_mcp import auth
from osb_mcp.auth import KeycloakAuthError, get_access_token

TOKEN_URL = (
    "https://accounts.v2.opensourcebrain.org/auth/realms/osb2"
    "/protocol/openid-connect/token"
)


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """Clear the module-level token cache around every test."""

    auth._cached_token = None
    auth._cached_token_expiry = 0.0
    yield
    auth._cached_token = None
    auth._cached_token_expiry = 0.0


@pytest.fixture
def credentials(monkeypatch):
    """Set the resource-owner credentials the helper reads."""

    monkeypatch.setenv("OSB_USERNAME", "alice")
    monkeypatch.setenv("OSB_PASSWORD", "s3cret")


@pytest.fixture(autouse=True)
def _isolate_keycloak_env(monkeypatch):
    """Ignore any Keycloak overrides from the ambient environment.

    Without this, an environment that sets ``OSB_KEYCLOAK_TOKEN_URL`` or
    ``OSB_KEYCLOAK_REALM`` makes the helper post to a different endpoint than
    the one asserted below.
    """

    for env_var in (
        auth.OSB_KEYCLOAK_TOKEN_URL_ENV,
        auth.OSB_KEYCLOAK_REALM_ENV,
        auth.OSB_KEYCLOAK_CLIENT_ID_ENV,
        auth.OSB_KEYCLOAK_CLIENT_SECRET_ENV,
    ):
        monkeypatch.delenv(env_var, raising=False)


def _client(handler) -> httpx.Client:
    """Return an ``httpx.Client`` backed by a ``MockTransport``."""

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_get_access_token_success(credentials):
    """The success path posts the password grant and returns the token."""

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "tok-123", "expires_in": 300})

    with _client(handler) as client:
        token = get_access_token(client=client)

    assert token == "tok-123"
    assert captured["url"] == TOKEN_URL

    form = parse_qs(captured["body"])
    assert form["grant_type"] == ["password"]
    assert form["client_id"] == ["web-client"]
    assert form["username"] == ["alice"]
    assert form["password"] == ["s3cret"]


def test_missing_credentials_raise_without_request(monkeypatch):
    """Missing credentials raise before any HTTP request is made."""

    monkeypatch.delenv("OSB_USERNAME", raising=False)
    monkeypatch.delenv("OSB_PASSWORD", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request should be made")

    with _client(handler) as client, pytest.raises(KeycloakAuthError):
        get_access_token(client=client)


def test_rejected_grant_raises(credentials):
    """A 400 response from Keycloak raises ``KeycloakAuthError``."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "bad credentials"},
        )

    with _client(handler) as client, pytest.raises(KeycloakAuthError):
        get_access_token(client=client)


def test_non_json_body_raises(credentials):
    """A non-JSON token response raises ``KeycloakAuthError``."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with _client(handler) as client, pytest.raises(KeycloakAuthError):
        get_access_token(client=client)


def test_caching_avoids_second_request(credentials):
    """A second call within the token lifetime does not hit the transport."""

    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(
            200, json={"access_token": "tok-cached", "expires_in": 300}
        )

    with _client(handler) as client:
        first = get_access_token(client=client)
        second = get_access_token(client=client)

    assert first == second == "tok-cached"
    assert calls["count"] == 1
