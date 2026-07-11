#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经验存储并发安全测试（3.12.23）。

覆盖：多进程并发 append、混合并发操作后可解析、写入中断旧文件完整、
inactive 不注入、淘汰可观察、task/global/both 工具回归、旧格式向后兼容、
乐观并发检查、both 事务回滚、legacy 重复 ID 语义一致。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import utils.experience_store as es
from utils.experience_store import (
    AppendResult,
    ConcurrencyConflictError,
    ExperienceEntry,
    append_experience_entry,
    append_experience_many,
    delete_experience_entry,
    file_revision,
    list_experience_entries,
    parse_experience_entries,
    read_experience_file,
    replace_experience_entry,
    write_experience_entries,
)

BACKEND_DIR = str(Path(__file__).resolve().parent.parent)

# 子进程 worker：向指定文件追加 N 条经验（真实跨进程并发）
_WORKER_SRC = r"""
import sys
sys.path.insert(0, sys.argv[4])
from pathlib import Path
from utils.experience_store import append_experience_entry
path = Path(sys.argv[1]); n = int(sys.argv[2]); tag = sys.argv[3]
for i in range(n):
    append_experience_entry(path, "Task Experience: alpha_agent",
                            f"entry from {tag} #{i}", source=tag, max_tokens=10_000_000)
print("done")
"""

# 子进程 worker：混合操作（append + 对自己刚写的条目 replace/delete）
_MIXED_WORKER_SRC = r"""
import sys
sys.path.insert(0, sys.argv[3])
from pathlib import Path
from utils.experience_store import append_experience_entry, replace_experience_entry, delete_experience_entry
path = Path(sys.argv[1]); tag = sys.argv[2]
title = "Task Experience: alpha_agent"
ids = [append_experience_entry(path, title, f"{tag} c{i}", source=tag, max_tokens=10_000_000).entry.entry_id for i in range(4)]
replace_experience_entry(path, title, ids[0], f"{tag} replaced", source=tag)
delete_experience_entry(path, title, ids[1])
print("done")
"""


class ExperienceStoreConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "experience" / "alpha_agent.md"
        self.title = "Task Experience: alpha_agent"

    # ---------- 要求1：20 进程并发 append，条目完整且 ID 唯一 ----------

    def test_20_process_concurrent_append_no_loss_unique_ids(self):
        procs = []
        n_procs, per_proc = 20, 5
        for k in range(n_procs):
            procs.append(
                subprocess.Popen(
                    [sys.executable, "-c", _WORKER_SRC, str(self.path), str(per_proc), f"p{k}", BACKEND_DIR],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=BACKEND_DIR,
                )
            )
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode()[-500:])
        entries = parse_experience_entries(self.path)
        self.assertEqual(len(entries), n_procs * per_proc, "并发下发生条目丢失")
        ids = [e.entry_id for e in entries]
        self.assertEqual(len(ids), len(set(ids)), "entry_id 出现重复")
        # revision 单调推进到总写入次数
        self.assertEqual(file_revision(self.path), n_procs * per_proc)
        # 每个进程的每条都在
        contents = {e.content for e in entries}
        for k in range(n_procs):
            for i in range(per_proc):
                self.assertIn(f"entry from p{k} #{i}", contents)

    # ---------- 要求2：append/replace/delete 混合并发后文件可解析 ----------

    def test_concurrent_mixed_ops_file_stays_parseable(self):
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", _MIXED_WORKER_SRC, str(self.path), f"m{k}", BACKEND_DIR],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=BACKEND_DIR,
            )
            for k in range(10)
        ]
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode()[-500:])
        entries = parse_experience_entries(self.path)
        # 每进程 4 append -1 delete = 3 条存活
        self.assertEqual(len(entries), 10 * 3)
        for e in entries:
            self.assertTrue(e.entry_id.startswith("exp_"))
            self.assertTrue(e.content)
        # 每进程的 replace 生效
        replaced = [e for e in entries if e.content.endswith("replaced")]
        self.assertEqual(len(replaced), 10)

    # ---------- 要求3：写入中断，旧文件保持完整 ----------

    def test_interrupted_write_keeps_old_file_intact(self):
        append_experience_entry(self.path, self.title, "safe entry", source="t", max_tokens=999999)
        before_bytes = self.path.read_bytes()
        with mock.patch("utils.experience_store.os.replace", side_effect=OSError("simulated crash")):
            with self.assertRaises(OSError):
                append_experience_entry(self.path, self.title, "crash entry", source="t", max_tokens=999999)
        self.assertEqual(self.path.read_bytes(), before_bytes, "写入失败破坏了旧文件")
        # 临时文件已清理
        leftovers = [p for p in self.path.parent.iterdir() if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [])
        # 恢复后还能正常写
        result = append_experience_entry(self.path, self.title, "after recovery", source="t", max_tokens=999999)
        self.assertIsInstance(result, AppendResult)
        self.assertEqual(len(parse_experience_entries(self.path)), 2)

    # ---------- 要求5：淘汰可观察，返回被淘汰 ID；新条目不被淘汰 ----------

    def test_eviction_returns_evicted_ids_and_protects_new_entry(self):
        r1 = append_experience_entry(self.path, self.title, "A" * 400, source="t", max_tokens=999999)
        r2 = append_experience_entry(self.path, self.title, "B" * 400, source="t", max_tokens=999999)
        self.assertEqual(r1.evicted_ids, [])
        # 预算 120 token（≈480 字符）：容不下三条，最旧的两条被淘汰
        r3 = append_experience_entry(self.path, self.title, "C" * 400, source="t", max_tokens=120)
        self.assertEqual(set(r3.evicted_ids), {r1.entry.entry_id, r2.entry.entry_id})
        survivors = [e.entry_id for e in parse_experience_entries(self.path)]
        self.assertEqual(survivors, [r3.entry.entry_id])
        # 极端：预算小于新条目本身 → 新条目受保护、绝不淘汰自己
        r4 = append_experience_entry(self.path, self.title, "D" * 400, source="t", max_tokens=1)
        self.assertIn(r3.entry.entry_id, r4.evicted_ids)
        self.assertEqual([e.entry_id for e in parse_experience_entries(self.path)], [r4.entry.entry_id])
        # append 返回 revision
        self.assertEqual(r4.revision, file_revision(self.path))

    # ---------- 要求6 附：乐观并发检查 ----------

    def test_optimistic_concurrency_checks(self):
        r = append_experience_entry(self.path, self.title, "v1", source="t", max_tokens=999999)
        rev = file_revision(self.path)
        # 错误 revision → 冲突且文件未变
        with self.assertRaises(ConcurrencyConflictError):
            replace_experience_entry(self.path, self.title, r.entry.entry_id, "v2",
                                     source="t", expected_revision=rev + 99)
        self.assertEqual(parse_experience_entries(self.path)[0].content, "v1")
        # 正确 revision → 成功
        ok = replace_experience_entry(self.path, self.title, r.entry.entry_id, "v2",
                                      source="t", expected_revision=rev)
        self.assertTrue(ok)
        self.assertEqual(parse_experience_entries(self.path)[0].content, "v2")
        # expected_updated_at 不匹配 → 冲突
        with self.assertRaises(ConcurrencyConflictError):
            delete_experience_entry(self.path, self.title, r.entry.entry_id,
                                    expected_updated_at="1999-01-01T00:00:00")
        # 匹配 → 删除成功
        current = parse_experience_entries(self.path)[0].updated_at
        self.assertTrue(delete_experience_entry(self.path, self.title, r.entry.entry_id,
                                                expected_updated_at=current))
        self.assertEqual(parse_experience_entries(self.path), [])

    # ---------- 要求7：旧格式 Markdown 向后兼容 ----------

    def test_backward_compat_with_legacy_markdown(self):
        legacy = (
            "# Task Experience: alpha_agent\n\n"
            "## exp_20260601_120000_abcdef12\n"
            "- created_at: 2026-06-01T12:00:00\n"
            "- updated_at: 2026-06-01T12:00:00\n"
            "- source: agent\n"
            "- status: active\n"
            "\n"
            "旧格式经验内容一\n"
            "\n\n---\n\n"
            "## exp_20260601_120000_deadbeef\n"
            "- created_at: 2026-06-01T12:00:01\n"
            "- updated_at: 2026-06-01T12:00:01\n"
            "- source: user\n"
            "- status: inactive\n"
            "\n"
            "旧格式经验内容二\n"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(legacy, encoding="utf-8")
        # 无 revision 注释 → 0；条目完整解析
        revision, entries = read_experience_file(self.path)
        self.assertEqual(revision, 0)
        self.assertEqual([e.entry_id for e in entries],
                         ["exp_20260601_120000_abcdef12", "exp_20260601_120000_deadbeef"])
        self.assertEqual(entries[1].status, "inactive")
        # 在旧文件上 append：保留旧条目、加 revision 头
        r = append_experience_entry(self.path, self.title, "新条目", source="agent", max_tokens=999999)
        self.assertEqual(file_revision(self.path), 1)
        self.assertEqual(len(parse_experience_entries(self.path)), 3)
        # 对旧 ID replace/delete 正常
        self.assertTrue(replace_experience_entry(self.path, self.title,
                                                 "exp_20260601_120000_abcdef12", "改写", source="t"))
        self.assertTrue(delete_experience_entry(self.path, self.title, "exp_20260601_120000_deadbeef"))
        self.assertEqual(len(parse_experience_entries(self.path)), 2)

    # ---------- legacy 重复 ID：replace 与 delete 语义一致（都作用全部） ----------

    def test_duplicate_legacy_ids_replace_and_delete_consistent(self):
        dup = ExperienceEntry("exp_dup", "2026-01-01T00:00:00", "2026-01-01T00:00:00", "a", "active", "one")
        dup2 = ExperienceEntry("exp_dup", "2026-01-01T00:00:01", "2026-01-01T00:00:01", "a", "active", "two")
        write_experience_entries(self.path, self.title, [dup, dup2])
        self.assertTrue(replace_experience_entry(self.path, self.title, "exp_dup", "uniform", source="t"))
        contents = [e.content for e in parse_experience_entries(self.path)]
        self.assertEqual(contents, ["uniform", "uniform"], "replace 应作用于全部同 ID 条目")
        self.assertTrue(delete_experience_entry(self.path, self.title, "exp_dup"))
        self.assertEqual(parse_experience_entries(self.path), [])

    # ---------- scope=both 事务：第二个目标写失败回滚第一个 ----------

    def test_both_scope_transaction_rolls_back_on_second_failure(self):
        path_a = self.root / "a" / "alpha_agent.md"
        path_b = self.root / "b" / "alpha_agent.md"
        append_experience_many([(path_a, "A"), (path_b, "B")], "seed", source="t", max_tokens=999999)
        bytes_a, bytes_b = path_a.read_bytes(), path_b.read_bytes()

        real_write = es._atomic_write_text
        def failing_write(path, text):
            if Path(path) == path_b:
                raise OSError("simulated disk full on second target")
            return real_write(path, text)

        with mock.patch.object(es, "_atomic_write_text", side_effect=failing_write):
            with self.assertRaises(OSError):
                append_experience_many([(path_a, "A"), (path_b, "B")], "tx entry", source="t", max_tokens=999999)
        self.assertEqual(path_a.read_bytes(), bytes_a, "事务失败后第一个目标未回滚")
        self.assertEqual(path_b.read_bytes(), bytes_b)
        # 事务成功路径：两边同时出现
        results = append_experience_many([(path_a, "A"), (path_b, "B")], "ok entry", source="t", max_tokens=999999)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(parse_experience_entries(path_a)), 2)
        self.assertEqual(len(parse_experience_entries(path_b)), 2)


