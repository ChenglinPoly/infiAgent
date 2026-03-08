#!/usr/bin/env python3
from utils.windows_compat import safe_print
# -*- coding: utf-8 -*-
"""
层级管理器 - 管理Agent调用层级和共享上下文
简化版本，去除冗余功能，保留核心逻辑
"""

import os
import json
import threading
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path


class HierarchyManager:
    """Agent层级管理器"""
    
    def __init__(self, task_id: str):
        """
        初始化层级管理器
        
        Args:
            task_id: 任务ID
        """
        self.task_id = task_id
        self.lock = threading.Lock()
        
        # 文件路径 - 使用用户主目录（跨平台）
        conversations_dir = Path.home() / "mla_v3" / "conversations"
        conversations_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名：hash + 最后文件夹名
        import hashlib
        task_hash = hashlib.md5(task_id.encode()).hexdigest()[:8]
        # 跨平台路径处理：检查是否是路径（包含/或\）
        task_folder = Path(task_id).name if (os.sep in task_id or '/' in task_id or '\\' in task_id) else task_id
        task_name = f"{task_hash}_{task_folder}"
        
        self.stack_file = conversations_dir / f'{task_name}_stack.json'
        self.context_file = conversations_dir / f'{task_name}_share_context.json'
        
        # 初始化文件
        self._initialize_files()
    
    def _initialize_files(self):
        """初始化栈文件和共享上下文文件"""
        # 初始化栈文件
        if not self.stack_file.exists():
            with open(self.stack_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "stack": [],
                    "created_at": datetime.now().isoformat()
                }, f, indent=2, ensure_ascii=False)
        
        # 初始化共享上下文文件
        if not self.context_file.exists():
            with open(self.context_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "task_id": self.task_id,
                    "current": {
                        "instructions": [],
                        "hierarchy": {},
                        "agents_status": {},
                        "start_time": datetime.now().isoformat(),
                        "last_updated": datetime.now().isoformat()
                    },
                    "agent_time_history": {},
                    "history": [],
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2, ensure_ascii=False)
    
    def _load_stack(self) -> List[Dict]:
        """加载当前栈状态"""
        try:
            with open(self.stack_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("stack", [])
        except Exception as e:
            safe_print(f"⚠️ 加载栈文件失败: {e}")
            return []
    
    def _save_stack(self, stack: List[Dict]):
        """保存栈状态"""
        try:
            with open(self.stack_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "stack": stack,
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            safe_print(f"⚠️ 保存栈文件失败: {e}")
    
    def _load_context(self) -> Dict:
        """加载共享上下文"""
        try:
            with open(self.context_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            safe_print(f"⚠️ 加载共享上下文失败: {e}")
            return {
                "task_id": self.task_id,
                "current": {
                    "instructions": [],
                    "hierarchy": {},
                    "agents_status": {}
                },
                "agent_time_history": {},
                "history": []
            }
    
    def _save_context(self, context: Dict):
        """保存共享上下文"""
        try:
            context["last_updated"] = datetime.now().isoformat()
            with open(self.context_file, 'w', encoding='utf-8') as f:
                json.dump(context, f, indent=2, ensure_ascii=False)
        except Exception as e:
            safe_print(f"⚠️ 保存共享上下文失败: {e}")
    
    def start_new_instruction(self, instruction: str) -> str:
        """
        开始一个新的指令
        
        Args:
            instruction: 新的指令内容
            
        Returns:
            指令ID
        """
        with self.lock:
            import hashlib
            context = self._load_context()
            
            # ✅ 检查是否已存在相同指令（避免重复）
            existing_instructions = context["current"].get("instructions", [])
            for existing in existing_instructions:
                if existing.get("instruction") == instruction:
                    safe_print(f"ℹ️ 指令已存在，跳过添加: {instruction[:50]}...")
                    return existing.get("instruction_id", "")
            
            # 生成指令ID
            content_for_hash = f"{self.task_id}|{instruction}"
            hash_object = hashlib.md5(content_for_hash.encode())
            instruction_hash = hash_object.hexdigest()[:12]
            instruction_id = f"instruction_{instruction_hash}"
            
            # 添加到current指令列表
            instruction_entry = {
                "instruction": instruction,
                "instruction_id": instruction_id,
                "start_time": datetime.now().isoformat()
            }
            
            context["current"]["instructions"].append(instruction_entry)
            self._save_context(context)
            
            safe_print(f"📝 新指令已添加: {instruction_id} -> {instruction[:50]}...")
            
            return instruction_id
    
    def push_agent(self, agent_name: str, user_input: str) -> str:
        """
        Agent入栈操作
        
        Args:
            agent_name: Agent名称
            user_input: 用户输入
            
        Returns:
            生成的agent_id
        """
        with self.lock:
            import hashlib
            
            # 生成agent_id
            content_for_hash = f"{agent_name}|{self.task_id}|{user_input}"
            hash_object = hashlib.md5(content_for_hash.encode())
            agent_hash = hash_object.hexdigest()[:12]
            agent_id = f"{agent_name}_{agent_hash}"
            
            # 加载当前状态
            stack = self._load_stack()
            context = self._load_context()
            
            # 获取父Agent（栈顶）
            parent_id = None
            level = 0
            if stack:
                parent_id = stack[-1]["agent_id"]
                level = stack[-1]["level"] + 1
            
            # 创建Agent栈条目
            agent_entry = {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "parent_id": parent_id,
                "level": level,
                "user_input": user_input,
                "start_time": datetime.now().isoformat()
            }
            
            # 入栈
            stack.append(agent_entry)
            self._save_stack(stack)
            
            # 更新共享上下文
            if agent_id not in context["current"]["hierarchy"]:
                context["current"]["hierarchy"][agent_id] = {
                    "parent": parent_id,
                    "children": [],
                    "level": level
                }
            
            # 如果有父Agent，将当前Agent添加到父Agent的children列表
            if parent_id and parent_id in context["current"]["hierarchy"]:
                if agent_id not in context["current"]["hierarchy"][parent_id]["children"]:
                    context["current"]["hierarchy"][parent_id]["children"].append(agent_id)
            
            # 更新Agent状态（不保存action_history，它保存在单独文件中）
            context["current"]["agents_status"][agent_id] = {
                "agent_name": agent_name,
                "status": "running",
                "initial_input": user_input,
                "start_time": datetime.now().isoformat(),
                "parent_id": parent_id,
                "level": level,
                "latest_thinking": "",  # 只保留最新的thinking
                "loaded_skills": []     # 当前上下文中已注入的 skills
            }
            
            # 记录时间历史
            if "agent_time_history" not in context:
                context["agent_time_history"] = {}
            context["agent_time_history"][agent_id] = {
                "start_time": datetime.now().isoformat(),
                "end_time": None
            }
            
            self._save_context(context)
            
            safe_print(f"📚 Agent入栈: {agent_name} (ID: {agent_id}, Level: {level})")
            
            return agent_id
    
    def pop_agent(self, agent_id: str, final_output: str = ""):
        """
        Agent出栈操作
        
        Args:
            agent_id: Agent ID
            final_output: 最终输出内容
        """
        with self.lock:
            stack = self._load_stack()
            
            # 从栈中移除
            new_stack = [entry for entry in stack if entry["agent_id"] != agent_id]
            self._save_stack(new_stack)
            
            # 更新共享上下文中的Agent状态
            context = self._load_context()
            if agent_id in context["current"]["agents_status"]:
                end_time = datetime.now().isoformat()
                context["current"]["agents_status"][agent_id]["status"] = "completed"
                context["current"]["agents_status"][agent_id]["final_output"] = final_output
                context["current"]["agents_status"][agent_id]["end_time"] = end_time
                
                # 删除latest_thinking（已完成的agent不需要thinking，只保留final_output）
                if "latest_thinking" in context["current"]["agents_status"][agent_id]:
                    del context["current"]["agents_status"][agent_id]["latest_thinking"]
                
                # 更新时间历史
                if agent_id in context.get("agent_time_history", {}):
                    context["agent_time_history"][agent_id]["end_time"] = end_time
            
            self._save_context(context)
            
            # 检查是否当前栈已清空（无可 resume 的运行中 agent），若是则归档 current 到 history
            self._check_and_complete_if_all_done()
            
            safe_print(f"📚 Agent出栈: {agent_id}")
    
    def update_thinking(self, agent_id: str, thinking: str):
        """
        更新Agent的thinking（只保留最新的）
        
        Args:
            agent_id: Agent ID
            thinking: thinking内容
        """
        with self.lock:
            context = self._load_context()
            
            if agent_id in context["current"]["agents_status"]:
                context["current"]["agents_status"][agent_id]["latest_thinking"] = thinking
                context["current"]["agents_status"][agent_id]["thinking_updated_at"] = datetime.now().isoformat()
                self._save_context(context)

    def get_loaded_skills(self, agent_id: str) -> List[Dict]:
        """获取当前 agent 已加载到上下文中的 skills。"""
        context = self._load_context()
        agent_info = context.get("current", {}).get("agents_status", {}).get(agent_id, {})
        skills = agent_info.get("loaded_skills", [])
        return skills if isinstance(skills, list) else []

    def add_loaded_skill(self, agent_id: str, skill_info: Dict):
        """向当前 agent 的上下文挂载一个 skill。"""
        with self.lock:
            context = self._load_context()
            agent_info = context.get("current", {}).get("agents_status", {}).get(agent_id)
            if not agent_info:
                return
            loaded = agent_info.get("loaded_skills", [])
            if not isinstance(loaded, list):
                loaded = []
            skill_name = skill_info.get("name")
            loaded = [s for s in loaded if s.get("name") != skill_name]
            loaded.append(skill_info)
            agent_info["loaded_skills"] = loaded
            self._save_context(context)

    def remove_loaded_skill(self, agent_id: str, skill_name: str):
        """从当前 agent 的上下文卸载一个 skill。"""
        with self.lock:
            context = self._load_context()
            agent_info = context.get("current", {}).get("agents_status", {}).get(agent_id)
            if not agent_info:
                return
            loaded = agent_info.get("loaded_skills", [])
            if not isinstance(loaded, list):
                loaded = []
            agent_info["loaded_skills"] = [s for s in loaded if s.get("name") != skill_name]
            self._save_context(context)
    
    def add_action(self, agent_id: str, action: Dict):
        """
        添加动作记录（仅用于兼容，实际action_history保存在单独文件中）
        
        Args:
            agent_id: Agent ID
            action: 动作记录
        """
        # 不再在share_context中保存action_history
        # action_history由ConversationStorage管理
        pass
    
    def get_context(self) -> Dict:
        """获取完整的共享上下文"""
        return self._load_context()
    
    def _check_and_complete_if_all_done(self):
        """
        检查是否应将 current 归档到 history。
        
        关键逻辑：**以 stack 是否为空为准**（而不是 agents_status 是否都为 completed / 终态）。
        
        原因：
        - 用户可能会人为中断/暂停任务（例如 Ctrl+C、需求变更），导致某些 agent 状态仍停留在 running，
          但 stack 已被清空（不可 resume / 实际已无运行中的 agent）。
        - 如果仍按 agents_status 判断，会出现 current 永远无法归档到 history 的问题。
        """
        context = self._load_context()
        current_agents = context.get("current", {}).get("agents_status", {})
        
        # 栈非空：说明仍存在运行链路，不能归档
        stack = self._load_stack()
        if stack:
            return
        
        # 栈为空：仅当 current 有实际内容时才归档（避免空归档）
        current_instructions = context.get("current", {}).get("instructions", [])
        if not current_agents and not current_instructions:
            return
        
        safe_print("🎉 当前栈已清空，移动current到history")
        
        # 移动到history
        history_entry = {
            "instructions": context["current"]["instructions"].copy(),
            "hierarchy": context["current"]["hierarchy"].copy(),
            "agents_status": context["current"]["agents_status"].copy(),
            "start_time": context["current"].get("start_time"),
            "completion_time": datetime.now().isoformat()
        }
        
        context["history"].append(history_entry)
        
        # 清空current
        context["current"] = {
            "instructions": [],
            "hierarchy": {},
            "agents_status": {},
            "start_time": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
        
        # 清空栈（保持幂等）
        self._save_stack([])
        
        self._save_context(context)
        safe_print("✅ 任务已归档到history")
    
    def get_current_agent_id(self) -> Optional[str]:
        """获取当前栈顶的Agent ID"""
        stack = self._load_stack()
        return stack[-1]["agent_id"] if stack else None


# 全局管理器缓存
_managers_cache = {}
_cache_lock = threading.Lock()


def get_hierarchy_manager(task_id: str) -> HierarchyManager:
    """
    获取缓存的层级管理器实例
    
    Args:
        task_id: 任务ID
        
    Returns:
        HierarchyManager实例
    """
    with _cache_lock:
        if task_id not in _managers_cache:
            _managers_cache[task_id] = HierarchyManager(task_id)
        return _managers_cache[task_id]


if __name__ == "__main__":
    # 测试层级管理器
    manager = HierarchyManager("test_task")
    safe_print("✅ 层级管理器初始化成功")
    
    # 测试指令添加
    instr_id = manager.start_new_instruction("测试任务")
    safe_print(f"✅ 添加指令: {instr_id}")
    
    # 测试Agent入栈
    agent1_id = manager.push_agent("test_agent", "测试输入")
    safe_print(f"✅ Agent入栈: {agent1_id}")
    
    # 测试thinking更新
    manager.update_thinking(agent1_id, "这是一个测试thinking")
    safe_print("✅ Thinking更新成功")
    
    # 测试动作添加
    manager.add_action(agent1_id, {
        "tool_name": "file_read",
        "arguments": {"path": "test.txt"},
        "result": {"status": "success"}
    })
    safe_print("✅ 动作记录成功")

