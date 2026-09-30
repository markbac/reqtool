"""
tests/test_auth.py
===================
Unit tests for reqtool authentication, user store, JWT handling, and REST endpoints.
"""

from pathlib import Path
import pytest
from reqtool.auth import UserStore, hash_password, verify_password, create_token, verify_token


def test_password_hashing():
    pwd = "SecretPassword123"
    h, salt = hash_password(pwd)
    assert len(h) > 0
    assert len(salt) > 0
    assert verify_password(pwd, h, salt) is True
    assert verify_password("WrongPassword", h, salt) is False


def test_jwt_creation_and_verification(tmp_path: Path):
    repo_root = tmp_path
    token = create_token("john_doe", "editor", repo_root)
    assert isinstance(token, str)
    assert len(token) > 20

    payload = verify_token(token, repo_root)
    assert payload is not None
    assert payload["sub"] == "john_doe"
    assert payload["role"] == "editor"

    # Invalid token test
    assert verify_token("invalid.token.str", repo_root) is None


def test_user_store_operations(tmp_path: Path):
    store = UserStore(tmp_path)
    # Default admin seeded
    users = store.load_users()
    assert "admin" in users
    assert store.authenticate("admin", "admin123") is not None

    # Create new user
    new_u = store.create_user("alice", "alicepass", "Alice Smith", "alice@example.com", "editor")
    assert new_u["username"] == "alice"
    assert store.authenticate("alice", "alicepass") is not None
    assert store.authenticate("alice", "wrongpass") is None

    # Duplicate creation error
    with pytest.raises(ValueError):
        store.create_user("alice", "password")


class TestAuthApi:
    def test_login_success(self, client):
        r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["user"]["username"] == "admin"

    def test_login_failure(self, client):
        r = client.post("/auth/login", json={"username": "admin", "password": "wrongpassword"})
        assert r.status_code == 401

    def test_get_me_with_bearer(self, client):
        login_res = client.post("/auth/login", json={"username": "admin", "password": "admin123"}).json()
        token = login_res["access_token"]

        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == "admin"
        assert data["authenticated"] is True

    def test_list_and_create_users_api(self, client):
        login_res = client.post("/auth/login", json={"username": "admin", "password": "admin123"}).json()
        token = login_res["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create user via API
        r = client.post("/auth/users", json={
            "username": "bob",
            "password": "bobpassword",
            "full_name": "Bob Builder",
            "role": "editor"
        }, headers=headers)
        assert r.status_code == 201
        assert r.json()["username"] == "bob"

        # List users
        r_list = client.get("/auth/users", headers=headers)
        assert r_list.status_code == 200
        user_list = r_list.json()
        usernames = [u["username"] for u in user_list]
        assert "admin" in usernames
        assert "bob" in usernames
