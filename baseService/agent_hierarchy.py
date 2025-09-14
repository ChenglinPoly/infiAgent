import os
import json
import threading
from typing import Dict, List, Optional, Any
from datetime import datetime

# 获取项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# API导入 - Agent层级管理和长期记忆模块


class AgentHierarchyManager:
    """
    Agent层级管理器，负责维护agent调用栈和共享上下文
    """
    
    def __init__(self, task_id: str):
        """
        初始化层级管理器
        
        Args:
            task_id (str): 任务ID
        """
        self.task_id = task_id
        self.lock = threading.Lock()  # 线程安全锁
        
        # 文件路径
        self.stack_file = os.path.join(project_root, 'conversations', f'{task_id}_stack.json')
        self.context_file = os.path.join(project_root, 'conversations', f'{task_id}_share_context.json')
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.stack_file), exist_ok=True)
        
        # 初始化文件
        self._initialize_files()
    
    def _initialize_files(self):
        """初始化栈文件和共享上下文文件"""
        # 初始化栈文件
        if not os.path.exists(self.stack_file):
            with open(self.stack_file, 'w', encoding='utf-8') as f:
                json.dump({"stack": [], "created_at": datetime.now().isoformat()}, f, indent=2, ensure_ascii=False)
        
        # 初始化共享上下文文件
        if not os.path.exists(self.context_file):
            with open(self.context_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "task_id": self.task_id,
                    "current": {
                        "instructions": [],  # 当前运行的指令列表 [{"instruction": str, "start_time": str, "instruction_id": str}]
                        "hierarchy": {},  # agent_id -> {"parent": parent_id, "children": [child_ids], "level": int}
                        "agents_status": {},  # agent_id -> {"status": "waiting/completed", "progress": str, "initial_input": str, "start_time": str, "end_time": str}
                        "start_time": datetime.now().isoformat(),
                        "last_updated": datetime.now().isoformat()
                    },
                    "agent_time_history": {},  # 保存Agent的历史时间信息 agent_id -> {"start_time": str, "end_time": str}
                    "history": [],  # 已完成任务的历史记录 [{"instructions": [], "hierarchy": {}, "agents_status": {}, "completion_time": str}]
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
            print(f"⚠️ 加载栈文件失败: {e}")
            return []
    
    def _save_stack(self, stack: List[Dict]):
        """保存栈状态"""
        try:
            data = {
                "stack": stack,
                "created_at": datetime.now().isoformat() if not os.path.exists(self.stack_file) else self._get_creation_time(),
                "last_updated": datetime.now().isoformat()
            }
            with open(self.stack_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ 保存栈文件失败: {e}")
    
    def _load_context(self) -> Dict:
        """加载共享上下文"""
        try:
            with open(self.context_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载共享上下文失败: {e}")
            return {
                "task_id": self.task_id,
                "hierarchy": {},
                "agents_status": {},
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
    
    def _save_context(self, context: Dict):
        """保存共享上下文"""
        try:
            context["last_updated"] = datetime.now().isoformat()
            with open(self.context_file, 'w', encoding='utf-8') as f:
                json.dump(context, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ 保存共享上下文失败: {e}")
    
    def _get_creation_time(self) -> str:
        """获取文件创建时间"""
        try:
            with open(self.stack_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("created_at", datetime.now().isoformat())
        except:
            return datetime.now().isoformat()
    
    def start_new_instruction(self, instruction: str) -> str:
        """
        开始一个新的指令（从start.py调用）
        
        Args:
            instruction (str): 新的指令内容
            
        Returns:
            str: 指令ID
        """
        with self.lock:
            context = self._load_context()
            
            # 检查是否已存在相同指令
            existing_instructions = context["current"].get("instructions", [])
            for existing in existing_instructions:
                if existing.get("instruction") == instruction:
                    print(f"ℹ️ 指令已存在，跳过添加: {instruction[:50]}...")
                    return existing.get("instruction_id", "")
            
            # 生成基于内容的指令ID
            import hashlib
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
            context["current"]["last_updated"] = datetime.now().isoformat()
            
            self._save_context(context)
            
            print(f"📝 新指令已添加: {instruction_id} -> {instruction[:50]}...")
            
            return instruction_id
    
    def complete_current_task(self):
        """
        完成当前任务，将current内容移动到history
        """
        with self.lock:
            context = self._load_context()
            
            if not context["current"]["instructions"]:
                print("ℹ️ 当前没有正在进行的任务")
                return
            
            # 将current内容添加到history
            history_entry = {
                "instructions": context["current"]["instructions"].copy(),
                "hierarchy": context["current"]["hierarchy"].copy(),
                "agents_status": context["current"]["agents_status"].copy(),
                "start_time": context["current"]["start_time"],
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
            
            context["last_updated"] = datetime.now().isoformat()
            self._save_context(context)
            
            print(f"✅ 当前任务已完成，状态已移动到历史记录")
    
    def clear_current_task(self):
        """
        清空当前任务（用于中途暂停或重新开始）
        """
        with self.lock:
            context = self._load_context()
            
            # 清空current但不移动到history
            context["current"] = {
                "instructions": [],
                "hierarchy": {},
                "agents_status": {},
                "start_time": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
            
            context["last_updated"] = datetime.now().isoformat()
            self._save_context(context)
            
            print(f"🔄 当前任务已清空，可以开始新任务")
    
    def check_and_complete_task_if_needed(self):
        """
        检查是否所有Agent都已完成，如果是则自动完成任务
        注意：此方法假设调用者已经持有锁
        """
        # 不再获取锁，假设调用者已经持有锁
        context = self._load_context()
        current_agents = context.get("current", {}).get("agents_status", {})
        
        if not current_agents:
            return False
        
        # 检查是否所有Agent都已完成
        all_completed = all(
            agent_status.get("status") == "completed" 
            for agent_status in current_agents.values()
        )
        
        if all_completed:
            print("🎉 检测到所有Agent已完成，自动完成当前任务")
            self._complete_current_task_internal()  # 使用内部方法，不重新获取锁
            
            # 清空栈
            self._save_stack([])
            print("🗑️ 所有任务完成，栈已清空")
            
            return True
        
        return False
    
    def _complete_current_task_internal(self):
        """
        完成当前任务的内部方法（不获取锁）
        """
        context = self._load_context()
        
        if not context["current"]["instructions"]:
            print("ℹ️ 当前没有正在进行的任务")
            return
        
        # 将current内容添加到history
        history_entry = {
            "instructions": context["current"]["instructions"].copy(),
            "hierarchy": context["current"]["hierarchy"].copy(),
            "agents_status": context["current"]["agents_status"].copy(),
            "start_time": context["current"]["start_time"],
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
        
        context["last_updated"] = datetime.now().isoformat()
        self._save_context(context)
        
        print(f"✅ 当前任务已完成，状态已移动到历史记录")
    
    def push_agent(self, agent_name: str, user_input: str) -> str:
        """
        Agent入栈操作
        
        Args:
            agent_name (str): Agent名称
            user_input (str): 用户输入（初始输入）
            
        Returns:
            str: 生成的agent_id
        """
        with self.lock:
            # 生成基于内容的agent_id（与conversation文件保持一致）
            import hashlib
            content_for_hash = f"{agent_name}|{self.task_id}|{user_input}"
            hash_object = hashlib.md5(content_for_hash.encode())
            agent_hash = hash_object.hexdigest()[:12]
            agent_id = f"{agent_name}_{agent_hash}"
            
            # 加载当前栈
            stack = self._load_stack()
            context = self._load_context()
            
            # 检查Agent是否已经存在
            if agent_id in context.get("current", {}).get("agents_status", {}):
                existing_agent = context["current"]["agents_status"][agent_id]
                print(f"ℹ️ Agent已存在: {agent_name} (ID: {agent_id}, Status: {existing_agent.get('status')})")
                return agent_id
            
            # 检查agent_time_history中是否有历史时间记录
            agent_time_history = context.get("agent_time_history", {})
            historical_start_time = None
            historical_end_time = None
            
            if agent_id in agent_time_history:
                historical_start_time = agent_time_history[agent_id].get("start_time")
                historical_end_time = agent_time_history[agent_id].get("end_time")
                print(f"🕰️ 发现Agent历史时间记录: {agent_id}, 原始启动时间: {historical_start_time}")
            else:
                # 如果没有历史记录，保存新的时间到历史中
                current_time = datetime.now().isoformat()
                agent_time_history[agent_id] = {
                    "start_time": current_time,
                    "end_time": None
                }
                context["agent_time_history"] = agent_time_history
                print(f"📝 创建新的Agent时间记录: {agent_id}, 启动时间: {current_time}")
            
            # 获取父Agent（栈顶）
            parent_id = None
            level = 0
            if stack:
                parent_id = stack[-1]["agent_id"]
                level = stack[-1]["level"] + 1
            
            # 创建Agent栈条目，使用历史时间（如果存在）
            start_time_to_use = historical_start_time if historical_start_time else datetime.now().isoformat()
            agent_entry = {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "parent_id": parent_id,
                "level": level,
                "user_input": user_input,
                "start_time": start_time_to_use
            }
            
            # 入栈
            stack.append(agent_entry)
            self._save_stack(stack)
            
            # 更新共享上下文（操作current部分）
            # context已经在上面加载了
            
            # 更新current层级关系
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
            
            # 更新current Agent状态，使用历史时间（如果存在）
            context["current"]["agents_status"][agent_id] = {
                "agent_name": agent_name,
                "status": "waiting",  # 初始状态为等待
                "progress": f"Agent {agent_name} 已启动，正在处理任务...",
                "initial_input": user_input,
                "start_time": start_time_to_use,
                "end_time": historical_end_time,  # 如果有历史end_time也使用历史的
                "parent_id": parent_id,
                "level": level,
                "waiting_for": ""  # 当前等待的子Agent信息
            }
            
            context["current"]["last_updated"] = datetime.now().isoformat()
            
            self._save_context(context)
            
            print(f"📚 Agent入栈: {agent_name} (ID: {agent_id}, Level: {level}, Parent: {parent_id})")
            
            return agent_id
    
    def pop_agent(self, agent_id: str, final_output: str = ""):
        """
        Agent出栈操作（当Agent调用final_output工具成功后）
        
        Args:
            agent_id (str): Agent ID
            final_output (str): 最终输出内容
        """
        with self.lock:
            # 加载当前栈
            stack = self._load_stack()
            
            # 找到并移除对应的Agent
            new_stack = []
            found = False
            for entry in stack:
                if entry["agent_id"] == agent_id:
                    found = True
                    print(f"📚 Agent出栈: {entry['agent_name']} (ID: {agent_id})")
                else:
                    new_stack.append(entry)
            
            if not found:
                print(f"⚠️ 警告：尝试出栈的Agent {agent_id} 不在栈中")
                return
            
            self._save_stack(new_stack)
            
            # 更新共享上下文中的Agent状态（操作current部分）
            context = self._load_context()
            if agent_id in context["current"]["agents_status"]:
                end_time = datetime.now().isoformat()
                context["current"]["agents_status"][agent_id]["status"] = "completed"
                context["current"]["agents_status"][agent_id]["progress"] = final_output if final_output else "任务已完成"
                context["current"]["agents_status"][agent_id]["end_time"] = end_time
                context["current"]["last_updated"] = datetime.now().isoformat()
                
                # 更新agent_time_history中的end_time
                if "agent_time_history" not in context:
                    context["agent_time_history"] = {}
                if agent_id in context["agent_time_history"]:
                    context["agent_time_history"][agent_id]["end_time"] = end_time
                    print(f"🕰️ 更新Agent历史结束时间: {agent_id} -> {end_time}")
            
            self._save_context(context)
            
            # 检查是否需要自动完成任务
            self.check_and_complete_task_if_needed()
    
    def update_agent_progress(self, agent_id: str, progress: str, progress_type: str = "thinking"):
        """
        更新Agent进度信息
        
        Args:
            agent_id (str): Agent ID
            progress (str): 进度信息（thinking内容或其他进度描述）
            progress_type (str): 进度类型 ("thinking", "waiting", "general")
        """
        with self.lock:
            context = self._load_context()
            
            if agent_id in context["current"]["agents_status"]:
                agent_status = context["current"]["agents_status"][agent_id]
                
                # 根据进度类型智能合并信息
                if progress_type == "thinking":
                    # thinking内容，检查是否有等待信息需要保留
                    current_progress = agent_status.get("progress", "")
                    waiting_info = agent_status.get("waiting_for", "")
                    
                    if waiting_info:
                        # 合并thinking内容和等待信息
                        combined_progress = f"{progress}\n\n当前状态：{waiting_info}"
                        agent_status["progress"] = combined_progress
                    else:
                        agent_status["progress"] = progress
                        
                elif progress_type == "waiting":
                    # 等待子Agent，检查是否有thinking内容需要保留
                    current_progress = agent_status.get("progress", "")
                    
                    # 提取现有的thinking内容（排除之前的等待信息）
                    thinking_content = ""
                    if current_progress and not current_progress.startswith("Agent") and not current_progress.startswith("正在等待"):
                        # 如果包含"当前状态："，只保留之前的部分
                        if "\n\n当前状态：" in current_progress:
                            thinking_content = current_progress.split("\n\n当前状态：")[0]
                        else:
                            thinking_content = current_progress
                    
                    # 更新等待信息
                    agent_status["waiting_for"] = progress
                    
                    # 合并thinking内容和等待信息
                    if thinking_content:
                        agent_status["progress"] = f"{thinking_content}\n\n当前状态：{progress}"
                    else:
                        agent_status["progress"] = progress
                        
                else:  # general
                    # 一般进度更新，直接替换
                    agent_status["progress"] = progress
                    agent_status["waiting_for"] = ""  # 清除等待信息
                
                agent_status["last_progress_update"] = datetime.now().isoformat()
                context["current"]["last_updated"] = datetime.now().isoformat()
                self._save_context(context)
                print(f"📈 更新Agent进度 ({progress_type}): {agent_id[:20]}... -> {progress[:50]}...")
            else:
                print(f"⚠️ 警告：尝试更新不存在的Agent进度: {agent_id}")
    
    def get_current_agent_id(self) -> Optional[str]:
        """
        获取当前栈顶的Agent ID
        
        Returns:
            Optional[str]: 栈顶Agent ID，如果栈为空则返回None
        """
        stack = self._load_stack()
        return stack[-1]["agent_id"] if stack else None
    
    def get_stack_top_agent(self) -> Optional[Dict]:
        """
        获取栈顶Agent的完整信息
        
        Returns:
            Optional[Dict]: 栈顶Agent信息，如果栈为空则返回None
        """
        stack = self._load_stack()
        return stack[-1] if stack else None
    
    def get_parent_agent_id(self, agent_id: str) -> Optional[str]:
        """
        获取指定Agent的父Agent ID
        
        Args:
            agent_id (str): Agent ID
            
        Returns:
            Optional[str]: 父Agent ID，如果没有父Agent则返回None
        """
        context = self._load_context()
        hierarchy = context.get("current", {}).get("hierarchy", {})
        if agent_id in hierarchy:
            return hierarchy[agent_id].get("parent")
        return None
    
    def get_hierarchy_info(self) -> Dict:
        """
        获取完整的层级信息
        
        Returns:
            Dict: 包含层级关系和状态的完整信息
        """
        return self._load_context()
    
    def get_context_for_agent(self, current_agent_id: str) -> str:
        """
        为特定Agent生成上下文信息，用于添加到对话中
        
        Args:
            current_agent_id (str): 当前Agent的ID
            
        Returns:
            str: Markdown格式的上下文信息
        """
        context = self._load_context()
        
        # 构建Markdown格式的上下文信息
        context_md = "# 🤖 Agent协同系统上下文概览\n\n"
        
        # 1. 系统说明
        context_md += "## 📋 重要说明\n"
        context_md += "- 你处于一个多层级Agent协同系统中\n"
        context_md += "- Level 0的Agent接收用户的初始输入，你们协同工作的最终目的是服务于用户的初始任务\n"
        context_md += "- 以下概览仅显示当前系统状态，不包含你的完整历史行动\n"
        context_md += "- 请根据你的层级和职责行动，不要越界\n"
        context_md += "- 在final_output中向父节点报告你的建议和结果\n"
        context_md += "- 标记为'已启动，正在处理任务...'的Agent就是你自己\n"
        context_md += "- 不要重复完成已经完成的动作！\n\n"
        
        # 2. 当前任务指令
        current_instructions = context.get("current", {}).get("instructions", [])
        if current_instructions:
            context_md += "## 📝 当前任务指令\n"
            context_md += "**请注意指令的先后顺序：**\n\n"
            for i, instr in enumerate(current_instructions):
                start_time = instr.get("start_time", "未知")
                context_md += f"{i+1}. **{instr.get('instruction', '未知')}**\n"
                context_md += f"   - 开始时间: {start_time}\n"
                context_md += f"   - 指令ID: {instr.get('instruction_id', '未知')}\n\n"
        
        # 3. 当前Agent调用层级（排除judge_agent）
        current_hierarchy = context.get("current", {}).get("hierarchy", {})
        current_agents = context.get("current", {}).get("agents_status", {})
        
        if current_agents:
            context_md += "## 🌳 当前Agent调用层级\n\n"
            
            # 找到根Agent（level 0）
            root_agents = [aid for aid, info in current_hierarchy.items() if info.get("parent") is None]
            
            for root_id in root_agents:
                context_md += self._format_agent_hierarchy_md(root_id, current_hierarchy, current_agents, 0, current_agent_id)
        
                # 4. 历史任务概览
        history = context.get("history", [])
        if history:
            context_md += "## 📚 历史任务概览\n"
            context_md += f"**这是同一工作空间中之前已经完成的任务 ({len(history)} 个)：**\n\n"
            
            for i, hist in enumerate(history):
                hist_instructions = hist.get("instructions", [])
                hist_agents = hist.get("agents_status", {})
                start_time = hist.get("start_time", "未知")
                completion_time = hist.get("completion_time", "未知")
                
                context_md += f"### 历史任务 {i+1}\n"
                context_md += f"- **起止时间**: {start_time} → {completion_time}\n"
                
                # 用户指令列表
                if hist_instructions:
                    context_md += "- **用户指令列表**:\n"
                    for j, instr in enumerate(hist_instructions):
                        context_md += f"  {j+1}. {instr.get('instruction', '未知')}\n"
                
                # Level 0和Level 1的Agent进度（排除judge_agent）
                level_0_1_agents = [
                    (aid, agent_info) for aid, agent_info in hist_agents.items() 
                    if agent_info.get("level") in [0, 1] and agent_info.get("agent_name", "") != "judge_agent"
                ]
                
                if level_0_1_agents:
                    context_md += "- **主要Agent执行情况**:\n"
                    # 按level分组显示，Level 0和Level 1平级
                    level_0_agents = [(aid, info) for aid, info in level_0_1_agents if info.get("level") == 0]
                    level_1_agents = [(aid, info) for aid, info in level_0_1_agents if info.get("level") == 1]
                    
                    # 显示Level 0 Agent
                    for aid, agent_info in level_0_agents:
                        agent_name = agent_info.get("agent_name", "未知")
                        progress = agent_info.get("progress", "无进度信息")
                        agent_start = agent_info.get("start_time", "未知")
                        agent_end = agent_info.get("end_time", "未知")
                        
                        context_md += f"  - **{agent_name}** (Level 0 - 主控Agent)\n"
                        context_md += f"    - 时间: {agent_start} → {agent_end}\n"
                        context_md += f"    - 进度: {progress}\n"
                    # 显示Level 1 Agent
                    for aid, agent_info in level_1_agents:
                        agent_name = agent_info.get("agent_name", "未知")
                        progress = agent_info.get("progress", "无进度信息")
                        agent_start = agent_info.get("start_time", "未知")
                        agent_end = agent_info.get("end_time", "未知")
                        
                        context_md += f"  - **{agent_name}** (Level 1 - 执行Agent)\n"
                        context_md += f"    - 时间: {agent_start} → {agent_end}\n"
                        context_md += f"    - 进度: {progress}\n"
                
                context_md += "\n"
        
        context_md += "---\n"
        context_md += "*以上为系统上下文概览，请根据你的职责和层级继续执行任务*\n"
        
        return context_md
    
    def _format_agent_hierarchy_md(self, agent_id: str, hierarchy: Dict, agents_status: Dict, indent: int, current_agent_id: str) -> str:
        """
        格式化Agent层级为Markdown格式（排除judge_agent）
        
        Args:
            agent_id (str): Agent ID
            hierarchy (Dict): 层级关系
            agents_status (Dict): Agent状态
            indent (int): 缩进级别
            current_agent_id (str): 当前Agent ID
            
        Returns:
            str: 格式化的Markdown文本
        """
        if agent_id not in agents_status:
            return ""
        
        agent_info = agents_status[agent_id]
        agent_name = agent_info.get("agent_name", "未知")
        
        # 跳过judge_agent
        if agent_name == "judge_agent":
            return ""
        
        level = agent_info.get("level", 0)
        status = agent_info.get("status", "未知")
        progress = agent_info.get("progress", "无进度信息")
        initial_input = agent_info.get("initial_input", "未知")
        
        # 状态图标
        status_emoji = "✅" if status == "completed" else "⏳"
        current_marker = " 👈 **[你自己]**" if agent_id == current_agent_id else ""
        
        # 缩进
        indent_str = "  " * indent
        
        result = f"{indent_str}- {status_emoji} **{agent_name}** (Level {level}){current_marker}\n"
        result += f"{indent_str}  - 输入: {initial_input[:80]}{'...' if len(initial_input) > 80 else ''}\n"
        result += f"{indent_str}  - 状态: {status}\n"
        result += f"{indent_str}  - 进度: {progress}\n"
        # 递归处理子Agent
        children = hierarchy.get(agent_id, {}).get("children", [])
        for child_id in children:
            result += self._format_agent_hierarchy_md(child_id, hierarchy, agents_status, indent + 1, current_agent_id)
        
        return result
    
    def print_hierarchy_tree(self):
        """打印层级树结构（用于调试）"""
        context = self._load_context()
        hierarchy = context.get("current", {}).get("hierarchy", {})
        agents_status = context.get("current", {}).get("agents_status", {})
        
        print(f"\n🌳 Task {self.task_id} 当前Agent调用层级树：")
        print("=" * 50)
        
        # 显示当前指令
        current_instructions = context.get("current", {}).get("instructions", [])
        if current_instructions:
            print("📝 当前指令:")
            for i, instr in enumerate(current_instructions):
                print(f"  {i+1}. {instr['instruction'][:60]}... (开始时间: {instr['start_time']})")
            print()
        
        # 找到根节点（没有父节点的Agent）
        root_agents = [aid for aid, info in hierarchy.items() if info.get("parent") is None]
        
        for root_id in root_agents:
            self._print_agent_tree(root_id, hierarchy, agents_status, 0)
        
        print("=" * 50)
        
        # 显示历史记录摘要
        history = context.get("history", [])
        if history:
            print(f"\n📚 历史任务记录 ({len(history)} 个已完成任务):")
            for i, hist in enumerate(history):
                print(f"  {i+1}. 完成时间: {hist.get('completion_time', '未知')}")
                instructions = hist.get("instructions", [])
                if instructions:
                    print(f"     指令: {instructions[0].get('instruction', '未知')[:60]}...")
            print("=" * 50)
    
    def _print_agent_tree(self, agent_id: str, hierarchy: Dict, agents_status: Dict, indent: int):
        """递归打印Agent树"""
        if agent_id not in agents_status:
            return
        
        status_info = agents_status[agent_id]
        status_emoji = "✅" if status_info["status"] == "completed" else "⏳"
        
        indent_str = "  " * indent
        print(f"{indent_str}{status_emoji} {status_info['agent_name']} (Level {status_info['level']})")
        print(f"{indent_str}   📝 输入: {status_info['initial_input'][:50]}...")
        print(f"{indent_str}   📊 进度: {status_info['progress'][:50]}...")
        print(f"{indent_str}   🕐 状态: {status_info['status']}")
        
        # 递归打印子Agent
        children = hierarchy.get(agent_id, {}).get("children", [])
        for child_id in children:
            self._print_agent_tree(child_id, hierarchy, agents_status, indent + 1)
    
    def cleanup_files(self):
        """清理任务相关的层级文件"""
        try:
            if os.path.exists(self.stack_file):
                os.remove(self.stack_file)
            if os.path.exists(self.context_file):
                os.remove(self.context_file)
            print(f"🗑️ 已清理任务 {self.task_id} 的层级文件")
        except Exception as e:
            print(f"⚠️ 清理层级文件失败: {e}")
    
    def smart_clean_for_restart(self):
        """
        智能清理：保留已完成的Agent，删除等待中的Agent，为重新开始做准备
        """
        with self.lock:
            context = self._load_context()
            
            if not context.get("current"):
                print("ℹ️ 当前没有需要清理的状态")
                return
            
            current_agents = context["current"].get("agents_status", {})
            current_hierarchy = context["current"].get("hierarchy", {})
            current_instructions = context["current"].get("instructions", [])
            
            print(f"🔍 分析当前状态: {len(current_agents)} 个Agent")
            
            # 分离completed和waiting的Agent
            completed_agents = {}
            completed_hierarchy = {}
            waiting_agent_ids = []
            
            for agent_id, agent_status in current_agents.items():
                if agent_status.get("status") == "completed":
                    completed_agents[agent_id] = agent_status
                    # 保留对应的层级关系
                    if agent_id in current_hierarchy:
                        completed_hierarchy[agent_id] = current_hierarchy[agent_id]
                    print(f"✅ 保留已完成Agent: {agent_status['agent_name']} (Level {agent_status['level']})")
                else:
                    waiting_agent_ids.append(agent_id)
                    print(f"🗑️ 将删除等待中Agent: {agent_status['agent_name']} (Level {agent_status['level']})")
            
            # 清理completed Agent的children中的waiting Agent引用
            for agent_id, hierarchy_info in completed_hierarchy.items():
                # 过滤children，只保留completed的子Agent
                filtered_children = [
                    child_id for child_id in hierarchy_info.get("children", [])
                    if child_id in completed_agents
                ]
                completed_hierarchy[agent_id]["children"] = filtered_children
            
            # 更新current状态：保留completed，删除waiting
            context["current"]["agents_status"] = completed_agents
            context["current"]["hierarchy"] = completed_hierarchy
            context["current"]["instructions"] = current_instructions  # 保留指令
            context["current"]["last_updated"] = datetime.now().isoformat()
            
            # 清空栈（waiting的Agent都在栈中，completed的早就出栈了）
            self._save_stack([])
            
            self._save_context(context)
            
            print(f"🎯 智能清理完成:")
            print(f"   保留: {len(completed_agents)} 个已完成Agent")
            print(f"   删除: {len(waiting_agent_ids)} 个等待中Agent")
            print(f"   保留: {len(current_instructions)} 条指令")
            print(f"   栈已清空")
    
    def fix_inconsistent_state(self):
        """
        修复栈和上下文状态不一致的问题
        """
        with self.lock:
            stack = self._load_stack()
            context = self._load_context()
            
            print(f"🔧 开始修复状态不一致问题...")
            print(f"栈中Agent数量: {len(stack)}")
            print(f"上下文中Agent数量: {len(context.get('current', {}).get('agents_status', {}))}")
            
            # 获取栈中的Agent ID列表
            stack_agent_ids = [entry["agent_id"] for entry in stack]
            
            # 获取上下文中的Agent ID列表
            context_agent_ids = list(context.get("current", {}).get("agents_status", {}).keys())
            
            # 找出已完成但仍在栈中的Agent
            completed_agents_in_stack = []
            for agent_id in stack_agent_ids:
                if agent_id in context.get("current", {}).get("agents_status", {}):
                    agent_status = context["current"]["agents_status"][agent_id]
                    if agent_status.get("status") == "completed":
                        completed_agents_in_stack.append(agent_id)
            
            if completed_agents_in_stack:
                print(f"🔄 发现 {len(completed_agents_in_stack)} 个已完成但仍在栈中的Agent，正在清理...")
                
                # 从栈中移除已完成的Agent
                new_stack = [entry for entry in stack if entry["agent_id"] not in completed_agents_in_stack]
                self._save_stack(new_stack)
                
                print(f"✅ 已清理完成的Agent，栈中剩余: {len(new_stack)} 个Agent")
            
            # 检查是否所有任务都已完成
            remaining_agents = context.get("current", {}).get("agents_status", {})
            if remaining_agents:
                all_completed = all(
                    agent_status.get("status") == "completed" 
                    for agent_status in remaining_agents.values()
                )
                
                if all_completed:
                    print("🎉 所有Agent已完成，执行完整清理")
                    self._complete_current_task_internal()
                    self._save_stack([])


def get_hierarchy_manager(task_id: str) -> AgentHierarchyManager:
    """
    获取或创建层级管理器实例
    
    Args:
        task_id (str): 任务ID
        
    Returns:
        AgentHierarchyManager: 层级管理器实例
    """
    return AgentHierarchyManager(task_id)


# 全局管理器缓存（避免重复创建）
_managers_cache = {}
_cache_lock = threading.Lock()

def get_cached_hierarchy_manager(task_id: str) -> AgentHierarchyManager:
    """
    获取缓存的层级管理器实例
    
    Args:
        task_id (str): 任务ID
        
    Returns:
        AgentHierarchyManager: 层级管理器实例
    """
    with _cache_lock:
        if task_id not in _managers_cache:
            _managers_cache[task_id] = AgentHierarchyManager(task_id)
        return _managers_cache[task_id]


if __name__ == "__main__":
    # 测试代码
    manager = AgentHierarchyManager("test_task")
    
    # 模拟Agent调用序列
    agent1_id = manager.push_agent("MainAgent", "处理用户查询")
    manager.update_agent_progress(agent1_id, "正在分析用户需求...")
    
    agent2_id = manager.push_agent("SubAgent1", "执行子任务1")
    manager.update_agent_progress(agent2_id, "正在处理数据...")
    
    agent3_id = manager.push_agent("SubAgent2", "执行子任务2")
    manager.update_agent_progress(agent3_id, "正在生成报告...")
    
    # 打印层级树
    manager.print_hierarchy_tree()
    
    # 模拟Agent完成
    manager.pop_agent(agent3_id, "子任务2完成")
    manager.pop_agent(agent2_id, "子任务1完成")
    manager.update_agent_progress(agent1_id, "所有子任务已完成，正在汇总结果...")
    manager.pop_agent(agent1_id, "主任务完成")
    
    # 再次打印层级树
    print("\n完成后的层级树：")
    manager.print_hierarchy_tree() 