import sys
import os
import json
import importlib
import hashlib
from typing import List, Dict, Any, Optional, Union

# 将项目根目录添加到Python路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.llm_client import LLMClient, ChatMessage, ModelType, normalize_model_name
from baseService.logger_service import AgentLogger
try:
    from Services.thinking_service import analyze_task_progress
    HAS_THINKING_SERVICE = True
except ImportError as e:
    # 备用导入
    from baseService.thinking_agent import analyze_task_progress
    HAS_THINKING_SERVICE = False
    print(f"警告：无法导入思考服务，使用备用导入: {e}")
from baseService.config_merger import ensure_merged_config
try:
    from Services.agent_coordination_service import get_cached_hierarchy_manager
    HAS_COORDINATION_SERVICE = True
    print("✅ 使用新的Agent协同服务")
except ImportError as e:
    # 备用导入
    from baseService.agent_hierarchy import get_cached_hierarchy_manager
    HAS_COORDINATION_SERVICE = False
    print(f"⚠️ 无法导入Agent协同服务，使用备用导入: {e}")

# 导入新的服务
try:
    from Services.context_length_control_service import ContextLengthController
    HAS_CONTEXT_SERVICE = True
except ImportError as e:
    HAS_CONTEXT_SERVICE = False
    print(f"警告：无法导入上下文长度控制服务: {e}")
    ContextLengthController = None

try:
    from Services.conversation_service import ConversationManager, ConversationState, ToolCallEntry
    HAS_CONVERSATION_SERVICE = True
except ImportError as e:
    HAS_CONVERSATION_SERVICE = False
    print(f"警告：无法导入对话服务: {e}")
    ConversationManager = None
    ConversationState = None
    ToolCallEntry = None

try:
    from Services.shared_context_construction_service import SharedContextConstructor
    HAS_SHARED_CONTEXT_SERVICE = True
except ImportError as e:
    HAS_SHARED_CONTEXT_SERVICE = False
    print(f"警告：无法导入共享上下文构造服务: {e}")
    SharedContextConstructor = None


