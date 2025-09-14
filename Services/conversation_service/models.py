#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conversation Service 数据模型
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class ChatMessage:
    """聊天消息数据类"""
    role: str  # "user", "assistant", "system"
    content: str


@dataclass
class ToolCallEntry:
    """工具调用条目"""
    id: str
    name: str
    arguments: Dict[str, Any]
    status: str  # "pending", "completed", "failed"
    turn: int
    timestamp: str
    result: Optional[Dict[str, Any]] = None
    completed_timestamp: Optional[str] = None


@dataclass
class ConversationState:
    """对话状态 - 包含所有需要持久化的信息"""
    # 基本信息
    agent_name: str
    agent_id: Optional[str]
    system_prompt: str
    available_tools: List[str]
    model_type: str
    task_id: str
    user_input: str
    current_turn: int
    
    # 对话历史
    history: List[ChatMessage]
    
    # 工具调用日志
    tool_calls_log: List[ToolCallEntry] = field(default_factory=list)
    
    # 时间戳
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式用于JSON序列化"""
        return {
            "agent_name": self.agent_name,
            "agent_id": self.agent_id,
            "system_prompt": self.system_prompt,
            "available_tools": self.available_tools,
            "model_type": self.model_type,
            "task_id": self.task_id,
            "user_input": self.user_input,
            "current_turn": self.current_turn,
            "history": [
                {"role": msg.role, "content": msg.content}
                for msg in self.history
            ],
            "tool_calls_log": [
                {
                    "id": tool.id,
                    "name": tool.name,
                    "arguments": tool.arguments,
                    "status": tool.status,
                    "turn": tool.turn,
                    "timestamp": tool.timestamp,
                    "result": tool.result,
                    "completed_timestamp": tool.completed_timestamp
                }
                for tool in self.tool_calls_log
            ],
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationState':
        """从字典创建ConversationState对象"""
        history = [
            ChatMessage(role=msg["role"], content=msg["content"])
            for msg in data.get("history", [])
        ]
        
        tool_calls_log = [
            ToolCallEntry(
                id=tool["id"],
                name=tool["name"],
                arguments=tool["arguments"],
                status=tool["status"],
                turn=tool["turn"],
                timestamp=tool["timestamp"],
                result=tool.get("result"),
                completed_timestamp=tool.get("completed_timestamp")
            )
            for tool in data.get("tool_calls_log", [])
        ]
        
        return cls(
            agent_name=data["agent_name"],
            agent_id=data.get("agent_id"),
            system_prompt=data["system_prompt"],
            available_tools=data["available_tools"],
            model_type=data["model_type"],
            task_id=data["task_id"],
            user_input=data["user_input"],
            current_turn=data["current_turn"],
            history=history,
            tool_calls_log=tool_calls_log,
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )
