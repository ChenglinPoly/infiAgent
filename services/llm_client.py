#!/usr/bin/env python3
from utils.windows_compat import safe_print
# -*- coding: utf-8 -*-
"""
简化的LLM客户端 - 使用LiteLLM统一接口
"""

import os
import yaml
import time
import json
import copy
import concurrent.futures
import re
from typing import Callable, List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from litellm import completion  # 直接导入completion函数
import litellm

from utils.user_paths import (
    ensure_user_llm_config_exists,
    get_task_file_prefix,
    get_user_conversations_dir,
    get_user_runtime_dir,
)


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str
    content: str


@dataclass
class ToolCall:
    """工具调用"""
    id: str          
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """LLM响应"""
    status: str  # "success" or "error"
    output: str
    tool_calls: List[ToolCall]
    model: str
    finish_reason: str
    usage: Optional[Dict] = None
    error_information: str = ""
    reasoning_content: str = ""  # 模型的推理/思考内容（如 Claude thinking, Deepseek reasoning）
    thinking_blocks: Optional[List[Dict]] = None  # Anthropic 专用的 thinking_blocks


_RAW_TOOL_CALLS_SECTION_BEGIN = "<|tool_calls_section_begin|>"
_RAW_TOOL_CALLS_SECTION_END = "<|tool_calls_section_end|>"
_RAW_TOOL_CALL_PATTERN = re.compile(
    r"<\|tool_call_begin\|>(.*?)<\|tool_call_argument_begin\|>(.*?)<\|tool_call_end\|>",
    re.DOTALL,
)


def _marker_prefix_overlap(text: str, marker: str) -> int:
    """返回 text 尾部与 marker 前缀的最大重叠长度，用于流式解析跨 chunk 标记。"""
    if not text or not marker:
        return 0
    max_size = min(len(text), len(marker) - 1)
    for size in range(max_size, 0, -1):
        if text.endswith(marker[:size]):
            return size
    return 0


class _EmbeddedToolCallStreamState:
    """过滤模型直接吐出的原始 tool-call section，同时保留其中的原始标记以便后续解析。"""

    def __init__(self):
        self._pending = ""
        self._captured_parts: List[str] = []
        self._in_section = False

    def feed(self, text: str) -> str:
        if not text:
            return ""

        self._pending += text
        visible_parts: List[str] = []

        while self._pending:
            if not self._in_section:
                start_idx = self._pending.find(_RAW_TOOL_CALLS_SECTION_BEGIN)
                if start_idx >= 0:
                    if start_idx > 0:
                        visible_parts.append(self._pending[:start_idx])
                    self._pending = self._pending[start_idx + len(_RAW_TOOL_CALLS_SECTION_BEGIN):]
                    self._in_section = True
                    continue

                hold = _marker_prefix_overlap(self._pending, _RAW_TOOL_CALLS_SECTION_BEGIN)
                if hold:
                    visible_parts.append(self._pending[:-hold])
                    self._pending = self._pending[-hold:]
                else:
                    visible_parts.append(self._pending)
                    self._pending = ""
                break

            end_idx = self._pending.find(_RAW_TOOL_CALLS_SECTION_END)
            if end_idx >= 0:
                if end_idx > 0:
                    self._captured_parts.append(self._pending[:end_idx])
                self._pending = self._pending[end_idx + len(_RAW_TOOL_CALLS_SECTION_END):]
                self._in_section = False
                continue

            hold = _marker_prefix_overlap(self._pending, _RAW_TOOL_CALLS_SECTION_END)
            if hold:
                self._captured_parts.append(self._pending[:-hold])
                self._pending = self._pending[-hold:]
            else:
                self._captured_parts.append(self._pending)
                self._pending = ""
            break

        return "".join(visible_parts)

    def finish(self) -> tuple[str, str]:
        visible_tail = ""
        if self._pending:
            if self._in_section:
                self._captured_parts.append(self._pending)
            else:
                visible_tail = self._pending
        self._pending = ""
        return visible_tail, "".join(self._captured_parts)


