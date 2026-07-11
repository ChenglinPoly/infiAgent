#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
import sys
import unittest
from unittest import mock

from utils import windows_compat


class _DummyStream(io.StringIO):
    def __init__(self):
        super().__init__()
        self.reconfigure_calls = []

    def reconfigure(self, **kwargs):
        self.reconfigure_calls.append(kwargs)


class WindowsCompatTests(unittest.TestCase):
    def test_setup_console_encoding_prefers_reconfigure(self):
        stdout = _DummyStream()
        stderr = _DummyStream()
        with mock.patch.object(sys, "platform", "win32"):
            with mock.patch.object(sys, "stdout", stdout), mock.patch.object(sys, "stderr", stderr):
                windows_compat.setup_console_encoding()
        self.assertEqual(len(stdout.reconfigure_calls), 1)
        self.assertEqual(len(stderr.reconfigure_calls), 1)
        self.assertEqual(stdout.reconfigure_calls[0]["encoding"], "utf-8")
        self.assertEqual(stderr.reconfigure_calls[0]["encoding"], "utf-8")

    def test_safe_print_ignores_closed_file_on_windows(self):
        closed = io.StringIO()
        closed.close()
        with mock.patch.object(sys, "platform", "win32"):
            with mock.patch.object(sys, "stdout", closed), mock.patch.object(sys, "stderr", closed):
                windows_compat.safe_print("hello")


if __name__ == "__main__":
    unittest.main()
