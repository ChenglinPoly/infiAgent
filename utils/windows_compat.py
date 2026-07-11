#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows兼容性工具
确保emoji和中文字符能在Windows控制台正常显示
"""
import sys


def _reconfigure_stream(stream):
    """优先原位 reconfigure，避免重新包裹 stdout/stderr 导致解释器退出时报 closed file。"""
    if stream is None or getattr(stream, "closed", False):
        return
    try:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True, write_through=True)
    except Exception:
        # 某些 IDE/重定向流不支持 reconfigure；此时保持原状即可
        pass


def setup_console_encoding():
    """设置控制台为UTF-8编码（Windows专用），并启用实时输出"""
    if sys.platform == 'win32':
        try:
            _reconfigure_stream(sys.stdout)
            _reconfigure_stream(sys.stderr)
        except Exception:
            # 如果设置失败，不影响程序运行
            pass


def safe_print(*args, **kwargs):
    """
    安全的print函数，自动flush避免Windows缓冲区问题
    """
    if sys.platform == 'win32' and 'flush' not in kwargs:
        kwargs['flush'] = True
    try:
        print(*args, **kwargs)
    except ValueError as exc:
        # Windows 某些 IDE/关闭中的控制台在解释器收尾阶段会触发 closed file。
        if sys.platform == 'win32' and 'closed file' in str(exc).lower():
            return
        raise
    if sys.platform == 'win32':
        try:
            if getattr(sys.stdout, 'closed', False) is False:
                sys.stdout.flush()
            if getattr(sys.stderr, 'closed', False) is False:
                sys.stderr.flush()
        except Exception:
            pass


# 自动设置（导入时执行）
setup_console_encoding()