class SimpleLLMClient:
    """简化的LLM客户端 - 基于LiteLLM"""
    
    def __init__(self, llm_config_path: str = None, tools_config_path: str = None):
        """
        初始化LLM客户端
        
        Args:
            llm_config_path: LLM配置文件路径
            tools_config_path: 工具配置文件路径
        """
        # 加载LLM配置
        if llm_config_path is None:
            llm_config_path = ensure_user_llm_config_exists()
        
        if not os.path.exists(llm_config_path):
            raise FileNotFoundError(f"LLM配置文件不存在: {llm_config_path}")
        
        with open(llm_config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 读取配置
        self.base_url = self.config.get("base_url", "")
        self.api_key = self.config.get("api_key", "")
        self.temperature = self.config.get("temperature", 0)
        self.max_tokens = self.config.get("max_tokens", 0)
        self.max_context_window = self.config.get("max_context_window", 100000)  # 上下文窗口限制
        
        # 读取超时配置（默认值：600s, 20s, 20s）
        self.timeout = self.config.get("timeout", 600)  # LiteLLM 原生：总超时
        self.stream_timeout = self.config.get("stream_timeout", 20)  # LiteLLM 原生：流式超时
        self.first_chunk_timeout = self.config.get("first_chunk_timeout", 20)  # 应用层强制：首包超时
        
        # 解析模型配置（支持两种格式）
        self.models = []  # 模型名称列表
        self.figure_models = []
        self.compressor_models = []
        self.model_configs = {}  # 模型名称 -> 配置字典
        self.default_models = {}

        self._parse_models_config(self.config.get("models", []), self.models, "execution")
        self._parse_models_config(self.config.get("figure_models", []), self.figure_models, "image_generation")
        self._parse_models_config(self.config.get("compressor_models", []), self.compressor_models, "compressor")
        self.thinking_models = []
        self._parse_models_config(self.config.get("thinking_models", []), self.thinking_models, "thinking")
        # 如果没有配置 thinking_models，回退到 models
        if not self.thinking_models:
            self.thinking_models = list(self.models)
        self.default_models.setdefault("thinking", self.thinking_models[0] if self.thinking_models else "")
        self.read_figure_models = []
        self._parse_models_config(self.config.get("read_figure_models", []), self.read_figure_models, "read_figure")
        if not self.read_figure_models:
            self.read_figure_models = list(self.models)
        self.default_models.setdefault("read_figure", self.read_figure_models[0] if self.read_figure_models else "")
        self.default_models.setdefault("execution", self.models[0] if self.models else "")
        self.default_models.setdefault("image_generation", self.figure_models[0] if self.figure_models else "")
        self.default_models.setdefault("compressor", self.compressor_models[0] if self.compressor_models else "")
        self.default_tool_choice = self._load_default_tool_choice()
        # 多模态配置
        self.multimodal = self.config.get("multimodal", False)
        self.compressor_multimodal = self.config.get("compressor_multimodal", False)
        
        if not self.api_key:
            raise ValueError("未配置API密钥")
        
        if not self.models:
            raise ValueError("未配置可用模型列表")
        
        # 加载工具配置
        self.tools_config = {}
        if tools_config_path and os.path.exists(tools_config_path):
            with open(tools_config_path, 'r', encoding='utf-8') as f:
                self.tools_config = yaml.safe_load(f)
        
        # 配置LiteLLM
        litellm.set_verbose = False  # 关闭详细日志
        litellm.drop_params = True  # 自动丢弃不支持的参数（如Anthropic不支持parallel_tool_calls）
        
        safe_print(f"✅ LLM客户端初始化成功（LiteLLM）")
        safe_print(f"   Base URL: {self.base_url}")
        safe_print(f"   可用模型: {len(self.models)} 个")
        safe_print(f"   Figure模型: {len(self.figure_models)} 个")
        safe_print(f"   Compressor模型: {len(self.compressor_models)} 个")
        safe_print(f"   默认Temperature: {self.temperature}")
        safe_print(f"   默认Max Tokens: {self.max_tokens}")
        safe_print(f"   超时配置: timeout={self.timeout}s, stream_timeout={self.stream_timeout}s, first_chunk_timeout={self.first_chunk_timeout}s")
        safe_print(f"   多模态: multimodal={self.multimodal}, compressor_multimodal={self.compressor_multimodal}")
    
    def _parse_models_config(self, models_config: List, target_list: List, category: str):
        """
        解析模型配置，支持两种格式：
        1. 字符串格式：直接是模型名称
        2. 对象格式：包含 name 和额外参数
        
        Args:
            models_config: 原始模型配置列表
            target_list: 目标列表（self.models, self.figure_models 等）
        """
        default_name = ""
        for model_item in models_config:
            if isinstance(model_item, str):
                # 简单格式：直接是模型名称
                target_list.append(model_item)
                self.model_configs[model_item] = {}
                if not default_name:
                    default_name = model_item
            elif isinstance(model_item, dict):
                # 对象格式：包含额外参数
                model_name = model_item.get("name")
                if not model_name:
                    safe_print(f"⚠️ 模型配置缺少 'name' 字段，跳过: {model_item}")
                    continue
                
                target_list.append(model_name)
                # 保存除 name 外的所有参数
                extra_params = {k: v for k, v in model_item.items() if k != "name"}
                self.model_configs[model_name] = extra_params
                if extra_params.get("default") is True:
                    default_name = model_name
                elif not default_name:
                    default_name = model_name

                if extra_params:
                    safe_print(f"   📝 模型 {model_name} 配置了额外参数: {list(extra_params.keys())}")
            else:
                safe_print(f"⚠️ 不支持的模型配置格式，跳过: {model_item}")
        if default_name:
            self.default_models[category] = default_name

    def _load_default_tool_choice(self) -> Dict[str, str]:
        raw = self.config.get("tool_choice", {}) or {}
        defaults = {
            "execution": "required",
            "thinking": "none",
            "compressor": "none",
            "image_generation": "none",
            "read_figure": "none",
        }
        if isinstance(raw, dict):
            for key, value in raw.items():
                normalized = str(value or "").strip().lower()
                if normalized in {"required", "auto", "none"}:
                    defaults[str(key)] = normalized
        elif isinstance(raw, str):
            normalized = str(raw).strip().lower()
            if normalized in {"required", "auto", "none"}:
                defaults["execution"] = normalized
        return defaults

    def get_default_tool_choice(self, category: str = "execution") -> str:
        return self.default_tool_choice.get(category, "required")

    @staticmethod
    def _embedded_tool_name_from_id(raw_call_id: str) -> str:
        token = str(raw_call_id or "").strip()
        if not token:
            return ""
        if token.startswith("functions."):
            token = token[len("functions."):]
        if ":" in token:
            token = token.rsplit(":", 1)[0]
        return token.strip()

    def _parse_embedded_tool_calls(self, raw_markup: str) -> List[ToolCall]:
        text = str(raw_markup or "")
        if not text or "<|tool_call_begin|>" not in text:
            return []

        final_calls: List[ToolCall] = []
        for idx, match in enumerate(_RAW_TOOL_CALL_PATTERN.finditer(text)):
            raw_call_id = str(match.group(1) or "").strip()
            raw_args = str(match.group(2) or "").strip()
            tool_name = self._embedded_tool_name_from_id(raw_call_id)
            if not tool_name:
                continue

            args: Dict[str, Any]
            if not raw_args:
                args = {}
            else:
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = self._try_fix_json(raw_args) or {}

            final_calls.append(
                ToolCall(
                    id=raw_call_id or f"embedded_call_{idx}",
                    name=tool_name,
                    arguments=args,
                )
            )
        return final_calls

    @staticmethod
    def _merge_tool_calls(primary: List[ToolCall], secondary: List[ToolCall]) -> List[ToolCall]:
        merged: List[ToolCall] = []
        seen = set()
        for tool_call in list(primary or []) + list(secondary or []):
            args_key = json.dumps(tool_call.arguments or {}, ensure_ascii=False, sort_keys=True)
            key = (str(tool_call.id or "").strip(), str(tool_call.name or "").strip(), args_key)
            fallback_key = (str(tool_call.name or "").strip(), args_key)
            if key in seen or fallback_key in seen:
                continue
            seen.add(key)
            seen.add(fallback_key)
            merged.append(tool_call)
        return merged
    def _build_debug_messages_snapshot(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建适合落盘的消息快照，避免大字段让调试文件无限膨胀。"""
        debug_msgs = copy.deepcopy(messages)
        for debug_msg in debug_msgs:
            content = debug_msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        image_url = part.get("image_url", {}).get("url", "")
                        if len(image_url) > 120:
                            part["image_url"]["url"] = image_url[:80] + f"...({len(image_url)} chars)"
            elif isinstance(content, str) and len(content) > 2000:
                if (debug_msg.get("role") or "").lower() != "system":
                    debug_msg["content"] = content[:2000] + f"\n...({len(content)} chars total)"
        return debug_msgs

    def _resolve_debug_output_path(self, debug_task_id: Optional[str]) -> Path:
        debug_task_id = str(debug_task_id or "").strip()
        if debug_task_id:
            conversations_dir = get_user_conversations_dir()
            conversations_dir.mkdir(parents=True, exist_ok=True)
            return conversations_dir / f"{get_task_file_prefix(debug_task_id)}_llm_debug.jsonl"

        debug_dir = get_user_runtime_dir() / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        return debug_dir / "llm_debug.jsonl"

    def _append_debug_record(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        debug_task_id: Optional[str] = None,
        debug_label: str = "execution",
        tool_choice: Optional[str] = None,
        tool_count: int = 0,
        emit_tokens: Optional[str] = None,
    ) -> None:
        debug_file = self._resolve_debug_output_path(debug_task_id)
        payload = {
            "timestamp": datetime.now().isoformat(),
            "pid": os.getpid(),
            "task_id": str(debug_task_id or "").strip() or None,
            "debug_label": str(debug_label or "execution").strip() or "execution",
            "model": model,
            "message_count": len(messages),
            "tool_count": tool_count,
            "tool_choice": tool_choice,
            "emit_tokens": emit_tokens,
            "messages": self._build_debug_messages_snapshot(messages),
        }
        with open(debug_file, "a", encoding="utf-8") as debug_handle:
            debug_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        safe_print(f"📋 DEBUG: messages JSONL 已追加到 {debug_file}")

    def resolve_model(self, category: str = "execution", preferred: Optional[str] = None) -> str:
        model_groups = {
            "execution": self.models,
            "thinking": self.thinking_models or self.models,
            "compressor": self.compressor_models or self.models,
            "image_generation": self.figure_models or self.models,
            "read_figure": self.read_figure_models or self.models,
        }
        candidates = model_groups.get(category, self.models) or self.models
        preferred_name = str(preferred or "").strip()
        if preferred_name and preferred_name in candidates:
            return preferred_name
        default_name = str(self.default_models.get(category) or "").strip()
        if default_name and default_name in candidates:
            return default_name
        return candidates[0] if candidates else preferred_name

    def resolve_tool_choice(
        self,
        category: str = "execution",
        model: Optional[str] = None,
        requested: Optional[str] = None,
    ) -> str:
        normalized_requested = str(requested or "").strip().lower()
        if normalized_requested in {"required", "auto", "none"}:
            return normalized_requested

        normalized_model = str(model or "").strip()
        if normalized_model:
            model_choice = str(self.model_configs.get(normalized_model, {}).get("tool_choice", "")).strip().lower()
            if model_choice in {"required", "auto", "none"}:
                return model_choice

        return self.get_default_tool_choice(category)
    
    def chat(
        self,
        history: List,
        model: str,
        system_prompt: str,
        tool_list: List[str],
        tool_choice: Optional[str] = None,
        temperature: float = None,
        max_tokens: int = None,
        max_retries: int = 3,
        emit_tokens: str = None,
        debug_task_id: Optional[str] = None,
        debug_label: str = "execution",
        stream_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> LLMResponse:
        """
        调用LLM进行对话 (增强版：支持流式监控、自动重试、参数修复)
        
        Args:
            history: 对话历史，支持两种格式：
                     1. List[ChatMessage] - 传统格式（向后兼容）
                     2. List[Dict] - OpenAI原生格式，支持 tool/assistant/multimodal 消息
            model: 模型名称
            system_prompt: 系统提示词
            tool_list: 可用工具列表
            tool_choice: 工具选择策略；None 表示由调用方或模型配置决定
            temperature: 温度参数（None则使用配置文件默认值）
            max_tokens: 最大token数（None则使用配置文件默认值）
            max_retries: 最大重试次数（默认3次，即总共最多4次尝试）
            debug_task_id: 可选 task_id；传入后调试请求会按 task 追加到 conversations 目录
            debug_label: 调试记录标签，用于区分 execution / thinking / compressor 等来源
            
        Returns:
            LLMResponse对象
        """
        # 使用配置文件的默认值
        if temperature is None:
            temperature = self.temperature
        if max_tokens is None:
            max_tokens = self.max_tokens
        
        # 重试循环
        last_error = None
        fixed_system_prompt = system_prompt  # 可能会被修复的 system prompt
        type_fix_attempted = False  # 是否已尝试类型修复
        
        for retry_count in range(max_retries + 1):
            if retry_count > 0:
                safe_print(f"   🔄 LLM重试 {retry_count}/{max_retries}...")
                time.sleep(2 * retry_count)  # 指数退避：2秒, 4秒, 6秒
                
                # 根据上次错误生成提示（帮助 LLM 避免重复错误）
                if last_error:
                    retry_hint = self._generate_retry_hint(last_error.error_information, retry_count)
                    if retry_hint:
                        fixed_system_prompt = system_prompt + "\n\n" + retry_hint
                        safe_print(f"   📝 添加错误提醒: {retry_hint[:80]}...")
            
            # 调用内部实现
            response = self._chat_internal(
                history, model, fixed_system_prompt, tool_list, 
                tool_choice, temperature, max_tokens, emit_tokens, debug_task_id, debug_label, stream_callback
            )
            
            # 如果成功，直接返回
            if response.status == "success":
                if retry_count > 0 or type_fix_attempted:
                    safe_print(f"   ✅ 重试成功 (第{retry_count + 1}次尝试)")
                return response
            
            # 检查是否是工具参数类型错误（优先处理，不消耗重试次数）
            if not type_fix_attempted and ("did not match schema" in response.error_information or "expected array, but got string" in response.error_information):
                safe_print(f"   🔧 检测到工具参数类型错误，尝试自动修复...")
                
                # 尝试修复 system prompt（添加参数类型提示）
                fix_hint = self._generate_type_fix_hint(response.error_information)
                if fix_hint:
                    fixed_system_prompt = system_prompt + "\n\n" + fix_hint
                    safe_print(f"   📝 已添加参数类型提示，立即重试...")
                    type_fix_attempted = True
                    last_error = response
                    
                    # 立即重试，不计入retry_count
                    response = self._chat_internal(
                        history, model, fixed_system_prompt, tool_list, 
                        tool_choice, temperature, max_tokens, emit_tokens, debug_task_id, debug_label, stream_callback
                    )
                    
                    if response.status == "success":
                        safe_print(f"   ✅ 参数类型修复成功！")
                        return response
                    else:
                        safe_print(f"   ⚠️ 修复后仍失败，继续常规重试...")
                        last_error = response
                        continue
            
            # 所有错误都重试（包括API余额不足、密钥错误等）
            error_type = self._get_error_type(response.error_information)
            safe_print(f"   ⚠️ {error_type} (第{retry_count + 1}次)")
            last_error = response
            
            if retry_count < max_retries:
                continue  # 继续重试
            else:
                # 达到最大重试次数，抛出异常（让上层捕获并触发错误处理）
                safe_print(f"   ❌ 已达到最大重试次数 ({max_retries + 1})")
                error_msg = f"LLM 调用失败（已重试 {max_retries + 1} 次）: {response.error_information}"
                raise Exception(error_msg)
                # return response
        
        # 所有重试都失败了
        safe_print(f"   ❌ LLM调用失败（已重试{max_retries + 1}次）")
        return last_error
    
    def _chat_internal(
        self,
        history: List,
        model: str,
        system_prompt: str,
        tool_list: List[str],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
        emit_tokens: str = None,
        debug_task_id: Optional[str] = None,
        debug_label: str = "execution",
        stream_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> LLMResponse:
        """
        LLM调用的内部实现（使用 LiteLLM 原生超时机制）
        
        Args:
            emit_tokens: 控制是否向 JSONL 事件流发送流式 token。
                None - 不发送（默认，用于 compressor 等辅助调用）
                "token" - 发送 content delta 为 token 事件（主 Agent 调用）
                "thinking" - 发送 content delta 为 thinking_token 事件（Thinking Agent 调用）
            debug_task_id: 可选 task_id；传入后调试请求会按 task 追加到 conversations 目录
            debug_label: 调试记录标签，用于区分不同类型的 LLM 调用
        """
        try:
            def _emit_stream_chunk(kind: str, text: str, current_model: str):
                if not stream_callback or not text:
                    return
                try:
                    stream_callback({
                        "kind": str(kind or "content"),
                        "text": text,
                        "model": current_model,
                        "debug_label": debug_label,
                    })
                except Exception:
                    pass

            # 构建工具定义（OpenAI格式）
            tools_definition = self._build_tools_definition(tool_list)
            
            # 转换消息格式（兼容 ChatMessage 和 dict 两种输入）
            messages = [{"role": "system", "content": system_prompt}]
            for msg in history:
                if isinstance(msg, dict):
                    # dict 格式：直接使用（支持 tool/assistant/multimodal 等复杂消息）
                    messages.append(msg)
                elif isinstance(msg, ChatMessage):
                    # ChatMessage 格式：转换为 dict（向后兼容）
                    messages.append({"role": msg.role, "content": msg.content})
                else:
                    # 尝试 duck typing
                    messages.append({"role": msg.role, "content": msg.content})
            
            # 获取模型级别的配置（可覆盖全局 api_key 和 base_url）
            model_extra_params = self.model_configs.get(model, {})
            model_api_key = model_extra_params.get("api_key", self.api_key)
            model_base_url = model_extra_params.get("base_url", self.base_url)
            
            # 构建请求参数
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "api_key": model_api_key,
                "stream": True,  # 启用流式模式
                # --- LiteLLM 原生超时设定（从配置文件读取）---
                "timeout": self.timeout,              # 建立连接及整体响应的最大等待时间（秒）
                "stream_timeout": self.stream_timeout,  # 两个流式数据块（chunk）之间的最大间隔时间（秒）
            }
            
            # 只在 base_url 非空时添加 api_base
            if model_base_url:
                kwargs["api_base"] = model_base_url
            
            # 只在max_tokens > 0时添加
            if max_tokens > 0:
                kwargs["max_tokens"] = max_tokens
            
            # 添加工具定义（只有当工具列表非空时才添加工具相关参数）
            if tools_definition:
                # 工具列表非空：正常添加工具参数
                kwargs["tools"] = tools_definition
                if tool_choice == "required":
                    kwargs["tool_choice"] = "required"
                kwargs["parallel_tool_calls"] = False
            # 注意：当 tools_definition 为空时，即使 tool_choice="none" 也不添加任何参数
            # 这避免了 API 错误：When using `tool_choice`, `tools` must be set

            # === DEBUG: 将完整 messages 结构追加写入 task 级 JSONL ===
            try:
                self._append_debug_record(
                    messages=messages,
                    model=model,
                    debug_task_id=debug_task_id,
                    debug_label=debug_label,
                    tool_choice=tool_choice,
                    tool_count=len(tools_definition),
                    emit_tokens=emit_tokens,
                )
            except Exception as debug_error:
                safe_print(f"⚠️ DEBUG 写入失败: {debug_error}")
            # === END DEBUG ===
            
            # 添加模型特定的额外参数（api_key 和 base_url 已在上面处理）
            if model_extra_params:
                if "provider" in model_extra_params:
                    if "extra_body" not in kwargs:
                        kwargs["extra_body"] = {}
                    kwargs["extra_body"]["provider"] = model_extra_params["provider"]
                
                if "extra_headers" in model_extra_params:
                    kwargs["extra_headers"] = model_extra_params["extra_headers"]
                
                if "extra_body" in model_extra_params:
                    if "extra_body" not in kwargs:
                        kwargs["extra_body"] = {}
                    kwargs["extra_body"].update(model_extra_params["extra_body"])

            # 发起流式请求（LiteLLM 会根据 timeout 和 stream_timeout 自动管理超时）
            def _should_retry_without_required_tool_choice(msg: str) -> bool:
                m = (msg or "").lower()
                if "tool_choice" not in m:
                    return False
                incompat_markers = [
                    "thinking",
                    "thinking mode",
                    "reasoning",
                    "does not support",
                    "unsupported",
                    "invalidparameter",
                    "required or object",
                    "required",
                    "object",
                ]
                return any(marker in m for marker in incompat_markers)

            # 有些 OpenAI-compatible（如月之暗面/Kimi）会拒绝 tool_choice=required + thinking。
            # 这里做一次“就地兼容重试”：第一次失败则移除 tool_choice，保持 tools 但不强制 required。
            # 这类报错文案在不同 provider/router 上差异很大，因此只要是 tool_choice=required
            # 且首轮失败信息明确指向 tool_choice 不兼容，就降级为 auto 重试一次。
            for _compat_try in range(2):
                safe_print(f"   🌊 正在调用LLM (timeout={kwargs['timeout']}s, stream_timeout={kwargs['stream_timeout']}s)...")
                safe_print(f"   📨 请求模型: {model}")
                safe_print(f"   🛠️ 工具数量: {len(tools_definition)}")
                safe_print(f"   📝 消息数: {len(messages)}")
                request_start_time = time.time()

                # 累积变量
                accumulated_content = ""
                accumulated_reasoning_content = ""  # reasoning/thinking 内容
                visible_content = ""
                visible_reasoning_content = ""
                accumulated_tool_calls = {}  # index -> {id, name, arguments}
                finish_reason = "unknown"
                response_model = model
                chunk_count = 0
                content_stream_state = _EmbeddedToolCallStreamState()
                reasoning_stream_state = _EmbeddedToolCallStreamState()

                def _emit_visible_text(kind: str, text: str):
                    if not text:
                        return

                    _emit_stream_chunk(kind, text, response_model)

                    if kind == "content":
                        try:
                            safe_print(text, end="", flush=True)
                            if emit_tokens:
                                from utils.event_emitter import get_event_emitter as _get_ee
                                _ee = _get_ee()
                                if _ee.enabled:
                                    if emit_tokens == "thinking":
                                        _ee.emit({"type": "thinking_token", "text": text})
                                    else:
                                        _ee.token(text)
                        except Exception:
                            pass
                        return

                    try:
                        if emit_tokens:
                            from utils.event_emitter import get_event_emitter as _get_ee_reason
                            _ee_reason = _get_ee_reason()
                            if _ee_reason.enabled:
                                event_type = "thinking_token" if emit_tokens == "thinking" else "reasoning_token"
                                _ee_reason.emit({"type": event_type, "text": text})
                    except Exception:
                        pass

                try:
                    # --- 强制首包超时检测（包含 completion 调用以防止连接池死锁）---
                    try:
                        # 定义完整的初始化和首包获取函数（防止 httpx 连接池锁死锁）
                        def get_response_and_first_chunk():
                            iterator = completion(**kwargs)
                            first = next(iterator)
                            return iterator, first

                        # 强制首包超时时间（秒），包含连接建立+首包接收，防止 httpx 连接池死锁
                        first_chunk_timeout = self.first_chunk_timeout  # 从配置文件读取

                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(get_response_and_first_chunk)
                            try:
                                # 强制等待整个初始化过程（包括 completion 调用）
                                response_iterator, first_chunk = future.result(timeout=first_chunk_timeout)

                                # 处理首包
                                chunk_count += 1
                                latency = time.time() - request_start_time
                                safe_print(f"   ⚡️ 首包延迟: {latency:.2f}s")

                                # 处理首包逻辑
                                if hasattr(first_chunk, 'model'):
                                    response_model = first_chunk.model

                                if first_chunk.choices:
                                    delta = first_chunk.choices[0].delta
                                    if hasattr(delta, 'content') and delta.content:
                                        accumulated_content += delta.content
                                        visible_piece = content_stream_state.feed(delta.content)
                                        visible_content += visible_piece
                                        _emit_visible_text("content", visible_piece)

                                    # 累积 reasoning_content（thinking/reasoning 模型）
                                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                                        accumulated_reasoning_content += delta.reasoning_content
                                        visible_reasoning_piece = reasoning_stream_state.feed(delta.reasoning_content)
                                        visible_reasoning_content += visible_reasoning_piece
                                        _emit_visible_text("reasoning", visible_reasoning_piece)

                                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                                        for tc in delta.tool_calls:
                                            idx = tc.index
                                            if idx not in accumulated_tool_calls:
                                                accumulated_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                                            if tc.id:
                                                accumulated_tool_calls[idx]["id"] = tc.id
                                            if tc.function and tc.function.name:
                                                accumulated_tool_calls[idx]["name"] += tc.function.name
                                            if tc.function and tc.function.arguments:
                                                accumulated_tool_calls[idx]["arguments"] += tc.function.arguments

                                    if first_chunk.choices[0].finish_reason:
                                        finish_reason = first_chunk.choices[0].finish_reason

                            except concurrent.futures.TimeoutError:
                                raise TimeoutError(f"连接建立或首包接收超时（超过 {first_chunk_timeout}s）- 可能原因：httpx连接池死锁、网络断开、服务器无响应")

                    except StopIteration:
                        safe_print("   ⚠️ 响应为空（无数据块）")
                        return LLMResponse(
                            status="error",
                            output="",
                            tool_calls=[],
                            model=model,
                            finish_reason="empty",
                            error_information="Empty response - no chunks received"
                        )

                    # --- 继续处理剩余 chunk ---
                    for chunk in response_iterator:
                        chunk_count += 1

                        if hasattr(chunk, 'model'):
                            response_model = chunk.model

                        if not chunk.choices:
                            continue

                        delta = chunk.choices[0].delta

                        # A. 累积文本内容
                        if hasattr(delta, 'content') and delta.content:
                            accumulated_content += delta.content
                            visible_piece = content_stream_state.feed(delta.content)
                            visible_content += visible_piece
                            _emit_visible_text("content", visible_piece)

                        # A2. 累积 reasoning_content（thinking/reasoning 模型）
                        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                            accumulated_reasoning_content += delta.reasoning_content
                            visible_reasoning_piece = reasoning_stream_state.feed(delta.reasoning_content)
                            visible_reasoning_content += visible_reasoning_piece
                            _emit_visible_text("reasoning", visible_reasoning_piece)

                        # B. 累积工具调用
                        if hasattr(delta, 'tool_calls') and delta.tool_calls:
                            for tc in delta.tool_calls:
                                idx = tc.index
                                if idx not in accumulated_tool_calls:
                                    accumulated_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}

                                if tc.id:
                                    accumulated_tool_calls[idx]["id"] = tc.id
                                if tc.function and tc.function.name:
                                    accumulated_tool_calls[idx]["name"] += tc.function.name
                                if tc.function and tc.function.arguments:
                                    accumulated_tool_calls[idx]["arguments"] += tc.function.arguments

                        # C. 记录结束原因
                        if chunk.choices[0].finish_reason:
                            finish_reason = chunk.choices[0].finish_reason

                    safe_print(f"   ✅ 流式响应完成，共接收 {chunk_count} 个数据块")

                    visible_tail, embedded_content_markup = content_stream_state.finish()
                    if visible_tail:
                        visible_content += visible_tail
                        _emit_visible_text("content", visible_tail)

                    visible_reasoning_tail, embedded_reasoning_markup = reasoning_stream_state.finish()
                    if visible_reasoning_tail:
                        visible_reasoning_content += visible_reasoning_tail
                        _emit_visible_text("reasoning", visible_reasoning_tail)

                    # 构建最终的 ToolCall 对象列表
                    final_tool_calls = []
                    for idx in sorted(accumulated_tool_calls.keys()):
                        tc_data = accumulated_tool_calls[idx]

                        try:
                            args_str = tc_data["arguments"]
                            if not args_str:
                                args = {}
                            else:
                                args = json.loads(args_str)
                        except json.JSONDecodeError as e:
                            safe_print(f"\n⚠️ 工具参数JSON解析失败: {str(e)}")
                            safe_print(f"   原始参数: {tc_data['arguments'][:200]}...")

                            args = self._try_fix_json(tc_data["arguments"])
                            if args:
                                safe_print(f"   ✅ JSON 自动修复成功")
                            else:
                                safe_print(f"   ❌ JSON 修复失败，使用空参数")
                                args = {}

                        final_tool_calls.append(ToolCall(
                            id=tc_data["id"] or f"call_{idx}",
                            name=tc_data["name"],
                            arguments=args
                        ))

                    embedded_tool_calls = self._merge_tool_calls(
                        self._parse_embedded_tool_calls(embedded_content_markup),
                        self._parse_embedded_tool_calls(embedded_reasoning_markup),
                    )

                    if not embedded_tool_calls and (
                        "<|tool_call_begin|>" in accumulated_content or "<|tool_call_begin|>" in accumulated_reasoning_content
                    ):
                        embedded_tool_calls = self._merge_tool_calls(
                            self._parse_embedded_tool_calls(accumulated_content),
                            self._parse_embedded_tool_calls(accumulated_reasoning_content),
                        )

                    final_tool_calls = self._merge_tool_calls(final_tool_calls, embedded_tool_calls)
                    if final_tool_calls and finish_reason in {"", "unknown", "stop"}:
                        finish_reason = "tool_calls"

                    return LLMResponse(
                        status="success",
                        output=visible_content,
                        tool_calls=final_tool_calls,
                        model=response_model,
                        finish_reason=finish_reason,
                        reasoning_content=visible_reasoning_content
                    )

                except Exception as _compat_e:
                    _compat_msg = str(_compat_e)
                    if (
                        _compat_try == 0
                        and kwargs.get("tool_choice") == "required"
                        and tools_definition
                        and _should_retry_without_required_tool_choice(_compat_msg)
                    ):
                        safe_print("⚠️ 当前模型/路由不兼容 tool_choice=required，自动降级为 tool_choice=auto 重试一次...")
                        kwargs.pop("tool_choice", None)
                        continue
                    raise
        
        except Exception as e:
            # 捕获所有异常，包括 LiteLLM 抛出的超时异常
            error_msg = str(e)
            is_timeout = any(keyword in error_msg.lower() for keyword in ["timeout", "timed out", "time out"])
            
            if is_timeout:
                safe_print(f"⏱️  LLM调用超时 (原生超时机制)")
                safe_print(f"   超时详情: {error_msg}")
                safe_print(f"   💡 提示: 如果频繁超时，可能是：")
                safe_print(f"      1. 网络连接不稳定")
                safe_print(f"      2. 上下文过长导致 API 响应缓慢")
                safe_print(f"      3. API 服务商限流或过载")
            else:
                safe_print(f"❌ LLM调用异常: {error_msg}")
            
            # 返回包含详细错误信息的响应
            import traceback
            error_detail = traceback.format_exc()
            
            return LLMResponse(
                status="error",
                output="",
                tool_calls=[],
                model=model,
                finish_reason="timeout" if is_timeout else "error",
                error_information=f"{error_msg}\n\nDetails:\n{error_detail}"
            )
    
    def set_tools_config(self, tools_config: Dict):
        """
        设置工具配置（从ConfigLoader传入）
        
        Args:
            tools_config: 工具配置字典
        """
        self.tools_config = tools_config
    
    def _try_fix_json(self, json_str: str) -> Dict:
        """
        尝试修复常见的 JSON 格式错误
        
        Args:
            json_str: 可能有问题的 JSON 字符串
            
        Returns:
            解析后的字典，失败返回 None
        """
        if not json_str or not json_str.strip():
            return {}
        
        try:
            # 策略 1: 去除尾部多余的逗号
            fixed = json_str.strip()
            if fixed.endswith(',}'):
                fixed = fixed[:-2] + '}'
            if fixed.endswith(',]'):
                fixed = fixed[:-2] + ']'
            
            # 策略 2: 补全缺失的结束括号
            open_braces = fixed.count('{')
            close_braces = fixed.count('}')
            if open_braces > close_braces:
                fixed += '}' * (open_braces - close_braces)
            
            open_brackets = fixed.count('[')
            close_brackets = fixed.count(']')
            if open_brackets > close_brackets:
                fixed += ']' * (open_brackets - close_brackets)
            
            # 策略 3: 尝试解析
            result = json.loads(fixed)
            return result
        
        except Exception:
            # 所有修复策略都失败
            return None
    
    def _generate_type_fix_hint(self, error_info: str) -> str:
        """
        从错误信息中提取参数类型错误，生成修复提示
        
        Args:
            error_info: 错误信息字符串
            
        Returns:
            修复提示文本（添加到 system prompt）
        """
        try:
            import re
            
            # 提取工具名
            tool_match = re.search(r"tool (\w+) did not match", error_info)
            if not tool_match:
                return ""
            tool_name = tool_match.group(1)
            
            # 提取所有参数错误（支持多个参数同时出错）
            param_errors = re.findall(r"`/([\w_]+)`:\s*expected\s+(\w+),\s*but\s+got\s+(\w+)", error_info)
            
            if not param_errors:
                return ""
            
            # 分类处理
            null_params = []
            type_mismatches = []
            
            for param_name, expected_type, actual_type in param_errors:
                if actual_type == "null":
                    null_params.append(param_name)
                else:
                    type_mismatches.append((param_name, expected_type, actual_type))
            
            hints = []
            
            # 处理 null 值错误
            if null_params:
                params_str = "、".join(null_params)
                hints.append(f"""
⚠️ 参数 null 值错误：
工具 {tool_name} 的参数 {params_str} 被设置为 null

重要规则：
- 可选参数如果不需要，必须完全省略，不要传 null！
- 错误示例: {{"path": "file.txt", "start_line": null}}  ❌
- 正确示例: {{"path": "file.txt"}}  ✅
""")
            
            # 处理类型不匹配错误
            for param_name, expected_type, actual_type in type_mismatches:
                safe_print(f"   🔍 检测到: 工具 {tool_name}, 参数 {param_name}, 需要 {expected_type}, 得到 {actual_type}")
                
                if expected_type == "array" and actual_type == "string":
                    hints.append(f"""
⚠️ 参数类型错误：
工具 {tool_name} 的参数 {param_name} 必须是数组类型！
- 错误: {{"{param_name}": "value"}}  ❌
- 正确: {{"{param_name}": ["value"]}}  ✅
""")
                elif expected_type == "string" and actual_type == "array":
                    hints.append(f"""
⚠️ 参数类型错误：
工具 {tool_name} 的参数 {param_name} 必须是字符串类型！
- 错误: {{"{param_name}": ["value"]}}  ❌
- 正确: {{"{param_name}": "value"}}  ✅
""")
                else:
                    hints.append(f"""
⚠️ 参数类型错误：
工具 {tool_name} 的参数 {param_name} 需要 {expected_type}，实际得到 {actual_type}
""")
            
            return "\n".join(hints) if hints else ""
        
        except Exception as e:
            safe_print(f"   ⚠️ 生成修复提示失败: {e}")
            return ""
    
    def _get_error_type(self, error_info: str) -> str:
        """
        从错误信息中提取友好的错误类型描述
        
        Args:
            error_info: 错误信息字符串
            
        Returns:
            友好的错误类型描述
        """
        if "timeout" in error_info.lower() or "timed out" in error_info.lower():
            return "连接超时"
        elif "Internal Server Error" in error_info:
            return "服务器内部错误"
        elif "Failed to parse" in error_info and "JSON" in error_info:
            return "JSON格式错误"
        elif "expected integer, but got null" in error_info:
            return "参数null值错误"
        elif "expected array, but got string" in error_info:
            return "参数类型错误(string→array)"
        elif "expected string, but got array" in error_info:
            return "参数类型错误(array→string)"
        elif "did not match schema" in error_info:
            return "参数校验失败"
        elif "not in request.tools" in error_info:
            return "工具不存在错误"
        elif "Invalid API key" in error_info or "api_key" in error_info.lower():
            return "API密钥错误"
        elif "rate limit" in error_info.lower():
            return "速率限制"
        elif "insufficient" in error_info.lower() or "quota" in error_info.lower():
            return "余额不足"
        else:
            return "未知错误"
    
    def _generate_retry_hint(self, error_info: str, retry_count: int) -> str:
        """
        根据错误信息生成重试提示（添加到 system prompt）
        
        Args:
            error_info: 错误信息字符串
            retry_count: 当前重试次数
            
        Returns:
            重试提示文本
        """
        import re
        
        # 1. 服务器错误 - 静默重试（不需要提示 LLM）
        if "Internal Server Error" in error_info:
            return ""
        
        # 2. null 值错误 - 最常见
        if "but got null" in error_info:
            # 尝试提取所有 null 参数
            null_params = re.findall(r"`/([\w_]+)`:\s*expected\s+\w+,\s*but\s+got\s+null", error_info)
            if null_params:
                params_str = "、".join(null_params)
                hint = f"""
⚠️ 第{retry_count}次重试警告：
上次调用失败！原因：参数 {params_str} 被设置为 null

重要规则：
- 可选参数如果不需要，必须完全省略，不要传递 null 值！
- 错误示例: {{"path": "file.txt", "start_line": null}}  ❌
- 正确示例: {{"path": "file.txt"}}  ✅ (直接省略 start_line)

请重新生成工具调用，确保不传递 null 值。
"""
                return hint
        
        # 3. JSON 解析错误
        if "Failed to parse" in error_info and "JSON" in error_info:
            hint = f"""
⚠️ 第{retry_count}次重试警告：
上次调用失败！原因：工具参数 JSON 格式错误

JSON 格式要求：
- 所有键名必须用双引号：{{"key": "value"}}  ✅  {{key: "value"}}  ❌
- 字符串值必须用双引号：{{"path": "file.txt"}}  ✅  {{"path": 'file.txt'}}  ❌
- 不要有尾部逗号：{{"a": 1, "b": 2}}  ✅  {{"a": 1, "b": 2,}}  ❌
- 特殊字符需要转义：{{"path": "C:\\\\file.txt"}}  ✅

请重新生成工具调用，确保 JSON 格式正确。
"""
            return hint
        
        # 4. 工具不存在错误
        if "not in request.tools" in error_info:
            # 尝试提取工具名
            tool_match = re.search(r"attempted to call tool ['\"](\w+)['\"]", error_info)
            wrong_tool = tool_match.group(1) if tool_match else "某个工具"
            
            hint = f"""
⚠️ 第{retry_count}次重试警告：
上次调用失败！原因：尝试调用不存在的工具 '{wrong_tool}'

重要规则：
- 只能调用提供的工具列表中的工具
- 不要自己发明或假设存在某个工具
- 仔细检查可用工具列表

请重新生成工具调用，只使用已提供的工具。
"""
            return hint
        
        # 5. 类型不匹配（array vs string）
        if "expected array, but got string" in error_info:
            tool_match = re.search(r"tool (\w+) did not match", error_info)
            param_match = re.search(r"`/([\w_]+)`:\s*expected array", error_info)
            
            tool_name = tool_match.group(1) if tool_match else "某工具"
            param_name = param_match.group(1) if param_match else "某参数"
            
            hint = f"""
⚠️ 第{retry_count}次重试警告：
上次调用失败！原因：工具 {tool_name} 的参数 {param_name} 类型错误

类型要求：
- 参数 {param_name} 必须是数组（array）类型
- 错误示例: {{"{param_name}": "value"}}  ❌
- 正确示例: {{"{param_name}": ["value"]}}  ✅

请重新生成工具调用，使用数组格式（方括号包裹）。
"""
            return hint
        
        # 6. API 余额/密钥错误 - 也给提示（虽然重试可能无效）
        if "insufficient" in error_info.lower() or "quota" in error_info.lower():
            hint = f"""
⚠️ 第{retry_count}次重试警告：
上次调用失败！原因：API 余额不足或配额已用尽

这可能是临时问题，正在重试...
如果持续失败，请检查 API 账户状态。
"""
            return hint
        
        if "Invalid API key" in error_info or "api_key" in error_info.lower():
            hint = f"""
⚠️ 第{retry_count}次重试警告：
上次调用失败！原因：API 密钥错误或无效

这可能是临时问题，正在重试...
如果持续失败，请检查 API 密钥配置。
"""
            return hint
        
        # 7. 通用提示
        hint = f"""
⚠️ 第{retry_count}次重试警告：
上次调用失败！错误信息：{error_info[:200]}

请仔细检查工具调用的格式、参数类型和值，确保符合工具定义。
"""
        return hint
    
    def _build_tools_definition(self, tool_list: List[str]) -> List[Dict]:
        """构建工具定义（OpenAI格式）"""
        if not self.tools_config:
            return []
        
        tools = []
        for tool_name in tool_list:
            if tool_name in self.tools_config:
                tool_config = self.tools_config[tool_name]
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool_config.get("name", tool_name),
                        "description": tool_config.get("description", ""),
                        "parameters": tool_config.get("parameters", {})
                    }
                })
        
        return tools


if __name__ == "__main__":
    # 测试LLM客户端
    try:
        client = SimpleLLMClient()
        safe_print(f"✅ 可用模型: {client.models}")
        
        # 测试简单调用
        history = [ChatMessage(role="user", content="你好")]
        response = client.chat(
            history=history,
            model=client.models[0],  # 使用第一个可用模型
            system_prompt="你是一个AI助手，请使用工具来完成任务",
            tool_list=["dir_list"],
            tool_choice="required"
        )
        
        safe_print(f"✅ 响应状态: {response.status}")
        safe_print(f"✅ 工具调用数量: {len(response.output)}")
        if response.tool_calls:
            safe_print(f"✅ 第一个工具: {response.tool_calls[0].name}")
    except Exception as e:
        safe_print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
