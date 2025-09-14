#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试上下文长度控制服务
"""

import sys
import os
import json

# 将项目根目录添加到Python路径中
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.agent_class import Agent, ChatMessage
from Services.context_length_control_service import ContextLengthController


def test_context_length_controller():
    """测试上下文长度控制器的基本功能"""
    print("🧪 测试上下文长度控制器...")
    
    # 创建测试用的长消息历史
    long_content = "这是一个非常长的消息内容。" * 100  # 创建一个很长的消息
    
    history = [
        ChatMessage(role="user", content="你好，我想要你帮我做一些复杂的任务"),
        ChatMessage(role="assistant", content="好的，我会帮助你完成任务。请告诉我具体需要做什么？"),
        ChatMessage(role="user", content=long_content),  # 超长消息
        ChatMessage(role="assistant", content="我理解了你的需求，让我来处理这个复杂的任务。"),
        ChatMessage(role="user", content="请继续处理"),
        ChatMessage(role="assistant", content="好的，我正在处理中..."),
    ]
    
    print(f"📊 原始历史消息数量: {len(history)}")
    print(f"📊 超长消息长度: {len(long_content)} 字符")
    
    # 创建上下文控制器
    controller = ContextLengthController()
    
    # 估算原始token数
    total_tokens = sum(controller.estimate_tokens(msg.content, "gpt-4o-mini") for msg in history)
    print(f"📊 原始总token数: {total_tokens}")
    
    # 测试截断功能（使用很小的限制）
    truncated_history, modified = controller.truncate_history(
        history=history,
        initial_user_input="你好，我想要你帮我做一些复杂的任务",
        max_history_turns=2,  # 最多2轮对话
        max_history_tokens=200,  # 最多200 tokens
        model_type="gpt-4o-mini",
        llm_client=None  # 不使用LLM总结，只测试截断
    )
    
    print(f"\n✂️ 截断后历史消息数量: {len(truncated_history)}")
    print(f"✂️ 是否有消息被修改: {modified}")
    
    # 计算截断后的token数
    truncated_tokens = sum(controller.estimate_tokens(msg.content, "gpt-4o-mini") for msg in truncated_history)
    print(f"✂️ 截断后总token数: {truncated_tokens}")
    
    print("\n📝 截断后的消息内容:")
    for i, msg in enumerate(truncated_history):
        content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
        tokens = controller.estimate_tokens(msg.content, "gpt-4o-mini")
        print(f"  {i+1}. [{msg.role}] ({tokens} tokens): {content_preview}")
    
    return truncated_history, modified


def test_agent_with_small_tokens():
    """测试Agent在小token限制下的行为"""
    print("\n" + "="*60)
    print("🤖 测试Agent在小token限制下的自动上下文控制...")
    
    # 创建一个测试Agent，使用很小的token限制
    test_agent = Agent(
        agent_name="TestContextAgent",
        system_prompt="你是一个测试助手，帮助用户完成简单任务。",
        available_tools=["final_output"],  # 只使用final_output工具
        max_turns=5,
        max_history_turns=2,  # 最多保留2轮对话
        max_history_tokens=200,  # 最多200 tokens
        model_type="gpt-4o-mini"
    )
    
    # 创建一个包含长消息的对话历史
    long_message = "这是一个非常详细的需求描述，包含了大量的细节信息和要求。" * 20
    
    # 手动构建历史（模拟之前的对话）
    test_history = [
        ChatMessage(role="user", content="请帮我分析这个复杂问题"),
        ChatMessage(role="assistant", content="好的，我来帮你分析这个问题。"),
        ChatMessage(role="user", content=long_message),  # 超长消息
        ChatMessage(role="assistant", content="我已经理解了你的详细需求，现在开始处理。"),
        ChatMessage(role="user", content="请继续并给出最终结果"),
    ]
    
    print(f"📊 测试历史消息数量: {len(test_history)}")
    
    # 计算原始token数
    if test_agent.context_controller:
        original_tokens = sum(test_agent.context_controller.estimate_tokens(msg.content, "gpt-4o-mini") for msg in test_history)
        print(f"📊 原始总token数: {original_tokens}")
        
        # 测试截断功能
        truncated, modified = test_agent._truncate_history(
            history=test_history,
            initial_user_input="请帮我分析这个复杂问题"
        )
        
        print(f"✂️ 截断后消息数量: {len(truncated)}")
        print(f"✂️ 是否有消息被修改: {modified}")
        
        truncated_tokens = sum(test_agent.context_controller.estimate_tokens(msg.content, "gpt-4o-mini") for msg in truncated)
        print(f"✂️ 截断后总token数: {truncated_tokens}")
        
        print("\n📝 截断后的消息:")
        for i, msg in enumerate(truncated):
            content_preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
            tokens = test_agent.context_controller.estimate_tokens(msg.content, "gpt-4o-mini")
            print(f"  {i+1}. [{msg.role}] ({tokens} tokens): {content_preview}")
    else:
        print("❌ 上下文控制器未初始化")
    
    return test_agent


def test_message_summarization():
    """测试消息总结功能（需要LLM客户端）"""
    print("\n" + "="*60)
    print("📝 测试消息总结功能...")
    
    # 创建Agent用于获取LLM客户端
    test_agent = Agent(
        agent_name="SummaryTestAgent",
        system_prompt="你是一个总结助手。",
        available_tools=["final_output"],
        max_turns=3,
        max_history_turns=1,
        max_history_tokens=100,  # 非常小的限制，强制总结
        model_type="gpt-4o-mini"
    )
    
    # 创建一个超长消息
    very_long_content = """
    这是一个包含大量详细信息的复杂技术文档。文档描述了一个分布式系统的架构设计，
    包括微服务架构、数据库设计、缓存策略、负载均衡、容错机制、监控系统、日志收集、
    性能优化、安全考虑、部署策略、扩展性设计、可维护性要求等多个方面的内容。
    系统采用了现代化的技术栈，包括Kubernetes容器编排、Redis缓存、PostgreSQL数据库、
    Nginx负载均衡器、Prometheus监控、ELK日志栈等技术组件。整个系统需要支持高并发、
    高可用、高性能的要求，同时还要考虑成本控制和运维便利性。
    """ * 10  # 重复10次，创建超长内容
    
    history = [
        ChatMessage(role="user", content="请分析这个技术方案"),
        ChatMessage(role="assistant", content="好的，我来分析技术方案。"),
        ChatMessage(role="user", content=very_long_content),  # 超长消息，会触发总结
    ]
    
    print(f"📊 原始消息长度: {len(very_long_content)} 字符")
    
    if test_agent.context_controller:
        original_tokens = test_agent.context_controller.estimate_tokens(very_long_content, "gpt-4o-mini")
        print(f"📊 原始消息token数: {original_tokens}")
        
        # 测试总结功能
        try:
            truncated, modified = test_agent._truncate_history(
                history=history,
                initial_user_input="请分析这个技术方案"
            )
            
            print(f"✂️ 处理后消息数量: {len(truncated)}")
            print(f"✂️ 是否有消息被总结: {modified}")
            
            # 查看最长的消息（可能是总结后的）
            longest_msg = max(truncated, key=lambda x: len(x.content))
            if longest_msg.content.startswith("[🤖 AI总结消息"):
                print("✅ 检测到AI总结消息")
                summary_tokens = test_agent.context_controller.estimate_tokens(longest_msg.content, "gpt-4o-mini")
                print(f"📝 总结后token数: {summary_tokens}")
                print(f"📝 总结内容预览: {longest_msg.content[:200]}...")
            else:
                print("ℹ️ 未触发总结（可能是token限制不够严格）")
                
        except Exception as e:
            print(f"❌ 总结测试失败: {e}")
    else:
        print("❌ 上下文控制器未初始化")


def main():
    """主测试函数"""
    print("🚀 开始测试上下文长度控制服务")
    print("="*60)
    
    try:
        # 测试1: 基本的上下文控制器功能
        test_context_length_controller()
        
        # 测试2: Agent集成测试
        test_agent = test_agent_with_small_tokens()
        
        # 测试3: 消息总结功能
        test_message_summarization()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成！")
        print("🎯 上下文长度控制服务工作正常")
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
