#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Context Length Controller - 上下文长度控制器
专门处理对话历史的长度控制、截断和压缩
"""

import json
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass


@dataclass
class ChatMessage:
    """聊天消息数据类"""
    role: str  # "user", "assistant", "system"
    content: str


class ContextLengthController:
    """
    上下文长度控制器
    负责对话历史的智能截断和消息压缩
    """
    
    def __init__(self):
        """初始化上下文长度控制器"""
        pass
    
    def truncate_history(
        self,
        history: List[ChatMessage],
        initial_user_input: str,
        max_history_turns: int,
        max_history_tokens: int,
        model_type: str,
        # LLM客户端用于总结
        llm_client: Any = None,
        # 日志函数
        logger_func: Optional[Callable[[str], None]] = None
    ) -> Tuple[List[ChatMessage], bool]:
        """
        智能截断对话历史，保留系统提示词+用户初始指令+最近N轮或M tokens的对话
        
        Args:
            history: 完整的对话历史
            initial_user_input: 用户的初始输入
            max_history_turns: 最大保留的对话轮数
            max_history_tokens: 最大保留的对话tokens数
            model_type: 模型类型（用于token估算）
            estimate_tokens_func: token估算函数
            summarize_message_func: 消息总结函数
            get_context_info_func: 获取上下文信息的函数（可选）
            logger_func: 日志记录函数（可选）
            current_turn: 当前轮次
            
        Returns:
            Tuple[List[ChatMessage], bool]: (截断后的对话历史, 是否有消息被总结修改)
        """
        if not history:  # 空历史处理
            return history, False
        
        # 标记是否有消息被修改
        messages_modified = False
        
        # 对于短对话，也要添加共享上下文并保存
        if len(history) <= 2:
            processed_history, short_modified = self._process_short_history(
                history, max_history_tokens, model_type, llm_client
            )
            messages_modified = short_modified
            
            return processed_history, messages_modified
        
        # 找到第一条用户消息（初始指令）
        first_user_msg, first_user_index = self._find_initial_user_message(history, initial_user_input)
        
        if first_user_index == -1:
            # 如果没找到初始指令，保留最近的对话
            if logger_func:
                logger_func("未找到初始用户指令，直接截断最近对话")
            print("⚠️ 未找到初始用户指令，直接截断最近对话")
            
            truncated_recent, recent_modified = self._truncate_recent_messages(
                history, max_history_turns, max_history_tokens, model_type, llm_client
            )
            
            return truncated_recent, recent_modified
        
        # 处理核心消息（初始用户指令）
        core_content = first_user_msg.content
        core_tokens = self.estimate_tokens(core_content, model_type)
        
        # 如果核心消息过长，也需要总结
        core_message_max_tokens = max(max_history_tokens // 4, 100)
        if core_tokens > core_message_max_tokens and not self._is_already_summarized(core_content):
            print(f"🔄 处理超长核心消息 (原始: {core_tokens} tokens)")
            core_content = self._summarize_message(core_content, core_message_max_tokens, model_type, llm_client)
            core_tokens = self.estimate_tokens(core_content, model_type)
            print(f"✅ 核心消息处理完成 (压缩后: {core_tokens} tokens)")
            messages_modified = True
            
            # 替换原始历史中的核心消息
            history[first_user_index] = ChatMessage(role=first_user_msg.role, content=core_content)
        
        core_messages = [ChatMessage(role=first_user_msg.role, content=core_content)]
        
        # 计算可用于最近对话的token预算
        available_tokens = max_history_tokens - core_tokens
        
        # 从最后开始，向前收集消息
        recent_messages, recent_modified = self._collect_recent_messages(
            history, first_user_index, available_tokens, max_history_turns, 
            model_type, llm_client
        )
        
        if recent_modified:
            messages_modified = True
        
        # 构建最终的历史记录
        final_history = core_messages + recent_messages if recent_messages else core_messages
        
        
        # 记录截断信息
        if len(final_history) < len(history):
            truncated_count = len(history) - len(final_history)
            total_tokens = sum(self.estimate_tokens(msg.content, model_type) for msg in final_history)
            
            if logger_func:
                logger_func(
                    f"对话历史已截断：保留 {len(final_history)}/{len(history)} 条消息，"
                    f"估算 {total_tokens} tokens，截断了 {truncated_count} 条消息"
                )
            
            print(f"📝 对话历史截断：保留 {len(final_history)}/{len(history)} 条消息，估算约 {total_tokens} tokens")
        
        return final_history, messages_modified
    
    def _process_short_history(
        self, 
        history: List[ChatMessage], 
        max_history_tokens: int,
        model_type: str,
        llm_client: Any
    ) -> Tuple[List[ChatMessage], bool]:
        """处理短对话历史中的超长消息"""
        messages_modified = False
        processed_history = []
        
        for i, msg in enumerate(history):
            msg_tokens = self.estimate_tokens(msg.content, model_type)
            single_message_max_tokens = max(max_history_tokens // 4, 100)
            
            if msg_tokens > single_message_max_tokens and not self._is_already_summarized(msg.content):
                print(f"🔄 短对话中发现超长消息，进行总结处理")
                summarized_content = self._summarize_message(msg.content, single_message_max_tokens, model_type, llm_client)
                processed_msg = ChatMessage(role=msg.role, content=summarized_content)
                processed_history.append(processed_msg)
                messages_modified = True
                
                # 替换原始历史中的消息
                history[i] = processed_msg
            else:
                processed_history.append(msg)
        
        return processed_history, messages_modified
    
    def _find_initial_user_message(self, history: List[ChatMessage], initial_user_input: str) -> Tuple[Optional[ChatMessage], int]:
        """查找初始用户消息"""
        for i, msg in enumerate(history):
            if msg.role == "user" and msg.content == initial_user_input:
                return msg, i
        return None, -1
    
    def _collect_recent_messages(
        self,
        history: List[ChatMessage],
        first_user_index: int,
        available_tokens: int,
        max_history_turns: int,
        model_type: str,
        llm_client: Any
    ) -> Tuple[List[ChatMessage], bool]:
        """收集最近的消息"""
        recent_messages = []
        recent_tokens = 0
        messages_modified = False
        
        # 设置单条消息的最大token限制（总限制的1/4，确保至少能容纳4条消息）
        single_message_max_tokens = max(available_tokens // 4, 100)
        
        for i in range(len(history) - 1, first_user_index, -1):
            msg = history[i]
            msg_tokens = self.estimate_tokens(msg.content, model_type)
            
            # 处理超长单条消息
            processed_content = msg.content
            if msg_tokens > single_message_max_tokens and not self._is_already_summarized(msg.content):
                print(f"🔄 处理超长消息 (原始: {msg_tokens} tokens)")
                processed_content = self._summarize_message(msg.content, single_message_max_tokens, model_type, llm_client)
                msg_tokens = self.estimate_tokens(processed_content, model_type)
                print(f"✅ 消息处理完成 (压缩后: {msg_tokens} tokens)")
                messages_modified = True
                
                # 替换原始历史中的消息
                history[i] = ChatMessage(role=msg.role, content=processed_content)
            
            # 检查是否超过轮数限制或token限制
            if (len(recent_messages) // 2 >= max_history_turns or  # 按对话轮次计算（1轮=1个user+1个assistant）
                recent_tokens + msg_tokens > available_tokens):
                break
            
            # 创建处理后的消息对象
            processed_msg = ChatMessage(role=msg.role, content=processed_content)
            recent_messages.insert(0, processed_msg)
            recent_tokens += msg_tokens
        
        return recent_messages, messages_modified
    
    def _truncate_recent_messages(
        self, 
        history: List[ChatMessage], 
        max_history_turns: int,
        max_history_tokens: int,
        model_type: str,
        llm_client: Any
    ) -> Tuple[List[ChatMessage], bool]:
        """简单的最近消息截断（当找不到初始指令时的备用方案）"""
        messages_modified = False
        
        if len(history) <= max_history_turns * 2:
            # 即使不需要截断，也要检查是否有超长消息需要总结
            processed_history = []
            for i, msg in enumerate(history):
                msg_tokens = self.estimate_tokens(msg.content, model_type)
                single_message_max_tokens = max(max_history_tokens // 4, 100)
                
                if msg_tokens > single_message_max_tokens and not self._is_already_summarized(msg.content):
                    print(f"🔄 发现超长消息，进行总结处理")
                    summarized_content = self._summarize_message(msg.content, single_message_max_tokens, model_type, llm_client)
                    processed_msg = ChatMessage(role=msg.role, content=summarized_content)
                    processed_history.append(processed_msg)
                    messages_modified = True
                    
                    # 替换原始历史中的消息
                    history[i] = processed_msg
                else:
                    processed_history.append(msg)
            
            return processed_history, messages_modified
        
        # 保留最近的N轮对话，但要确保token不超限
        recent_messages = []
        total_tokens = 0
        
        # 设置单条消息的最大token限制
        single_message_max_tokens = max(max_history_tokens // 4, 100)
        
        for i in range(len(history) - 1, -1, -1):
            msg = history[i]
            msg_tokens = self.estimate_tokens(msg.content, model_type)
            
            # 处理超长单条消息
            processed_content = msg.content
            if msg_tokens > single_message_max_tokens and not self._is_already_summarized(msg.content):
                print(f"🔄 处理超长消息 (原始: {msg_tokens} tokens)")
                processed_content = self._summarize_message(msg.content, single_message_max_tokens, model_type, llm_client)
                msg_tokens = self.estimate_tokens(processed_content, model_type)
                print(f"✅ 消息处理完成 (压缩后: {msg_tokens} tokens)")
                messages_modified = True
                
                # 替换原始历史中的消息
                history[i] = ChatMessage(role=msg.role, content=processed_content)
            
            if (len(recent_messages) >= max_history_turns * 2 or 
                total_tokens + msg_tokens > max_history_tokens):
                break
            
            # 创建处理后的消息对象
            processed_msg = ChatMessage(role=msg.role, content=processed_content)
            recent_messages.insert(0, processed_msg)
            total_tokens += msg_tokens
        
        final_history = recent_messages if recent_messages else history[-1:]  # 至少保留最后一条消息
        return final_history, messages_modified
    
    def estimate_tokens(self, text: str, model_type: str) -> int:
        """
        使用tiktoken精确计算文本的token数量
        
        Args:
            text: 要估算的文本
            model_type: 模型类型
            
        Returns:
            int: 精确的token数量
        """
        try:
            import tiktoken
            
            # 根据模型类型选择合适的编码器
            model_name = model_type.lower()
            
            if any(x in model_name for x in ["gpt", "o1", "o3", "claude", "gemini", "deepseek"]):
                # 大多数模型使用cl100k_base编码
                encoding = tiktoken.get_encoding("cl100k_base")
            else:
                # 默认使用cl100k_base编码
                encoding = tiktoken.get_encoding("cl100k_base")
            
            # 计算精确的token数量
            tokens = encoding.encode(text)
            return len(tokens)
            
        except ImportError:
            # 如果tiktoken未安装，回退到简单估算
            print("⚠️ tiktoken未安装，使用简单估算方法")
            return self._simple_token_estimate(text)
        
        except Exception as e:
            # 如果tiktoken计算失败，回退到简单估算
            print(f"⚠️ tiktoken计算失败，使用简单估算: {e}")
            return self._simple_token_estimate(text)
    
    def _simple_token_estimate(self, text: str) -> int:
        """简单的token估算方法"""
        # 简单估算：英文按4字符1token，中文按1.5字符1token
        chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
        other_chars = len(text) - chinese_chars
        
        # 中文字符按1.5字符1token，其他字符按4字符1token估算
        estimated_tokens = int(chinese_chars / 1.5 + other_chars / 4)
        return max(1, estimated_tokens)  # 至少1个token
    
    def split_message_by_tokens(self, content: str, max_tokens: int, model_type: str) -> List[str]:
        """
        基于token数量智能分割消息
        
        Args:
            content: 要分割的内容
            max_tokens: 每个片段的最大token数
            model_type: 模型类型
            
        Returns:
            List[str]: 分割后的片段列表
        """
        try:
            import tiktoken
            
            # 获取编码器
            model_name = model_type.lower()
            if any(x in model_name for x in ["gpt", "claude", "gemini", "deepseek"]):
                encoding = tiktoken.get_encoding("cl100k_base")
            else:
                encoding = tiktoken.get_encoding("cl100k_base")
            
            # 将内容编码为tokens
            tokens = encoding.encode(content)
            
            # 按token数分割
            chunks = []
            for i in range(0, len(tokens), max_tokens):
                chunk_tokens = tokens[i:i + max_tokens]
                chunk_text = encoding.decode(chunk_tokens)
                chunks.append(chunk_text)
            
            return chunks
            
        except ImportError:
            # tiktoken未安装，使用字符分割作为备用
            print("⚠️ tiktoken未安装，使用字符分割方法")
            return self._split_by_chars(content, max_tokens)
            
        except Exception as e:
            # 分割失败，使用字符分割作为备用
            print(f"⚠️ token分割失败，使用字符分割: {e}")
            return self._split_by_chars(content, max_tokens)
    
    def _split_by_chars(self, content: str, max_tokens: int) -> List[str]:
        """基于字符数分割消息（备用方案）"""
        chunk_size_chars = int(max_tokens * 2.5)  # 粗略估算
        chunks = []
        for i in range(0, len(content), chunk_size_chars):
            chunk = content[i:i + chunk_size_chars]
            chunks.append(chunk)
        return chunks
    
    def _summarize_message(self, message_content: str, max_tokens: int, model_type: str, llm_client: Any) -> str:
        """
        对超长消息进行分割和总结
        
        Args:
            message_content: 原始消息内容
            max_tokens: 单个片段的最大token数
            model_type: 模型类型
            llm_client: LLM客户端
            
        Returns:
            str: 总结后的消息内容
        """
        try:
            # 检查是否已经是总结后的消息
            if self._is_already_summarized(message_content):
                print("ℹ️ 消息已经是总结后的内容，跳过重复总结")
                return message_content
            
            # 估算消息的token数
            total_tokens = self.estimate_tokens(message_content, model_type)
            
            if total_tokens <= max_tokens:
                return message_content
            
            print(f"🔄 检测到超长消息({total_tokens} tokens)，开始分片总结...")
            
            # 确定每片的大小 - 使用用户设定的max_tokens作为单片大小
            chunk_size = max_tokens
            
            # 使用智能的基于token的分割
            chunks = self.split_message_by_tokens(message_content, chunk_size, model_type)
            
            print(f"📝 消息已分割为 {len(chunks)} 个片段，每片约{chunk_size} tokens")
            
            # 计算每片总结的目标长度（约为chunk_size的60%，确保压缩效果）
            target_summary_tokens = int(chunk_size * 0.6)
            
            # 对每个片段进行总结
            summaries = []
            previous_summary = ""
            
            for i, chunk in enumerate(chunks):
                try:
                    chunk_tokens = self.estimate_tokens(chunk, model_type)
                    print(f"🔄 处理片段 {i+1}/{len(chunks)} ({chunk_tokens} tokens)")
                    
                    # 构建总结提示，包含前面的上下文
                    summary_prompt = f"""请对以下内容进行智能总结，要求：
