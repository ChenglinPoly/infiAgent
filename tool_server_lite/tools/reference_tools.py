#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参考文献管理工具 - 安全维护 reference.bib 文件
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional

from .file_tools import BaseTool, get_abs_path


_ENTRY_HEADER_RE = re.compile(r"^\s*@(?P<type>\w+)\s*[\{\(]\s*(?P<key>[^,\s]+)\s*,", re.DOTALL)


@dataclass
class BibEntry:
    entry_type: str
    key: str
    content: str
    start: int
    end: int


def _extract_entry_header(entry_text: str) -> Optional[tuple[str, str]]:
    match = _ENTRY_HEADER_RE.match(entry_text or "")
    if not match:
        return None
    return match.group("type").strip(), match.group("key").strip()


def _scan_bib_entries(content: str) -> List[BibEntry]:
    """
    以 brace-aware 方式扫描 BibTeX 条目，尽量保留原文本和原顺序。
    支持 @type{...} 和 @type(...) 两种外层形式。
    """
    if not content:
        return []

    entries: List[BibEntry] = []
    length = len(content)
    i = 0

    while i < length:
        at_idx = content.find("@", i)
        if at_idx < 0:
            break

        j = at_idx + 1
        while j < length and (content[j].isalnum() or content[j] in {"_", "-"}):
            j += 1
        entry_type = content[at_idx + 1:j].strip()
        if not entry_type:
            i = at_idx + 1
            continue

        while j < length and content[j].isspace():
            j += 1
        if j >= length or content[j] not in "{(":
            i = at_idx + 1
            continue

        opener = content[j]
        closer = "}" if opener == "{" else ")"
        depth = 1
        k = j + 1

        while k < length and depth > 0:
            ch = content[k]
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
            k += 1

        if depth != 0:
            # 不完整条目：停止扫描，避免误删后续内容
            break

        entry_text = content[at_idx:k]
        header = _extract_entry_header(entry_text)
        if header is None:
            i = k
            continue

        parsed_type, key = header
        entries.append(BibEntry(entry_type=parsed_type, key=key, content=entry_text, start=at_idx, end=k))
        i = k

    return entries


def _normalize_entries_input(entries: Any) -> List[str]:
    if entries is None:
        return []
    if isinstance(entries, str):
        entries = [entries]
    if not isinstance(entries, list):
        raise ValueError("entries 必须是字符串或字符串数组")
    normalized = []
    for entry in entries:
        text = str(entry or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_bib_text(path: Path, content: str) -> None:
    _ensure_parent(path)
    normalized = content
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    path.write_text(normalized, encoding="utf-8")


def _format_append_block(existing_text: str, new_entries: List[str]) -> str:
    suffix = "\n\n".join(new_entries)
    if not existing_text.strip():
        return suffix
    base = existing_text.rstrip()
    return f"{base}\n\n{suffix}"


class ReferenceListTool(BaseTool):
    """列出 reference.bib 的原文或结构化摘要。"""

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            bib_path = parameters.get("bib_path", "reference.bib")
            output_mode = str(parameters.get("output_mode") or "raw").strip().lower()
            abs_bib_path = get_abs_path(task_id, bib_path)

            if not abs_bib_path.exists():
                return {
                    "status": "error",
                    "output": "",
                    "error": f"文件不存在: {bib_path}"
                }

            content = abs_bib_path.read_text(encoding="utf-8")
            if not content.strip():
                if output_mode == "raw":
                    return {"status": "success", "output": "(文件为空)", "error": ""}
                return {
                    "status": "success",
                    "output": json.dumps({"count": 0, "entries": []}, ensure_ascii=False, indent=2),
                    "error": "",
                }

            if output_mode == "raw":
                return {"status": "success", "output": content, "error": ""}

            entries = _scan_bib_entries(content)
            summary = {
                "count": len(entries),
                "entries": [
                    {"key": item.key, "type": item.entry_type, "start": item.start, "end": item.end}
                    for item in entries
                ],
            }
            return {
                "status": "success",
                "output": json.dumps(summary, ensure_ascii=False, indent=2),
                "error": "",
            }

        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": f"读取失败: {str(e)}"
            }


