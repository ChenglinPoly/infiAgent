#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exec a command after applying a Landlock filesystem policy.

This module is intentionally dependency-free. It is used by execute_command in
Docker/Linux deployments to keep shell commands inside the current task while
still allowing read/execute access to host-installed tools and Python packages.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, Iterable


SYS_LANDLOCK_CREATE_RULESET = 444
SYS_LANDLOCK_ADD_RULE = 445
SYS_LANDLOCK_RESTRICT_SELF = 446

LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1

PR_SET_NO_NEW_PRIVS = 38

ACCESS_EXECUTE = 1 << 0
ACCESS_WRITE_FILE = 1 << 1
ACCESS_READ_FILE = 1 << 2
ACCESS_READ_DIR = 1 << 3
ACCESS_REMOVE_DIR = 1 << 4
ACCESS_REMOVE_FILE = 1 << 5
ACCESS_MAKE_CHAR = 1 << 6
ACCESS_MAKE_DIR = 1 << 7
ACCESS_MAKE_REG = 1 << 8
ACCESS_MAKE_SOCK = 1 << 9
ACCESS_MAKE_FIFO = 1 << 10
ACCESS_MAKE_BLOCK = 1 << 11
ACCESS_MAKE_SYM = 1 << 12
ACCESS_REFER = 1 << 13
ACCESS_TRUNCATE = 1 << 14

BASE_HANDLED = (
    ACCESS_EXECUTE
    | ACCESS_WRITE_FILE
    | ACCESS_READ_FILE
    | ACCESS_READ_DIR
    | ACCESS_REMOVE_DIR
    | ACCESS_REMOVE_FILE
    | ACCESS_MAKE_CHAR
    | ACCESS_MAKE_DIR
    | ACCESS_MAKE_REG
    | ACCESS_MAKE_SOCK
    | ACCESS_MAKE_FIFO
    | ACCESS_MAKE_BLOCK
    | ACCESS_MAKE_SYM
)
READ_ONLY = ACCESS_EXECUTE | ACCESS_READ_FILE | ACCESS_READ_DIR


class LandlockRulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class LandlockPathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int),
    ]


def _errno_error(message: str) -> OSError:
    code = ctypes.get_errno()
    return OSError(code, f"{message}: {os.strerror(code)}")


def _syscall(libc, number: int, *args):
    result = libc.syscall(number, *args)
    if result == -1:
        raise _errno_error(f"syscall {number} failed")
    return result


def _landlock_abi(libc) -> int:
    try:
        return int(_syscall(libc, SYS_LANDLOCK_CREATE_RULESET, 0, 0, LANDLOCK_CREATE_RULESET_VERSION))
    except OSError as exc:
        if exc.errno in {errno.ENOSYS, errno.EOPNOTSUPP, errno.EINVAL, errno.EPERM}:
            return 0
        raise


def _handled_access_for_abi(abi: int) -> int:
    handled = BASE_HANDLED
    if abi >= 2:
        handled |= ACCESS_REFER
    if abi >= 3:
        handled |= ACCESS_TRUNCATE
    return handled


def _path_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Iterable):
        return [str(item) for item in value if str(item).strip()]
    return []


def _add_path_rule(libc, ruleset_fd: int, path: str, access: int, handled: int) -> None:
    resolved = Path(path).expanduser().resolve(strict=False)
    if not resolved.exists():
        return
    flags = getattr(os, "O_PATH", 0) | getattr(os, "O_CLOEXEC", 0)
    parent_fd = os.open(str(resolved), flags)
    try:
        attr = LandlockPathBeneathAttr(access & handled, parent_fd)
        _syscall(
            libc,
            SYS_LANDLOCK_ADD_RULE,
            ruleset_fd,
            LANDLOCK_RULE_PATH_BENEATH,
            ctypes.byref(attr),
            0,
        )
    finally:
        os.close(parent_fd)


def apply_landlock(rules: Dict[str, Any]) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    libc.prctl.restype = ctypes.c_int
    abi = _landlock_abi(libc)
    if abi <= 0:
        raise RuntimeError("Landlock is not available in this kernel/container")

    handled = _handled_access_for_abi(abi)
    ruleset_attr = LandlockRulesetAttr(handled)
    ruleset_fd = _syscall(
        libc,
        SYS_LANDLOCK_CREATE_RULESET,
        ctypes.byref(ruleset_attr),
        ctypes.sizeof(ruleset_attr),
        0,
    )
    try:
        rw_access = handled
        ro_access = READ_ONLY & handled
        for path in _path_list(rules.get("read_only")):
            _add_path_rule(libc, ruleset_fd, path, ro_access, handled)
        for path in _path_list(rules.get("read_write")):
            _add_path_rule(libc, ruleset_fd, path, rw_access, handled)

        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            raise _errno_error("prctl(PR_SET_NO_NEW_PRIVS) failed")
        _syscall(libc, SYS_LANDLOCK_RESTRICT_SELF, ruleset_fd, 0)
    finally:
        os.close(ruleset_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply Landlock policy and exec command")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("landlock_exec: missing command", file=sys.stderr)
        return 2

    raw_rules = os.environ.get("MLA_LANDLOCK_RULES_JSON", "{}")
    try:
        rules = json.loads(raw_rules)
        if not isinstance(rules, dict):
            rules = {}
    except Exception as exc:
        print(f"landlock_exec: invalid MLA_LANDLOCK_RULES_JSON: {exc}", file=sys.stderr)
        return 2

    fail_closed = str(os.environ.get("MLA_SANDBOX_FAIL_CLOSED") or "1").strip().lower() in {"1", "true", "yes", "on"}
    try:
        apply_landlock(rules)
    except Exception as exc:
        if fail_closed:
            print(f"landlock_exec: failed to apply Landlock policy: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 126
        print(f"landlock_exec: warning: Landlock disabled: {type(exc).__name__}: {exc}", file=sys.stderr)

    os.chdir(args.cwd)
    os.execvp(command[0], command)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
