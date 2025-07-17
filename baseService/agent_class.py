import sys
import os
import json
import importlib
import hashlib
from typing import List, Dict, Any, Optional

# 将项目根目录添加到Python路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.llm_client import LLMClient, ChatMessage, ModelType
from baseService.logger_service import AgentLogger
from baseService.thinking_agent import analyze_task_progress


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
        model_type: ModelType = ModelType.CLAUDE_3_7_SONNET
    ):
        """
        初始化Agent。

        Args:
            agent_name (str): Agent的名称，用于日志记录。
            system_prompt (str): 系统提示词，定义Agent的角色和行为。
            available_tools (List[str]): 可用的工具列表。
            max_turns (int, optional): 防止无限循环的最大执行轮次。
            model_type (ModelType, optional): 使用的LLM模型类型。
        """
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.available_tools = available_tools
        self.max_turns = max_turns
        self.model_type = model_type
        
        # 初始化LLM客户端
        tools_config_path = os.path.join(project_root, 'baseService', 'tools_config.yaml')
        self.client = LLMClient(tools_config_file=tools_config_path)
        
        # 日志记录器将在run方法中初始化（需要task_id）
        self.agent_logger = None
        
        # 对话历史相关
        self.conversation_dir = os.path.join(project_root, 'conversations')
        self._ensure_conversation_dir()
        
        # 工具调用计数器，用于thinking agent触发
        self.tool_call_counter = 0
    
    def _ensure_conversation_dir(self):
        """确保对话记录目录存在"""
        if not os.path.exists(self.conversation_dir):
            os.makedirs(self.conversation_dir)
    
    def _generate_conversation_filename(self, task_id: str, user_input: str) -> str:
        """
        根据除max_turns外的所有输入内容生成对话文件名。
        
        Args:
            task_id (str): 任务ID
            user_input (str): 用户输入
            
        Returns:
            str: 对话文件的完整路径
        """
        # 创建用于生成文件名的组合字符串（不包括max_turns）
        content_for_hash = f"{self.agent_name}|{self.system_prompt}|{sorted(self.available_tools)}|{self.model_type.value}|{task_id}|{user_input}"
        # 生成哈希值作为文件名的一部分
        hash_object = hashlib.md5(content_for_hash.encode())
        file_hash = hash_object.hexdigest()[:12]  # 取前12位作为文件名
        
        # 构建文件名：任务ID_哈希值.json
        filename = f"{task_id}_{file_hash}.json"
        return os.path.join(self.conversation_dir, filename)
    
    def _save_conversation(self, task_id: str, user_input: str, history: List[ChatMessage], current_turn: int):
        """
        保存对话历史到JSON文件。
        
        Args:
            task_id (str): 任务ID
            user_input (str): 用户输入
            history (List[ChatMessage]): 对话历史
            current_turn (int): 当前轮次
        """
        try:
            conversation_file = self._generate_conversation_filename(task_id, user_input)
            
            # 准备保存的数据
            conversation_data = {
                "agent_name": self.agent_name,
                "system_prompt": self.system_prompt,
                "available_tools": self.available_tools,
                "model_type": self.model_type.value,
                "task_id": task_id,
                "user_input": user_input,
                "current_turn": current_turn,
                "history": [
                    {
                        "role": msg.role,
                        "content": msg.content
                    } for msg in history
                ],
                "timestamp": self._get_current_timestamp()
            }
            
            # 保存到文件
            with open(conversation_file, 'w', encoding='utf-8') as f:
                json.dump(conversation_data, f, indent=2, ensure_ascii=False)
                
            if self.agent_logger:
                self.agent_logger.info(f"💾 对话历史已保存到: {conversation_file}")
                
        except Exception as e:
            if self.agent_logger:
                self.agent_logger.error("save_conversation", f"保存对话历史失败: {str(e)}")
            print(f"⚠️ 保存对话历史失败: {e}")
    
    def _load_conversation(self, task_id: str, user_input: str) -> Optional[tuple]:
        """
        从JSON文件加载对话历史。
        
        Args:
            task_id (str): 任务ID
            user_input (str): 用户输入
            
        Returns:
            Optional[tuple]: (history, current_turn) 如果找到文件，否则返回None
        """
        try:
            conversation_file = self._generate_conversation_filename(task_id, user_input)
            
            if not os.path.exists(conversation_file):
                return None
                
            with open(conversation_file, 'r', encoding='utf-8') as f:
                conversation_data = json.load(f)
            
            # 验证数据完整性（排除max_turns）
            expected_agent = self.agent_name
            expected_system = self.system_prompt
            expected_tools = sorted(self.available_tools)
            expected_model = self.model_type.value
            
            if (conversation_data.get("agent_name") != expected_agent or
                conversation_data.get("system_prompt") != expected_system or
                sorted(conversation_data.get("available_tools", [])) != expected_tools or
                conversation_data.get("model_type") != expected_model or
                conversation_data.get("task_id") != task_id or
                conversation_data.get("user_input") != user_input):
                
                print(f"⚠️ 对话历史文件存在，但配置不匹配，将创建新的对话")
                return None
            
            # 重建对话历史
            history = [
                ChatMessage(role=msg["role"], content=msg["content"])
                for msg in conversation_data.get("history", [])
            ]
            
            current_turn = conversation_data.get("current_turn", 0)
            
            if self.agent_logger:
                self.agent_logger.info(f"📂 已加载对话历史，从第 {current_turn + 1} 轮继续")
            
            return history, current_turn
            
        except Exception as e:
            if self.agent_logger:
                self.agent_logger.error("load_conversation", f"加载对话历史失败: {str(e)}")
            print(f"⚠️ 加载对话历史失败: {e}")
            return None
    
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
        if history[-1].content.startswith("继续"):
            pass
        else:
            history.append(ChatMessage(role="user", content="继续,本轮没有工具在运行，也没有任何返回结果"))
    
    def _trigger_thinking_agent(self, task_description: str, history: List[ChatMessage]) -> Optional[str]:
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
                analysis_history.append(ChatMessage(role="assistant", content="我来分析一下当前的任务进展。"))
            
            # 调用thinking agent进行分析
            analysis_result = analyze_task_progress(
                task_description=task_description,
                conversation_history=analysis_history,
                agent_system_prompt=self.system_prompt,
                model_type=self.model_type
            )
            
            return analysis_result
            
        except Exception as e:
            error_msg = f"ThinkingAgent分析失败: {str(e)}"
            print(f"[{self.agent_name}] {error_msg}")
            if self.agent_logger:
                self.agent_logger.error("thinking_agent_error", error_msg)
            return None
        
       
    
    def _cleanup_conversation(self, task_id: str, user_input: str):
        """
        清理已完成的对话文件（可选）。
        
        Args:
            task_id (str): 任务ID
            user_input (str): 用户输入
        """
        try:
            conversation_file = self._generate_conversation_filename(task_id, user_input)
            if os.path.exists(conversation_file):
                os.remove(conversation_file)
                if self.agent_logger:
                    self.agent_logger.info(f"🗑️ 已清理对话历史文件: {conversation_file}")
        except Exception as e:
            if self.agent_logger:
                self.agent_logger.warning(f"清理对话历史文件失败: {str(e)}")
    
    def list_conversation_files(self) -> List[str]:
        """
        列出所有保存的对话文件。
        
        Returns:
            List[str]: 对话文件列表
        """
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
        # 初始化日志记录器
        self.agent_logger = AgentLogger(self.agent_name, task_id)
        
        # 记录任务开始信息
        additional_info = {
            "max_turns": self.max_turns,
            "available_tools": self.available_tools,
            "model_type": self.model_type.value
        }
        self.agent_logger.start(user_input, additional_info)
        
        print(f"🤖 启动 {self.agent_name}，处理任务: {task_id} 🤖")
        self.agent_logger.info(f"可用工具列表: {self.available_tools}")
        
        # 尝试加载现有的对话历史
        loaded_data = self._load_conversation(task_id, user_input)
        if loaded_data:
            history, start_turn = loaded_data
            print(f"📂 找到现有对话记录，从第 {start_turn + 1} 轮继续执行")
            
            # 检查对话是否已经完成
            if history and history[-1].role == "assistant":
                last_response = history[-1].content
                # 尝试解析最后一条assistant消息，看是否是完成状态
                try:
                    # 尝试解析为JSON
                    
                    
                    result = json.loads(last_response.strip('```json').strip('```'))
                    

                    status = result.get("status")
                    if status in ["success", "error"]:
                        print(f"✅ 发现对话已完成，状态: {status.upper()}")
                        print(f"直接返回之前的结果，无需重新执行")
                        self.agent_logger.info(f"对话已完成，直接返回结果: {status}")
                        return result
                    elif status == "thinking":
                        print(f"🤔 发现对话中断于thinking状态，添加'继续'消息并继续执行")
                        self.agent_logger.info(f"对话中断于thinking状态，添加继续消息")
                        # thinking状态，添加继续消息（如果最后一条不是继续消息的话）
                        
                except json.JSONDecodeError:
                    # 不是JSON格式，检查是否包含完成关键词
                    if "完成" in last_response or "成功" in last_response:
                        success_result = {
                            "status": "success", 
                            "output": last_response, 
                            "error_information": ""
                        }
                        print(f"✅ 发现对话已完成，直接返回之前的结果")
                        self.agent_logger.info(f"对话已完成，直接返回结果: success")
                        return success_result
                    else:
                        # 不是完成状态的纯文本，可能是思考过程或中间状态，添加继续消息
                        print(f"🔄 发现对话中断于中间状态，添加'继续'消息并继续执行")
                        self.agent_logger.info(f"对话中断于中间状态，添加继续消息")
                        self._add_continue_message_if_needed(history)
            elif history and history[-1].role == "user" and history[-1].content == "继续":
                print(f"🔄 发现对话已添加继续消息，直接继续执行")
                self.agent_logger.info(f"对话已包含继续消息，直接继续执行")
        else:
            # 构建新的对话历史
            history = [ChatMessage(role="user", content=user_input)]
            start_turn = 0
            print(f"🆕 开始新的对话")
        self._add_continue_message_if_needed(history)
        
        
        # 执行循环
        for i in range(start_turn, self.max_turns):
            self.agent_logger.turn_start(i + 1, self.max_turns)
            print(f"\n--- {self.agent_name} 第 {i+1}/{self.max_turns} 轮执行 ---")
            
            # 每轮都保存对话历史
            self._save_conversation(task_id, user_input, history, i)
     
            # 记录 LLM 请求
            self.agent_logger.llm_request(
                model=self.model_type.value,
                system_prompt=self.system_prompt,
                user_input=user_input if i == 0 else "继续执行",
                available_tools=self.available_tools
            )

            llm_response = self.client.chat(
                history=history,
                model=self.model_type,
                system_prompt=self.system_prompt,
                tool_list=self.available_tools,
                tool_choice="auto"
            )
            
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



            try:
                tool_calls = llm_response.tool_calls
            except:
                tool_calls = False
                
            # 情况一：LLM进行了工具调用
            if tool_calls:
                print(f"[{self.agent_name}] 正在调用工具: {[call.name for call in tool_calls]}")
                for tool_single in tool_calls:
                    print(tool_single,'命令详情')
                
                # if llm_response.output:
                #     history.append(ChatMessage(
                #         role="assistant", 
                #         content=llm_response.output
                #     ))
                    
                
                # 将LLM的工具调用请求添加到历史记录
                #history.append(ChatMessage(role="assistant", content=json.dumps({"tool_calls": [call.__dict__ for call in tool_calls]})))
                
                
                for tool_call in tool_calls:
                    tool_result = self._execute_tool(tool_call, task_id)
                    
                    # 增加工具调用计数
                    self.tool_call_counter += 1
                    
                    # 如果是 final_output 工具，直接返回结果
                    if tool_call.name == "final_output":
                        print(f"[{self.agent_name}] 检测到 final_output 工具调用，直接返回最终结果")
                        self.agent_logger.decision(tool_result["status"], tool_result["output"])
                        self.agent_logger.end(tool_result, "final_output_called")

                        history.append(ChatMessage(
                            role="assistant", 
                            content=json.dumps(tool_result,ensure_ascii=False),
                        ))

                        self._save_conversation(task_id, user_input, history, i)

                        return tool_result
                    
                    # 智能处理工具调用信息，截断过长的字段值
                    tool_call_info = tool_call.__dict__.copy()
                    if 'arguments' in tool_call_info and isinstance(tool_call_info['arguments'], dict):
                        processed_args = {}
                        for key, value in tool_call_info['arguments'].items():
                            if isinstance(value, str) and len(value) > 500:
                                # 对于过长的字符串，显示类型信息和长度，而不是截断内容
                                if key == 'content':
                                    # 对于 content 字段，显示开头和类型信息
                                    preview = value[:100].replace('\n', ' ').replace('\r', ' ')
                                    processed_args[key] = f"[长内容:{len(value)}字符] {preview}..."
                                elif key == 'file_path':
                                    # 文件路径保持完整
                                    processed_args[key] = value
                                else:
                                    # 其他字段截断前100字符
                                    processed_args[key] = value[:100] + "..."
                            else:
                                processed_args[key] = value
                        tool_call_info['arguments'] = processed_args
                    
                    content_tool_calls = json.dumps({"tool_calls": [tool_call_info]}, ensure_ascii=False)
                    # 将工具的执行结果添加到历史记录，确保JSON正确解码
                    try:
                        tool_result_str = json.dumps(tool_result, ensure_ascii=False)
                    except:
                        tool_result_str = str(tool_result)
                    

                    history.append(ChatMessage(
                        role="assistant", 
                        content=llm_response.output,
                    ))
                    
                    history.append(ChatMessage(
                        role="user", 
                        content=f'{content_tool_calls}成功执行，结果为tool_result:{tool_result_str}'
                    ))
                
                # 检查是否需要触发thinking agent（每5轮工具调用后）
                if self.tool_call_counter % 5 == 0:
                    thinking_analysis = self._trigger_thinking_agent(user_input, history)
                    if thinking_analysis:
                        # 添加thinking agent的分析结果到对话历史
                        history.append(ChatMessage(
                            role="assistant",
                            content=thinking_analysis
                        ))
                        print(f"[{self.agent_name}] 第{self.tool_call_counter}轮工具调用后，ThinkingAgent分析已添加")
                        self.agent_logger.info(f"ThinkingAgent分析已添加到第{i+1}轮对话")
                
                # 保存更新后的对话历史
                self._save_conversation(task_id, user_input, history, i)
                continue

            # 情况二：LLM返回了文本（尝试解析为JSON）
            # elif llm_response.output:
            #     # 首先检查是否是thinking状态assistant
            #     try:
            #         parsed_response = json.loads(llm_response.output.strip('```json').strip('```'))
            #         if parsed_response.get("status") == "thinking":
            #             print(f"[{self.agent_name}] 检测到thinking状态，添加继续消息")
            #             # 添加assistant消息到历史
            #             history.append(ChatMessage(role="assistant", content=llm_response.output))
            #             history.append(ChatMessage(role="user", content="思考结束请你继续执行"))
            #             # 添加"继续"消息
            #             # self._add_continue_message_if_needed(history)
            #             # 保存对话历史
            #             self._save_conversation(task_id, user_input, history, i)
            #             continue
            #     except json.JSONDecodeError:
            #         pass
                
            #     # 处理其他类型的输出
            #     result = self._process_llm_output(llm_response.output)
            #     if result:
            #         # 添加assistant消息到历史
            #         history.append(ChatMessage(role="assistant", content=str(result)))
            #         print(history,'historycheng1')
            #         # 返回最终结果前保存对话历史
            #         self._save_conversation(task_id, user_input, history, i)
            #         print(history,'historycheng2')
            #         print('resultcheng1',result,'resultcheng')
            #         return result
            #     else:
            #         history.append(ChatMessage(role="assistant", content=str(llm_response.output)))
            #         history.append(ChatMessage(role="user", content="你的输出格式有误，请严格按照提示词指令"))

                    
            #     # 添加assistant消息到历史
            #     #history.append(ChatMessage(role="assistant", content=llm_response.output))
            #     history.append(ChatMessage(role="user", content=""))
            #     # 保存更新后的对话历史
            #     self._save_conversation(task_id, user_input, history, i)
            #     continue
            
            # # 情况三：LLM既没有调用工具也没有返回内容
            else:
                error_msg = f"{self.agent_name} 没有返回任何有效响应。ai没有使用工具"
                self.agent_logger.error("no_response", error_msg)
                error_result = {"status": "error", "output": "", "error_information": error_msg}
                # 保存出错时的对话历史
                self._save_conversation(task_id, user_input, history, i)
                self.agent_logger.end(error_result, "no_response")
                return error_result

        # 超过最大轮次
        error_msg = f"{self.agent_name} 执行超过最大轮次限制。"
        self.agent_logger.warning(f"执行达到最大轮次限制: {self.max_turns}")
        error_result = {"status": "error", "output": "", "error_information": error_msg}
        # 保存超时时的对话历史
        self._save_conversation(task_id, user_input, history, self.max_turns - 1)
        self.agent_logger.end(error_result, "max_turns_exceeded")
        return error_result

    def _get_tool_level(self, tool_name: str) -> int:
        """
        获取工具的级别。
        
        Args:
            tool_name (str): 工具名称
            
        Returns:
            int: 工具级别，默认为4
        """
        try:
            import yaml
            tools_level_path = os.path.join(project_root, 'baseService', 'tools_level.yaml')
            with open(tools_level_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                tool_config = config.get("tools", {}).get(tool_name, {})
                return tool_config.get("level", 4)  # 默认返回level 4
        except Exception as e:
            print(f"⚠️ 获取工具级别失败: {e}")
            return 4  # 默认返回level 4

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
            # 获取工具级别并动态导入模块
            tool_level = self._get_tool_level(tool_call.name)
            
            # 根据级别构建模块路径
            if tool_level == 4:
                module_path = f"agentLevelFour.{tool_call.name}"
            elif tool_level == 3:
                module_path = f"agentLevelThree.{tool_call.name}"
            elif tool_level == 2:
                module_path = f"agentLevelTwo.{tool_call.name}"
            elif tool_level == 1:
                module_path = f"agentLevelOne.{tool_call.name}"
            
            module = importlib.import_module(module_path)
            arguments = tool_call.arguments.copy()
            if "task_id" not in arguments:
                arguments['task_id'] = task_id
            
            tool_result = module.run(**arguments)
            print(f"[{self.agent_name}] 工具 '{tool_call.name}' (level {tool_level}) 执行结果: {tool_result['status']}")
            
            # 记录工具执行
            self.agent_logger.tool_execution(tool_call.name, tool_call.arguments, tool_result)
            
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
            

            
            # else:
            #     # 状态不是预期的值，但仍然是有效JSON，作为普通响应处理
            #     print(f"[{self.agent_name}] 响应: {output}")
                
            #     # 如果响应看起来像是完成了，就返回结果
            #     if "完成" in output or "成功" in output:
            #         success_result = {
            #             "status": "success", 
            #             "output": output, 
            #             "error_information": ""
            #         }
            #         self.agent_logger.decision("success", output)
            #         self.agent_logger.end(success_result, "task_completed")
            #         return success_result
                
            return None

        except json.JSONDecodeError:
            # 不是JSON格式，作为普通文本响应处理
            print(f"[{self.agent_name}] 响应: {output}")
            
            # 如果响应看起来像是完成了，就返回结果
            # if "完成" in output or "成功" in output:
            #     success_result = {
            #         "status": "success", 
            #         "output": output, 
            #         "error_information": ""
            #     }
            #     self.agent_logger.decision("success", output)
            #     self.agent_logger.end(success_result, "task_completed")
            #     return success_result
            
            return None


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
        max_turns=10
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
