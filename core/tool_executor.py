#!/usr/bin/env python3
from utils.windows_compat import safe_print
# -*- coding: utf-8 -*-
"""
工具执行器 - 统一使用进程内 direct-tools 模式。
"""

import json
import time
import uuid
import asyncio
import threading
from typing import Dict, Any

from tool_server_lite.registry import get_runtime_registry, get_runtime_registry_failures
from utils.mcp_manager import call_mcp_tool
from utils.tool_hooks import trigger_tool_hooks

class ToolExecutor:
    """工具执行器 - 统一使用进程内 direct-tools 模式"""
    
    # 危险工具列表（需要用户确认）
    DANGEROUS_TOOLS = [
        "file_write",      # 文件写入
        "execute_command", # 执行命令
    ]
    
    def __init__(
        self,
        config_loader,
        hierarchy_manager,
        direct_mode=False,
        extra_event_handlers=None,
        exit_on_error: bool = True,
        raise_on_error: bool = False,
        stream_llm_tokens: bool = False,
    ):
        """
        初始化工具执行器
        
        Args:
            config_loader: 配置加载器
            hierarchy_manager: 层级管理器
            direct_mode: 兼容旧参数，当前始终使用进程内 direct-tools 模式
        """
        self.config_loader = config_loader
        self.hierarchy_manager = hierarchy_manager
        self.direct_mode = True
        self.extra_event_handlers = list(extra_event_handlers or [])
        self.exit_on_error = bool(exit_on_error)
        self.raise_on_error = bool(raise_on_error)
        self.stream_llm_tokens = bool(stream_llm_tokens)
        self._tools_registry = None  # 懒加载
        safe_print("🔧 工具执行器: 进程内直接调用模式（无需 ToolServer）")
        
        # 权限管理：task_id → auto_mode 映射
        self.task_permissions = {}  # {task_id: {"auto_mode": True/False}}
        self.agent_id = ""
        self.agent_name = ""

    def set_agent_context(self, *, agent_id: str = "", agent_name: str = ""):
        self.agent_id = str(agent_id or "")
        self.agent_name = str(agent_name or "")

    def _agent_level(self) -> int:
        try:
            context = self.hierarchy_manager.get_context()
            hierarchy = ((context or {}).get("current") or {}).get("hierarchy") or {}
            return int(((hierarchy.get(self.agent_id) or {}).get("level")) or 0)
        except Exception:
            return 0
    
    def _init_tools_registry(self):
        """
        懒加载：初始化进程内工具注册表（与 server.py 的注册中心一致）
        仅在 direct_mode=True 时使用
        """
        if self._tools_registry is not None:
            return
        
        safe_print("🔧 初始化进程内工具注册表...")
        self._tools_registry = get_runtime_registry(force_reload=True)
        safe_print(f"✅ 工具注册表初始化完成，共 {len(self._tools_registry)} 个工具")
    
    def _call_direct(self, tool_name: str, arguments: Dict, task_id: str) -> Dict:
        """
        进程内直接调用工具（不经过 HTTP）
        
        返回格式保持与旧工具执行层一致（data 被 json.dumps 到 output 字符串），
        确保 agent_executor 中的后续处理逻辑（如 image_read base64 提取）兼容。
        """
        try:
            # 懒加载工具注册表
            self._init_tools_registry()
            
            tool = self._tools_registry.get(tool_name)
            if not tool:
                failure_reason = ""
                for item in get_runtime_registry_failures():
                    if item.get("name") == tool_name:
                        failure_reason = item.get("error", "")
                        break
                return {
                    "status": "error",
                    "output": "",
                    "error_information": (
                        f"工具未注册到运行时: {tool_name}"
                        + (f"（加载失败原因: {failure_reason}）" if failure_reason else "")
                    )
                }
            
            safe_print(f"   🔧 直接调用工具: {tool_name}")
            
            # 调用工具（保持与既有工具返回格式兼容）
            #
            # 注意：部分工具（如 human_in_loop）只实现 execute_async（用于非阻塞等待），
            # 在 direct_mode 下也必须支持，否则会触发 NotImplementedError。
            if hasattr(tool, "execute_async") and callable(getattr(tool, "execute_async")):
                # 在子线程里创建 event loop 执行，避免未来在已有 event loop 场景下崩溃
                result_holder: Dict[str, Any] = {}
                err_holder: Dict[str, Any] = {}

                def _runner():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            coro = tool.execute_async(task_id, arguments)
                            result_holder["tool_result"] = loop.run_until_complete(coro)
                        finally:
                            loop.close()
                    except Exception as e:
                        err_holder["error"] = e

                t = threading.Thread(target=_runner, daemon=True)
                t.start()
                t.join()

                if err_holder.get("error") is not None:
                    raise err_holder["error"]
                tool_result = result_holder.get("tool_result")
            else:
                tool_result = tool.execute(task_id, arguments)
            
            # 包装返回值（保持与既有工具执行层的 output 字段格式一致）
            wrapped = {
                "status": "success",
                "output": json.dumps(tool_result, indent=2, ensure_ascii=False),
                "error_information": ""
            }
            # 透传内部控制字段，供 agent_executor 处理特殊副作用（load/offload skill、fresh 等）
            if isinstance(tool_result, dict):
                for key, value in tool_result.items():
                    if str(key).startswith("_"):
                        wrapped[key] = value
            return wrapped
        
        except Exception as e:
            try:
                safe_print(f"❌ 直接调用工具异常: {tool_name}: {str(e)[:300]}")
            except Exception:
                pass
            return {
                "status": "error",
                "output": "",
                "error_information": f"直接调用工具失败: {str(e)}"
            }
    
    def set_task_permission(self, task_id: str, auto_mode: bool):
        """设置任务的权限模式"""
        self.task_permissions[task_id] = {"auto_mode": auto_mode}
        safe_print(f"🔐 任务权限设置: {task_id} → auto_mode={auto_mode}")
    
    def is_auto_mode(self, task_id: str) -> bool:
        """检查任务是否为自动模式（默认 True）"""
        return self.task_permissions.get(task_id, {}).get("auto_mode", True)
    
    def _request_tool_confirmation(self, tool_name: str, arguments: Dict[str, Any], task_id: str) -> bool:
        """
        请求工具执行确认
        
        Returns:
            True - 用户批准执行
            False - 用户拒绝执行
        """
        try:
            # 生成唯一确认ID
            confirm_id = f"confirm_{tool_name}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            from tool_server_lite.tools.human_tools import (
                create_tool_confirmation,
                get_tool_confirmation_status,
            )

            created = create_tool_confirmation(confirm_id, task_id, tool_name, arguments)
            if not created.get("success"):
                safe_print("⚠️  创建确认请求失败，默认拒绝执行")
                return False
            
            safe_print(f"⏸️  等待用户确认: {tool_name}")
            
            # 轮询等待用户响应（最多等待 300 秒）
            max_wait = 300
            check_interval = 2
            elapsed = 0
            
            while elapsed < max_wait:
                time.sleep(check_interval)
                elapsed += check_interval
                
                try:
                    result = get_tool_confirmation_status(confirm_id)
                    if result.get("found") and result.get("status") == "completed":
                        approved = result.get("result") == "approved"
                        if approved:
                            safe_print(f"✅ 用户批准执行: {tool_name}")
                        else:
                            safe_print(f"❌ 用户拒绝执行: {tool_name}")
                        return approved
                except Exception:
                    continue
            
            # 超时，默认拒绝
            safe_print(f"⏱️  确认超时，拒绝执行: {tool_name}")
            return False
            
        except Exception as e:
            safe_print(f"❌ 确认请求失败: {e}，拒绝执行")
            return False
    
    def execute(self, tool_name: str, arguments: Dict[str, Any], task_id: str) -> Dict:
        """
        执行工具调用
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            task_id: 任务ID
            
        Returns:
            执行结果字典
        """
        try:
            trigger_tool_hooks(
                when="before",
                tool_name=tool_name,
                task_id=task_id,
                arguments=arguments,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                agent_level=self._agent_level(),
            )
        except Exception:
            pass

        try:
            # 获取工具配置
            tool_config = self.config_loader.get_tool_config(tool_name)
            tool_type = tool_config.get("type")
            
            # 特殊处理final_output
            if tool_name == "final_output":
                result = {
                    "status": arguments.get("status", "success"),
                    "output": arguments.get("output", ""),
                    "error_information": arguments.get("error_information", "")
                }
            elif tool_type == "tool_call_agent":
                if tool_name in self.DANGEROUS_TOOLS and not self.is_auto_mode(task_id):
                    approved = self._request_tool_confirmation(tool_name, arguments, task_id)
                    if not approved:
                        result = {
                            "status": "error",
                            "output": "",
                            "error_information": f"工具执行被用户拒绝: {tool_name}"
                        }
                    elif tool_config.get("_mcp"):
                        result = call_mcp_tool(tool_config, arguments)
                    else:
                        result = self._call_direct(tool_name, arguments, task_id)
                elif tool_config.get("_mcp"):
                    result = call_mcp_tool(tool_config, arguments)
                else:
                    result = self._call_direct(tool_name, arguments, task_id)
            elif tool_type == "llm_call_agent":
                result = self._execute_sub_agent(tool_name, tool_config, arguments, task_id)
            else:
                result = {
                    "status": "error",
                    "output": "",
                    "error_information": f"不支持的工具类型: {tool_type}"
                }
        except Exception as e:
            result = {
                "status": "error",
                "output": "",
                "error_information": f"工具执行失败: {str(e)}"
            }

        try:
            trigger_tool_hooks(
                when="after",
                tool_name=tool_name,
                task_id=task_id,
                arguments=arguments,
                result=result,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                agent_level=self._agent_level(),
            )
        except Exception:
            pass
        return result
    
    def _execute_sub_agent(
        self,
        agent_name: str,
        agent_config: Dict,
        arguments: Dict,
        task_id: str
    ) -> Dict:
        """执行子Agent调用"""
        try:
            # 导入Agent执行器（避免循环导入）
            from core.agent_executor import AgentExecutor
            
            # 获取任务输入
            task_input = arguments.get("task_input", "")
            
            # 创建子Agent执行器（传递 direct_mode 保持一致）
            sub_agent = AgentExecutor(
                agent_name=agent_name,
                agent_config=agent_config,
                config_loader=self.config_loader,
                hierarchy_manager=self.hierarchy_manager,
                direct_tools=self.direct_mode,
                extra_event_handlers=self.extra_event_handlers,
                exit_on_error=self.exit_on_error,
                raise_on_error=self.raise_on_error,
                stream_llm_tokens=self.stream_llm_tokens,
            )
            
            # 执行子Agent
            result = sub_agent.run(task_id, task_input)
            
            return result
        
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            safe_print(f"❌ 子Agent执行失败: {e}")
            safe_print(f"详细错误:\n{error_detail}")
            return {
                "status": "error",
                "output": "",
                "error_information": f"子Agent执行失败: {str(e)}\n{error_detail}"
            }


if __name__ == "__main__":
    from utils.config_loader import ConfigLoader
    from core.hierarchy_manager import get_hierarchy_manager
    
    # 测试工具执行器
    config_loader = ConfigLoader("infiHelper")
    hierarchy_manager = get_hierarchy_manager("test_task")
    
    executor = ToolExecutor(config_loader, hierarchy_manager)
    safe_print(f"✅ 工具执行器初始化成功")
    safe_print("   Mode: direct-tools")
    
    # 测试final_output
    result = executor.execute("final_output", {
        "task_id": "test",
        "status": "success",
        "output": "测试完成"
    }, "test_task")
    
    safe_print(f"✅ final_output测试: {result}")
