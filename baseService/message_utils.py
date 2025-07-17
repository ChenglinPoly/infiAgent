#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息处理工具模块
用于处理对话消息，确保 assistant 和 user 交替进行
"""

from typing import List, Dict, Union
from dataclasses import dataclass


@dataclass
class Message:
    """消息数据类"""
    role: str  # "user", "assistant", "system"
    content: str


def merge_consecutive_user_messages(messages: List[Dict[str, str]], 
                                   separator: str = "\n\n") -> List[Dict[str, str]]:
    """
    合并连续的用户消息，确保 assistant 和 user 交替进行
    
    Args:
        messages: 消息列表，每个消息包含 role 和 content 字段
        separator: 合并多个连续消息时使用的分隔符
    
    Returns:
        处理后的消息列表，确保没有连续的相同角色消息
    """
    if not messages:
        return []
    
    # 处理后的消息列表
    processed_messages = []
    
    # 当前累积的消息内容
    current_role = None
    current_content_parts = []
    
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        
        # 跳过空消息
        if not content.strip():
            continue
        
        # 如果角色相同，累积内容
        if role == current_role:
            current_content_parts.append(content)
        else:
            # 角色不同，先保存之前累积的消息
            if current_role is not None and current_content_parts:
                merged_content = separator.join(current_content_parts)
                processed_messages.append({
                    "role": current_role,
                    "content": merged_content
                })
            
            # 开始新的累积
            current_role = role
            current_content_parts = [content]
    
    # 处理最后一组消息
    if current_role is not None and current_content_parts:
        merged_content = separator.join(current_content_parts)
        processed_messages.append({
            "role": current_role,
            "content": merged_content
        })
    
    return processed_messages


def ensure_alternating_roles(messages: List[Dict[str, str]], 
                            default_assistant_response: str = "我明白了，请继续。") -> List[Dict[str, str]]:
    """
    确保消息中 assistant 和 user 严格交替
    如果出现连续的 user 消息，会先合并它们，然后在需要时插入默认的 assistant 响应
    
    Args:
        messages: 消息列表
        default_assistant_response: 当需要插入 assistant 响应时使用的默认内容
    
    Returns:
        处理后的消息列表，确保角色严格交替
    """
    # 首先合并连续的相同角色消息
    merged_messages = merge_consecutive_user_messages(messages)
    
    if not merged_messages:
        return []
    
    alternating_messages = []
    last_role = None
    
    for message in merged_messages:
        current_role = message["role"]
        
        # system 消息特殊处理，可以出现在任何位置
        if current_role == "system":
            alternating_messages.append(message)
            continue
        
        # 如果出现连续的 user 消息（在合并后仍然有问题）
        if current_role == "user" and last_role == "user":
            # 插入一个默认的 assistant 响应
            alternating_messages.append({
                "role": "assistant",
                "content": default_assistant_response
            })
        
        # 如果出现连续的 assistant 消息
        elif current_role == "assistant" and last_role == "assistant":
            # 这种情况比较少见，但我们可以跳过这条消息或合并
            # 这里选择合并到上一条消息
            if alternating_messages and alternating_messages[-1]["role"] == "assistant":
                alternating_messages[-1]["content"] += "\n\n" + message["content"]
                continue
        
        alternating_messages.append(message)
        last_role = current_role
    
    return alternating_messages


def clean_tool_calls_from_content(content: str) -> str:
    """
    从消息内容中清理 tool_calls 相关的内容
    保留工具名和参数的简要信息（不超过50个字符）
    
    Args:
        content: 原始消息内容
    
    Returns:
        清理后的消息内容，包含简化的工具调用信息
    """
    import re
    import json
    
    # 检查是否是纯 JSON 格式的 tool_calls
    try:
        parsed = json.loads(content.strip())
        if isinstance(parsed, dict) and "tool_calls" in parsed:
            tool_calls = parsed["tool_calls"]
            if isinstance(tool_calls, list) and tool_calls:
                # 提取工具调用的简要信息
                summaries = []
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict):
                        tool_name = tool_call.get("name", "unknown")
                        # 简化参数信息，智能处理不同类型的参数
                        args = tool_call.get("arguments", {})
                        if isinstance(args, dict):
                            # 智能处理不同参数
                            key_args = []
                            for k, v in args.items():
                                if k == 'content' and isinstance(v, str) and len(v) > 50:
                                    # content 字段显示长度信息
                                    key_args.append(f"{k}=[{len(v)}字符]")
                                elif k in ['file_path', 'task_id', 'tool_name']:
                                    # 重要字段完整显示
                                    key_args.append(f"{k}={str(v)}")
                                else:
                                    # 其他字段截断显示
                                    key_args.append(f"{k}={str(v)[:15]}")
                                
                                # 只显示前3个参数
                                if len(key_args) >= 3:
                                    break
                            
                            arg_summary = ", ".join(key_args)
                            if len(arg_summary) > 60:
                                arg_summary = arg_summary[:60] + "..."
                        else:
                            arg_summary = str(args)[:20]
                        
                        summary = f"{tool_name}({arg_summary})"
                        if len(summary) > 45:
                            summary = summary[:45] + "..."
                        summaries.append(summary)
                
                # 组合所有工具调用的简要信息
                result = "[工具调用: " + ", ".join(summaries) + "]"
                if len(result) > 80:
                    result = result[:77] + "...]"
                return result
            
            # 如果tool_calls为空或格式不对
            return "[工具调用: 无效格式]"
    except json.JSONDecodeError:
        pass
    
    # 使用正则表达式查找并替换 tool_calls 模式
    patterns = [
        (r'\{"tool_calls"\s*:\s*\[.*?\]\}', lambda m: "[工具调用: JSON格式]"),
        (r'"tool_calls"\s*:\s*\[.*?\]', lambda m: "[工具调用]"),
    ]
    
    cleaned_content = content
    for pattern, replacement in patterns:
        if re.search(pattern, cleaned_content, flags=re.DOTALL):
            cleaned_content = re.sub(pattern, replacement(""), cleaned_content, flags=re.DOTALL)
    
    return cleaned_content.strip()


def preprocess_messages_for_llm(messages: List[Dict[str, str]], 
                               clean_tool_calls: bool = True,
                               ensure_alternating: bool = True) -> List[Dict[str, str]]:
    """
    为 LLM 预处理消息列表
    
    Args:
        messages: 原始消息列表
        clean_tool_calls: 是否清理 tool_calls 内容
        ensure_alternating: 是否确保角色交替
    
    Returns:
        处理后的消息列表
    """
    processed_messages = []
    
    for message in messages:
        processed_message = message.copy()
        
        # 清理 tool_calls 内容
        if clean_tool_calls:
            cleaned_content = processed_message["content"]
            # 即使清理后内容为空，也要保留消息以维持角色序列
            processed_message["content"] = cleaned_content if cleaned_content else "[空消息]"
            processed_messages.append(processed_message)
        else:
            processed_messages.append(processed_message)
    
    # 确保角色交替
    if ensure_alternating:
        processed_messages = ensure_alternating_roles(processed_messages)
    
    return processed_messages


# 使用示例和测试
def test_message_processing():
    """测试消息处理功能"""
    print("🧪 测试消息处理功能")
    
    # 测试数据：包含连续用户消息的对话
    test_messages = [
    {
      "role": "user",
      "content": "\n\"我已成功完成了收集cyber-physical Internet物流问题相关文献的任务。根据用户的研究需求，我使用paper_search_agent工具收集了8篇高质量的学术论文，涵盖了四个关键方面：\\n\\n1. CPI在物流路由优化方面的应用：\\n   - \\\"Routing protocols for B2B e-commerce logistics in cyber-physical internet(CPI)\\\" - 研究CPI环境下B2B电子商务物流的路由协议\\n   - \\\"A carbon-aware routing protocol for optimizing carbon emissions in modular construction logistics\\\" - 探讨碳排放优化的路由协议在模块化建筑物流中的应用\\n\\n2. CPI与物联网(IoT)在物流中的集成：\\n   - \\\"Cyber-Physical Internet(CPI)-enabled logistics infrastructure integration framework in the greater bay area\\\" - 提出了大湾区CPI赋能的物流基础设施集成框架\\n   - \\\"The research landscape around the physical internet–a bibliometric analysis\\\" - 文献综述分析了物理互联网研究领域，包括与物联网的集成\\n\\n3. CPI支持的智能物流系统：\\n   - \\\"Cyber-physical internet based intelligent operation platform for off-site construction supply chain management\\\" - 介绍了基于CPI的非现场建筑供应链管理智能运营平台\\n   - \\\"Operations with physical internet\\\" - 探讨了物理互联网环境下的运营方法\\n\\n4. 物流中的实时数据处理与决策：\\n   - \\\"Out-of-Order Architecture for Real-Time Data-Driven Resilient Planning and Scheduling of Cyber-Physical Manufacturing Systems\\\" - 提出了一种用于实时数据驱动的弹性规划和调度的乱序架构\\n   - \\\"Cyber-Physical Internet Asset Services and Hosts: Creation, Configuration, Execution\\\" - 讨论了CPI资产服务和主机的创建、配置和执行\\n\\n所有论文都已成功下载并保存在'upload'目录中，文件格式为PDF。judge_agent已确认这些论文符合原始任务要求，能为用户研究cyber-physical Internet的物流问题提供全面的理论基础、最新研究进展和应用案例。这些资料不仅可以支持后续idea的产生，也适合作为related work的参考材料。用户的最初研究需求是：我想要研究 cyber-physical Internet 的物流问题\n"
    },
    {
      "role": "user",
      "content": "继续,注意不要在内容中调用工具，绝对不要输出 tool_calls字段影响解析"
    },
    {
      "role": "assistant",
      "content": "{\"tool_calls\": [{\"id\": \"toolu_bdrk_01Kx55xnqPJQejSNX9qYkFad\", \"name\": \"dir_list\", \"arguments\": {\"dir_path\": \"upload\", \"recursive\": false}}]}"
    },
    {
      "role": "user",
      "content": "继续,注意不要在内容中调用工具，绝对不要输出 tool_calls字段影响解析"
    }
  ]
    
    
    
    # 测试完整预处理
    print("\n✨ 完整预处理后:")
    processed = preprocess_messages_for_llm(test_messages)
    print(processed)
    
    print("\n✅ 测试完成!")


if __name__ == "__main__":
    test_message_processing() 