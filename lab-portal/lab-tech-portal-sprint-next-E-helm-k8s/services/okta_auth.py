import json
import logging
import os
import secrets
from typing import Dict, Mapping, Optional
from urllib.parse import urlencode

import jwt
import requests

logger = logging.getLogger(__name__)


class OktaAuthError(RuntimeError):
    """Raised when Okta authentication fails."""


def _get_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise OktaAuthError(f"Missing required environment variable: {key}")
    return value


class OktaAuthService:
    """Service wrapper for Okta OIDC authentication flows."""

    def __init__(self, *, timeout: int = 10) -> None:
        self._timeout = timeout
        self._issuer = _get_env("OKTA_ISSUER").rstrip("/")
        self._client_id = _get_env("OKTA_CLIENT_ID")
        self._client_secret = _get_env("OKTA_CLIENT_SECRET")
        self._redirect_uri = _get_env("OKTA_REDIRECT_URI")
        self._session = requests.Session()
        self._discovery: Optional[Dict[str, object]] = None
        self._jwks: Optional[Dict[str, object]] = None

    @property
    def redirect_uri(self) -> str:
        return self._redirect_uri

    def get_authorization_url(self, *, state: str, nonce: str) -> str:
        config = self._get_discovery()
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": self._redirect_uri,
            "state": state,
            "nonce": nonce,
        }
        return f"{config['authorization_endpoint']}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> Dict[str, str]:
        config = self._get_discovery()
        token_endpoint = config["token_endpoint"]
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
        }
        headers = {"Accept": "application/json"}
        try:
            response = self._session.post(
                token_endpoint,
                data=payload,
                headers=headers,
                auth=(self._client_id, self._client_secret),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.error("Error communicating with Okta token endpoint: %s", exc)
            raise OktaAuthError("Failed to communicate with Okta token endpoint") from exc

        if response.status_code >= 300:
            logger.error("Okta token request failed (status %s): %s", response.status_code, response.text)
            raise OktaAuthError("Okta token request failed")

        try:
            tokens = response.json()
        except ValueError as exc:
            logger.error("Okta returned invalid token payload: %s", response.text)
            raise OktaAuthError("Okta token response was not valid JSON") from exc

        if "id_token" not in tokens:
            raise OktaAuthError("Okta token response missing id_token")

        return tokens

    def verify_id_token(self, id_token: str, *, nonce: Optional[str] = None) -> Dict[str, object]:
        header = jwt.get_unverified_header(id_token)
        kid = header.get("kid")
        algorithm = header.get("alg", "RS256")
        if not kid:
            raise OktaAuthError("ID token header missing kid")

        jwk = self._get_jwk_for_kid(kid)
        key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))

        try:
            claims = jwt.decode(
                id_token,
                key=key,
                algorithms=[algorithm],
                audience=self._client_id,
                issuer=self._issuer,
            )
        except jwt.PyJWTError as exc:
            logger.error("Failed to verify Okta ID token: %s", exc)
            raise OktaAuthError("Failed to verify Okta ID token") from exc

        if nonce and claims.get("nonce") != nonce:
            raise OktaAuthError("ID token nonce did not match")

        return claims

    @staticmethod
    def extract_identity(claims: Mapping[str, object]) -> Dict[str, object]:
        """Extract user identity fields from validated Okta ID token claims.

        Returns a dict with email, display_name, username, and groups.
        The ``groups`` key holds the Okta groups claim (list[str]) used by
        services/rbac.py for tier mapping (Slice A, Issue #44).
        """
        email = claims.get("email")
        if not email:
            raise OktaAuthError("ID token did not include an email claim")

        name = claims.get("name") or claims.get("preferred_username") or email
        username = claims.get("preferred_username") or email

        # Extract groups claim — Okta sends this when "Groups" is added to the
        # ID token scope in the Okta app configuration.
        raw_groups = claims.get("groups")
        groups: list[str] = (
            [str(g) for g in raw_groups if isinstance(g, str)]
            if isinstance(raw_groups, list)
            else []
        )

        return {
            "email": str(email),
            "display_name": str(name),
            "username": str(username),
            "groups": groups,
        }

    def new_state(self) -> str:
        return secrets.token_urlsafe(24)

    def new_nonce(self) -> str:
        return secrets.token_urlsafe(24)

    def get_logout_url(self, *, id_token: Optional[str], post_logout_redirect: str) -> Optional[str]:
        config = self._get_discovery()
        endpoint = config.get("end_session_endpoint")
        if not endpoint:
            return None

        params = {"post_logout_redirect_uri": post_logout_redirect}
        if id_token:
            params["id_token_hint"] = id_token
        return f"{endpoint}?{urlencode(params)}"

    def _get_discovery(self) -> Dict[str, object]:
        if self._discovery:
            return self._discovery

        discovery_url = f"{self._issuer}/.well-known/openid-configuration"
        try:
            response = self._session.get(discovery_url, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.error("Error fetching Okta discovery document: %s", exc)
            raise OktaAuthError("Failed to fetch Okta discovery document") from exc

        if response.status_code >= 300:
            logger.error("Okta discovery request failed (status %s): %s", response.status_code, response.text)
            raise OktaAuthError("Okta discovery request failed")

        try:
            self._discovery = response.json()
        except ValueError as exc:
            logger.error("Okta returned invalid discovery document: %s", response.text)
            raise OktaAuthError("Okta discovery document was not valid JSON") from exc

        return self._discovery

    def _get_jwks(self) -> Dict[str, object]:
        if self._jwks:
            return self._jwks

        config = self._get_discovery()
        jwks_uri = config["jwks_uri"]
        try:
            response = self._session.get(jwks_uri, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.error("Error fetching Okta JWKS: %s", exc)
            raise OktaAuthError("Failed to fetch Okta JWKS") from exc

        if response.status_code >= 300:
            logger.error("Okta JWKS request failed (status %s): %s", response.status_code, response.text)
            raise OktaAuthError("Okta JWKS request failed")

        try:
            self._jwks = response.json()
        except ValueError as exc:
            logger.error("Okta returned invalid JWKS: %s", response.text)
            raise OktaAuthError("Okta JWKS was not valid JSON") from exc

        return self._jwks

    def _get_jwk_for_kid(self, kid: str) -> Dict[str, object]:
        jwks = self._get_jwks()
        keys = jwks.get("keys", []) if isinstance(jwks, dict) else []
        for key in keys:
            if key.get("kid") == kid:
                return key

        self._jwks = None
        jwks = self._get_jwks()
        keys = jwks.get("keys", []) if isinstance(jwks, dict) else []
        for key in keys:
            if key.get("kid") == kid:
                return key

        raise OktaAuthError("Unable to find matching JWKS key for ID token")
