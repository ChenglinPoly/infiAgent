#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conversation Manager - 对话管理器
专门处理对话历史的保存、加载和工具调用状态管理
"""

import os
import json
import hashlib
from typing import List, Dict, Any, Optional, Callable, Tuple
from pathlib import Path
from datetime import datetime

from .models import ConversationState, ChatMessage, ToolCallEntry


class ConversationManager:
    """
    对话管理器
    负责对话历史的持久化和工具调用状态管理
    """
    
    def __init__(self, conversation_dir: str = None):
        """
        初始化对话管理器
        
        Args:
            conversation_dir: 对话存储目录，如果为None则使用默认目录
        """
        if conversation_dir is None:
            # 默认使用项目根目录下的conversations文件夹
            current_dir = Path(__file__).parent.parent.parent
            conversation_dir = str(current_dir / "conversations")
        
        self.conversation_dir = conversation_dir
        self._ensure_conversation_dir()
    
    def _ensure_conversation_dir(self):
        """确保对话记录目录存在"""
        if not os.path.exists(self.conversation_dir):
            os.makedirs(self.conversation_dir)
    
    def _generate_conversation_filename(self, task_id: str, user_input: str, suffix: str = "") -> str:
        """
        根据task_id和用户输入生成对话文件名
        
        Args:
            task_id: 任务ID
            user_input: 用户输入
            suffix: 文件名后缀（如"_fact_input"）
            
        Returns:
            str: 对话文件的完整路径
        """
        # 创建用于生成文件名的组合字符串
        content_for_hash = f"{task_id}|{user_input}"
        # 生成哈希值作为文件名的一部分
        hash_object = hashlib.md5(content_for_hash.encode())
        file_hash = hash_object.hexdigest()[:12]  # 取前12位作为文件名
        
        # 构建文件名：任务ID_哈希值[后缀].json
        filename = f"{task_id}_{file_hash}{suffix}.json"
        return os.path.join(self.conversation_dir, filename)
    
    def save_conversation(self, conversation_state: ConversationState, logger_func: Optional[Callable[[str], None]] = None) -> bool:
        """
        保存对话历史到JSON文件
        
        Args:
            conversation_state: 对话状态
            logger_func: 日志记录函数（可选）
            
        Returns:
            bool: 是否保存成功
        """
        try:
            conversation_file = self._generate_conversation_filename(
                conversation_state.task_id, 
                conversation_state.user_input
            )
            
            # 保存到文件
            with open(conversation_file, 'w', encoding='utf-8') as f:
                json.dump(conversation_state.to_dict(), f, indent=2, ensure_ascii=False)
            
            if logger_func:
                logger_func(f"💾 对话历史已保存到: {conversation_file}")
            
            return True
            
        except Exception as e:
            if logger_func:
                logger_func(f"保存对话历史失败: {str(e)}")
            print(f"⚠️ 保存对话历史失败: {e}")
            return False
    
    def save_truncated_conversation(self, conversation_state: ConversationState, truncated_history: List[ChatMessage], logger_func: Optional[Callable[[str], None]] = None) -> bool:
        """
        保存截断后的对话历史到独立文件（带_fact_input后缀）
        
        Args:
            conversation_state: 对话状态
            truncated_history: 截断后的对话历史
            logger_func: 日志记录函数（可选）
            
        Returns:
            bool: 是否保存成功
        """
        try:
            conversation_file = self._generate_conversation_filename(
                conversation_state.task_id, 
                conversation_state.user_input, 
                "_fact_input"
            )
            
            # 创建截断后的对话状态
            truncated_data = conversation_state.to_dict()
            truncated_data["truncated_history"] = [
                {"role": msg.role, "content": msg.content}
                for msg in truncated_history
            ]
            
            # 保存到文件
            with open(conversation_file, 'w', encoding='utf-8') as f:
                json.dump(truncated_data, f, indent=2, ensure_ascii=False)
            
            if logger_func:
                logger_func(f"💾 截断后的对话历史已保存到: {conversation_file}")
            
            return True
            
        except Exception as e:
            if logger_func:
                logger_func(f"保存截断对话历史失败: {str(e)}")
            print(f"⚠️ 保存截断对话历史失败: {e}")
            return False
    
    def load_conversation(self, task_id: str, user_input: str, expected_agent_name: str, logger_func: Optional[Callable[[str], None]] = None) -> Optional[ConversationState]:
        """
        从JSON文件加载对话历史
        
        Args:
            task_id: 任务ID
            user_input: 用户输入
            expected_agent_name: 期望的Agent名称（用于验证）
            logger_func: 日志记录函数（可选）
            
        Returns:
            Optional[ConversationState]: 加载的对话状态，如果失败则返回None
            特殊返回值："AGENT_NAME_MISMATCH" 表示Agent名称不匹配
        """
        try:
            conversation_file = self._generate_conversation_filename(task_id, user_input)
            
            if not os.path.exists(conversation_file):
                return None
            
            with open(conversation_file, 'r', encoding='utf-8') as f:
                conversation_data = json.load(f)
            
            # 验证数据完整性
            if (conversation_data.get("task_id") != task_id or
                conversation_data.get("user_input") != user_input):
                print(f"⚠️ 对话历史文件存在，但task_id或user_input不匹配，将创建新的对话")
                return None
            
            # 检查agent_name是否匹配
            if conversation_data.get("agent_name") != expected_agent_name:
                print(f"❌ 严重错误：Agent名称不匹配！")
                print(f"   历史文件中的Agent: {conversation_data.get('agent_name')}")
                print(f"   当前Agent: {expected_agent_name}")
                print(f"   这表明任务内容与之前冲突，导致hash命名错误")
                print(f"   请略微修改任务内容，确保hash问题消除")
                
                # 返回特殊标记
                return "AGENT_NAME_MISMATCH"
            
            # 重建对话状态
            conversation_state = ConversationState.from_dict(conversation_data)
            
            if logger_func:
                logger_func(f"📂 已加载对话历史，从第 {conversation_state.current_turn + 1} 轮继续")
                if conversation_state.tool_calls_log:
                    pending_tools = [tool for tool in conversation_state.tool_calls_log if tool.status == "pending"]
                    logger_func(f"🔄 发现 {len(pending_tools)} 个待处理的工具调用")
            
            return conversation_state
            
        except Exception as e:
            if logger_func:
                logger_func(f"加载对话历史失败: {str(e)}")
            print(f"⚠️ 加载对话历史失败: {e}")
            return None
    
    def add_tool_call_to_log(self, conversation_state: ConversationState, tool_call_name: str, tool_call_arguments: Dict, turn: int, logger_func: Optional[Callable[[str], None]] = None) -> str:
        """
        将工具调用添加到状态日志中，状态为pending
        
        Args:
            conversation_state: 对话状态
            tool_call_name: 工具名称
            tool_call_arguments: 工具参数
            turn: 当前轮次
            logger_func: 日志记录函数（可选）
            
        Returns:
            str: 工具调用的唯一ID
        """
        tool_call_id = f"{tool_call_name}_{turn}_{len(conversation_state.tool_calls_log)}"
        
        tool_call_entry = ToolCallEntry(
            id=tool_call_id,
            name=tool_call_name,
            arguments=tool_call_arguments.copy(),
            status="pending",
            turn=turn,
            timestamp=datetime.now().isoformat()
        )
        
        conversation_state.tool_calls_log.append(tool_call_entry)
        
        if logger_func:
            logger_func(f"📝 工具调用已记录: {tool_call_name} (ID: {tool_call_id})")
        
        return tool_call_id
    
    def update_tool_call_status(self, conversation_state: ConversationState, tool_call_id: str, status: str, result: Dict = None, logger_func: Optional[Callable[[str], None]] = None):
        """
        更新工具调用状态
        
        Args:
            conversation_state: 对话状态
            tool_call_id: 工具调用ID
            status: 新状态 ("pending", "completed", "failed")
            result: 工具执行结果
            logger_func: 日志记录函数（可选）
        """
        for tool_entry in conversation_state.tool_calls_log:
            if tool_entry.id == tool_call_id:
                tool_entry.status = status
                tool_entry.completed_timestamp = datetime.now().isoformat()
                if result is not None:
                    tool_entry.result = result
                
                if logger_func:
                    logger_func(f"🔄 工具调用状态更新: {tool_entry.name} -> {status}")
                break
    
    def get_pending_tool_calls(self, conversation_state: ConversationState) -> List[ToolCallEntry]:
        """获取所有pending状态的工具调用"""
        return [tool for tool in conversation_state.tool_calls_log if tool.status == "pending"]
    
    def check_final_output_completed(self, conversation_state: ConversationState) -> bool:
        """
        检查工具调用日志中是否有已完成的final_output工具
        
        Args:
            conversation_state: 对话状态
            
        Returns:
            bool: 是否有已完成的final_output工具
        """
        for tool_entry in conversation_state.tool_calls_log:
            if (tool_entry.name == "final_output" and 
                tool_entry.status == "completed"):
                return True
        return False
    
    def get_final_output_result(self, conversation_state: ConversationState, token_usage: Dict = None) -> Optional[Dict]:
        """
        从工具调用日志中获取final_output的结果
        
        Args:
            conversation_state: 对话状态
            token_usage: token使用统计（用于补充到结果中）
            
        Returns:
            Optional[Dict]: final_output的结果，如果没有则返回None
        """
        for tool_entry in conversation_state.tool_calls_log:
            if (tool_entry.name == "final_output" and 
                tool_entry.status == "completed"):
                result = tool_entry.result.copy() if tool_entry.result else {}
                # 确保包含token统计
                if token_usage and "token_usage" not in result:
                    result["token_usage"] = token_usage.copy()
                return result
        return None
    
    def process_pending_tool_calls(self, conversation_state: ConversationState, tool_executor: Callable[[Any, str], Dict], task_id: str, logger_func: Optional[Callable[[str], None]] = None) -> List[ChatMessage]:
        """
        处理所有pending状态的工具调用，并将结果添加到对话历史中
        
        Args:
            conversation_state: 对话状态
            tool_executor: 工具执行函数 (tool_call_object, task_id) -> result
            task_id: 任务ID
            logger_func: 日志记录函数（可选）
            
        Returns:
            List[ChatMessage]: 更新后的对话历史
        """
        pending_tools = self.get_pending_tool_calls(conversation_state)
        
        if not pending_tools:
            return conversation_state.history
        
        print(f"🔄 发现 {len(pending_tools)} 个待处理的工具调用，正在恢复执行...")
        
        # 收集所有待处理的工具调用信息
        all_pending_tool_calls = []
        all_tool_results = []
        
        for tool_entry in pending_tools:
            try:
                print(f"🔄 恢复执行工具: {tool_entry.name}")
                
                # 重新构造工具调用对象
                from baseService.llm_client import ToolCall
                tool_call = ToolCall(
                    id=tool_entry.id,
                    name=tool_entry.name,
                    arguments=tool_entry.arguments
                )
                
                # 执行工具
                tool_result = tool_executor(tool_call, task_id)
                
                # 更新工具状态
                self.update_tool_call_status(conversation_state, tool_entry.id, "completed", tool_result, logger_func)
                
                # 收集工具调用信息和结果
                tool_call_info = {
                    "id": tool_entry.id,
                    "name": tool_entry.name,
                    "arguments": tool_entry.arguments
                }
                all_pending_tool_calls.append(tool_call_info)
                all_tool_results.append({
                    "tool_name": tool_entry.name,
                    "tool_id": tool_entry.id,
                    "result": tool_result
                })
                
                print(f"✅ 工具 {tool_entry.name} 恢复执行完成")
                
            except Exception as e:
                print(f"❌ 恢复执行工具 {tool_entry.name} 失败: {e}")
                # 更新状态为失败
                self.update_tool_call_status(conversation_state, tool_entry.id, "failed", {"status": "error", "error_information": str(e)}, logger_func)
                
                # 收集失败的工具结果
                all_tool_results.append({
                    "tool_name": tool_entry.name,
                    "tool_id": tool_entry.id,
                    "result": {"status": "error", "error_information": str(e)}
                })
        
        # 更新对话历史
        updated_history = conversation_state.history.copy()
        
        # 如果有工具调用，按照正确的格式添加到对话历史
        if all_pending_tool_calls:
            # Assistant消息：包含工具调用信息
            content_with_tool_calls = {
                "text": "恢复执行pending工具调用",
                "tool_calls": all_pending_tool_calls
            }
            
            updated_history.append(ChatMessage(
                role="assistant",
                content=json.dumps(content_with_tool_calls, ensure_ascii=False)
            ))
            
            # User消息：只包含工具执行结果
            try:
                tool_results_str = json.dumps({"tool_results": all_tool_results}, ensure_ascii=False)
            except:
                tool_results_str = str(all_tool_results)
            
            updated_history.append(ChatMessage(
                role="user",
                content=f'工具执行完成，结果：{tool_results_str}'
            ))
        
        # 更新对话状态中的历史
        conversation_state.history = updated_history
        
        return updated_history
    
    def list_conversation_files(self) -> List[str]:
        """
        列出所有保存的对话文件
        
        Returns:
            List[str]: 对话文件列表
        """
        try:
            if not os.path.exists(self.conversation_dir):
                return []
            
            files = [f for f in os.listdir(self.conversation_dir) if f.endswith('.json')]
            return sorted(files)
        except Exception as e:
            print(f"⚠️ 列出对话文件失败: {e}")
            return []
    
    def cleanup_conversation(self, task_id: str, user_input: str, logger_func: Optional[Callable[[str], None]] = None) -> bool:
        """
        清理已完成的对话文件（可选）
        
        Args:
            task_id: 任务ID
            user_input: 用户输入
            logger_func: 日志记录函数（可选）
            
        Returns:
            bool: 是否清理成功
        """
        try:
            conversation_file = self._generate_conversation_filename(task_id, user_input)
            if os.path.exists(conversation_file):
                os.remove(conversation_file)
                if logger_func:
                    logger_func(f"🗑️ 已清理对话历史文件: {conversation_file}")
                return True
            return False
        except Exception as e:
            if logger_func:
                logger_func(f"清理对话历史文件失败: {str(e)}")
            return False
    
    def create_conversation_state(self, agent_name: str, agent_id: str, system_prompt: str, available_tools: List[str], model_type: str, task_id: str, user_input: str, current_turn: int = 0, history: List[ChatMessage] = None) -> ConversationState:
        """
        创建新的对话状态
        
        Args:
            agent_name: Agent名称
            agent_id: Agent ID
            system_prompt: 系统提示
            available_tools: 可用工具列表
            model_type: 模型类型
            task_id: 任务ID
            user_input: 用户输入
            current_turn: 当前轮次
            history: 对话历史
            
        Returns:
            ConversationState: 新创建的对话状态
        """
        if history is None:
            history = []
        
        return ConversationState(
            agent_name=agent_name,
            agent_id=agent_id,
            system_prompt=system_prompt,
            available_tools=available_tools,
            model_type=model_type,
            task_id=task_id,
            user_input=user_input,
            current_turn=current_turn,
            history=history
        )
