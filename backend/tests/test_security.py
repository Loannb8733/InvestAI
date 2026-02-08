"""Security module tests."""

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_password():
    """Test password hashing."""
    hashed = hash_password("mypassword")
    assert hashed != "mypassword"
    assert hashed.startswith("$2b$")


def test_verify_password_correct():
    """Test verifying correct password."""
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed) is True


def test_verify_password_incorrect():
    """Test verifying incorrect password."""
    hashed = hash_password("mypassword")
    assert verify_password("wrongpassword", hashed) is False


def test_create_access_token():
    """Test access token creation."""
    token = create_access_token(subject="user-123")
    assert isinstance(token, str)
    assert len(token) > 0


def test_decode_access_token():
    """Test decoding access token."""
    token = create_access_token(subject="user-123")
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_create_refresh_token():
    """Test refresh token creation."""
    token = create_refresh_token(subject="user-123")
    assert isinstance(token, str)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["type"] == "refresh"


def test_decode_invalid_token():
    """Test decoding an invalid token."""
    payload = decode_token("invalid.token.here")
    assert payload is None


def test_password_hash_uniqueness():
    """Test that same password gets different hashes (salted)."""
    hash1 = hash_password("samepassword")
    hash2 = hash_password("samepassword")
    assert hash1 != hash2
    assert verify_password("samepassword", hash1)
    assert verify_password("samepassword", hash2)
