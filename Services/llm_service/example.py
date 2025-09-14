#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Service 使用示例
"""

import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from Services.llm_service import LLMWrapper, ToolCall, LLMResponse
from Services.llm_service.config import LLMServiceConfig

def example_native_tool_call():
    """原生工具调用示例"""
    print("=== 原生工具调用示例 ===")
    
    # 初始化包装器
    wrapper = LLMWrapper()
    
    # 定义工具
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取指定城市的天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称"
                        },
                        "unit": {
                            "type": "string",
                            "description": "温度单位",
                            "enum": ["celsius", "fahrenheit"]
                        }
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    
    # 准备消息
    messages = [
        {"role": "user", "content": "请帮我查询北京的天气"}
    ]
    
    # 发送请求（使用原生工具调用）
    response = wrapper.chat(
        messages=messages,
        model="gpt-3.5-turbo",  # 直接使用模型名称
        tools=tools,
        tool_call_capability=True,  # 支持原生工具调用
        tool_choice="auto"
    )
    
    print(f"状态: {response.status}")
    print(f"模型: {response.model}")
    print(f"输出: {response.output}")
    print(f"完成原因: {response.finish_reason}")
    
    if response.tool_calls:
        print("工具调用:")
        for tool_call in response.tool_calls:
            print(f"  - ID: {tool_call.id}")
            print(f"  - 名称: {tool_call.name}")
            print(f"  - 参数: {tool_call.arguments}")
    
    if response.usage:
        print(f"Token 使用: {response.usage}")

def example_prompt_based_tool_call():
    """基于提示词的工具调用示例"""
    print("\n=== 基于提示词的工具调用示例 ===")
    
    # 初始化包装器
    wrapper = LLMWrapper()
    
    # 定义工具（同样的工具定义）
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "执行数学计算",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "要计算的数学表达式"
                        }
                    },
                    "required": ["expression"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "读取文件内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "文件路径"
                        },
                        "encoding": {
                            "type": "string",
                            "description": "文件编码",
                            "default": "utf-8"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        }
    ]
    
    # 准备消息
    messages = [
        {"role": "user", "content": "请计算 15 * 23 + 45"}
    ]
    
    # 发送请求（使用基于提示词的工具调用）
    response = wrapper.chat(
        messages=messages,
        model="some-model-without-native-tools",  # 假设这个模型不支持原生工具调用
        tools=tools,
        tool_call_capability=False,  # 不支持原生工具调用
        tool_choice="auto",
        prompt_language="zh"  # 中文提示词
    )
    
    print(f"状态: {response.status}")
    print(f"模型: {response.model}")
    print(f"输出: {response.output}")
    
    if response.tool_calls:
        print("解析出的工具调用:")
        for tool_call in response.tool_calls:
            print(f"  - ID: {tool_call.id}")
            print(f"  - 名称: {tool_call.name}")
            print(f"  - 参数: {tool_call.arguments}")

def example_config_usage():
    """配置使用示例"""
    print("\n=== 配置使用示例 ===")
    
    # 初始化配置管理器
    config = LLMServiceConfig()
    
    print("默认配置:")
    print(config.get_default_config())
    
    print("\nOpenAI 配置:")
    print(config.get_provider_config("openai"))
    
    print("\n可用模型:")
    models = config.get_available_models()
    for model in models[:5]:  # 只显示前5个
        print(f"  - {model}")
    
    print(f"\n总共 {len(models)} 个可用模型")

def example_with_custom_api():
    """自定义API使用示例"""
    print("\n=== 自定义API使用示例 ===")
    
    wrapper = LLMWrapper(timeout=2000, num_retries=5)
    
    messages = [
        {"role": "user", "content": "Hello, how are you?"}
    ]
    
    # 使用自定义API
    response = wrapper.chat(
        messages=messages,
        model="custom-model",
        api_key="your-custom-api-key",
        api_base="https://your-custom-api-endpoint.com/v1",
        temperature=0.7,
        max_tokens=100
    )
    
    print(f"状态: {response.status}")
    print(f"输出: {response.output}")
    if response.status == "error":
        print(f"错误信息: {response.error_information}")

def simple_test():
    """简单测试：测试原生支持和不支持toolcall的返回结构"""
    print("=== 简单测试：原生支持 vs 不支持 toolcall ===")
    
    # 初始化包装器
    wrapper = LLMWrapper()
    
    # 定义一个简单的工具
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "获取当前时间",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": "时区，例如：Asia/Shanghai"
                        }
                    },
                    "required": []
                }
            }
        }
    ]
    
    # 准备消息 - 使用更明确需要工具调用的场景
    messages = [
        {"role": "user", "content": "你好"}
    ]
    
    # 使用你的配置
    api_key = "sk-REDACTED"
    api_base = "https://proxy.infix-ai.xyz/v1"
    model = "gemini-2.5-flash"  # 测试 Claude 模型
    
    print("\n1. 测试原生工具调用支持:")
    print("-" * 40)
    
    try:
        response1 = wrapper.chat(
            messages=messages,
            model=model,
            api_key=api_key,
            api_base=api_base,
            tools=tools,
            tool_call_capability=True,  # 支持原生工具调用
            tool_choice="required"  # 强制调用工具
        )
        
        print(f"状态: {response1.status}")
        print(f"模型: {response1.model}")
        print(f"输出: {response1.output}")
        print(f"完成原因: {response1.finish_reason}")
        
        if response1.tool_calls:
            print("工具调用:")
            for tool_call in response1.tool_calls:
                print(f"  - ID: {tool_call.id}")
                print(f"  - 名称: {tool_call.name}")
                print(f"  - 参数: {tool_call.arguments}")
        else:
            print("没有工具调用")
        
        if response1.usage:
            print(f"Token 使用: {response1.usage}")
        
        if response1.status == "error":
            print(f"错误信息: {response1.error_information}")
    
    except Exception as e:
        print(f"原生工具调用测试出错: {e}")
    
    print("\n2. 测试基于提示词的工具调用:")
    print("-" * 40)
    
    try:
        response2 = wrapper.chat(
            messages=messages,
            model=model,
            api_key=api_key,
            api_base=api_base,
            tools=tools,
            tool_call_capability=False,  # 不支持原生工具调用
            tool_choice="required",  # 强制调用工具
            prompt_language="zh"
        )
        
        print(f"状态: {response2.status}")
        print(f"模型: {response2.model}")
        print(f"输出: {response2.output}")
        print(f"完成原因: {response2.finish_reason}")
        
        if response2.tool_calls:
            print("解析出的工具调用:")
            for tool_call in response2.tool_calls:
                print(f"  - ID: {tool_call.id}")
                print(f"  - 名称: {tool_call.name}")
                print(f"  - 参数: {tool_call.arguments}")
        else:
            print("没有解析出工具调用")
        
        if response2.usage:
            print(f"Token 使用: {response2.usage}")
        
        if response2.status == "error":
            print(f"错误信息: {response2.error_information}")
    
    except Exception as e:
        print(f"基于提示词的工具调用测试出错: {e}")

def main():
    """主函数"""
    print("LLM Service 简单测试")
    print("=" * 50)
    
    try:
        simple_test()
        print("\n测试完成！")
        
    except Exception as e:
        print(f"测试出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