class Agent:
    """
    通用的Agent类，可以执行各种任务。
    """
    def __init__(
        self,
        agent_name: str,
        system_prompt: str,
        available_tools: List[str],
        max_turns: int = 100,
        model_type: Union[str, ModelType] = "claude-3-7-sonnet-20250219",
        max_history_turns: int = 100,  # 最大保留的对话轮数
        max_history_tokens: int = 120000,  # 最大保留的对话tokens数
        # 重试机制配置
        max_retries: int = 5,  # 最大重试次数
        retry_delay: float = 10.0,  # 重试延迟时间（秒）
        retry_backoff: float = 1.5,  # 重试退避倍数
        allow_model_fallback: bool = True,  # 是否允许模型自动回退
        agent_system_name: str = None,  # Agent系统名称
        thinking_interval: int = 10,  # thinking触发间隔（每N轮工具调用后）
        **kwargs
    ):
        """
        初始化Agent。

        Args:
            agent_name (str): Agent的名称，用于日志记录。
            system_prompt (str): 系统提示词，定义Agent的角色和行为。
            available_tools (List[str]): 可用的工具列表。
            max_turns (int, optional): 防止无限循环的最大执行轮次。
            model_type: 使用的LLM模型类型，支持字符串或ModelType枚举。
            max_history_turns (int, optional): 最大保留的对话轮数。
            max_history_tokens (int, optional): 最大保留的对话tokens数。
            max_retries (int, optional): LLM调用失败时的最大重试次数。
            retry_delay (float, optional): 重试间隔时间（秒）。
            retry_backoff (float, optional): 重试延迟的退避倍数。
            allow_model_fallback (bool, optional): 是否允许模型自动回退。
        """
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.available_tools = available_tools
        self.max_turns = max_turns
        self.model_type = normalize_model_name(model_type)  # 规范化为字符串
        self.max_history_turns = max_history_turns
        self.max_history_tokens = max_history_tokens
        self.allow_model_fallback = allow_model_fallback
        
        # 重试机制配置
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff
        
        # Agent系统名称（用于多Agent系统支持）
        self.agent_system_name = agent_system_name
        
        # Thinking触发间隔
        self.thinking_interval = thinking_interval
        
        # 确保配置文件是最新的合并版本
        ensure_merged_config(self.agent_system_name)
        
        # 初始化LLM客户端
        from baseService.config_merger import get_agent_config_path
        tools_config_path = get_agent_config_path(self.agent_system_name)
        llm_config_path = os.path.join(project_root, 'config', 'run_env_config', 'llm_config.yaml')
        
        # 智能选择是否使用custom APIs：如果有custom配置就使用，否则使用官方API
        self.client = LLMClient(
            config_file=llm_config_path, 
            tools_config_file=tools_config_path, 
            use_custom_apis=self._should_use_custom_apis(llm_config_path),
            agent_system_name=self.agent_system_name
        )
        
        # 初始化上下文长度控制服务
        if HAS_CONTEXT_SERVICE:
            self.context_controller = ContextLengthController()
        else:
            self.context_controller = None
            print("⚠️ 上下文长度控制服务不可用，将使用内置方法")
        
        # 初始化对话管理服务
        if HAS_CONVERSATION_SERVICE:
            conversation_dir = os.path.join(project_root, 'conversations')
            self.conversation_manager = ConversationManager(conversation_dir)
        else:
            self.conversation_manager = None
            print("⚠️ 对话服务不可用，将使用内置方法")
            # 保留原有的对话目录管理（备用）
            self.conversation_dir = os.path.join(project_root, 'conversations')
            # 确保对话目录存在（备用）
            if not os.path.exists(self.conversation_dir):
                os.makedirs(self.conversation_dir)
        
        # 初始化共享上下文构造服务
        if HAS_SHARED_CONTEXT_SERVICE:
            conversation_dir = os.path.join(project_root, 'conversations')
            self.shared_context_constructor = SharedContextConstructor(conversation_dir)
        else:
            self.shared_context_constructor = None
            print("⚠️ 共享上下文构造服务不可用，将使用层级管理器的方法")
        
        # 日志记录器将在run方法中初始化（需要task_id）
        self.agent_logger = None
        
        # 工具调用计数器，用于thinking agent触发
        self.tool_call_counter = 0
        
        # 首次thinking标记
        self.first_thinking_done = False
        
        # 工具调用状态跟踪列表
        self.tool_calls_log = []
        
        # Token使用统计
        self.token_usage = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "llm_calls": 0,
            "tool_calls": 0
        }
        
        # Agent层级管理相关
        self.hierarchy_manager = None  # 将在run方法中初始化
        self.agent_id = None  # 当前Agent的唯一ID
        self.task_id = None  # 当前任务ID
    
    def _should_use_custom_apis(self, llm_config_path: str) -> bool:
        """
        智能判断是否应该使用custom APIs
        
        Args:
            llm_config_path (str): LLM配置文件路径
            
        Returns:
            bool: 是否使用custom APIs
        """
        try:
            import yaml
            with open(llm_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 检查是否有任何provider配置了有效的custom API
            providers = ["openai", "claude", "gemini"]
            
            for provider in providers:
                provider_config = config.get(provider, {})
                custom_config = provider_config.get("custom", {})
                
                # 如果有API密钥和base_url，认为配置了custom API
                if custom_config.get("api_key") and custom_config.get("base_url"):
                    return True
            
            # 没有找到任何custom API配置，使用官方API
            return False
            
        except Exception as e:
            print(f"⚠️ 读取LLM配置文件失败，使用官方API: {e}")
            return False
    
    
    def _get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    
    def _add_continue_message_if_needed(self, history: List[ChatMessage]):
        """
        如果需要，向对话历史添加'继续'消息。
        避免重复添加。
        
        Args:
            history (List[ChatMessage]): 对话历史
        """
        # 检查最后一条消息是否已经是"继续"
        if history[-1].content.startswith("Continue"):
            pass
        else:
            history.append(ChatMessage(role="user", content="Continue"))
    
    def _get_tools_descriptions(self) -> Dict[str, str]:
        """
        获取工具描述字典（无参数信息）
        
        Returns:
            Dict[str, str]: 工具名称到描述的映射
        """
        tools_descriptions = {}
        
        try:
            # 获取工具管理器
            if hasattr(self.client, 'tool_manager'):
                tool_manager = self.client.tool_manager
                
                for tool_name in self.available_tools:
                    # 获取工具定义
                    tool_config = tool_manager.tools_config.get("tools", {}).get(tool_name)
                    if tool_config:
                        # 只保留描述，不包含参数信息
                        description = tool_config.get("description", "无描述")
                        tools_descriptions[tool_name] = description
                    else:
                        tools_descriptions[tool_name] = "无描述"
            else:
                # 如果没有工具管理器，使用简单描述
                for tool_name in self.available_tools:
                    tools_descriptions[tool_name] = f"{tool_name}工具"
                    
        except Exception as e:
            print(f"⚠️ 获取工具描述失败: {e}")
            # 备用方案
            for tool_name in self.available_tools:
                tools_descriptions[tool_name] = f"{tool_name}工具"
        
        return tools_descriptions
    
    def _trigger_thinking_agent(self, task_description: str, history: List[ChatMessage], is_first_thinking: bool = False) -> Optional[str]:
        """
        触发thinking agent进行任务进展分析
        
        Args:
            task_description (str): 任务描述
            history (List[ChatMessage]): 当前对话历史
            
        Returns:
            Optional[str]: 分析结果，如果失败则返回None
        """
        try:
            print(f"[{self.agent_name}] 触发ThinkingAgent进行任务进展分析...")
            
            # 准备分析用的对话历史
            analysis_history = history.copy()
            
            # 检查最后一条消息是否是user角色，如果是则添加空的assistant消息
            if analysis_history and analysis_history[-1].role == "user":
                analysis_history.append(ChatMessage(role="assistant", content="Let me analyze the current progress of the task."))
            
            # 获取工具描述
            tools_descriptions = self._get_tools_descriptions()
            
            # 调用thinking agent进行分析
            analysis_result = analyze_task_progress(
                task_description=task_description,
                conversation_history=analysis_history,
                agent_system_prompt=self.system_prompt,
                agent_name=self.agent_name,
                is_first_thinking=is_first_thinking,
                available_tools=self.available_tools,
                tools_descriptions=tools_descriptions,
                model_type=self.model_type  # 现在是字符串
            )
            
            return analysis_result
            
        except Exception as e:
            error_msg = f"ThinkingAgent分析失败: {str(e)}"
            print(f"[{self.agent_name}] {error_msg}")
            if self.agent_logger:
                self.agent_logger.error("thinking_agent_error", error_msg)
            return None
    
    def _accumulate_token_usage(self, usage: Dict):
        """累计token使用统计"""
        if not usage:
            return
            
        self.token_usage["llm_calls"] += 1
        self.token_usage["total_prompt_tokens"] += usage.get("prompt_tokens", 0)
        self.token_usage["total_completion_tokens"] += usage.get("completion_tokens", 0)
        self.token_usage["total_tokens"] += usage.get("total_tokens", 0)
        
        # 记录详细信息
        if self.agent_logger:
            self.agent_logger.info(f"Token使用 - 本次: {usage.get('total_tokens', 0)}, 累计: {self.token_usage['total_tokens']}")
    
    def _accumulate_tool_token_usage(self, tool_result: Dict):
        """累计工具调用返回的token使用统计（仅针对使用LLM的工具，如其他Agent）"""
        if not isinstance(tool_result, dict):
            return
            
        # 检查工具调用结果是否包含token_usage信息
        # 只有调用LLM的工具（如agent_class实例）才会返回这个信息
        tool_token_usage = tool_result.get("token_usage")
        
        if tool_token_usage and isinstance(tool_token_usage, dict):
            # 验证token_usage数据的有效性
            if any(key in tool_token_usage for key in ["total_tokens", "total_prompt_tokens", "total_completion_tokens"]):
                self.token_usage["tool_calls"] += 1
                self.token_usage["total_prompt_tokens"] += tool_token_usage.get("total_prompt_tokens", 0)
                self.token_usage["total_completion_tokens"] += tool_token_usage.get("total_completion_tokens", 0)
                self.token_usage["total_tokens"] += tool_token_usage.get("total_tokens", 0)
                self.token_usage["llm_calls"] += tool_token_usage.get("llm_calls", 0)
                
                # 避免重复计算tool_calls
                sub_tool_calls = tool_token_usage.get("tool_calls", 0)
                if sub_tool_calls > 0:
                    self.token_usage["tool_calls"] += sub_tool_calls
                
                if self.agent_logger:
                    self.agent_logger.info(f"累计工具token - 工具返回: {tool_token_usage.get('total_tokens', 0)}, 新累计: {self.token_usage['total_tokens']}")
            else:
                # token_usage字段存在但数据无效
                if self.agent_logger:
                    self.agent_logger.warning(f"工具返回的token_usage数据无效: {tool_token_usage}")
        # 如果没有token_usage字段，说明这是普通工具（file_read, execute_shell等），不需要累计token
        
       
    
    
    def list_conversation_files(self) -> List[str]:
        """
        列出所有保存的对话文件。
        
        Returns:
            List[str]: 对话文件列表
        """
        if self.conversation_manager:
            return self.conversation_manager.list_conversation_files()
        else:
            # 使用原有方法（备用）
            try:
                if not os.path.exists(self.conversation_dir):
                    return []
                
                files = [f for f in os.listdir(self.conversation_dir) if f.endswith('.json')]
                return sorted(files)
            except Exception as e:
                print(f"⚠️ 列出对话文件失败: {e}")
                return []

    def run(self, task_id: str, user_input: str) -> Dict:
        """
        执行任务。

        Args:
            task_id (str): 任务的唯一ID，所有工具调用都将使用此ID。
            user_input (str): 用户输入的任务指令。

        Returns:
            Dict: 执行完成后的最终结果，包含 'status', 'output', 'error_information'。
        """
        # 保存task_id
        self.task_id = task_id
        
        # 初始化层级管理器
        self.hierarchy_manager = get_cached_hierarchy_manager(task_id)
        
        # 如果是第一个Agent（栈为空），注册新指令
        if not self.hierarchy_manager.get_current_agent_id():
            self.hierarchy_manager.start_new_instruction(user_input)
        
        # Agent入栈操作（在入栈前会自动检查栈顶确定父Agent）
        self.agent_id = self.hierarchy_manager.push_agent(self.agent_name, user_input)
        
        # 初始化日志记录器
        self.agent_logger = AgentLogger(self.agent_name, task_id)
        
        # 记录任务开始信息
        additional_info = {
            "max_turns": self.max_turns,
            "available_tools": self.available_tools,
            "model_type": self.model_type,
            "agent_id": self.agent_id  # 添加agent_id到日志信息
        }
        self.agent_logger.start(user_input, additional_info)
        
        print(f"🤖 启动 {self.agent_name}，处理任务: {task_id} 🤖")
        self.agent_logger.info(f"可用工具列表: {self.available_tools}")
        
        # 尝试加载现有的对话历史
        loaded_conversation_state = None  # 初始化变量
        if self.conversation_manager:
            # 使用新的对话服务
            loaded_conversation_state = self.conversation_manager.load_conversation(
                task_id, user_input, self.agent_name, self.agent_logger.info if self.agent_logger else None
            )
            
            if loaded_conversation_state == "AGENT_NAME_MISMATCH":
                loaded_data = "AGENT_NAME_MISMATCH"
            elif loaded_conversation_state:
                # 恢复工具调用日志
                self.tool_calls_log = [
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
                    for tool in loaded_conversation_state.tool_calls_log
                ]
                loaded_data = (loaded_conversation_state.history, loaded_conversation_state.current_turn)
            else:
                loaded_data = None
        else:
            # 对话服务不可用，无法加载历史对话
            loaded_data = None
            print("⚠️ 对话服务不可用，无法加载历史对话")
        if loaded_data == "AGENT_NAME_MISMATCH":
            # Agent名称不匹配，立即返回错误并出栈
            error_result = {
                "status": "error",
                "output": f"任务内容与之前冲突，导致hash命名错误。当前Agent: {self.agent_name}，请略微修改任务内容，确保hash问题消除。",
                "error_information": "Agent名称hash冲突",
                "token_usage": self.token_usage
            }
            
            # 模拟final_output的出栈行为
            self.hierarchy_manager.pop_agent(self.agent_id, error_result["output"])
            
            # 记录结束信息
            if self.agent_logger:
                self.agent_logger.end(error_result)
            
            return error_result
            
        elif loaded_data:
            history, start_turn = loaded_data
            print(f"📂 找到现有对话记录，从第 {start_turn + 1} 轮继续执行")
            
            # 处理pending状态的工具调用
            if self.conversation_manager and loaded_conversation_state:
                # 使用对话服务处理pending工具调用
                history = self.conversation_manager.process_pending_tool_calls(
                    loaded_conversation_state, 
                    self._execute_tool, 
                    task_id, 
                    self.agent_logger.info if self.agent_logger else None
                )
                # 同步工具调用日志
                self.tool_calls_log = [
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
                    for tool in loaded_conversation_state.tool_calls_log
                ]
            else:
                # 对话服务不可用，跳过pending工具调用处理
                print("⚠️ 对话服务不可用，跳过pending工具调用处理")
            
            # 检查任务是否已经完成 - 基于工具调用日志中的final_output状态
            if self.conversation_manager and loaded_conversation_state:
                final_output_completed = self.conversation_manager.check_final_output_completed(loaded_conversation_state)
            else:
                # 对话服务不可用，无法检查final_output状态
                final_output_completed = False
            
            if final_output_completed:
                # 任务已完成，从工具调用日志中获取最终结果
                if self.conversation_manager and loaded_conversation_state:
                    final_result = self.conversation_manager.get_final_output_result(loaded_conversation_state, self.token_usage)
                else:
                    final_result = None
                if final_result:
                    print(f"✅ 发现任务已完成，状态: {final_result.get('status', 'unknown').upper()}")
                    print(f"直接返回之前的final_output结果，无需重新执行")
                    self.agent_logger.info(f"任务已完成，直接返回final_output结果: {final_result.get('status')}")
                    return final_result
            
            # 任务未完成，检查对话状态
            if history and history[-1].role == "assistant":
                last_response = history[-1].content
                # 尝试解析最后一条assistant消息，看是否是工具调用状态
                try:
                    result = json.loads(last_response.strip('```json').strip('```'))
                    
                    # 检查是否是工具调用格式的消息（包含text和tool_calls）
                    if "text" in result and "tool_calls" in result:
                        # 这是工具调用消息，需要继续执行
                        print(f"🔄 发现对话中断于工具调用状态，添加'继续'消息并继续执行")
                        self.agent_logger.info(f"对话中断于工具调用状态，添加继续消息")
                        self._add_continue_message_if_needed(history)
                    else:
                        # 其他格式，可能是thinking状态或中间状态
                        print(f"🔄 发现对话中断于中间状态，添加'继续'消息并继续执行")
                        self.agent_logger.info(f"对话中断于中间状态，添加继续消息")
                        self._add_continue_message_if_needed(history)
                        
                except json.JSONDecodeError:
                    # 不是JSON格式，可能是思考过程或中间状态，添加继续消息
                    print(f"🔄 发现对话中断于中间状态，添加'继续'消息并继续执行")
                    self.agent_logger.info(f"对话中断于中间状态，添加继续消息")
                    self._add_continue_message_if_needed(history)
            elif history and history[-1].role == "user" and "继续" in history[-1].content:
                print(f"🔄 发现对话已添加继续消息，直接继续执行")
                self.agent_logger.info(f"对话已包含继续消息，直接继续执行")
        else:
            # 构建新的对话历史
            history = [ChatMessage(role="user", content=user_input)]
            start_turn = 0
            print(f"🆕 开始新的对话")
        
        self._add_continue_message_if_needed(history)
        
        # 如果是新对话且未进行过首次thinking，先进行初始规划
        if start_turn == 0 and not self.first_thinking_done:
            print(f"[{self.agent_name}] 开始行动前进行初始规划...")
            first_thinking = self._trigger_thinking_agent(user_input, history, is_first_thinking=True)
            if first_thinking:
                history.append(ChatMessage(role="assistant", content=first_thinking))
                self.first_thinking_done = True
                print(f"[{self.agent_name}] 初始规划完成，添加到对话历史")
                if self.agent_logger:
                    self.agent_logger.info("初始规划thinking已添加")
                
                # 更新Agent进度信息
                if self.hierarchy_manager and self.agent_id:
                    self.hierarchy_manager.update_agent_progress(self.agent_id, first_thinking, "thinking")
        
        max_tool_try=0
        # 执行循环
        for i in range(start_turn, self.max_turns):
            self.agent_logger.turn_start(i + 1, self.max_turns)
            print(f"\n--- {self.agent_name} 第 {i+1}/{self.max_turns} 轮执行 ---")
            
            # 每轮都保存对话历史
            self._save_conversation_with_service(task_id, user_input, history, i)
     
            # 在调用LLM之前智能截断对话历史
            truncated_history, messages_modified = self._truncate_history(history, user_input, current_turn=i)
            
            # 如果有消息被总结修改，保存修改后的原始历史
            if messages_modified:
                print("💾 检测到消息被总结修改，保存更新后的原始历史")
                self._save_conversation_with_service(task_id, user_input, history, i)
            
            # 记录 LLM 请求
            self.agent_logger.llm_request(
                model=self.model_type,  # 现在是字符串
                system_prompt=self.system_prompt,
                user_input=user_input if i == 0 else "继续执行",
                available_tools=self.available_tools
            )

            # 使用带重试机制的LLM调用
            try:
                llm_response = self._call_llm_with_retry(
                    history=truncated_history,  # 使用截断后的历史
                    system_prompt=self.system_prompt,
                    tool_list=self.available_tools,
                    tool_choice="required"
                )
            except Exception as e:
                # 重试失败，记录错误并返回错误结果
                error_msg = f"LLM调用失败（重试{self.max_retries}次后）: {str(e)}"
                self.agent_logger.error("llm_call_failed", error_msg)
                
                thinking_analysis = self._trigger_thinking_agent(user_input, history, is_first_thinking=False)
                
                # 更新Agent进度信息
                if thinking_analysis and self.hierarchy_manager and self.agent_id:
                    self.hierarchy_manager.update_agent_progress(self.agent_id, thinking_analysis, "thinking")
                
                error_result = {
                    "status": "error", 
                    "output": thinking_analysis if thinking_analysis else "LLM调用失败", 
                    "error_information": error_msg,
                    "token_usage": self.token_usage.copy()
                }
                # 保存出错时的对话历史
                self._save_conversation_with_service(task_id, user_input, history, i)
                self.agent_logger.end(error_result, "llm_call_failed")
                return error_result
            
            # 记录 LLM 响应
            response_data = {
                "status": llm_response.status,
                "model": llm_response.model,
                "finish_reason": llm_response.finish_reason,
                "output": llm_response.output,
                "error_information": llm_response.error_information,
                "tool_calls": llm_response.tool_calls
            }
            self.agent_logger.llm_response(response_data)
            print(llm_response.output,'llm_response.output')
            print(llm_response.tool_calls,'llm_response.tool_calls')
            
            # 累计token使用统计
            self._accumulate_token_usage(llm_response.usage)



            try:
                tool_calls = llm_response.tool_calls
            except:
                tool_calls = False
            
            
                
            # 情况一：LLM进行了工具调用
            if tool_calls:
                max_tool_try=0
                print(f"[{self.agent_name}] 正在调用工具: {[call.name for call in tool_calls]}")
                for tool_single in tool_calls:
                    print(tool_single,'命令详情')
                
                # 先记录所有工具调用为pending状态
                tool_call_ids = []
                for tool_call in tool_calls:
                    if self.conversation_manager:
                        # 创建临时对话状态用于工具调用管理
                        temp_state = self._create_conversation_state(task_id, user_input, history, i)
                        temp_state.tool_calls_log = [
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
                            for tool in self.tool_calls_log
                        ]
                        
                        tool_call_id = self.conversation_manager.add_tool_call_to_log(
                            temp_state, tool_call.name, tool_call.arguments, i, 
                            self.agent_logger.info if self.agent_logger else None
                        )
                        
                        # 同步回agent的工具调用日志
                        self.tool_calls_log = [
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
                            for tool in temp_state.tool_calls_log
                        ]
                    else:
                        # 对话服务不可用，抛出错误
                        raise RuntimeError("对话服务未初始化，无法记录工具调用")
                    
                    tool_call_ids.append(tool_call_id)
                
                # 保存包含pending工具调用的状态
                self._save_conversation_with_service(task_id, user_input, history, i)
                
                # 执行工具调用
                for j, tool_call in enumerate(tool_calls):
                    tool_call_id = tool_call_ids[j]
                    tool_result = self._execute_tool(tool_call, task_id)
                    
                    # 更新工具状态为completed
                    if self.conversation_manager:
                        # 使用对话服务更新工具状态
                        temp_state = self._create_conversation_state(task_id, user_input, history, i)
                        temp_state.tool_calls_log = [
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
                            for tool in self.tool_calls_log
                        ]
                        
                        self.conversation_manager.update_tool_call_status(
                            temp_state, tool_call_id, "completed", tool_result,
                            self.agent_logger.info if self.agent_logger else None
                        )
                        
                        # 同步回agent的工具调用日志
                        self.tool_calls_log = [
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
                            for tool in temp_state.tool_calls_log
                        ]
                    else:
                        raise RuntimeError("对话服务未初始化，无法更新工具状态")
                    
                    # 增加工具调用计数
                    self.tool_call_counter += 1
                    
                    # 如果是 final_output 工具，直接返回结果
                    if tool_call.name == "final_output":
                        print(f"[{self.agent_name}] 检测到 final_output 工具调用，直接返回最终结果")
                        self.agent_logger.decision(tool_result["status"], tool_result["output"])
                        
                        # Agent出栈操作
                        if self.hierarchy_manager and self.agent_id:
                            final_output_content = tool_result.get("output", "任务已完成")
                            self.hierarchy_manager.pop_agent(self.agent_id, final_output_content)
                        
                        # 添加token统计到最终结果
                        tool_result["token_usage"] = self.token_usage.copy()
                        self.agent_logger.end(tool_result, "final_output_called")

                        # 正确的对话流程：assistant包含LLM回复和工具调用信息
                        tool_call_info = tool_call.__dict__.copy()
                        content_with_tool_calls = {
                            "text": llm_response.output,
                            "tool_calls": [tool_call_info]
                        }
                        
                        history.append(ChatMessage(
                            role="assistant", 
                            content=json.dumps(content_with_tool_calls, ensure_ascii=False),
                        ))

                        self._save_conversation_with_service(task_id, user_input, history, i)

                        return tool_result
                
                # 处理非final_output工具调用
                # 智能处理工具调用信息，清理参数中的markdown标记
                all_tool_calls_info = []
                for tool_call in tool_calls:
                    tool_call_info = tool_call.__dict__.copy()
                    if 'arguments' in tool_call_info and isinstance(tool_call_info['arguments'], dict):
                        processed_args = {}
                        for key, value in tool_call_info['arguments'].items():
                            if isinstance(value, str):
                                processed_args[key] = value.replace('```json', '').replace('```', '')
                            else:
                                processed_args[key] = value
                        tool_call_info['arguments'] = processed_args
                    all_tool_calls_info.append(tool_call_info)
                
                # 正确的对话流程：assistant消息包含LLM回复和工具调用信息
                content_with_tool_calls = {
                    "text": llm_response.output,
                    "tool_calls": all_tool_calls_info
                }
                
                history.append(ChatMessage(
                    role="assistant", 
                    content=json.dumps(content_with_tool_calls, ensure_ascii=False),
                ))
                
                # 收集所有工具执行结果
                all_tool_results = []
                for j, tool_call in enumerate(tool_calls):
                    tool_call_id = tool_call_ids[j]
                    # 从工具调用日志中获取结果
                    for tool_entry in self.tool_calls_log:
                        if tool_entry["id"] == tool_call_id:
                            tool_result = tool_entry.get("result", {})
                            all_tool_results.append({
                                "tool_name": tool_call.name,
                                "tool_id": tool_call_id,
                                "result": tool_result
                            })
                            break
                
                # user消息只包含工具执行结果
                try:
                    tool_results_str = json.dumps({"tool_results": all_tool_results}, ensure_ascii=False)
                except:
                    tool_results_str = str(all_tool_results)
                
                history.append(ChatMessage(
                    role="user", 
                    content=f'工具执行完成，结果：{tool_results_str}'
                ))
                
                # 检查是否需要触发thinking agent（按配置的间隔）
                if self.tool_call_counter % self.thinking_interval == 0:
                    thinking_analysis = self._trigger_thinking_agent(user_input, history, is_first_thinking=False)
                    if thinking_analysis:
                        # 添加thinking agent的分析结果到对话历史
                        history.append(ChatMessage(
                            role="assistant",
                            content=thinking_analysis
                        ))
                        print(f"[{self.agent_name}] 第{self.tool_call_counter}轮工具调用后，ThinkingAgent分析已添加")
                        self.agent_logger.info(f"ThinkingAgent分析已添加到第{i+1}轮对话")
                        
                        # 更新Agent进度信息
                        if self.hierarchy_manager and self.agent_id:
                            self.hierarchy_manager.update_agent_progress(self.agent_id, thinking_analysis, "thinking")
                
                # 保存更新后的对话历史
                self._save_conversation_with_service(task_id, user_input, history, i)
                continue
            else:
                if max_tool_try<5:
                    max_tool_try+=1
                    history.append(ChatMessage(
                    role="user", 
                    content=f'没有使用工具，请使用工具尝试解决问题'
                ))
                    self._save_conversation_with_service(task_id, user_input, history, i)  
                    continue
                thinking_analysis = self._trigger_thinking_agent(user_input, history, is_first_thinking=False)
                
                # 更新Agent进度信息
                if thinking_analysis and self.hierarchy_manager and self.agent_id:
                    self.hierarchy_manager.update_agent_progress(self.agent_id, thinking_analysis, "thinking")
                
                error_msg = f"{self.agent_name} 没有返回任何有效响应。ai没有使用工具"
                self.agent_logger.error("no_response", error_msg)
                error_result = {"status": "error", "output": thinking_analysis, "error_information": error_msg}
                # 保存出错时的对话历史
                history.append(ChatMessage(
                            role="assistant",
                            content=thinking_analysis
                        ))
                self._save_conversation_with_service(task_id, user_input, history, i)
                self.agent_logger.end(error_result, "no_response")
                continue
                return error_result

        # 超过最大轮次
        error_msg = f"{self.agent_name} 执行超过最大轮次限制。"
        self.agent_logger.warning(f"执行达到最大轮次限制: {self.max_turns}")
        thinking_analysis = self._trigger_thinking_agent(user_input, history)
        
        # 更新Agent进度信息
        if thinking_analysis and self.hierarchy_manager and self.agent_id:
            self.hierarchy_manager.update_agent_progress(self.agent_id, thinking_analysis, "thinking")
        
        error_result = {
            "status": "error", 
            "output": thinking_analysis, 
            "error_information": error_msg,
            "token_usage": self.token_usage.copy()
        }
        # 保存超时时的对话历史
        self._save_conversation_with_service(task_id, user_input, history, self.max_turns - 1)
        self.agent_logger.end(error_result, "max_turns_exceeded")
        return error_result

    def _execute_tool(self, tool_call, task_id: str) -> Dict:
        """
        执行单个工具调用。
        
        Args:
            tool_call: 工具调用对象
            task_id (str): 任务ID
            
        Returns:
            Dict: 工具执行结果
        """
        try:
            # 特殊处理 final_output 工具
            if tool_call.name == "final_output":
                # 直接返回工具参数作为最终结果
                result = {
                    "status": tool_call.arguments.get("status", "success"),
                    "output": tool_call.arguments.get("output", ""),
                    "error_information": tool_call.arguments.get("error_information", "")
                }
                print(f"[{self.agent_name}] 调用 final_output 工具，直接返回结果: {result['status']}")
                self.agent_logger.tool_execution(tool_call.name, tool_call.arguments, result)

                return result

            print(tool_call.name,'tool_call')
            
            from baseService.base_agent import run as tool_run
            tool_result, tool_level = tool_run(task_id=task_id, tool_name=tool_call.name, arguments=tool_call.arguments)
            print(f"[{self.agent_name}] 工具 '{tool_call.name}' (level {tool_level}) 执行结果: {tool_result['status']}")
            
            # 记录工具执行
            self.agent_logger.tool_execution(tool_call.name, tool_call.arguments, tool_result)
            
            # 累计工具调用的token使用（如果工具是agent_class）
            self._accumulate_tool_token_usage(tool_result)
            
            return tool_result

        except Exception as e:
            error_msg = str(e)
            print(f"[{self.agent_name}] 执行工具 '{tool_call.name}' 时发生本地错误: {e}")
            
            # 记录工具错误
            self.agent_logger.tool_error(tool_call.name, error_msg)
            
            return {"status": "error", "output": "", "error_information": error_msg}

    def _process_llm_output(self, output: str) -> Optional[Dict]:
        """
        处理LLM的文本输出。
        
        Args:
            output (str): LLM的输出文本
            
        Returns:
            Optional[Dict]: 如果是最终结果则返回结果字典，否则返回None
        """
        try:
            # 尝试解析为JSON
            result = json.loads(output.strip('```json').strip('```'))
            status = result.get("status")
            
            if status in ["success", "error"]:
                print(f"[{self.agent_name}] 完成执行，状态: {status.upper()}")
                
                # 记录最终决策
                self.agent_logger.decision(status, result.get("output", ""))
                self.agent_logger.end(result, "task_completed")
                
                return result
            
                
            return None

        except json.JSONDecodeError:
            # 不是JSON格式，作为普通文本响应处理
            print(f"[{self.agent_name}] 响应: {output}")
            return None

    
    def _truncate_history(self, history: List[ChatMessage], initial_user_input: str, current_turn: int = 0) -> tuple[List[ChatMessage], bool]:
        """
        智能截断对话历史，保留系统提示词+用户初始指令+最近N轮或M tokens的对话。
        
        Args:
            history (List[ChatMessage]): 完整的对话历史
            initial_user_input (str): 用户的初始输入
            current_turn (int): 当前轮次（用于保存截断历史）
            
        Returns:
            tuple[List[ChatMessage], bool]: (截断后的对话历史, 是否有消息被总结修改)
        """
        # 第一步：在压缩前添加共享上下文信息
        history_with_context = history.copy()
        context_info = self._get_context_info()
        if context_info:
            context_message = ChatMessage(role="user", content=context_info)
            history_with_context.append(context_message)
            if self.agent_logger:
                self.agent_logger.info("已添加Agent协同系统上下文信息")
        
        # 第二步：使用上下文长度控制服务进行压缩和截断
        if self.context_controller:
            truncated_history, messages_modified = self.context_controller.truncate_history(
                history=history_with_context,
                initial_user_input=initial_user_input,
                max_history_turns=self.max_history_turns,
                max_history_tokens=self.max_history_tokens,
                model_type=self.model_type,
                llm_client=self.client,
                logger_func=self.agent_logger.info if self.agent_logger else None
            )
            
            # 第三步：agent_class自己处理保存截断后的历史
            if self.task_id and self.conversation_manager:
                conversation_state = self._create_conversation_state(self.task_id, initial_user_input, history, current_turn)
                self.conversation_manager.save_truncated_conversation(
                    conversation_state, 
                    truncated_history, 
                    self.agent_logger.info if self.agent_logger else None
                )
            
            return truncated_history, messages_modified
        
        # 如果没有服务，抛出错误（不再保留旧方法）
        raise RuntimeError("上下文长度控制服务未初始化，无法处理对话历史")
    
    def _get_context_info(self) -> Optional[str]:
        """获取Agent协同系统上下文信息"""
        if self.shared_context_constructor and self.task_id and self.agent_id:
            # 使用新的共享上下文构造服务
            return self.shared_context_constructor.get_context_for_agent(self.task_id, self.agent_id)
        elif self.hierarchy_manager and self.agent_id:
            # 备用：使用层级管理器的方法
            print("使用层级管理器的方法")
            return self.hierarchy_manager.get_context_for_agent(self.agent_id)
        return None
    
    def update_progress(self, progress: str, progress_type: str = "thinking"):
        """
        手动更新Agent进度信息
        
        Args:
            progress (str): 进度描述
            progress_type (str): 进度类型 ("thinking", "waiting", "general")
        """
        if self.hierarchy_manager and self.agent_id:
            self.hierarchy_manager.update_agent_progress(self.agent_id, progress, progress_type)
    
    def get_hierarchy_info(self) -> Optional[Dict]:
        """
        获取当前任务的层级信息
        
        Returns:
            Optional[Dict]: 层级信息，如果层级管理器未初始化则返回None
        """
        if self.hierarchy_manager:
            return self.hierarchy_manager.get_hierarchy_info()
        return None
    
    def print_hierarchy_tree(self):
        """打印当前任务的Agent调用层级树"""
        if self.hierarchy_manager:
            self.hierarchy_manager.print_hierarchy_tree()
        else:
            print("⚠️ 层级管理器未初始化")
    
    def _create_conversation_state(self, task_id: str, user_input: str, history: List[ChatMessage], current_turn: int) -> ConversationState:
        """创建对话状态对象"""
        if self.conversation_manager:
            return self.conversation_manager.create_conversation_state(
                agent_name=self.agent_name,
                agent_id=self.agent_id,
                system_prompt=self.system_prompt,
                available_tools=self.available_tools,
                model_type=self.model_type,
                task_id=task_id,
                user_input=user_input,
                current_turn=current_turn,
                history=history
            )
        return None
    
    def _save_conversation_with_service(self, task_id: str, user_input: str, history: List[ChatMessage], current_turn: int):
        """使用对话服务保存对话"""
        if self.conversation_manager:
            conversation_state = self._create_conversation_state(task_id, user_input, history, current_turn)
            # 同步工具调用日志到对话状态
            conversation_state.tool_calls_log = [
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
                for tool in self.tool_calls_log
            ]
            
            return self.conversation_manager.save_conversation(
                conversation_state, 
                self.agent_logger.info if self.agent_logger else None
            )
        else:
            # 使用原有方法（备用）
            # 备用方法已删除，抛出错误
            raise RuntimeError("对话服务未初始化，无法保存对话")
    
    def _call_llm_with_retry(self, history: List[ChatMessage], system_prompt: str, tool_list: List[str], tool_choice: str = "required"):
        """
        带重试机制的LLM调用方法
        
        Args:
            history (List[ChatMessage]): 对话历史
            system_prompt (str): 系统提示词
            tool_list (List[str]): 可用工具列表
            tool_choice (str): 工具选择策略
            
        Returns:
            LLMResponse: LLM响应对象
            
        Raises:
            Exception: 当所有重试都失败时抛出最后一次的异常
        """
        import time
        
        last_exception = None
        current_delay = self.retry_delay
        
        for attempt in range(self.max_retries + 1):  # +1 因为第一次不算重试
            try:
                if self.agent_logger:
                    if attempt == 0:
                        self.agent_logger.info(f"🤖 调用LLM: {self.model_type}")
                    else:
                        self.agent_logger.info(f"🔄 LLM调用重试 {attempt}/{self.max_retries}")
                
                # 调用LLM
                llm_response = self.client.chat(
                    history=history,
                    model=self.model_type,
                    system_prompt=system_prompt,
                    tool_list=tool_list,
                    tool_choice=tool_choice,
                    allow_model_fallback=self.allow_model_fallback
                )
                
                # 检查响应状态
                if llm_response.status == "success":
                    if attempt > 0 and self.agent_logger:
                        self.agent_logger.info(f"✅ LLM调用在第{attempt + 1}次尝试后成功")
                    return llm_response
                elif llm_response.status == "error":
                    # LLM返回了错误状态
                    error_msg = llm_response.error_information
                    
                    # 检查是否是可重试的错误
                    if self._is_retryable_error(error_msg):
                        if attempt < self.max_retries:
                            if self.agent_logger:
                                self.agent_logger.warning(f"⚠️ LLM调用失败(可重试): {error_msg}")
                                self.agent_logger.info(f"⏰ 等待 {current_delay:.1f} 秒后重试...")
                            print(f"[{self.agent_name}] LLM调用失败，{current_delay:.1f}秒后重试 ({attempt + 1}/{self.max_retries + 1}): {error_msg}")
                            
                            time.sleep(current_delay)
                            current_delay *= self.retry_backoff  # 指数退避
                            continue
                        else:
                            # 达到最大重试次数
                            if self.agent_logger:
                                self.agent_logger.error("llm_retry_exhausted", f"LLM调用重试次数耗尽: {error_msg}")
                            raise Exception(f"LLM调用失败，重试{self.max_retries}次后仍然失败: {error_msg}")
                    else:
                        # 不可重试的错误，直接返回
                        if self.agent_logger:
                            self.agent_logger.error("llm_non_retryable_error", f"LLM调用遇到不可重试错误: {error_msg}")
                        return llm_response

            except Exception as e:
                last_exception = e
                error_msg = str(e)
                
                # 检查是否是可重试的异常
                if self._is_retryable_error(error_msg):
                    if attempt < self.max_retries:
                        if self.agent_logger:
                            self.agent_logger.warning(f"⚠️ LLM调用异常(可重试): {error_msg}")
                            self.agent_logger.info(f"⏰ 等待 {current_delay:.1f} 秒后重试...")
                        print(f"[{self.agent_name}] LLM调用异常，{current_delay:.1f}秒后重试 ({attempt + 1}/{self.max_retries + 1}): {error_msg}")
                        
                        time.sleep(current_delay)
                        current_delay *= self.retry_backoff  # 指数退避
                        continue
                    else:
                        # 达到最大重试次数
                        if self.agent_logger:
                            self.agent_logger.error("llm_retry_exhausted", f"LLM调用重试次数耗尽: {error_msg}")
                        raise Exception(f"LLM调用失败，重试{self.max_retries}次后仍然失败: {error_msg}")
                else:
                    # 不可重试的异常，直接抛出
                    if self.agent_logger:
                        self.agent_logger.error("llm_non_retryable_exception", f"LLM调用遇到不可重试异常: {error_msg}")
                    raise e
        
        # 理论上不应该到达这里
        if last_exception:
            raise last_exception
        else:
            raise Exception("LLM调用失败，原因未知")
    
    def _is_retryable_error(self, error_msg: str) -> bool:
        """
        判断错误是否可重试
        
        Args:
            error_msg (str): 错误信息
            
        Returns:
            bool: 是否可重试
        """
        if not error_msg:
            return False
        
        error_msg_lower = error_msg.lower()
        
        # 可重试的错误模式
        retryable_patterns = [
            # 配额和速率限制
            "quota", "resource_exhausted", "rate limit", "too many requests",
            "429", "quota exceeded", "billing", "current quota",
            
            # 网络相关错误
            "timeout", "connection", "network", "socket", "dns",
            "502", "503", "504", "gateway", "service unavailable",
            
            # 服务器临时错误
            "internal server error", "500", "server error", "temporarily unavailable",
            "service temporarily unavailable", "overloaded",
            
            # 其他临时错误
            "try again", "retry", "temporary", "temporarily"
        ]
        
        # 检查是否包含可重试的错误模式
        for pattern in retryable_patterns:
            if pattern in error_msg_lower:
                return True
        
        return False


if __name__ == '__main__':
    # --- 使用示例：展示对话恢复功能 ---
    
    # 自定义系统提示
    custom_system_prompt = """
    你是一个AI助手，负责帮助用户完成各种任务。
    你可以使用提供的工具来执行操作。
    
    请根据用户的指令，使用合适的工具来完成任务。
    如果任务完成，请返回以下格式的JSON：
    {
        "status": "success",
        "output": "任务完成的详细说明",
        "error_information": ""
    }
    
    如果遇到错误，请返回：
    {
        "status": "error", 
        "output": "错误说明",
        "error_information": "具体错误信息"
    }
    """
    
    # 自定义工具列表
    custom_tools = [
        "file_write",
        "file_read", 
        "dir_list",
        "execute_code"
    ]
    
    # 创建Agent实例
    test_agent = Agent(
        agent_name="TestAgent",
        system_prompt=custom_system_prompt,
        available_tools=custom_tools,
        max_turns=10,
        max_history_turns=5,    # 最多保疙5轮对话
        max_history_tokens=10000  # 最多保畐10000个tokens
    )
    
    # 用户任务
    task_id = "agent_test"
    user_task = "请在当前目录创建一个名为 'hello.py' 的文件，内容是打印 'Hello, World!'，然后执行这个文件。"
    
    print("🔍 检查是否有现有的对话记录...")
    conversation_files = test_agent.list_conversation_files()
    print(f"现有对话文件: {conversation_files}")
    
    # 第一次运行Agent（可能会中断）
    print("\n🚀 首次运行Agent...")
    result = test_agent.run(
        task_id=task_id,
        user_input=user_task
    )
    
    print("\n" + "="*20 + " 第一次执行结果 " + "="*20)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 演示：再次运行相同任务（会自动恢复对话）
    print("\n" + "="*50)
    print("💫 演示对话恢复功能：再次运行相同任务...")
    print("如果之前的对话没有完成，Agent会从之前的状态继续执行")
    
    result2 = test_agent.run(
        task_id=task_id,
        user_input=user_task
    )
    
    print("\n" + "="*20 + " 第二次执行结果 " + "="*20)
    print(json.dumps(result2, indent=2, ensure_ascii=False))
    
    print("\n📋 查看最终的对话文件...")
    final_files = test_agent.list_conversation_files()
    print(f"最终对话文件: {final_files}")
    print("="*65)
