#!/usr/bin/env python3
"""
Authentication helpers for the OSB MCP server.

Obtains an access token from the Open Source Brain (v2) Keycloak server
using the OAuth2 resource-owner password grant, so that tools can
authenticate write requests to the OSB APIs.

File: osb_mcp/auth.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import logging
import os
import time

import httpx
from fastmcp import Context

logger = logging.getLogger(__name__)

#: Environment variable holding the OSB username.
OSB_USERNAME_ENV = "OSB_USERNAME"
#: Environment variable holding the OSB password.
OSB_PASSWORD_ENV = "OSB_PASSWORD"
#: Environment variable overriding the Keycloak token endpoint URL.
OSB_KEYCLOAK_TOKEN_URL_ENV = "OSB_KEYCLOAK_TOKEN_URL"
#: Environment variable overriding the Keycloak realm.
OSB_KEYCLOAK_REALM_ENV = "OSB_KEYCLOAK_REALM"
#: Environment variable overriding the Keycloak client id.
OSB_KEYCLOAK_CLIENT_ID_ENV = "OSB_KEYCLOAK_CLIENT_ID"
#: Environment variable holding the optional Keycloak client secret.
OSB_KEYCLOAK_CLIENT_SECRET_ENV = "OSB_KEYCLOAK_CLIENT_SECRET"
#: Environment variable holding a pre-issued OSB bearer token.
OSB_API_TOKEN_ENV = "OSB_API_TOKEN"

#: Default Keycloak base URL of the production OSB (v2) deployment.
OSB_KEYCLOAK_BASE_URL_DEFAULT = "https://accounts.v2.opensourcebrain.org/auth"
#: Default Keycloak realm of the production OSB (v2) deployment.
OSB_KEYCLOAK_REALM_DEFAULT = "osb2"
#: Default Keycloak client id of the production OSB (v2) deployment.
OSB_KEYCLOAK_CLIENT_ID_DEFAULT = "web-client"

REQUEST_TIMEOUT = httpx.Timeout(30)

#: Seconds subtracted from a token's lifetime so that it is refreshed
#: shortly before it actually expires.
EXPIRY_MARGIN = 30.0

#: Cached access token and the monotonic time at which it expires.
_cached_token: str | None = None
_cached_token_expiry: float = 0.0


class KeycloakAuthError(Exception):
    """Raised when an access token cannot be obtained from Keycloak."""


def _token_url() -> str:
    """Return the Keycloak token endpoint URL.

    ``OSB_KEYCLOAK_TOKEN_URL``, when set, is used verbatim.  Otherwise the
    URL is built from the default production base URL and the realm from
    ``OSB_KEYCLOAK_REALM`` (default ``osb2``).
    """
    explicit = os.environ.get(OSB_KEYCLOAK_TOKEN_URL_ENV)
    if explicit:
        return explicit
    realm = os.environ.get(OSB_KEYCLOAK_REALM_ENV, OSB_KEYCLOAK_REALM_DEFAULT)
    return (
        f"{OSB_KEYCLOAK_BASE_URL_DEFAULT}/realms/{realm}/protocol/openid-connect/token"
    )


def _client_id() -> str:
    """Return the Keycloak client id."""
    return os.environ.get(OSB_KEYCLOAK_CLIENT_ID_ENV, OSB_KEYCLOAK_CLIENT_ID_DEFAULT)


def _request_token(client: httpx.Client | None = None) -> tuple[str, float]:
    """Request a fresh access token from Keycloak.

    Uses the OAuth2 resource-owner password grant with the credentials from
    ``OSB_USERNAME`` and ``OSB_PASSWORD``.  The password and the returned
    token are never logged.

    Args:
        client: Optional ``httpx.Client`` to use for the request.  When
            omitted, a short-lived client is created and closed.

    Returns:
        A ``(token, expires_in)`` tuple, where ``expires_in`` is the token
        lifetime in seconds.

    Raises:
        KeycloakAuthError: If the credentials are missing or the token
            request fails.
    """
    username = os.environ.get(OSB_USERNAME_ENV)
    password = os.environ.get(OSB_PASSWORD_ENV)
    if not username or not password:
        raise KeycloakAuthError(
            "OSB_USERNAME and OSB_PASSWORD must both be set to obtain an access token"
        )

    data = {
        "grant_type": "password",
        "client_id": _client_id(),
        "username": username,
        "password": password,
    }
    client_secret = os.environ.get(OSB_KEYCLOAK_CLIENT_SECRET_ENV)
    if client_secret:
        data["client_secret"] = client_secret

    url = _token_url()

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=REQUEST_TIMEOUT)

    try:
        response = client.post(url, data=data)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise KeycloakAuthError(
            "Keycloak rejected the token request "
            f"(HTTP {exc.response.status_code}): {exc.response.text[:2000]}"
        ) from exc
    except httpx.HTTPError as exc:
        raise KeycloakAuthError(
            "Could not reach the Keycloak token endpoint: "
            f"{exc.__class__.__name__}: {exc}"
        ) from exc
    finally:
        if owns_client:
            client.close()

    try:
        payload = response.json()
    except ValueError as exc:
        raise KeycloakAuthError("Keycloak returned a non-JSON token response") from exc

    token = payload.get("access_token")
    if not token:
        raise KeycloakAuthError(
            "Keycloak token response did not contain an access_token"
        )

    try:
        expires_in = float(payload.get("expires_in", 300))
    except (TypeError, ValueError):
        expires_in = 300.0

    return token, expires_in


def get_access_token(client: httpx.Client | None = None) -> str:
    """Return a valid OSB access token, using a cached one when possible.

    The token is obtained from Keycloak with the resource-owner password
    grant (see :func:`_request_token`) and cached until shortly before it
    expires, so repeated calls do not hit the token endpoint.

    Args:
        client: Optional ``httpx.Client`` to use for the request.  When
            omitted, a short-lived client is created and closed.

    Returns:
        The access token string.

    Raises:
        KeycloakAuthError: If no token can be obtained.
    """
    global _cached_token, _cached_token_expiry

    now = time.monotonic()
    if _cached_token is not None and now < _cached_token_expiry:
        return _cached_token

    token, expires_in = _request_token(client)
    _cached_token = token
    _cached_token_expiry = now + max(expires_in - EXPIRY_MARGIN, 0.0)
    return token


def resolve_auth(
    ctx: Context | None = None,
    *,
    required: bool = False,
) -> tuple[dict[str, str], dict | None]:
    """Resolve the Authorization header for an OSB request.

    The bearer token is resolved from, in order:

    1. the incoming MCP request's ``Authorization`` header (the multi-user
       path, where the host forwards the caller's bearer token);
    2. the ``OSB_API_TOKEN`` environment variable (the single-user path);
    3. the Keycloak credentials in ``OSB_USERNAME``/``OSB_PASSWORD`` via
       :func:`get_access_token`.

    The raw token is never logged or returned.

    Args:
        ctx: The FastMCP context for the current request.  Accepted for
            explicitness and future use; the header read itself uses the
            request-scoped context variable.
        required: When ``True``, a missing credential yields a structured
            error instead of empty headers.

    Returns:
        A ``(headers, error)`` tuple.  On success ``headers`` holds the
        ``Authorization`` header and ``error`` is ``None``.  When no
        credential is available, ``headers`` is empty and ``error`` is
        ``None`` if ``required`` is ``False``, otherwise a structured
        ``{"Error": ...}`` mapping.
    """
    from fastmcp.server.dependencies import get_http_headers

    request_headers = get_http_headers(include={"authorization"})
    authorization = request_headers.get("authorization")
    if authorization:
        return {"Authorization": authorization}, None

    token = os.environ.get(OSB_API_TOKEN_ENV)
    if token:
        return {"Authorization": f"Bearer {token}"}, None

    try:
        token = get_access_token()
    except KeycloakAuthError:
        token = None
    if token:
        return {"Authorization": f"Bearer {token}"}, None

    if required:
        return {}, {
            "Error": (
                "Authentication required: no bearer token available "
                "(provide an Authorization header or set OSB_API_TOKEN / "
                "OSB_USERNAME+OSB_PASSWORD)."
            )
        }
    return {}, None
