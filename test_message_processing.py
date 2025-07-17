#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息预处理测试
"""

from baseService.llm_client import LLMClient, ChatMessage, ModelType
from baseService.message_utils import preprocess_messages_for_llm

def test_message_preprocessing():
    """测试消息预处理功能"""
    print("🧪 消息预处理测试")
    print("=" * 50)
    
    # 测试场景1：连续用户消息
    print("\n📝 场景1：连续用户消息合并")
    messages1 = [
        ChatMessage(role="user", content="创建一个图"),
        ChatMessage(role="user", content="继续,注意不要在内容中调用工具"), 
        ChatMessage(role="assistant", content="好的，我来创建图表"),
        ChatMessage(role="user", content="请继续"),
    ]
    
    print("原始消息:")
    for i, msg in enumerate(messages1):
        print(f"  {i+1}. [{msg.role}] {msg.content}")
    
    # 转换为字典格式并预处理
    message_dicts1 = [{"role": msg.role, "content": msg.content} for msg in messages1]
    processed1 = preprocess_messages_for_llm(message_dicts1, clean_tool_calls=True, ensure_alternating=True)
    
    print("\n处理后消息:")
    for i, msg in enumerate(processed1):
        print(f"  {i+1}. [{msg['role']}] {msg['content']}")
    
    # 测试场景2：包含tool_calls内容的消息
    print("\n" + "=" * 50)
    print("📝 场景2：清理tool_calls内容")
    messages2 = [
        ChatMessage(role="user", content="帮我写一个文件"),
        ChatMessage(role="assistant", content='我来帮您写文件\n{"tool_calls": [{"id": "123", "name": "file_write", "arguments": {"filename": "test.txt"}}]}'),
        ChatMessage(role="user", content="谢谢"),
    ]
    
    print("原始消息:")
    for i, msg in enumerate(messages2):
        print(f"  {i+1}. [{msg.role}] {msg.content}")
    
    message_dicts2 = [{"role": msg.role, "content": msg.content} for msg in messages2]
    processed2 = preprocess_messages_for_llm(message_dicts2, clean_tool_calls=True, ensure_alternating=True)
    
    print("\n处理后消息:")
    for i, msg in enumerate(processed2):
        print(f"  {i+1}. [{msg['role']}] {msg['content']}")
    
    # 测试场景3：复杂混合情况
    print("\n" + "=" * 50)
    print("📝 场景3：复杂混合情况")
    messages3 = [
        ChatMessage(role="system", content="您是一个AI助手"),
        ChatMessage(role="user", content="创建一个图"),
        ChatMessage(role="user", content="继续,注意不要在内容中调用工具"),
        ChatMessage(role="assistant", content='好的，我来创建\n{"tool_calls": [{"id": "abc", "name": "plot_create"}]}'),
        ChatMessage(role="assistant", content="图表已经创建完成"),
        ChatMessage(role="user", content="很好"),
        ChatMessage(role="user", content="请继续优化"),
    ]
    
    print("原始消息:")
    for i, msg in enumerate(messages3):
        print(f"  {i+1}. [{msg.role}] {msg.content}")
    
    message_dicts3 = [{"role": msg.role, "content": msg.content} for msg in messages3]
    processed3 = preprocess_messages_for_llm(message_dicts3, clean_tool_calls=True, ensure_alternating=True)
    
    print("\n处理后消息:")
    for i, msg in enumerate(processed3):
        print(f"  {i+1}. [{msg['role']}] {msg['content']}")

def test_llm_client_preprocessing():
    """测试LLMClient中的预处理功能"""
    print("\n" + "=" * 50)
    print("🤖 LLMClient 预处理测试")
    
    client = LLMClient()
    
    # 创建有问题的消息历史
    problematic_history = [
        ChatMessage(role="user", content="创建一个图"),
        ChatMessage(role="user", content="继续,注意不要在内容中调用工具"),
        ChatMessage(role="assistant", content='{"tool_calls": [{"id": "123", "name": "test"}]}'),
        ChatMessage(role="user", content="请继续"),
    ]
    
    print("原始消息历史:")
    for i, msg in enumerate(problematic_history):
        print(f"  {i+1}. [{msg.role}] {msg.content}")
    
    # 使用LLMClient的预处理方法
    processed_by_client = client._preprocess_history(problematic_history)
    
    print("\nLLMClient预处理后:")
    for i, msg in enumerate(processed_by_client):
        print(f"  {i+1}. [{msg['role']}] {msg['content']}")

if __name__ == "__main__":
    test_message_preprocessing()
    test_llm_client_preprocessing() 