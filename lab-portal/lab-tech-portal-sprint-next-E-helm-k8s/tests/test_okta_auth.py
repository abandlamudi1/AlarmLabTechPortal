"""Unit tests for OktaAuthService.

All network calls (OIDC discovery, JWKS, token endpoint) are mocked so no
real Okta instance is needed.  Tests are marked @pytest.mark.unit.
"""
import json
from unittest.mock import MagicMock
from urllib.parse import urlparse, parse_qs

import pytest
import requests

from services.okta_auth import OktaAuthService, OktaAuthError, _get_env


# ---------------------------------------------------------------------------
# Environment constants shared across unit tests
# ---------------------------------------------------------------------------

UNIT_ENV = {
    "OKTA_ISSUER": "https://dev-123.okta.com/oauth2/default",
    "OKTA_CLIENT_ID": "test-client-id",
    "OKTA_CLIENT_SECRET": "test-client-secret",
    "OKTA_REDIRECT_URI": "https://app.example.com/auth/callback",
}

DISCOVERY_DOC = {
    "authorization_endpoint": "https://dev-123.okta.com/oauth2/default/v1/authorize",
    "token_endpoint": "https://dev-123.okta.com/oauth2/default/v1/token",
    "jwks_uri": "https://dev-123.okta.com/oauth2/default/v1/keys",
    "end_session_endpoint": "https://dev-123.okta.com/oauth2/default/v1/logout",
    "issuer": "https://dev-123.okta.com/oauth2/default",
}