class WriteExperienceToolTests(unittest.TestCase):
    """要求6：task/global/both 操作路径 + inactive 不注入（要求4）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.task_dir = self.root / "tasks" / "t1"
        self.task_dir.mkdir(parents=True)
        # 固定 agent 上下文，避免依赖 hierarchy manager 的运行时状态
        patcher = mock.patch(
            "tool_server_lite.tools.experience_tools.resolve_runtime_agent_context",
            return_value={"agent_name": "alpha_agent", "agent_system": "demo_sys"},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        env_patcher = mock.patch.dict(os.environ, {"MLA_USER_DATA_ROOT": str(self.root)})
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

    def _tool(self):
        from tool_server_lite.tools.experience_tools import WriteExperienceTool
        return WriteExperienceTool()

    def test_task_global_both_regression(self):
        tool = self._tool()
        # both append：两个文件都出现，同时返回 revision 与 evicted
        r = tool.execute(str(self.task_dir), {"operation": "append", "scope": "both", "content": "共识经验"})
        self.assertEqual(r["status"], "success", r)
        self.assertEqual(len(r["results"]), 2)
        for item in r["results"]:
            self.assertEqual(item["status"], "appended")
            self.assertEqual(item["revision"], 1)
            self.assertEqual(item["evicted_ids"], [])
        entry_id = r["results"][0]["entry"]
        task_file = self.task_dir / "experience" / "alpha_agent.md"
        global_file = self.root / "knowledge" / "experience" / "demo_sys" / "alpha_agent.md"
        self.assertTrue(task_file.exists() and global_file.exists())

        # task list：含 revision
        r = tool.execute(str(self.task_dir), {"operation": "list", "scope": "task"})
        self.assertEqual(r["results"][0]["revision"], 1)
        self.assertEqual(len(r["results"][0]["entries"]), 1)

        # global replace（entry_id 在两个文件不同——both append 每个文件各自生成 ID）
        gid = tool.execute(str(self.task_dir), {"operation": "list", "scope": "global"})["results"][0]["entries"][0]["entry_id"]
        r = tool.execute(str(self.task_dir), {"operation": "replace", "scope": "global", "entry_id": gid, "content": "改写"})
        self.assertEqual(r["results"][0]["status"], "replaced")

        # expected_revision 冲突 → 明确报错
        r = tool.execute(str(self.task_dir), {"operation": "delete", "scope": "global", "entry_id": gid, "expected_revision": 99})
        self.assertEqual(r["status"], "error")
        self.assertIn("并发冲突", r["error"])
        # both + expected_revision → 拒绝（文件级检查不跨文件）
        r = tool.execute(str(self.task_dir), {"operation": "delete", "scope": "both", "entry_id": gid, "expected_revision": 2})
        self.assertEqual(r["status"], "error")

        # task delete 正常
        tid = tool.execute(str(self.task_dir), {"operation": "list", "scope": "task"})["results"][0]["entries"][0]["entry_id"]
        r = tool.execute(str(self.task_dir), {"operation": "delete", "scope": "task", "entry_id": tid})
        self.assertEqual(r["results"][0]["status"], "deleted")
        self.assertEqual(entry_id, entry_id)  # silence lint

    def test_inactive_entries_not_injected_into_context(self):
        # 要求4：inactive 条目不进 Agent 上下文
        from core.context_builder import ContextBuilder

        task_file = self.task_dir / "experience" / "alpha_agent.md"
        entries = [
            ExperienceEntry("exp_active", "2026-01-01T00:00:00", "2026-01-01T00:00:00", "a", "active", "ACTIVE_MARKER"),
            ExperienceEntry("exp_inactive", "2026-01-01T00:00:01", "2026-01-01T00:00:01", "a", "inactive", "INACTIVE_MARKER"),
        ]
        write_experience_entries(task_file, "Task Experience: alpha_agent", entries)

        class _DummyLoader:
            agent_system_name = "demo_sys"

        builder = ContextBuilder.__new__(ContextBuilder)  # 不跑重量级 __init__
        builder.config_loader = _DummyLoader()
        block = ContextBuilder._build_experience_blocks(builder, str(self.task_dir), "alpha_agent")
        self.assertIn("ACTIVE_MARKER", block)
        self.assertNotIn("INACTIVE_MARKER", block, "inactive 条目仍被注入上下文")
        # 全 inactive → 整块消失
        write_experience_entries(task_file, "Task Experience: alpha_agent", [entries[1]])
        block = ContextBuilder._build_experience_blocks(builder, str(self.task_dir), "alpha_agent")
        self.assertNotIn("INACTIVE_MARKER", block)
        self.assertNotIn("<任务经验>", block)

    def test_path_helpers_have_no_write_side_effect(self):
        # 修复清单8的补充验证：读路径不再创建文件
        from utils.experience_store import task_experience_path
        p = task_experience_path(str(self.task_dir), "alpha_agent")
        self.assertFalse(p.exists(), "路径解析不应创建文件")


if __name__ == "__main__":
    unittest.main()
