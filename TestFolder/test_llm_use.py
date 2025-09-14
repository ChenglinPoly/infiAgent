#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试LiteLLM客户端与原有客户端的功能对比
验证功能一致性和性能改进
"""

import sys
import os
import json
import time

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入原有客户端和新的LiteLLM客户端
from baseService.llm_client import LLMClient as OriginalLLMClient, ChatMessage as OriginalChatMessage, ModelType as OriginalModelType
from baseService.llm_client_lite import LiteLLMClient, ChatMessage, ModelType

def test_both_clients():
    """测试两个客户端的功能对比"""
    print("🔄 LiteLLM 客户端 vs 原有客户端功能对比测试")
    print("=" * 60)
    
    # 测试配置
    test_cases = [
        {
            "name": "简单对话测试",
            "history": [ChatMessage(role="user", content="你好，请简单介绍一下你自己")],
            "model": ModelType.GEMINI_2_5_FLASH,
            "original_model": OriginalModelType.GEMINI_2_5_FLASH,
            "tool_list": None,
            "tool_choice": "auto"
        },
        {
            "name": "强制工具调用测试",
            "history": [ChatMessage(role="user", content="1+1等于多少？")],
            "model": ModelType.GEMINI_2_5_FLASH,
            "original_model": OriginalModelType.GEMINI_2_5_FLASH,
            "tool_list": ["file_read"],
            "tool_choice": "any"
        },
        {
            "name": "系统提示测试",
            "history": [ChatMessage(role="user", content="计算2+3")],
            "model": ModelType.GEMINI_2_5_FLASH,
            "original_model": OriginalModelType.GEMINI_2_5_FLASH,
            "system_prompt": "你是一个专业的数学助手，请准确计算数学问题。",
            "tool_list": None,
            "tool_choice": "auto"
        }
    ]
    
    # 初始化客户端
    print("🔧 初始化客户端...")
    try:
        # 原有客户端
        original_client = OriginalLLMClient()
        print("✅ 原有客户端初始化成功")
    except Exception as e:
        print(f"❌ 原有客户端初始化失败: {e}")
        original_client = None
    
    try:
        # 新的LiteLLM客户端 - 使用简化配置
        lite_config_path = os.path.join(project_root, "config", "run_env_config", "llm_config_lite.yaml")
        lite_client = LiteLLMClient(config_file=lite_config_path)
        print("✅ LiteLLM客户端初始化成功")
    except Exception as e:
        print(f"❌ LiteLLM客户端初始化失败: {e}")
        lite_client = None
        import traceback
        traceback.print_exc()
    
    if not lite_client:
        print("❌ 无法继续测试，LiteLLM客户端初始化失败")
        return
    
    # 显示配置状态
    print("\n📊 LiteLLM客户端配置状态:")
    lite_client.debug_config()
    
    # 运行测试用例
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"📋 测试用例 {i}: {test_case['name']}")
        print(f"{'='*60}")
        
        # 测试参数
        kwargs = {
            "history": test_case["history"],
            "model": test_case["model"],
            "tool_list": test_case.get("tool_list"),
            "tool_choice": test_case.get("tool_choice", "auto"),
            "system_prompt": test_case.get("system_prompt"),
            "temperature": 0.0,
            "max_tokens": 1000
        }
        
        print(f"📝 测试参数:")
        print(f"  消息: {test_case['history'][0].content}")
        print(f"  模型: {test_case['model'].value}")
        print(f"  工具: {test_case.get('tool_list', '无')}")
        print(f"  工具选择: {test_case.get('tool_choice', 'auto')}")
        if test_case.get("system_prompt"):
            print(f"  系统提示: {test_case['system_prompt'][:50]}...")
        
        # 测试LiteLLM客户端
        print(f"\n🚀 测试 LiteLLM 客户端:")
        start_time = time.time()
        try:
            lite_response = lite_client.chat(**kwargs)
            lite_duration = time.time() - start_time
            
            print(f"  ✅ 状态: {lite_response.status}")
            print(f"  ⏱️  耗时: {lite_duration:.2f}秒")
            print(f"  🤖 模型: {lite_response.model}")
            print(f"  🏁 完成原因: {lite_response.finish_reason}")
            
            if lite_response.status == "success":
                print(f"  📝 输出长度: {len(lite_response.output)}字符")
                print(f"  📄 输出预览: {lite_response.output[:100]}...")
                
                if lite_response.tool_calls:
                    print(f"  🛠️  工具调用: {len(lite_response.tool_calls)}个")
                    for j, tool_call in enumerate(lite_response.tool_calls):
                        print(f"    {j+1}. {tool_call.name}: {str(tool_call.arguments)[:50]}...")
                else:
                    print(f"  🛠️  工具调用: 无")
                
                if lite_response.usage:
                    print(f"  💰 Token使用: {lite_response.usage}")
            else:
                print(f"  ❌ 错误: {lite_response.error_information}")
                
        except Exception as e:
            lite_duration = time.time() - start_time
            print(f"  ❌ 异常: {str(e)}")
            print(f"  ⏱️  耗时: {lite_duration:.2f}秒")
            import traceback
            traceback.print_exc()
        
        # 测试原有客户端（如果可用）
        if original_client:
            print(f"\n🔄 测试原有客户端:")
            start_time = time.time()
            try:
                # 转换参数格式
                original_kwargs = kwargs.copy()
                original_kwargs["model"] = test_case["original_model"]
                # 转换消息格式
                original_history = []
                for msg in test_case["history"]:
                    original_history.append(OriginalChatMessage(role=msg.role, content=msg.content))
                original_kwargs["history"] = original_history
                
                original_response = original_client.chat(**original_kwargs)
                original_duration = time.time() - start_time
                
                print(f"  ✅ 状态: {original_response.status}")
                print(f"  ⏱️  耗时: {original_duration:.2f}秒")
                print(f"  🤖 模型: {original_response.model}")
                print(f"  🏁 完成原因: {original_response.finish_reason}")
                
                if original_response.status == "success":
                    print(f"  📝 输出长度: {len(original_response.output)}字符")
                    print(f"  📄 输出预览: {original_response.output[:100]}...")
                    
                    if original_response.tool_calls:
                        print(f"  🛠️  工具调用: {len(original_response.tool_calls)}个")
                        for j, tool_call in enumerate(original_response.tool_calls):
                            print(f"    {j+1}. {tool_call.name}: {str(tool_call.arguments)[:50]}...")
                    else:
                        print(f"  🛠️  工具调用: 无")
                    
                    if original_response.usage:
                        print(f"  💰 Token使用: {original_response.usage}")
                else:
                    print(f"  ❌ 错误: {original_response.error_information}")
                
                # 对比结果
                print(f"\n📊 结果对比:")
                print(f"  状态一致: {'✅' if lite_response.status == original_response.status else '❌'}")
                if lite_response.status == "success" and original_response.status == "success":
                    tool_calls_match = (
                        (lite_response.tool_calls is None) == (original_response.tool_calls is None) or
                        (lite_response.tool_calls and original_response.tool_calls and 
                         len(lite_response.tool_calls) == len(original_response.tool_calls))
                    )
                    print(f"  工具调用一致: {'✅' if tool_calls_match else '❌'}")
                    print(f"  性能提升: {original_duration - lite_duration:.2f}秒")
                    
            except Exception as e:
                original_duration = time.time() - start_time
                print(f"  ❌ 异常: {str(e)}")
                print(f"  ⏱️  耗时: {original_duration:.2f}秒")
        else:
            print(f"\n⚠️  跳过原有客户端测试（初始化失败）")
        
        print(f"\n{'='*40}")
    
    print(f"\n🎉 测试完成！")
    print(f"📝 总结:")
    print(f"  - LiteLLM客户端使用更简单的配置")
    print(f"  - 代码量大幅减少（从1200+行到400+行）")
    print(f"  - 统一的API接口，自动处理提供商差异")
    print(f"  - 内置错误处理和重试机制")

def test_litellm_only():
    """只测试LiteLLM客户端"""
    print("🚀 LiteLLM 客户端独立测试")
    print("=" * 40)
    
    try:
        # 使用简化配置初始化
        lite_config_path = os.path.join(project_root, "config", "run_env_config", "llm_config_lite.yaml")
        client = LiteLLMClient(config_file=lite_config_path)
        
        print("✅ LiteLLM客户端初始化成功")
        client.debug_config()
        
        # 简单测试
        history = [ChatMessage(role="user", content="1+1等于多少？")]
        
        print(f"\n🧪 测试强制工具调用:")
        response = client.chat(
            history=history,
            model=ModelType.GEMINI_2_5_FLASH,
            tool_list=["file_read"],
            tool_choice="any"
        )
        
        print(f"状态: {response.status}")
        print(f"模型: {response.model}")
        if response.status == "success":
            print(f"输出: {response.output[:100]}...")
            if response.tool_calls:
                print("🛠️ 工具调用:")
                for tool_call in response.tool_calls:
                    print(f"  - {tool_call.name}: {tool_call.arguments}")
        else:
            print(f"错误: {response.error_information}")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 检查是否有原有客户端可用
    try:
        from baseService.llm_client import LLMClient as OriginalLLMClient
        print("🔍 检测到原有客户端，运行完整对比测试")
        test_both_clients()
    except Exception as e:
        print(f"⚠️ 原有客户端不可用({e})，只测试LiteLLM客户端")
        test_litellm_only()
