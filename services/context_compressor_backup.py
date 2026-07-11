#!/usr/bin/env python3
from utils.windows_compat import safe_print
# -*- coding: utf-8 -*-
"""
上下文压缩服务 - 智能压缩历史动作
策略：总结历史 + 保留最新
emmm主要是保底的压缩，直接截取的方法，目前是被弃用的
"""

import sys
import json
from typing import List, Dict
from pathlib import Path

# 确保可以导入其他模块
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from services.llm_client import SimpleLLMClient, ChatMessage
from utils.token_budget import count_tokens_text


class ContextCompressor:
    """上下文压缩器"""
    
    def __init__(self):
        """初始化压缩器"""
        self.llm_client = SimpleLLMClient()
        
        self.encoding = None
    
    def count_tokens(self, text: str) -> int:
        """统计文本的token数"""
        return count_tokens_text(str(text or ""))
    
    def compress_action_history(
        self,
        action_history: List[Dict],
        max_allowed_tokens: int
    ) -> List[Dict]:
        """
        压缩历史动作
        
        策略：
        1. 保留最近1条action（完整）
        2. 总结之前所有action为一段话
        3. 如果最近1条超过(max_allowed - 20k)，分段压缩它
        
        Args:
            action_history: 原始动作历史
            max_allowed_tokens: 允许的最大token数
            
        Returns:
            压缩后的动作历史
        """
        if not action_history:
            return []
        
        if len(action_history) == 1:
            # 只有一条，检查是否需要压缩
            single_action = action_history[0]
            single_tokens = self.count_tokens(json.dumps(single_action, ensure_ascii=False))
            
            if single_tokens > max_allowed_tokens - 20000:
                safe_print(f"🔄 单条action过大 ({single_tokens} tokens)，进行分段压缩")
                return [self._compress_large_action(single_action, max_allowed_tokens - 20000)]
            else:
                return action_history
        
        # 多条action的情况
        recent_action = action_history[-1]  # 最近的一条
        historical_actions = action_history[:-1]  # 之前的所有
        
        # 检查最近一条的大小
        recent_tokens = self.count_tokens(json.dumps(recent_action, ensure_ascii=False))
        
        if recent_tokens > max_allowed_tokens - 20000:
            # 最近一条本身就太大，需要压缩
            safe_print(f"🔄 最近action过大 ({recent_tokens} tokens)，进行分段压缩")
            compressed_recent = self._compress_large_action(recent_action, max_allowed_tokens - 20000)
            
            # 历史部分总结
            if historical_actions:
                summary_action = self._summarize_historical_actions(historical_actions)
                return [summary_action, compressed_recent]
            else:
                return [compressed_recent]
        else:
            # 最近一条正常，总结历史
            summary_action = self._summarize_historical_actions(historical_actions)
            
            # 检查总大小
            total_tokens = self.count_tokens(json.dumps([summary_action, recent_action], ensure_ascii=False))
            
            if total_tokens <= max_allowed_tokens:
                return [summary_action, recent_action]
            else:
                # 总结也太大了，进一步压缩总结
                safe_print(f"⚠️ 总结后仍超限 ({total_tokens} tokens)，使用极简总结")
                # 直接返回一个超简单的总结 + 最近action
                simple_summary = self._create_simple_summary(historical_actions)
                return [simple_summary, recent_action]
    
    def _summarize_historical_actions(self, actions: List[Dict]) -> Dict:
        """
        将历史actions总结为一段话
        
        Args:
            actions: 历史action列表
            
        Returns:
            一个特殊的"总结action"
        """
        try:
            # 构建历史摘要
            summary_text = f"历史共{len(actions)}个动作：\n"
            
            # 统计工具使用情况
            tool_counts = {}
            for action in actions:
                tool_name = action.get("tool_name", "unknown")
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
            
            summary_text += "\n工具调用统计：\n"
            for tool, count in tool_counts.items():
                summary_text += f"- {tool}: {count}次\n"
            
            # 提取关键结果
            summary_text += "\n关键结果：\n"
            for i, action in enumerate(actions[-5:], 1):  # 最后5个的摘要
                tool_name = action.get("tool_name", "")
                status = action.get("result", {}).get("status", "unknown")
                summary_text += f"{i}. {tool_name} - {status}\n"
            
            # 调用LLM进行智能总结
            prompt = f"""请将以下历史动作总结为一段简洁的描述（不超过500 tokens）：

{summary_text}

历史动作详情（JSON格式）：
{json.dumps(actions, ensure_ascii=False, indent=2)[:5000]}...

要求：
1. 总结完成了什么工作
2. 关键的输出和文件
3. 重要的发现或结果
4. 简洁但完整

请用中文总结："""
            
            history = [ChatMessage(role="user", content=prompt)]
            
            response = self.llm_client.chat(
                history=history,
                model=self.llm_client.models[0],
                system_prompt="你是一个专业的内容总结助手。",
                tool_list=[],
                tool_choice="auto"
            )
            
            if response.status == "success":
                summary = response.output
            else:
                summary = summary_text  # 使用统计摘要作为备用
            
            # 创建总结action
            return {
                "tool_name": "_historical_summary",
                "arguments": {
                    "action_count": len(actions),
                    "summary_method": "llm_summarization"
                },
                "result": {
                    "status": "success",
                    "output": f"[历史动作总结] {summary}",
                    "_is_summary": True,
                    "_summarized_count": len(actions)
                }
            }
        
        except Exception as e:
            safe_print(f"⚠️ 总结失败: {e}")
            # 失败时使用简单统计
            return self._create_simple_summary(actions)
    
    def _create_simple_summary(self, actions: List[Dict]) -> Dict:
        """创建简单的统计总结（不调用LLM）"""
        tool_counts = {}
        for action in actions:
            tool_name = action.get("tool_name", "unknown")
            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
        
        summary = f"历史共{len(actions)}个动作。"
        summary += "工具使用: " + ", ".join([f"{t}({c}次)" for t, c in tool_counts.items()])
        
        return {
            "tool_name": "_historical_summary",
            "arguments": {"action_count": len(actions)},
            "result": {
                "status": "success",
                "output": f"[历史动作简要总结] {summary}",
                "_is_summary": True,
                "_summarized_count": len(actions)
            }
        }
    
    def _compress_large_action(self, action: Dict, max_tokens: int) -> Dict:
        """
        压缩单个超大action
        
        策略：只压缩result.output部分
        
        Args:
            action: 原始action
            max_tokens: 最大允许token数
            
        Returns:
            压缩后的action
        """
        tool_name = action.get("tool_name", "")
        arguments = action.get("arguments", {})
        result = action.get("result", {})
        
        output = result.get("output", "")
        output_tokens = self.count_tokens(output)
        
        if output_tokens > max_tokens:
            safe_print(f"   压缩{tool_name}的output: {output_tokens} tokens → 目标 {max_tokens} tokens")
            
            # 策略：首尾保留法（使用tiktoken精确截取）
            if self.encoding:
                # 使用tiktoken精确截取
                tokens = self.encoding.encode(output)
                
                # 首尾各保留40%的目标token（总共80%）
                head_tokens_count = int(max_tokens * 0.4)
                tail_tokens_count = int(max_tokens * 0.4)
                
                head_tokens = tokens[:head_tokens_count]
                tail_tokens = tokens[-tail_tokens_count:]
                
                head_text = self.encoding.decode(head_tokens)
                tail_text = self.encoding.decode(tail_tokens)
                
                middle_info = f"\n\n[中间省略约 {output_tokens - max_tokens} tokens]\n\n"
                
                compressed_output = head_text + middle_info + tail_text
            else:
                # 没有tiktoken，简单截断（保守估计）
                chars_to_keep = int(max_tokens * 2)  # 1 token ≈ 2字符
                head_chars = chars_to_keep // 2
                tail_chars = chars_to_keep // 2
                
                compressed_output = output[:head_chars] + "\n\n[中间省略]\n\n" + output[-tail_chars:]
            
            # 验证压缩效果
            compressed_tokens = self.count_tokens(compressed_output)
            safe_print(f"   压缩结果: {compressed_tokens} tokens (压缩比: {compressed_tokens/output_tokens*100:.1f}%)")
            
            return {
                "tool_name": tool_name,
                "arguments": arguments,
                "result": {
                    **result,
                    "output": compressed_output,
                    "_compressed": True,
                    "_original_tokens": output_tokens,
                    "_compressed_tokens": compressed_tokens
                },
                "timestamp": action.get("timestamp", "")
            }
        
        return action


if __name__ == "__main__":
    # 测试时不实际运行LLM，只测试逻辑
    safe_print("✅ ContextCompressor模块加载成功")
    safe_print("功能：")
    safe_print("  1. 总结历史actions为一段话")
    safe_print("  2. 保留最近1条action")
    safe_print("  3. 如果最近1条超大，使用首尾保留法压缩")
    safe_print("\n策略：历史总结 + 最新完整 = 最佳平衡")
