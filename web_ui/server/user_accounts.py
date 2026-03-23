#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web UI user account storage and authentication helpers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml


USERS_FILE = Path(
    os.environ.get("WEB_UI_USERS_FILE", str(Path(__file__).resolve().parent / "users.yaml"))
).expanduser().resolve()
PBKDF2_ITERATIONS = 120_000


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _validate_username(username: str) -> str:
    value = str(username or "").strip()
    if not value:
        raise ValueError("Username is required")
    if len(value) < 3:
        raise ValueError("Username must be at least 3 characters")
    if len(value) > 32:
        raise ValueError("Username must be at most 32 characters")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
    if any(ch not in allowed for ch in value):
        raise ValueError("Username may only contain letters, numbers, dot, underscore, and hyphen")
    return value


def _validate_password(password: str) -> str:
    value = str(password or "")
    if len(value) < 6:
        raise ValueError("Password must be at least 6 characters")
    if len(value) > 256:
        raise ValueError("Password is too long")
    return value


def hash_password(password: str) -> str:
    password = _validate_password(password)
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_b64, digest_b64 = str(stored_hash or "").split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _normalize_record(username: str, raw: Any, *, default_role: str = "user") -> Dict[str, Any]:
    now = _now_iso()
    if isinstance(raw, str):
        return {
            "username": username,
            "password_hash": "",
            "legacy_password": raw,
            "role": default_role,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
        }
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid record for user {username}")
    return {
        "username": username,
        "password_hash": str(raw.get("password_hash") or ""),
        "legacy_password": str(raw.get("legacy_password") or ""),
        "role": str(raw.get("role") or default_role),
        "enabled": bool(raw.get("enabled", True)),
        "created_at": str(raw.get("created_at") or now),
        "updated_at": str(raw.get("updated_at") or now),
    }


def load_user_records() -> Dict[str, Dict[str, Any]]:
    if not USERS_FILE.exists():
        return {}
    try:
        payload = yaml.safe_load(USERS_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    raw_users = payload.get("users", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw_users, dict):
        return {}

    records: Dict[str, Dict[str, Any]] = {}
    provisional_admin: str | None = None
    for idx, (username, raw) in enumerate(raw_users.items()):
        safe_username = _validate_username(username)
        default_role = "admin" if idx == 0 else "user"
        record = _normalize_record(safe_username, raw, default_role=default_role)
        if provisional_admin is None and record.get("role") == "admin":
            provisional_admin = safe_username
        records[safe_username] = record

    if records and provisional_admin is None:
        first_username = next(iter(records.keys()))
        records[first_username]["role"] = "admin"

    return records


def save_user_records(records: Dict[str, Dict[str, Any]]) -> None:
    ordered = {}
    for username in sorted(records.keys(), key=lambda item: item.lower()):
        record = records[username]
        ordered[username] = {
            "password_hash": str(record.get("password_hash") or ""),
            "role": str(record.get("role") or "user"),
            "enabled": bool(record.get("enabled", True)),
            "created_at": str(record.get("created_at") or _now_iso()),
            "updated_at": str(record.get("updated_at") or _now_iso()),
        }
    USERS_FILE.write_text(
        yaml.safe_dump({"users": ordered}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def ensure_default_accounts() -> Dict[str, Dict[str, Any]]:
    records = load_user_records()
    if not records:
        records = {
            "admin": {
                "username": "admin",
                "password_hash": hash_password("admin123"),
                "legacy_password": "",
                "role": "admin",
                "enabled": True,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        }
        save_user_records(records)
        return records

    changed = False
    admin_count = 0
    for username, record in records.items():
        if record.get("legacy_password"):
            record["password_hash"] = hash_password(record["legacy_password"])
            record["legacy_password"] = ""
            record["updated_at"] = _now_iso()
            changed = True
        if record.get("role") == "admin" and record.get("enabled", True):
            admin_count += 1

    if records and admin_count == 0:
        first_username = next(iter(records.keys()))
        records[first_username]["role"] = "admin"
        records[first_username]["updated_at"] = _now_iso()
        changed = True

    if changed:
        save_user_records(records)
    return records


def authenticate_user(username: str, password: str) -> Dict[str, Any] | None:
    records = ensure_default_accounts()
    safe_username = _validate_username(username)
    record = records.get(safe_username)
    if not record or not record.get("enabled", True):
        return None
    if verify_password(password, record.get("password_hash", "")):
        return public_user_record(record)
    return None


def public_user_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "username": str(record.get("username") or ""),
        "role": str(record.get("role") or "user"),
        "enabled": bool(record.get("enabled", True)),
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
    }


def list_users() -> List[Dict[str, Any]]:
    records = ensure_default_accounts()
    return [public_user_record(records[name]) for name in sorted(records.keys(), key=lambda item: item.lower())]


def register_user(username: str, password: str, *, role: str = "user") -> Dict[str, Any]:
    records = ensure_default_accounts()
    safe_username = _validate_username(username)
    if safe_username in records:
        raise ValueError("Username already exists")
    safe_role = "admin" if role == "admin" else "user"
    now = _now_iso()
    records[safe_username] = {
        "username": safe_username,
        "password_hash": hash_password(password),
        "legacy_password": "",
        "role": safe_role,
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    save_user_records(records)
    return public_user_record(records[safe_username])


def update_user(username: str, *, password: str | None = None, role: str | None = None, enabled: bool | None = None, actor_username: str | None = None) -> Dict[str, Any]:
    records = ensure_default_accounts()
    safe_username = _validate_username(username)
    if safe_username not in records:
        raise ValueError("User not found")
    record = records[safe_username]
    original_role = record.get("role")
    original_enabled = bool(record.get("enabled", True))

    if password is not None and password != "":
        record["password_hash"] = hash_password(password)

    if role is not None:
        record["role"] = "admin" if role == "admin" else "user"

    if enabled is not None:
        record["enabled"] = bool(enabled)

    enabled_admins = [
        item for item in records.values()
        if item.get("role") == "admin" and bool(item.get("enabled", True))
    ]
    if original_role == "admin" and original_enabled:
        becomes_non_admin = record.get("role") != "admin" or not bool(record.get("enabled", True))
        if becomes_non_admin and len(enabled_admins) <= 1:
            raise ValueError("Cannot remove or disable the last enabled admin")

    if actor_username and safe_username == actor_username and not bool(record.get("enabled", True)):
        raise ValueError("You cannot disable your own account")

    record["updated_at"] = _now_iso()
    save_user_records(records)
    return public_user_record(record)


def delete_user(username: str, *, actor_username: str | None = None) -> None:
    records = ensure_default_accounts()
    safe_username = _validate_username(username)
    if safe_username not in records:
        raise ValueError("User not found")
    if actor_username and safe_username == actor_username:
        raise ValueError("You cannot delete your own account")

    record = records[safe_username]
    enabled_admins = [
        item for item in records.values()
        if item.get("role") == "admin" and bool(item.get("enabled", True))
    ]
    if record.get("role") == "admin" and bool(record.get("enabled", True)) and len(enabled_admins) <= 1:
        raise ValueError("Cannot delete the last enabled admin")

    records.pop(safe_username)
    save_user_records(records)
