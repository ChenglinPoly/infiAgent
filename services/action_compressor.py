#!/usr/bin/env python3
from utils.windows_compat import safe_print
# -*- coding: utf-8 -*-
"""
历史动作压缩服务
策略：总结历史XML + 保留最新action + 压缩最新action的大字段
"""

import json
from typing import List, Dict, Optional

try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False


class ActionCompressor:
    """历史动作压缩器"""
    
    # action_history 中的内部元数据字段（不参与 XML 转换和 token 统计）
    _INTERNAL_FIELDS = {"_turn", "tool_call_id", "assistant_content", "reasoning_content", "_has_image", "_image_base64"}
    
    def __init__(
        self,
        llm_client,
        preferred_model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        debug_task_id: Optional[str] = None,
    ):
        """
        初始化
        
        Args:
            llm_client: LLM客户端实例（用于总结）
        """
        self.llm_client = llm_client
        self.compressor_multimodal = getattr(llm_client, 'compressor_multimodal', False)
        self.preferred_model = preferred_model
        self.max_tokens = max_tokens
        self.debug_task_id = debug_task_id
        
        # 初始化tiktoken
        if HAS_TIKTOKEN:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        else:
            self.encoding = None

    def _resolve_compressor_model(self) -> str:
        return self.llm_client.resolve_model("compressor", self.preferred_model)

    def _resolve_compressor_tool_choice(self, model: str) -> str:
        return self.llm_client.resolve_tool_choice("compressor", model)
    
    def count_tokens(self, text: str) -> int:
        """统计token数"""
        if self.encoding:
            return len(self.encoding.encode(text))
        else:
            chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
            other_chars = len(text) - chinese_chars
            return int(chinese_chars / 1.5 + other_chars / 4)
    
    def compress_if_needed(
        self,
        action_history: List[Dict],
        max_context_window: int,
        thinking: str = "",
        task_input: str = "",
        save_callback=None  # 添加保存回调，确保压缩后立即保存
    ) -> List[Dict]:
        """
        检查并压缩历史动作
        
        策略：
        1. 保留最新1条action（完整或压缩大字段）
        2. 之前的所有action总结为一个summary_action
        3. 基于 thinking 和 task_input 判断哪些信息有效、哪些无关
        
        Args:
            action_history: 动作历史
            max_context_window: 最大窗口大小
            thinking: 当前的 thinking 内容（包含 todolist 和计划）
            task_input: 任务需求描述
            
        Returns:
            压缩后的action_history
        """
        if not action_history:
            return []
        
        # 如果只有一条
        if len(action_history) == 1:
            # 检查是否需要压缩字段
            return [self._compress_action_fields(action_history[0], max_context_window // 2)]
        
        # 分离最新和历史
        recent_action = action_history[-1]
        historical_actions = action_history[:-1]
        
        # 计算整体token数
        total_text = self._actions_to_xml(action_history)
        total_tokens = self.count_tokens(total_text+thinking+task_input)
        
        # 如果不超限，不压缩
        if total_tokens <= max_context_window - 20000:
            return action_history
        
        safe_print(f"🔄 历史动作需要压缩: {total_tokens} tokens > {max_context_window - 20000}")
        
        # 压缩策略：
        # 1. 历史 → 基于 thinking 和 task_input 智能总结为5k tokens
        # 2. 最新 → 压缩为max_window的50%
        
        summary_action = self._summarize_historical_xml(
            self._actions_to_xml(historical_actions),
            target_tokens=5000,  # 历史总结固定5k tokens
            thinking=thinking,
            task_input=task_input,
            max_context_window=max_context_window,
            actions=historical_actions  # 传递原始 actions（用于提取图片）
        )
        
        # 压缩最新action的大字段（50% of max_window）
        compressed_recent = self._compress_action_fields(
            recent_action,
            int(max_context_window * 0.5),  # 80000 * 0.5 = 40000 tokens
            thinking=thinking,
            task_input=task_input,
            max_context_window=max_context_window
        )
        
        result = [summary_action, compressed_recent]
        
        # 验证压缩效果
        result_xml = self._actions_to_xml(result)
        result_tokens = self.count_tokens(result_xml)
        safe_print(f"✅ 压缩完成: {total_tokens} tokens → {result_tokens} tokens (压缩比: {result_tokens/total_tokens*100:.1f}%)")
        
        return result
    
    def _actions_to_xml(self, actions: List[Dict]) -> str:
        """将actions转换为XML格式文本（跳过内部元数据字段）"""
        xml_parts = []
        for action in actions:
            tool_name = action.get("tool_name", "")
            arguments = action.get("arguments", {})
            result = action.get("result", {})
            
            action_xml = f"<action>\n  <tool_name>{tool_name}</tool_name>\n"
            
            # 参数（跳过内部字段）
            for k, v in arguments.items():
                if k in self._INTERNAL_FIELDS:
                    continue
                v_str = str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                action_xml += f"  <tool_use:{k}>{v_str}</tool_use:{k}>\n"
            
            # 结果（排除以 _ 开头的内部字段，特别是 _image_base64）
            result_clean = {k: v for k, v in result.items() if not k.startswith("_")}
            result_json = json.dumps(result_clean, ensure_ascii=False, indent=2)
            action_xml += f"  <result>\n{result_json}\n  </result>\n</action>"
            
            xml_parts.append(action_xml)
        
        return "\n\n".join(xml_parts)
    
    def _extract_images_from_actions(self, actions: List[Dict]) -> List[Dict]:
        """
        从 action 列表中提取图片数据（用于多模态压缩）
        
        Returns:
            [{base64: str, tool_name: str}] 列表（每张图一个条目）
        """
        images = []
        if not actions:
            return images
        for action in actions:
            if action.get("_has_image") and action.get("_image_base64"):
                img_data = action["_image_base64"]
                tool_name = action.get("tool_name", "image_read")
                # _image_base64 可能是列表或单值（兼容两种格式）
                if isinstance(img_data, list):
                    for b64 in img_data:
                        images.append({"base64": b64, "tool_name": tool_name})
                else:
                    images.append({"base64": img_data, "tool_name": tool_name})
        return images
    
    def _summarize_historical_xml(
        self, 
        xml_text: str, 
        target_tokens: int = 5000,
        thinking: str = "",
        task_input: str = "",
        max_context_window: int = None,
        actions: List[Dict] = None
    ) -> Dict:
        """
        总结历史XML内容为一个summary action
        基于 thinking 和 task_input 智能判断哪些信息有效
        支持分段压缩：如果数据量过大，自动分段处理
        支持多模态：当 compressor_multimodal=True 时，在压缩 LLM 调用中嵌入图片
        
        Args:
            xml_text: 历史actions的XML文本
            target_tokens: 目标token数
            thinking: 当前的 thinking 内容（包含 todolist 和计划）
            task_input: 任务需求描述
            max_context_window: 最大上下文窗口（用于判断是否需要分段）
            actions: 原始 action 列表（用于提取图片数据，可选）
            
        Returns:
            一个summary action
        """
        try:
            from services.llm_client import ChatMessage
            
            # 提取图片数据（如果支持多模态）
            images = self._extract_images_from_actions(actions) if self.compressor_multimodal and actions else []
            
            # 检查数据量，决定是否需要分段压缩
            xml_tokens = self.count_tokens(xml_text)
            
            # 获取压缩模型的上下文限制（从参数或LLM客户端获取）
            compressor_context_limit = max_context_window or self.llm_client.max_context_window
            
            # 构建上下文信息
            context_info = ""
            if task_input:
                context_info += f"\n<任务需求>\n{task_input}\n</任务需求>\n"
            if thinking:
                context_info += f"\n<当前进度与计划>\n{thinking}\n</当前进度与计划>\n"
            
            context_tokens = self.count_tokens(context_info)
            
            # 如果数据量 + 上下文 + 提示词 超过模型限制的60%，使用分段压缩
            overhead_tokens = 2000  # 提示词和格式的开销
            available_tokens = int(compressor_context_limit * 0.6) - context_tokens - overhead_tokens
            
            if xml_tokens > available_tokens:
                safe_print(f"   📦 数据量过大({xml_tokens} tokens)，启用分段压缩")
                return self._chunked_summarize(xml_text, target_tokens, thinking, task_input, available_tokens)
            
            # 数据量合适，直接压缩
            return self._single_summarize(xml_text, target_tokens, thinking, task_input, context_info, images=images)
        
        except Exception as e:
            safe_print(f"⚠️ 总结失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "tool_name": "_historical_summary",
                "arguments": {},
                "result": {"status": "success", "output": "[历史动作已省略]", "_is_summary": True}
            }
    
    def _single_summarize(
        self,
        xml_text: str,
        target_tokens: int,
        thinking: str,
        task_input: str,
        context_info: str,
        images: List[Dict] = None
    ) -> Dict:
        """
        单次压缩（数据量不大时使用）
        支持多模态：当有图片时，在 LLM 调用中嵌入图片
        
        Args:
            images: [{base64: str, tool_name: str}] 图片列表（可选）
        """
        prompt = f"""你是智能历史信息压缩助手。请基于任务需求和当前进度，智能压缩以下历史动作。

{context_info}

<历史动作>
{xml_text}
</历史动作>

压缩要求：
1. **目标长度**: 严格控制在 {target_tokens} tokens 以内
2. **智能筛选**: 
   - 分析 thinking 中的 todolist/计划，判断哪些动作是为了完成未完成的任务目标
   - 保留已完成任务相关的**关键结果**（如生成的文件路径、重要输出）
   - 丢弃无关或失败的尝试信息
3. **优先保留**:
   - 成功完成的关键步骤（如创建的文件、执行的代码、获取的数据）
   - 重要的文件路径和位置信息
   - 对后续任务有参考价值的输出
4. **可以丢弃**:
   - 重复的尝试和错误信息
   - 中间的调试过程
   - 与当前任务目标无关的探索性操作
5. **格式要求**:
   - 按时间顺序总结
   - 突出关键成果和产出
   - 保持信息的连贯性
{"6. **图片说明**: 下方附有历史动作中读取的图片，请在总结中包含对图片内容的文字描述。" if images else ""}

请直接输出压缩后的总结（中文）："""
        
        # 构建 messages（支持多模态图片嵌入）
        if images:
            content_parts = [{"type": "text", "text": prompt}]
            for img in images:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": img["base64"] if img["base64"].startswith("data:") else f"data:image/jpeg;base64,{img['base64']}"}
                })
                content_parts.append({
                    "type": "text",
                    "text": f"(Image from {img['tool_name']})"
                })
            history = [{"role": "user", "content": content_parts}]
        else:
            history = [{"role": "user", "content": prompt}]
        
        compressor_model = self._resolve_compressor_model()
        response = self.llm_client.chat(
            history=history,
            model=compressor_model,
            system_prompt=f"你是整体上下文构造专家。目标：将内容压缩到{target_tokens} tokens以内。",
            tool_list=[],
            tool_choice=self._resolve_compressor_tool_choice(compressor_model),
            max_tokens=self.max_tokens,
            debug_task_id=self.debug_task_id,
            debug_label="action_compressor",
        )
        
        summary = response.output if response.status == "success" else "[总结失败]"
        
        return {
            "tool_name": "_historical_summary",
            "arguments": {},
            "result": {
                "status": "success",
                "output": summary,
                "_is_summary": True
            }
        }
    
    def _chunked_summarize(
        self,
        xml_text: str,
        target_tokens: int,
        thinking: str,
        task_input: str,
        chunk_size_tokens: int
    ) -> Dict:
        """
        分段压缩（数据量过大时使用）
        
        Args:
            xml_text: 完整的XML文本
            target_tokens: 最终目标token数
            thinking: thinking内容
            task_input: 任务输入
            chunk_size_tokens: 每段的最大token数
        
        Returns:
            压缩后的summary action
        """
        from services.llm_client import ChatMessage
        
        # 按action分割xml_text
        # 简单方法：按 </action> 分割
        action_blocks = xml_text.split('</action>')
        action_blocks = [block + '</action>' for block in action_blocks if block.strip()]
        
        # 将actions分组到chunks中
        chunks = []
        current_chunk = []
        current_chunk_tokens = 0
        
        for action_block in action_blocks:
            action_tokens = self.count_tokens(action_block)
            
            if current_chunk_tokens + action_tokens > chunk_size_tokens and current_chunk:
                # 当前chunk已满，开始新chunk
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [action_block]
                current_chunk_tokens = action_tokens
            else:
                current_chunk.append(action_block)
                current_chunk_tokens += action_tokens
        
        # 添加最后一个chunk
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        safe_print(f"      分成 {len(chunks)} 段进行压缩")
        
        # 构建上下文信息
        context_info = ""
        if task_input:
            context_info += f"\n<任务需求>\n{task_input}\n</任务需求>\n"
        if thinking:
            context_info += f"\n<当前进度与计划>\n{thinking}\n</当前进度与计划>\n"
        
        # 对每个chunk进行压缩
        chunk_summaries = []
        target_per_chunk = target_tokens // len(chunks)
        
        for i, chunk in enumerate(chunks):
            safe_print(f"      压缩第 {i+1}/{len(chunks)} 段...")
            
            prompt = f"""你是智能历史信息压缩助手。这是分段压缩任务的第 {i+1}/{len(chunks)} 段。

{context_info}

<本段历史动作>
{chunk}
</本段历史动作>

压缩要求：
1. **目标长度**: 严格控制在 {target_per_chunk} tokens 以内
2. **智能筛选**: 
   - 根据任务需求和进度，保留关键结果和重要信息
   - 丢弃无关或失败的尝试
3. **优先保留**:
   - 成功的关键步骤和产出
   - 重要的文件路径和数据
   - 对后续任务有价值的输出
4. **格式要求**:
   - 按时间顺序简要总结本段的关键动作
   - 突出重要成果

请直接输出本段的压缩总结（中文）："""
            
            history = [ChatMessage(role="user", content=prompt)]
            
            try:
                compressor_model = self._resolve_compressor_model()
                response = self.llm_client.chat(
                    history=history,
                    model=compressor_model,
                    system_prompt=f"你是内容压缩专家。目标：将本段压缩到{target_per_chunk} tokens以内。",
                    tool_list=[],  # 空列表表示不使用工具
                    tool_choice=self._resolve_compressor_tool_choice(compressor_model),
                    max_tokens=self.max_tokens,
                    debug_task_id=self.debug_task_id,
                    debug_label="action_compressor",
                )
                
                if response.status == "success":
                    chunk_summaries.append(f"[段{i+1}] {response.output}")
                    safe_print(f"         ✅ 第{i+1}段压缩成功")
                else:
                    chunk_summaries.append(f"[段{i+1}] [压缩失败]")
                    safe_print(f"         ⚠️ 第{i+1}段压缩失败: {response.output}")
            except Exception as e:
                chunk_summaries.append(f"[段{i+1}] [压缩异常]")
                safe_print(f"         ❌ 第{i+1}段压缩异常: {e}")
        
        # 合并所有段的总结
        final_summary = "\n\n".join(chunk_summaries)
        
        safe_print(f"      ✅ 分段压缩完成，共{len(chunks)}段")
        
        return {
            "tool_name": "_historical_summary",
            "arguments": {},
            "result": {
                "status": "success",
                "output": final_summary,
                "_is_summary": True,
                "_chunked": True,
                "_chunks_count": len(chunks)
            }
        }
    
    def _compress_action_fields(
        self, 
        action: Dict, 
        max_field_tokens: int,
        thinking: str = "",
        task_input: str = "",
        max_context_window: int = None
    ) -> Dict:
        """
        压缩action中的大字段（arguments和result）
        
        Args:
            action: 原始action
            max_field_tokens: 单个字段的最大token数（通常是max_context_window/2）
            thinking: 当前的 thinking 内容
            task_input: 任务需求描述
            max_context_window: 最大上下文窗口（传递给字段压缩方法）
            
        Returns:
            压缩后的action
        """
        compressed_action = action.copy()
        
        # 压缩arguments中的大字段
        if "arguments" in compressed_action:
            compressed_args = {}
            for k, v in compressed_action["arguments"].items():
                v_str = str(v)
                v_tokens = self.count_tokens(v_str)
                
                if v_tokens > max_field_tokens:
                    safe_print(f"   🤖 LLM压缩arguments.{k}: {v_tokens} tokens → {max_field_tokens} tokens")
                    compressed_v = self._llm_compress_field(
                        v_str, 
                        max_field_tokens, 
                        action.get("tool_name", "unknown"),
                        thinking=thinking,
                        task_input=task_input,
                        field_context=f"工具 '{action.get('tool_name')}' 的参数 '{k}'",
                        max_context_window=max_context_window
                    )
                    compressed_args[k] = compressed_v
                else:
                    compressed_args[k] = v
            compressed_action["arguments"] = compressed_args
        
        # 压缩result.output
        if "result" in compressed_action and "output" in compressed_action["result"]:
            output = compressed_action["result"]["output"]
            output_tokens = self.count_tokens(output)
            
            if output_tokens > max_field_tokens:
                safe_print(f"   🤖 LLM压缩result.output: {output_tokens} tokens → {max_field_tokens} tokens")
                # 构建字段上下文（包含工具参数信息）
                args_summary = ", ".join([f"{k}={v}" for k, v in compressed_action.get("arguments", {}).items()])
                field_context = f"工具 '{action.get('tool_name')}' 的执行结果 (参数: {args_summary})"
                
                compressed_output = self._llm_compress_field(
                    output, 
                    max_field_tokens, 
                    action.get("tool_name", "unknown"),
                    thinking=thinking,
                    task_input=task_input,
                    field_context=field_context,
                    max_context_window=max_context_window
                )
                compressed_action["result"]["output"] = compressed_output
                compressed_action["result"]["_compressed"] = True
                compressed_action["result"]["_original_tokens"] = output_tokens
        
        return compressed_action
    
    def _llm_compress_field(
        self, 
        text: str, 
        target_tokens: int, 
        tool_name: str,
        thinking: str = "",
        task_input: str = "",
        field_context: str = "",
        max_context_window: int = None
    ) -> str:
        """
        使用LLM智能压缩单个字段
        支持分段压缩：如果字段内容过大，自动分段处理
        
        Args:
            text: 原始文本
            target_tokens: 目标token数
            tool_name: 工具名称（用于优化提示词）
            thinking: 当前的 thinking 内容
            task_input: 任务需求描述
            field_context: 字段上下文（如 "工具 'file_read' 的参数 'path'"）
            max_context_window: 最大上下文窗口（用于判断是否需要分段）
            
        Returns:
            压缩后的文本
        """
        try:
            from services.llm_client import ChatMessage
            
            # 根据工具类型定制提示词
            if "parse" in tool_name.lower() or "read" in tool_name.lower():
                content_type = "文档内容"
                focus = "保留文档的关键章节、核心论点、重要数据和结论"
            elif "execute" in tool_name.lower() or "run" in tool_name.lower():
                content_type = "代码执行结果"
                focus = "保留关键输出、错误信息、返回值和执行状态"
            elif "search" in tool_name.lower():
                content_type = "搜索结果"
                focus = "保留最相关的搜索结果和关键匹配信息"
            else:
                content_type = "内容"
                focus = "保留最重要的核心信息"
            
            # 构建上下文信息
            context_info = ""
            if task_input:
                context_info += f"\n<任务需求>\n{task_input}\n</任务需求>\n"
            if thinking:
                context_info += f"\n<当前进度与计划>\n{thinking}\n</当前进度与计划>\n"
            if field_context:
                context_info += f"\n<字段来源>\n这是最新动作中 {field_context} 的内容\n</字段来源>\n"
            
            # 检查字段大小，决定是否需要分段压缩
            text_tokens = self.count_tokens(text)
            context_tokens = self.count_tokens(context_info)
            
            # 获取压缩模型的上下文限制（从参数或LLM客户端获取）
            compressor_context_limit = max_context_window or self.llm_client.max_context_window
            overhead_tokens = 1000  # 提示词开销
            available_tokens = int(compressor_context_limit * 0.6) - context_tokens - overhead_tokens
            
            # 如果文本过大，使用分段压缩
            if text_tokens > available_tokens:
                safe_print(f"      📦 字段过大({text_tokens} tokens)，启用分段压缩")
                return self._chunked_compress_field(
                    text, target_tokens, tool_name, content_type, focus,
                    thinking, task_input, field_context, available_tokens
                )
            
            # 文本大小合适，直接压缩
            prompt = f"""你是智能内容压缩助手。请基于任务需求和当前进度，压缩以下{content_type}。

{context_info}

<待压缩的{content_type}>
{text}
</待压缩的{content_type}>

压缩要求：
1. **目标长度**: 严格控制在 {target_tokens} tokens 以内
2. **智能筛选**: 
   - 根据 thinking 中的任务进度，判断哪些信息对未完成的任务有价值
   - {focus}
   - 丢弃与当前任务目标无关的内容
3. **优先保留**:
   - 与任务目标直接相关的关键信息
   - 重要的文件路径、数据、结果
   - 后续步骤需要引用的内容
4. **可以丢弃**:
   - 冗余的细节和重复信息
   - 与任务无关的探索性内容
   - 中间过程的调试信息
5. **格式要求**:
   - 保持信息的连贯性和可读性
   - 使用总结和提炼，而非简单截断
   - 如果有结构化内容（表格、列表），保留关键部分

请直接输出压缩后的内容（不要额外说明）："""
            
            history = [ChatMessage(role="user", content=prompt)]
            
            compressor_model = self._resolve_compressor_model()
            response = self.llm_client.chat(
                history=history,
                model=compressor_model,
                system_prompt=f"你是智能内容压缩助手。目标：将{content_type}压缩到{target_tokens} tokens，同时保留核心信息。",
                tool_list=[],  # 空列表表示不使用工具
                tool_choice=self._resolve_compressor_tool_choice(compressor_model),
                max_tokens=self.max_tokens,
                debug_task_id=self.debug_task_id,
                debug_label="action_compressor",
            )
            
            compressed = response.output if response.status == "success" else text[:1000] + "\n[压缩失败，仅保留前1000字符]"
            
            # 验证压缩效果
            actual_tokens = self.count_tokens(compressed)
            safe_print(f"      压缩效果: {actual_tokens}/{target_tokens} tokens ({actual_tokens/target_tokens*100:.1f}%)")
            
            return compressed
            
        except Exception as e:
            safe_print(f"⚠️ LLM压缩失败，使用fallback: {e}")
            # fallback：首尾保留
            return self._fallback_compress(text, target_tokens)
    
    def _chunked_compress_field(
        self,
        text: str,
        target_tokens: int,
        tool_name: str,
        content_type: str,
        focus: str,
        thinking: str,
        task_input: str,
        field_context: str,
        chunk_size_tokens: int
    ) -> str:
        """
        分段压缩字段内容
        
        Args:
            text: 原始文本
            target_tokens: 最终目标token数
            tool_name: 工具名称
            content_type: 内容类型描述
            focus: 压缩重点
            thinking: thinking内容
            task_input: 任务输入
            field_context: 字段上下文
            chunk_size_tokens: 每段的最大token数
            
        Returns:
            压缩后的文本
        """
        from services.llm_client import ChatMessage
        
        # 按段落或固定字符数分割文本
        # 简单策略：按\n\n分割段落，如果段落太大则按字符数分割
        paragraphs = text.split('\n\n')
        
        chunks = []
        current_chunk = []
        current_chunk_tokens = 0
        
        for para in paragraphs:
            para_tokens = self.count_tokens(para)
            
            # 如果单个段落就超过chunk大小，需要强制分割
            if para_tokens > chunk_size_tokens:
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_chunk_tokens = 0
                
                # 按字符数强制分割大段落
                chars_per_chunk = int(chunk_size_tokens * 3)  # 粗略估计
                for i in range(0, len(para), chars_per_chunk):
                    chunk_text = para[i:i+chars_per_chunk]
                    chunks.append(chunk_text)
            else:
                if current_chunk_tokens + para_tokens > chunk_size_tokens and current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = [para]
                    current_chunk_tokens = para_tokens
                else:
                    current_chunk.append(para)
                    current_chunk_tokens += para_tokens
        
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        safe_print(f"         分成 {len(chunks)} 段进行字段压缩")
        
        # 构建上下文信息
        context_info = ""
        if task_input:
            context_info += f"\n<任务需求>\n{task_input}\n</任务需求>\n"
        if thinking:
            context_info += f"\n<当前进度与计划>\n{thinking}\n</当前进度与计划>\n"
        if field_context:
            context_info += f"\n<字段来源>\n这是最新动作中 {field_context} 的内容\n</字段来源>\n"
        
        # 压缩每个chunk
        chunk_results = []
        target_per_chunk = target_tokens // len(chunks)
        
        for i, chunk in enumerate(chunks):
            safe_print(f"         压缩字段第 {i+1}/{len(chunks)} 段...")
            
            prompt = f"""你是智能内容压缩助手。这是分段压缩的第 {i+1}/{len(chunks)} 段{content_type}。

{context_info}

<本段内容>
{chunk}
</本段内容>

压缩要求：
1. **目标长度**: 严格控制在 {target_per_chunk} tokens 以内
2. **智能筛选**: {focus}
3. **优先保留**: 关键信息、重要数据、文件路径
4. **格式要求**: 保持连贯性，使用总结而非截断

请直接输出本段的压缩结果："""
            
            history = [ChatMessage(role="user", content=prompt)]
            
            try:
                compressor_model = self._resolve_compressor_model()
                response = self.llm_client.chat(
                    history=history,
                    model=compressor_model,
                    system_prompt=f"压缩专家。目标：将本段压缩到{target_per_chunk} tokens。",
                    tool_list=[],  # 空列表表示不使用工具
                    tool_choice=self._resolve_compressor_tool_choice(compressor_model),
                    max_tokens=self.max_tokens,
                    debug_task_id=self.debug_task_id,
                    debug_label="action_compressor",
                )
                
                if response.status == "success":
                    chunk_results.append(response.output)
                    safe_print(f"            ✅ 第{i+1}段压缩成功")
                else:
                    chunk_results.append(chunk[:500] + "\n[本段压缩失败]")
                    safe_print(f"            ⚠️ 第{i+1}段压缩失败")
            except Exception as e:
                chunk_results.append(chunk[:500] + "\n[本段压缩异常]")
                safe_print(f"            ❌ 第{i+1}段压缩异常: {e}")
        
        # 合并结果
        final_result = '\n\n---\n\n'.join(chunk_results)
        
        safe_print(f"         ✅ 字段分段压缩完成，共{len(chunks)}段")
        
        return final_result
    
    def _fallback_compress(self, text: str, max_tokens: int) -> str:
        """
        备用压缩方案（首尾保留法）- 当LLM压缩失败时使用
        """
        if self.encoding:
            tokens = self.encoding.encode(text)
            head_count = int(max_tokens * 0.1)
            tail_count = int(max_tokens * 0.1)
            head_tokens = tokens[:head_count]
            tail_tokens = tokens[-tail_count:]
            head_text = self.encoding.decode(head_tokens)
            tail_text = self.encoding.decode(tail_tokens)
            omitted = len(tokens) - head_count - tail_count
            return f"{head_text}\n\n[中间省略约{omitted}个tokens]\n\n{tail_text}"
        else:
            # 简单字符截取
            chars = int(max_tokens * 2)
            head = chars // 2
            tail = chars // 2
            return f"{text[:head]}\n\n[中间省略]\n\n{text[-tail:]}"


if __name__ == "__main__":
    safe_print("✅ ActionCompressor模块加载成功")
    safe_print("\n压缩策略：")
    safe_print("1. 历史actions → LLM总结为5k tokens")
    safe_print("2. 最新action → 保留结构，LLM智能压缩大字段到50% max_window")
    safe_print("3. 备用方案 → 首尾保留法（当LLM失败时）")