1. 保留所有关键信息和要点
2. 保持逻辑结构清晰  
3. 目标长度约{target_summary_tokens}个tokens（约{int(target_summary_tokens*2.5)}字符）
4. 与前面内容保持连贯性

{f"前面部分的总结：{previous_summary}" if previous_summary else "这是第一部分内容"}

当前需要总结的内容：
{chunk}

请提供简洁但完整的总结："""
                    
                    # 调用LLM进行总结
                    if llm_client:
                        from baseService.llm_client import ChatMessage as LLMChatMessage
                        summary_history = [LLMChatMessage(role="user", content=summary_prompt)]
                        
                        summary_response = llm_client.chat(
                            history=summary_history,
                            model=model_type,
                            system_prompt=f"你是一个专业的内容总结助手。请对用户提供的内容进行智能总结，保留关键信息，目标长度约{target_summary_tokens}个tokens。",
                            tool_list=[],
                            tool_choice="none"
                        )
                        
                        if summary_response.status == "success":
                            summary = summary_response.output.strip()
                            print(f"✅ 片段 {i+1}/{len(chunks)} 总结完成")
                        else:
                            summary = f"[总结失败: {summary_response.error_information}]"
                            print(f"❌ 片段 {i+1} 总结失败: {summary_response.error_information}")
                    else:
                        summary = f"[无LLM客户端，无法总结片段 {i+1}]"
                        print(f"⚠️ 片段 {i+1} 无LLM客户端")
                    
                    summaries.append(summary)
                    previous_summary = summary  # 更新上下文
                    
                except Exception as e:
                    print(f"⚠️ 片段 {i+1} 总结失败: {e}")
                    summaries.append(f"[总结失败: {str(e)}]")
            
            # 合并所有总结
            if len(summaries) == 1:
                # 只有一个片段，直接使用
                final_summary = summaries[0]
            else:
                # 多个片段，标记每个片段
                final_summary = "\n\n".join([f"[片段 {i+1}] {summary}" for i, summary in enumerate(summaries)])
            
            # 添加总结标识
            summary_header = f"[🤖 AI总结消息 - 原消息过长({total_tokens} tokens)，已分{len(chunks)}片总结，每片约{chunk_size} tokens]\n\n"
            final_content = summary_header + final_summary
            
            print(f"✅ 消息总结完成，从 {total_tokens} tokens 压缩到约 {self.estimate_tokens(final_content, model_type)} tokens")
            
            return final_content
            
        except Exception as e:
            print(f"⚠️ 消息总结过程失败: {e}")
            # 如果总结失败，截断到前max_tokens字符
            truncated_chars = int(max_tokens * 2.5)
            return f"[消息过长，总结失败，已截断]\n\n{message_content[:truncated_chars]}..."
    
    def _is_already_summarized(self, content: str) -> bool:
        """
        检测消息是否已经是总结后的内容
        
        Args:
            content: 要检测的内容
            
        Returns:
            bool: 是否已经是总结后的内容
        """
        return content.startswith("[🤖 AI总结消息")