JWKS_DOC = {
    "keys": [
        {
            "kty": "RSA",
            "kid": "test-key-id",
            "use": "sig",
            "alg": "RS256",
            "n": "sEjTG3F0kNxgVzF8vn1IkYjD",
            "e": "AQAB",
        }
    ]
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def okta_unit(monkeypatch):
    """OktaAuthService with env vars patched and discovery cached."""
    for key, value in UNIT_ENV.items():
        monkeypatch.setenv(key, value)
    svc = OktaAuthService()
    # Pre-populate the discovery cache so most tests don't need to mock the
    # discovery network call.
    svc._discovery = DISCOVERY_DOC
    return svc


@pytest.fixture
def okta_fresh(monkeypatch):
    """OktaAuthService with env vars patched but NO cached discovery."""
    for key, value in UNIT_ENV.items():
        monkeypatch.setenv(key, value)
    return OktaAuthService()


# ---------------------------------------------------------------------------
# _get_env helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_env_returns_value(monkeypatch):
    """_get_env should return the env var value when set."""
    monkeypatch.setenv("_TEST_KEY", "hello")
    assert _get_env("_TEST_KEY") == "hello"


@pytest.mark.unit
def test_get_env_raises_when_missing(monkeypatch):
    """_get_env should raise OktaAuthError when the env var is absent."""
    monkeypatch.delenv("_TEST_KEY_MISSING", raising=False)
    with pytest.raises(OktaAuthError, match="_TEST_KEY_MISSING"):
        _get_env("_TEST_KEY_MISSING")


# ---------------------------------------------------------------------------
# Construction — missing credentials
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_missing_okta_issuer_raises(monkeypatch):
    """OktaAuthService must raise OktaAuthError if OKTA_ISSUER is absent."""
    for key, value in UNIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("OKTA_ISSUER", raising=False)
    with pytest.raises(OktaAuthError, match="OKTA_ISSUER"):
        OktaAuthService()


@pytest.mark.unit
def test_missing_okta_client_id_raises(monkeypatch):
    """OktaAuthService must raise OktaAuthError if OKTA_CLIENT_ID is absent."""
    for key, value in UNIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("OKTA_CLIENT_ID", raising=False)
    with pytest.raises(OktaAuthError, match="OKTA_CLIENT_ID"):
        OktaAuthService()


@pytest.mark.unit
def test_missing_okta_client_secret_raises(monkeypatch):
    """OktaAuthService must raise OktaAuthError if OKTA_CLIENT_SECRET is absent."""
    for key, value in UNIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("OKTA_CLIENT_SECRET", raising=False)
    with pytest.raises(OktaAuthError, match="OKTA_CLIENT_SECRET"):
        OktaAuthService()


@pytest.mark.unit
def test_missing_okta_redirect_uri_raises(monkeypatch):
    """OktaAuthService must raise OktaAuthError if OKTA_REDIRECT_URI is absent."""
    for key, value in UNIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("OKTA_REDIRECT_URI", raising=False)
    with pytest.raises(OktaAuthError, match="OKTA_REDIRECT_URI"):
        OktaAuthService()


# ---------------------------------------------------------------------------
# redirect_uri property
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_redirect_uri_property(okta_unit):
    """redirect_uri should return the configured redirect URI."""
    assert okta_unit.redirect_uri == UNIT_ENV["OKTA_REDIRECT_URI"]


# ---------------------------------------------------------------------------
# new_state / new_nonce
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_new_state_is_non_empty_string(okta_unit):
    """new_state should return a non-empty string."""
    state = okta_unit.new_state()
    assert isinstance(state, str)
    assert len(state) > 0


@pytest.mark.unit
def test_new_nonce_is_non_empty_string(okta_unit):
    """new_nonce should return a non-empty string."""
    nonce = okta_unit.new_nonce()
    assert isinstance(nonce, str)
    assert len(nonce) > 0


@pytest.mark.unit
def test_new_state_generates_unique_values(okta_unit):
    """new_state should return unique tokens across calls."""
    states = {okta_unit.new_state() for _ in range(10)}
    assert len(states) == 10


# ---------------------------------------------------------------------------
# get_authorization_url
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_authorization_url_contains_required_params(okta_unit):
    """get_authorization_url should include client_id, state, nonce, etc."""
    url = okta_unit.get_authorization_url(state="abc123", nonce="xyz789")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert params["client_id"][0] == "test-client-id"
    assert params["response_type"][0] == "code"
    assert params["state"][0] == "abc123"
    assert params["nonce"][0] == "xyz789"
    assert params["redirect_uri"][0] == UNIT_ENV["OKTA_REDIRECT_URI"]
    assert "openid" in params["scope"][0]


@pytest.mark.unit
def test_get_authorization_url_base_is_authorization_endpoint(okta_unit):
    """Authorization URL should start with the authorization endpoint from discovery."""
    url = okta_unit.get_authorization_url(state="s", nonce="n")
    assert url.startswith(DISCOVERY_DOC["authorization_endpoint"])


# ---------------------------------------------------------------------------
# _get_discovery
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_discovery_cached_after_first_call(okta_fresh, monkeypatch):
    """_get_discovery should only make one HTTP request (cache after first)."""
    call_count = {"n": 0}

    def fake_get(url, **kw):
        call_count["n"] += 1
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = DISCOVERY_DOC
        return resp

    monkeypatch.setattr(okta_fresh._session, "get", fake_get)

    okta_fresh._get_discovery()
    okta_fresh._get_discovery()  # second call — should use cache
    assert call_count["n"] == 1


@pytest.mark.unit
def test_get_discovery_network_error_raises(okta_fresh, monkeypatch):
    """_get_discovery must raise OktaAuthError on network failure."""
    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(okta_fresh._session, "get", raise_exc)
    with pytest.raises(OktaAuthError, match="Failed to fetch Okta discovery document"):
        okta_fresh._get_discovery()


@pytest.mark.unit
def test_get_discovery_non_200_raises(okta_fresh, monkeypatch):
    """_get_discovery must raise OktaAuthError on non-2xx from Okta."""
    resp = MagicMock()
    resp.status_code = 503
    resp.text = "Service unavailable"
    monkeypatch.setattr(okta_fresh._session, "get", lambda *a, **kw: resp)
    with pytest.raises(OktaAuthError, match="Okta discovery request failed"):
        okta_fresh._get_discovery()


@pytest.mark.unit
def test_get_discovery_invalid_json_raises(okta_fresh, monkeypatch):
    """_get_discovery must raise OktaAuthError when discovery doc is not JSON."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("not json")
    resp.text = "not json"
    monkeypatch.setattr(okta_fresh._session, "get", lambda *a, **kw: resp)
    with pytest.raises(OktaAuthError, match="not valid JSON"):
        okta_fresh._get_discovery()


# ---------------------------------------------------------------------------
# _get_jwks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_jwks_cached_after_first_call(okta_unit, monkeypatch):
    """_get_jwks should only make one HTTP request (cache after first)."""
    call_count = {"n": 0}

    def fake_get(url, **kw):
        call_count["n"] += 1
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = JWKS_DOC
        return resp

    monkeypatch.setattr(okta_unit._session, "get", fake_get)

    okta_unit._get_jwks()
    okta_unit._get_jwks()  # second call — should use cache
    assert call_count["n"] == 1


@pytest.mark.unit
def test_get_jwks_network_error_raises(okta_unit, monkeypatch):
    """_get_jwks must raise OktaAuthError on network failure."""
    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(okta_unit._session, "get", raise_exc)
    with pytest.raises(OktaAuthError, match="Failed to fetch Okta JWKS"):
        okta_unit._get_jwks()


@pytest.mark.unit
def test_get_jwks_non_200_raises(okta_unit, monkeypatch):
    """_get_jwks must raise OktaAuthError on non-2xx from Okta."""
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "Server error"
    monkeypatch.setattr(okta_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(OktaAuthError, match="Okta JWKS request failed"):
        okta_unit._get_jwks()


@pytest.mark.unit
def test_get_jwks_invalid_json_raises(okta_unit, monkeypatch):
    """_get_jwks must raise OktaAuthError when JWKS is not valid JSON."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("bad json")
    resp.text = "bad json"
    monkeypatch.setattr(okta_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(OktaAuthError, match="not valid JSON"):
        okta_unit._get_jwks()


# ---------------------------------------------------------------------------
# _get_jwk_for_kid
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_jwk_for_kid_found(okta_unit, monkeypatch):
    """_get_jwk_for_kid should return the key when kid is found in JWKS."""
    okta_unit._jwks = JWKS_DOC
    key = okta_unit._get_jwk_for_kid("test-key-id")
    assert key["kid"] == "test-key-id"


@pytest.mark.unit
def test_get_jwk_for_kid_not_found_raises(okta_unit, monkeypatch):
    """_get_jwk_for_kid should raise OktaAuthError if kid is not found."""
    # First JWKS fetch (from cache)
    okta_unit._jwks = JWKS_DOC

    # Second JWKS fetch (after cache clear) — still no match
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = JWKS_DOC  # same doc, no matching key
    monkeypatch.setattr(okta_unit._session, "get", lambda *a, **kw: resp)

    with pytest.raises(OktaAuthError, match="Unable to find matching JWKS key"):
        okta_unit._get_jwk_for_kid("unknown-kid")


@pytest.mark.unit
def test_get_jwk_for_kid_refreshes_cache_on_miss(okta_unit, monkeypatch):
    """_get_jwk_for_kid clears _jwks and retries when kid not found initially."""
    initial_jwks = {"keys": [{"kid": "old-kid", "kty": "RSA"}]}
    refreshed_jwks = {
        "keys": [
            {"kid": "old-kid", "kty": "RSA"},
            {"kid": "new-kid", "kty": "RSA"},
        ]
    }
    okta_unit._jwks = initial_jwks

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = refreshed_jwks
    monkeypatch.setattr(okta_unit._session, "get", lambda *a, **kw: resp)

    key = okta_unit._get_jwk_for_kid("new-kid")
    assert key["kid"] == "new-kid"


# ---------------------------------------------------------------------------
# exchange_code_for_tokens
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_exchange_code_for_tokens_success(okta_unit, monkeypatch):
    """exchange_code_for_tokens should return the parsed token dict."""
    token_payload = {
        "access_token": "access-abc",
        "id_token": "id-xyz",
        "token_type": "Bearer",
    }
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = token_payload

    monkeypatch.setattr(okta_unit._session, "post", lambda *a, **kw: resp)

    result = okta_unit.exchange_code_for_tokens("auth-code-123")
    assert result["id_token"] == "id-xyz"


@pytest.mark.unit
def test_exchange_code_missing_id_token_raises(okta_unit, monkeypatch):
    """exchange_code_for_tokens must raise OktaAuthError when id_token is absent."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": "only-access"}

    monkeypatch.setattr(okta_unit._session, "post", lambda *a, **kw: resp)

    with pytest.raises(OktaAuthError, match="missing id_token"):
        okta_unit.exchange_code_for_tokens("auth-code-123")


@pytest.mark.unit
def test_exchange_code_non_200_raises(okta_unit, monkeypatch):
    """exchange_code_for_tokens must raise OktaAuthError on non-2xx."""
    resp = MagicMock()
    resp.status_code = 400
    resp.text = "invalid_grant"

    monkeypatch.setattr(okta_unit._session, "post", lambda *a, **kw: resp)

    with pytest.raises(OktaAuthError, match="Okta token request failed"):
        okta_unit.exchange_code_for_tokens("bad-code")


@pytest.mark.unit
def test_exchange_code_network_error_raises(okta_unit, monkeypatch):
    """exchange_code_for_tokens must raise OktaAuthError on network failure."""
    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(okta_unit._session, "post", raise_exc)

    with pytest.raises(OktaAuthError, match="Failed to communicate with Okta token endpoint"):
        okta_unit.exchange_code_for_tokens("auth-code")


@pytest.mark.unit
def test_exchange_code_invalid_json_raises(okta_unit, monkeypatch):
    """exchange_code_for_tokens must raise OktaAuthError on bad JSON response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("bad json")
    resp.text = "not json"

    monkeypatch.setattr(okta_unit._session, "post", lambda *a, **kw: resp)

    with pytest.raises(OktaAuthError, match="not valid JSON"):
        okta_unit.exchange_code_for_tokens("auth-code")


# ---------------------------------------------------------------------------
# verify_id_token — malformed / expired token paths (no real RSA key needed)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_verify_id_token_missing_kid_raises(okta_unit):
    """verify_id_token must raise OktaAuthError when the header has no kid."""
    import jwt as pyjwt

    # Build a token without a kid header
    token = pyjwt.encode({"sub": "user"}, "secret", algorithm="HS256")

    with pytest.raises(OktaAuthError, match="missing kid"):
        okta_unit.verify_id_token(token)


@pytest.mark.unit
def test_verify_id_token_invalid_signature_raises(okta_unit, monkeypatch):
    """verify_id_token must raise OktaAuthError when signature verification fails."""
    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend

    # Generate a real RSA key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    # Sign with one key
    token = pyjwt.encode(
        {"sub": "user", "iss": "https://dev-123.okta.com/oauth2/default", "aud": "test-client-id"},
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key-id"},
    )

    # But provide a DIFFERENT public key in the JWKS
    other_private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    other_public_key = other_private_key.public_key()

    # Provide the wrong key in JWK format
    from cryptography.hazmat.primitives import serialization
    wrong_jwk_json = other_public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Mock _get_jwk_for_kid to return a valid-looking JWK that won't match the token
    wrong_private = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    wrong_public = wrong_private.public_key()

    # Use PyJWT's RSAAlgorithm to export a real JWK from wrong_public
    wrong_jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(wrong_public))
    wrong_jwk["kid"] = "test-key-id"

    monkeypatch.setattr(
        okta_unit, "_get_jwk_for_kid", lambda kid: wrong_jwk
    )

    with pytest.raises(OktaAuthError, match="Failed to verify Okta ID token"):
        okta_unit.verify_id_token(token)


@pytest.mark.unit
def test_verify_id_token_success(okta_unit, monkeypatch):
    """verify_id_token must return claims on a valid token."""
    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend

    # Generate RSA key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    public_key = private_key.public_key()

    claims_payload = {
        "sub": "user123",
        "email": "user@example.com",
        "name": "Test User",
        "iss": UNIT_ENV["OKTA_ISSUER"],
        "aud": UNIT_ENV["OKTA_CLIENT_ID"],
        "nonce": "test-nonce",
        # No exp so it won't expire during test
    }

    token = pyjwt.encode(
        claims_payload,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key-id"},
    )

    # Export the matching public key as JWK
    jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = "test-key-id"

    monkeypatch.setattr(okta_unit, "_get_jwk_for_kid", lambda kid: jwk)

    result = okta_unit.verify_id_token(token, nonce="test-nonce")
    assert result["email"] == "user@example.com"
    assert result["sub"] == "user123"


@pytest.mark.unit
def test_verify_id_token_nonce_mismatch_raises(okta_unit, monkeypatch):
    """verify_id_token must raise OktaAuthError when nonce does not match."""
    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend

    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    public_key = private_key.public_key()

    token = pyjwt.encode(
        {
            "sub": "user123",
            "email": "user@example.com",
            "nonce": "correct-nonce",
            "iss": UNIT_ENV["OKTA_ISSUER"],
            "aud": UNIT_ENV["OKTA_CLIENT_ID"],
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key-id"},
    )

    jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = "test-key-id"
    monkeypatch.setattr(okta_unit, "_get_jwk_for_kid", lambda kid: jwk)

    with pytest.raises(OktaAuthError, match="nonce did not match"):
        okta_unit.verify_id_token(token, nonce="wrong-nonce")


# ---------------------------------------------------------------------------
# extract_identity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extract_identity_full_claims():
    """extract_identity should return all expected fields from a full claims set."""
    claims = {
        "sub": "user123",
        "email": "user@example.com",
        "name": "Test User",
        "preferred_username": "testuser",
        "groups": ["Lab-Techs", "QE-Team"],
    }
    result = OktaAuthService.extract_identity(claims)
    assert result["email"] == "user@example.com"
    assert result["display_name"] == "Test User"
    assert result["username"] == "testuser"
    assert result["groups"] == ["Lab-Techs", "QE-Team"]


@pytest.mark.unit
def test_extract_identity_missing_email_raises():
    """extract_identity must raise OktaAuthError when email claim is absent."""
    claims = {"sub": "user123", "name": "Test User"}
    with pytest.raises(OktaAuthError, match="email claim"):
        OktaAuthService.extract_identity(claims)


@pytest.mark.unit
def test_extract_identity_name_fallback_to_preferred_username():
    """extract_identity falls back to preferred_username when name is missing."""
    claims = {
        "sub": "user123",
        "email": "user@example.com",
        "preferred_username": "testuser",
    }
    result = OktaAuthService.extract_identity(claims)
    assert result["display_name"] == "testuser"
    assert result["username"] == "testuser"


@pytest.mark.unit
def test_extract_identity_name_fallback_to_email():
    """extract_identity falls back to email when both name and preferred_username are absent."""
    claims = {"sub": "user123", "email": "user@example.com"}
    result = OktaAuthService.extract_identity(claims)
    assert result["display_name"] == "user@example.com"
    assert result["username"] == "user@example.com"


@pytest.mark.unit
def test_extract_identity_no_groups_returns_empty_list():
    """extract_identity returns an empty groups list when the claim is absent."""
    claims = {"sub": "user123", "email": "user@example.com"}
    result = OktaAuthService.extract_identity(claims)
    assert result["groups"] == []


@pytest.mark.unit
def test_extract_identity_groups_non_list_returns_empty():
    """extract_identity returns empty list when groups claim is not a list."""
    claims = {
        "sub": "user123",
        "email": "user@example.com",
        "groups": "not-a-list",
    }
    result = OktaAuthService.extract_identity(claims)
    assert result["groups"] == []


@pytest.mark.unit
def test_extract_identity_groups_filters_non_strings():
    """extract_identity only includes string values from the groups list."""
    claims = {
        "sub": "user123",
        "email": "user@example.com",
        "groups": ["Lab-Techs", 42, None, "QE-Team"],
    }
    result = OktaAuthService.extract_identity(claims)
    assert result["groups"] == ["Lab-Techs", "QE-Team"]


# ---------------------------------------------------------------------------
# get_logout_url
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_logout_url_with_id_token(okta_unit):
    """get_logout_url should include id_token_hint when id_token is provided."""
    url = okta_unit.get_logout_url(
        id_token="some-id-token",
        post_logout_redirect="https://app.example.com",
    )
    assert url is not None
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert params["id_token_hint"][0] == "some-id-token"
    assert params["post_logout_redirect_uri"][0] == "https://app.example.com"


@pytest.mark.unit
def test_get_logout_url_without_id_token(okta_unit):
    """get_logout_url should omit id_token_hint when id_token is None."""
    url = okta_unit.get_logout_url(
        id_token=None,
        post_logout_redirect="https://app.example.com",
    )
    assert url is not None
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert "id_token_hint" not in params


@pytest.mark.unit
def test_get_logout_url_no_end_session_endpoint_returns_none(okta_unit):
    """get_logout_url should return None when discovery doc lacks end_session_endpoint."""
    okta_unit._discovery = dict(DISCOVERY_DOC)
    del okta_unit._discovery["end_session_endpoint"]

    url = okta_unit.get_logout_url(
        id_token="token",
        post_logout_redirect="https://app.example.com",
    )
    assert url is None
