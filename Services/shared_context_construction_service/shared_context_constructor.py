#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared Context Constructor - 共享上下文构造器
专门负责读取所有相关数据并构造Agent间的共享上下文
"""

import os
import json
import glob
from typing import Dict, List, Optional, Any
from pathlib import Path


class SharedContextConstructor:
    """
    共享上下文构造器
    负责读取所有相关历史对话和层级信息，构造智能的共享上下文
    """
    
    def __init__(self, conversations_dir: str = None):
        """
        初始化共享上下文构造器
        
        Args:
            conversations_dir: 对话存储目录
        """
        if conversations_dir is None:
            # 默认使用项目根目录下的conversations文件夹
            current_dir = Path(__file__).parent.parent.parent
            conversations_dir = str(current_dir / "conversations")
        
        self.conversations_dir = conversations_dir
    
    def get_context_for_agent(self, task_id: str, current_agent_id: str) -> str:
        """
        为特定Agent构造共享上下文信息
        
        Args:
            task_id: 任务ID
            current_agent_id: 当前Agent的ID
            
        Returns:
            str: Markdown格式的共享上下文信息
        """
        # 1. 读取share_context.json文件
        share_context = self._load_share_context(task_id)
        
        # 2. 使用share_context数据构造基础上下文
        base_context = self._construct_base_context_from_share(share_context, current_agent_id)
        
        # 3. 读取所有相关的历史对话记录
        conversation_histories = self._load_conversation_histories(task_id)
        
        # 4. 增强上下文：添加历史对话摘要
        enhanced_context = self._enhance_context_with_histories(base_context, conversation_histories, task_id)
        
        return enhanced_context
    
    def _load_share_context(self, task_id: str) -> Dict:
        """
        加载share_context.json文件
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 共享上下文数据
        """
        share_context_file = os.path.join(self.conversations_dir, f"{task_id}_share_context.json")
        
        try:
            if os.path.exists(share_context_file):
                with open(share_context_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                print(f"⚠️ 未找到共享上下文文件: {share_context_file}")
                return {}
        except Exception as e:
            print(f"⚠️ 读取共享上下文文件失败: {e}")
            return {}
    
    def _load_conversation_histories(self, task_id: str) -> List[Dict]:
        """
        读取同一task_id下的所有历史对话记录
        
        Args:
            task_id: 任务ID
            
        Returns:
            List[Dict]: 历史对话记录列表
        """
        conversation_files = []
        
        try:
            # 查找所有匹配的对话文件
            pattern = os.path.join(self.conversations_dir, f"{task_id}_*.json")
            all_files = glob.glob(pattern)
            
            # 过滤掉stack和share_context文件，只保留对话文件
            for file_path in all_files:
                filename = os.path.basename(file_path)
                if not filename.endswith('_stack.json') and not filename.endswith('_share_context.json'):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            conversation_data = json.load(f)
                            conversation_files.append({
                                "filename": filename,
                                "data": conversation_data,
                                "file_path": file_path
                            })
                    except Exception as e:
                        print(f"⚠️ 读取对话文件 {filename} 失败: {e}")
            
            print(f"📂 找到 {len(conversation_files)} 个相关对话文件")
            return conversation_files
            
        except Exception as e:
            print(f"⚠️ 查找对话文件失败: {e}")
            return []
    
    def _construct_base_context_from_share(self, share_context: Dict, current_agent_id: str) -> str:
        """
        使用share_context数据构造基础上下文（当没有hierarchy_manager时）
        
        Args:
            share_context: 共享上下文数据
            current_agent_id: 当前Agent ID
            
        Returns:
            str: 基础上下文信息
        """
        context_md = "# 🤖 Agent协同系统上下文概览\n\n"
        
        # 系统说明
        context_md += "## 📋 重要说明\n"
        context_md += "- 你处于一个多层级Agent协同系统中\n"
        context_md += "- Level 0的Agent接收用户的初始输入，你们协同工作的最终目的是服务于用户的初始任务\n"
        context_md += "- 以下概览仅显示当前系统状态，不包含你的完整历史行动\n"
        context_md += "- 请根据你的层级和职责行动，不要越界\n\n"
        
        # 当前任务指令
        current_instructions = share_context.get("current", {}).get("instructions", [])
        if current_instructions:
            context_md += "## 📝 当前任务指令\n"
            for i, instr in enumerate(current_instructions):
                start_time = instr.get("start_time", "未知")
                context_md += f"{i+1}. **{instr.get('instruction', '未知')}**\n"
                context_md += f"   - 开始时间: {start_time}\n\n"
        
        # 当前Agent层级
        current_agents = share_context.get("current", {}).get("agents_status", {})
        current_hierarchy = share_context.get("current", {}).get("hierarchy", {})
        
        if current_agents:
            context_md += "## 🌳 当前Agent调用层级\n\n"
            
            # 找到根Agent（level 0）
            root_agents = [aid for aid, info in current_hierarchy.items() if info.get("parent") is None]
            
            for root_id in root_agents:
                context_md += self._format_agent_hierarchy_md(root_id, current_hierarchy, current_agents, 0, current_agent_id)
        
        # 历史任务概览
        history = share_context.get("history", [])
        if history:
            context_md += "## 📚 历史任务概览\n"
            context_md += f"**这是同一工作空间中之前已经完成的任务 ({len(history)} 个)：**\n\n"
            
            for i, hist in enumerate(history):
                hist_instructions = hist.get("instructions", [])
                start_time = hist.get("start_time", "未知")
                completion_time = hist.get("completion_time", "未知")
                
                context_md += f"### 历史任务 {i+1}\n"
                context_md += f"- **起止时间**: {start_time} → {completion_time}\n"
                
                if hist_instructions:
                    context_md += "- **用户指令列表**:\n"
                    for j, instr in enumerate(hist_instructions):
                        context_md += f"  {j+1}. {instr.get('instruction', '未知')}\n"
                context_md += "\n"
        
        context_md += "---\n"
        context_md += "*以上为系统上下文概览，请根据你的职责和层级继续执行任务*\n"
        
        return context_md
    
    def _format_agent_hierarchy_md(self, agent_id: str, hierarchy: Dict, agents_status: Dict, indent: int, current_agent_id: str) -> str:
        """
        格式化Agent层级为Markdown格式（排除judge_agent）
        
        Args:
            agent_id: Agent ID
            hierarchy: 层级关系
            agents_status: Agent状态
            indent: 缩进级别
            current_agent_id: 当前Agent ID
            
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
    
    def _enhance_context_with_histories(self, base_context: str, conversation_histories: List[Dict], task_id: str) -> str:
        """
        使用历史对话记录增强上下文
        
        Args:
            base_context: 基础上下文
            conversation_histories: 历史对话记录
            task_id: 任务ID
            
        Returns:
            str: 增强后的上下文
        """
        return base_context
        # if not conversation_histories:
        #     return base_context
        
        # enhanced_context = base_context + "\n\n"
        # enhanced_context += "## 💬 相关对话历史摘要\n\n"
        # enhanced_context += f"**在同一任务({task_id})中发现 {len(conversation_histories)} 个相关对话：**\n\n"
        
        # for i, conv_file in enumerate(conversation_histories):
        #     filename = conv_file["filename"]
        #     conv_data = conv_file["data"]
            
        #     # 提取关键信息
        #     agent_name = conv_data.get("agent_name", "未知")
        #     user_input = conv_data.get("user_input", "未知")
        #     current_turn = conv_data.get("current_turn", 0)
        #     history_count = len(conv_data.get("history", []))
        #     tool_calls_count = len(conv_data.get("tool_calls_log", []))
            
        #     enhanced_context += f"### 对话记录 {i+1}: {agent_name}\n"
        #     enhanced_context += f"- **文件**: {filename}\n"
        #     enhanced_context += f"- **初始输入**: {user_input[:100]}{'...' if len(user_input) > 100 else ''}\n"
        #     enhanced_context += f"- **对话轮次**: {current_turn}\n"
        #     enhanced_context += f"- **历史消息数**: {history_count}\n"
        #     enhanced_context += f"- **工具调用数**: {tool_calls_count}\n"
            
        #     # 如果有工具调用日志，显示最近的几个
        #     tool_calls_log = conv_data.get("tool_calls_log", [])
        #     if tool_calls_log:
        #         enhanced_context += "- **最近工具调用**:\n"
        #         recent_tools = tool_calls_log[-3:]  # 显示最近3个
        #         for tool in recent_tools:
        #             tool_name = tool.get("name", "未知")
        #             tool_status = tool.get("status", "未知")
        #             enhanced_context += f"  - {tool_name} ({tool_status})\n"
            
        #     enhanced_context += "\n"
        
        # enhanced_context += "---\n"
        # enhanced_context += "*以上历史信息可帮助理解任务背景和当前进展*\n"
        
        # return enhanced_context
    
    def get_all_task_conversations(self, task_id: str) -> Dict:
        """
        获取指定任务的所有相关信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 包含所有相关信息的字典
        """
        return {
            "share_context": self._load_share_context(task_id),
            "conversation_histories": self._load_conversation_histories(task_id),
            "stack_info": self._load_stack_info(task_id)
        }
    
    def _load_stack_info(self, task_id: str) -> Dict:
        """
        加载stack.json文件
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 栈信息
        """
        stack_file = os.path.join(self.conversations_dir, f"{task_id}_stack.json")
        
        try:
            if os.path.exists(stack_file):
                with open(stack_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {"stack": []}
        except Exception as e:
            print(f"⚠️ 读取栈文件失败: {e}")
            return {"stack": []}
    
    def get_conversation_summary(self, task_id: str, max_conversations: int = 5) -> str:
        """
        获取对话摘要信息
        
        Args:
            task_id: 任务ID
            max_conversations: 最大显示的对话数量
            
        Returns:
            str: 对话摘要
        """
        conversation_histories = self._load_conversation_histories(task_id)
        
        if not conversation_histories:
            return "📭 暂无相关对话历史"
        
        # 按文件修改时间排序，显示最新的对话
        sorted_conversations = sorted(
            conversation_histories, 
            key=lambda x: os.path.getmtime(x["file_path"]), 
            reverse=True
        )[:max_conversations]
        
        summary = f"## 💬 最近对话摘要 (显示最新 {len(sorted_conversations)} 个)\n\n"
        
        for i, conv_file in enumerate(sorted_conversations):
            conv_data = conv_file["data"]
            agent_name = conv_data.get("agent_name", "未知")
            user_input = conv_data.get("user_input", "未知")
            
            # 获取最后几条对话
            history = conv_data.get("history", [])
            if history:
                last_messages = history[-2:]  # 最后2条消息
                summary += f"### {agent_name} 最近对话\n"
                summary += f"**任务**: {user_input[:80]}{'...' if len(user_input) > 80 else ''}\n\n"
                
                for msg in last_messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")[:150]
                    summary += f"- **{role}**: {content}{'...' if len(msg.get('content', '')) > 150 else ''}\n"
                summary += "\n"
        
        return summary