class ReferenceAddTool(BaseTool):
    """按 citekey upsert 参考文献。"""

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            entries_input = _normalize_entries_input(parameters.get("entries", []))
            bib_path = parameters.get("bib_path", "reference.bib")
            abs_bib_path = get_abs_path(task_id, bib_path)

            if not entries_input:
                return {"status": "error", "output": "", "error": "缺少必需参数: entries"}

            replacements: Dict[str, BibEntry] = {}
            ordered_new_keys: List[str] = []
            for entry_text in entries_input:
                header = _extract_entry_header(entry_text)
                if header is None:
                    return {"status": "error", "output": "", "error": f"无效的 BibTeX 条目头部: {entry_text[:80]}"}
                entry_type, key = header
                replacements[key] = BibEntry(entry_type=entry_type, key=key, content=entry_text, start=0, end=0)
                if key not in ordered_new_keys:
                    ordered_new_keys.append(key)

            existing_text = abs_bib_path.read_text(encoding="utf-8") if abs_bib_path.exists() else ""
            existing_entries = _scan_bib_entries(existing_text)

            rebuilt_parts: List[str] = []
            cursor = 0
            updated_keys: List[str] = []
            preserved_keys: set[str] = set()

            for entry in existing_entries:
                rebuilt_parts.append(existing_text[cursor:entry.start])
                cursor = entry.end

                if entry.key in replacements:
                    if entry.key not in preserved_keys:
                        rebuilt_parts.append(replacements[entry.key].content)
                        updated_keys.append(entry.key)
                        preserved_keys.add(entry.key)
                    # 跳过重复旧 key，完成去重
                    continue

                rebuilt_parts.append(entry.content)

            rebuilt_parts.append(existing_text[cursor:])
            new_text = "".join(rebuilt_parts).rstrip()

            appended_keys = [key for key in ordered_new_keys if key not in preserved_keys]
            if appended_keys:
                new_entries = [replacements[key].content for key in appended_keys]
                new_text = _format_append_block(new_text, new_entries)

            _write_bib_text(abs_bib_path, new_text)

            result_lines = []
            if updated_keys:
                result_lines.append(f"已更新 {len(updated_keys)} 条参考文献: {', '.join(updated_keys)}")
            if appended_keys:
                result_lines.append(f"已新增 {len(appended_keys)} 条参考文献: {', '.join(appended_keys)}")
            if not result_lines:
                result_lines.append("没有有效变更。")

            return {"status": "success", "output": "\n".join(result_lines), "error": ""}

        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": f"添加失败: {str(e)}"
            }


class ReferenceDeleteTool(BaseTool):
    """按 citekey 精确删除参考文献。"""

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            keys = parameters.get("keys", [])
            bib_path = parameters.get("bib_path", "reference.bib")

            if not keys:
                return {"status": "error", "output": "", "error": "缺少必需参数: keys"}
            if isinstance(keys, str):
                keys = [keys]
            if not isinstance(keys, list):
                return {"status": "error", "output": "", "error": "keys 必须是字符串或字符串数组"}
            delete_keys = [str(key).strip() for key in keys if str(key).strip()]
            if not delete_keys:
                return {"status": "error", "output": "", "error": "没有有效的 keys"}

            abs_bib_path = get_abs_path(task_id, bib_path)
            if not abs_bib_path.exists():
                return {"status": "error", "output": "", "error": f"文件不存在: {bib_path}"}

            content = abs_bib_path.read_text(encoding="utf-8")
            entries = _scan_bib_entries(content)
            if not entries:
                return {"status": "error", "output": "", "error": "未解析到任何 BibTeX 条目"}

            rebuilt_parts: List[str] = []
            cursor = 0
            deleted_keys: List[str] = []

            for entry in entries:
                rebuilt_parts.append(content[cursor:entry.start])
                cursor = entry.end
                if entry.key in delete_keys:
                    deleted_keys.append(entry.key)
                    continue
                rebuilt_parts.append(entry.content)

            rebuilt_parts.append(content[cursor:])

            if not deleted_keys:
                return {
                    "status": "error",
                    "output": "",
                    "error": f"未找到要删除的文献: {', '.join(delete_keys)}"
                }

            new_text = "".join(rebuilt_parts).strip()
            _write_bib_text(abs_bib_path, new_text)

            not_found_keys = [key for key in delete_keys if key not in deleted_keys]
            remaining_count = len(_scan_bib_entries(abs_bib_path.read_text(encoding="utf-8")))
            result_parts = [f"成功删除 {len(deleted_keys)} 条参考文献: {', '.join(deleted_keys)}"]
            if not_found_keys:
                result_parts.append(f"未找到: {', '.join(not_found_keys)}")
            result_parts.append(f"剩余 {remaining_count} 条参考文献")

            return {"status": "success", "output": "\n".join(result_parts), "error": ""}

        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": f"删除失败: {str(e)}"
            }
