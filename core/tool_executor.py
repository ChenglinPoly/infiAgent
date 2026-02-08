#!/usr/bin/env python3
from utils.windows_compat import safe_print
# -*- coding: utf-8 -*-
"""
工具执行器 - 支持两种模式：
1. HTTP 模式（默认）：通过 HTTP 调用独立的 ToolServer 进程
2. Direct 模式：进程内直接调用工具类，无需 ToolServer（桌面应用使用）
"""

import requests
import yaml
import json
import time
import uuid
import asyncio
import threading
from typing import Dict, Any
from pathlib import Path


class ToolExecutor:
    """工具执行器 - 支持 HTTP 模式和进程内直接调用模式"""
    
    # 危险工具列表（需要用户确认）
    DANGEROUS_TOOLS = [
        "file_write",      # 文件写入
        "pip_install",     # 安装包
        "execute_code",    # 执行代码
    ]
    
    def __init__(self, config_loader, hierarchy_manager, direct_mode=False):
        """
        初始化工具执行器
        
        Args:
            config_loader: 配置加载器
            hierarchy_manager: 层级管理器
            direct_mode: 是否使用进程内直接调用模式（不依赖 ToolServer HTTP 服务）
        """
        self.config_loader = config_loader
        self.hierarchy_manager = hierarchy_manager
        self.task_cache = {}  # 缓存已创建的任务
        self.direct_mode = direct_mode
        
        if direct_mode:
            # 进程内模式：直接初始化工具注册表
            self._tools_registry = None  # 懒加载
            self.tools_server_url = None
            safe_print("🔧 工具执行器: 进程内直接调用模式（无需 ToolServer）")
        else:
            # HTTP 模式：从 tool_config.yaml 读取 ToolServer URL
            self._tools_registry = None
            self.tools_server_url = self._load_tools_server_url()
        
        # 权限管理：task_id → auto_mode 映射
        self.task_permissions = {}  # {task_id: {"auto_mode": True/False}}
    
    def _load_tools_server_url(self) -> str:
        """从配置文件加载工具服务器URL"""
        try:
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "run_env_config" / "tool_config.yaml"
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                url = config.get('tools_server', 'http://127.0.0.1:8001/')
                # 移除末尾的斜杠
                return url.rstrip('/')
        except Exception as e:
            safe_print(f"⚠️ 加载工具服务器配置失败: {e}，使用默认值")
            return "http://127.0.0.1:8001"
    
    def _init_tools_registry(self):
        """
        懒加载：初始化进程内工具注册表（与 server.py 的 TOOLS 字典一致）
        仅在 direct_mode=True 时使用
        """
        if self._tools_registry is not None:
            return
        
        safe_print("🔧 初始化进程内工具注册表...")
        
        from tool_server_lite.tools import (
            FileReadTool, FileWriteTool, DirListTool, DirCreateTool,
            FileMoveTool, FileDeleteTool,
            WebSearchTool, GoogleScholarSearchTool, ArxivSearchTool,
            CrawlPageTool, FileDownloadTool,
            ParseDocumentTool,
            VisionTool, ImageReadTool, CreateImageTool,
            AudioTool, PaperAnalyzeTool,
            MarkdownToPdfTool, MarkdownToDocxTool,
            HumanInLoopTool,
            ExecuteCodeTool, PipInstallTool, ExecuteCommandTool,
            GrepTool, CodeProcessManagerTool,
            ReferenceListTool, ReferenceAddTool, ReferenceDeleteTool,
            ImagesToPptTool, LoadSkillTool,
        )
        
        self._tools_registry = {
            "file_read": FileReadTool(),
            "file_write": FileWriteTool(),
            "dir_list": DirListTool(),
            "dir_create": DirCreateTool(),
            "file_move": FileMoveTool(),
            "file_delete": FileDeleteTool(),
            "web_search": WebSearchTool(),
            "google_scholar_search": GoogleScholarSearchTool(),
            "arxiv_search": ArxivSearchTool(),
            "crawl_page": CrawlPageTool(),
            "file_download": FileDownloadTool(),
            "parse_document": ParseDocumentTool(),
            "vision_tool": VisionTool(),
            "image_read": ImageReadTool(),
            "create_image": CreateImageTool(),
            "audio_tool": AudioTool(),
            "paper_analyze_tool": PaperAnalyzeTool(),
            "md_to_pdf": MarkdownToPdfTool(),
            "md_to_docx": MarkdownToDocxTool(),
            "human_in_loop": HumanInLoopTool(),
            "execute_code": ExecuteCodeTool(),
            "pip_install": PipInstallTool(),
            "execute_command": ExecuteCommandTool(),
            "grep": GrepTool(),
            "manage_code_process": CodeProcessManagerTool(),
            "reference_list": ReferenceListTool(),
            "reference_add": ReferenceAddTool(),
            "reference_delete": ReferenceDeleteTool(),
            "images_to_ppt": ImagesToPptTool(),
            "load_skill": LoadSkillTool(),
        }
        
        # 尝试加载浏览器工具（可能不可用）
        try:
            from tool_server_lite.tools import (
                BrowserLaunchTool, BrowserCloseTool, BrowserNavigateTool,
                BrowserSnapshotTool, BrowserExecuteJsTool,
                BrowserNewPageTool, BrowserSwitchPageTool,
                BrowserClosePageTool, BrowserListPagesTool,
                BrowserClickTool, BrowserTypeTool, BrowserWaitTool,
                BrowserMouseMoveTool, BrowserMouseClickCoordsTool,
                BrowserDragAndDropTool, BrowserHoverTool, BrowserScrollTool,
            )
            self._tools_registry.update({
                "browser_launch": BrowserLaunchTool(),
                "browser_close": BrowserCloseTool(),
                "browser_navigate": BrowserNavigateTool(),
                "browser_snapshot": BrowserSnapshotTool(),
                "browser_execute_js": BrowserExecuteJsTool(),
                "browser_new_page": BrowserNewPageTool(),
                "browser_switch_page": BrowserSwitchPageTool(),
                "browser_close_page": BrowserClosePageTool(),
                "browser_list_pages": BrowserListPagesTool(),
                "browser_click": BrowserClickTool(),
                "browser_type": BrowserTypeTool(),
                "browser_wait": BrowserWaitTool(),
                "browser_mouse_move": BrowserMouseMoveTool(),
                "browser_mouse_click_coords": BrowserMouseClickCoordsTool(),
                "browser_drag_and_drop": BrowserDragAndDropTool(),
                "browser_hover": BrowserHoverTool(),
                "browser_scroll": BrowserScrollTool(),
            })
        except ImportError:
            safe_print("⚠️ 浏览器工具不可用（缺少 playwright），跳过")
        
        safe_print(f"✅ 工具注册表初始化完成，共 {len(self._tools_registry)} 个工具")
    
    def _call_direct(self, tool_name: str, arguments: Dict, task_id: str) -> Dict:
        """
        进程内直接调用工具（不经过 HTTP）
        
        返回格式与 _call_toolserver 完全一致（保持 json.dumps 包装），
        确保 agent_executor 中的后续处理逻辑（如 image_read base64 提取）兼容。
        """
        try:
            # 懒加载工具注册表
            self._init_tools_registry()
            
            tool = self._tools_registry.get(tool_name)
            if not tool:
                return {
                    "status": "error",
                    "output": "",
                    "error_information": f"工具不存在: {tool_name}"
                }
            
            safe_print(f"   🔧 直接调用工具: {tool_name}")
            
            # 调用工具（与 ToolServer 的调用方式一致）
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
            
            # 包装返回值（与 _call_toolserver 格式一致：data 被 json.dumps 到 output 字符串）
            return {
                "status": "success",
                "output": json.dumps(tool_result, indent=2, ensure_ascii=False),
                "error_information": ""
            }
        
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
    
    def _ensure_task_exists(self, task_id: str):
        """确保任务在toolServer中存在"""
        if task_id in self.task_cache:
            return
        
        try:
            # URL 编码 task_id（避免路径中的特殊字符和双斜杠问题）
            from urllib.parse import quote
            encoded_task_id = quote(task_id, safe='')
            
            # 检查任务状态（确保 URL 格式正确）
            status_url = f"{self.tools_server_url}/api/task/{encoded_task_id}/status"
            response = requests.get(status_url, timeout=5)
            
            if response.status_code == 200:
                self.task_cache[task_id] = True
                return
            
            # 任务不存在，创建它
            create_url = f"{self.tools_server_url}/api/task/create"
            params = {"task_id": task_id, "task_name": f"MLA-V3-{task_id}"}
            create_response = requests.post(create_url, params=params, timeout=10)
            
            if create_response.status_code == 200:
                safe_print(f"✅ 任务 '{task_id}' 已在toolServer中创建")
                self.task_cache[task_id] = True
            else:
                safe_print(f"⚠️ 创建任务失败: {create_response.text}")
        
        except Exception as e:
            safe_print(f"⚠️ 检查/创建任务时出错: {e}")
    
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
            
            # 创建确认请求
            create_url = f"{self.tools_server_url}/api/tool-confirmation/create"
            create_payload = {
                "confirm_id": confirm_id,
                "task_id": task_id,
                "tool_name": tool_name,
                "arguments": arguments
            }
            
            response = requests.post(create_url, json=create_payload, timeout=5)
            if response.status_code != 200:
                safe_print(f"⚠️  创建确认请求失败，默认拒绝执行")
                return False
            
            safe_print(f"⏸️  等待用户确认: {tool_name}")
            
            # 轮询等待用户响应（最多等待 300 秒）
            max_wait = 300
            check_interval = 2
            elapsed = 0
            
            status_url = f"{self.tools_server_url}/api/tool-confirmation/{confirm_id}"
            
            while elapsed < max_wait:
                time.sleep(check_interval)
                elapsed += check_interval
                
                try:
                    status_response = requests.get(status_url, timeout=5)
                    if status_response.status_code == 200:
                        result = status_response.json()
                        
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
            # 获取工具配置
            tool_config = self.config_loader.get_tool_config(tool_name)
            tool_type = tool_config.get("type")
            
            # 特殊处理final_output
            if tool_name == "final_output":
                return {
                    "status": arguments.get("status", "success"),
                    "output": arguments.get("output", ""),
                    "error_information": arguments.get("error_information", "")
                }
            
            # 判断是普通工具还是子Agent
            if tool_type == "tool_call_agent":
                # 检查是否为危险工具且需要确认
                if tool_name in self.DANGEROUS_TOOLS and not self.is_auto_mode(task_id):
                    # 请求用户确认
                    approved = self._request_tool_confirmation(tool_name, arguments, task_id)
                    
                    if not approved:
                        # 用户拒绝执行
                        return {
                            "status": "error",
                            "output": "",
                            "error_information": f"工具执行被用户拒绝: {tool_name}"
                        }
                
                # 普通工具 - 根据模式选择调用方式
                if self.direct_mode:
                    return self._call_direct(tool_name, arguments, task_id)
                else:
                    return self._call_toolserver(tool_name, arguments, task_id)
            
            elif tool_type == "llm_call_agent":
                # 子Agent - 递归调用
                # 注意：uuid 已在 agent_executor 中添加（仅对 level != 0）
                return self._execute_sub_agent(tool_name, tool_config, arguments, task_id)
            
            else:
                return {
                    "status": "error",
                    "output": "",
                    "error_information": f"不支持的工具类型: {tool_type}"
                }
        
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error_information": f"工具执行失败: {str(e)}"
            }
    
    def _call_toolserver(self, tool_name: str, arguments: Dict, task_id: str) -> Dict:
        """通过HTTP调用toolServer执行工具"""
        try:
            # 确保任务存在
            self._ensure_task_exists(task_id)
            
            # 构建请求
            execute_url = f"{self.tools_server_url}/api/tool/execute"
            payload = {
                "task_id": task_id,
                "tool_name": tool_name,
                "params": arguments
            }
            
            headers = {
                'Content-Type': 'application/json; charset=utf-8',
                'Accept': 'application/json; charset=utf-8'
            }
            
            safe_print(f"   🔗 调用toolServer: {tool_name}")
            
            # 发送请求
            response = requests.post(
                execute_url,
                json=payload,
                headers=headers,
                timeout=100000
            )
            response.raise_for_status()
            
            # 解析响应
            tool_server_response = response.json()
            
            if tool_server_response.get("success"):
                output_data = tool_server_response.get("data", {})
                return {
                    "status": "success",
                    "output": json.dumps(output_data, indent=2, ensure_ascii=False),
                    "error_information": ""
                }
            else:
                error_msg = tool_server_response.get("error", "工具服务器返回未知错误")
                return {
                    "status": "error",
                    "output": "",
                    "error_information": error_msg
                }
        
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error_information": f"调用toolServer失败: {str(e)}"
            }
    
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
                direct_tools=self.direct_mode
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
    safe_print(f"   ToolServer URL: {executor.tools_server_url}")
    
    # 测试final_output
    result = executor.execute("final_output", {
        "task_id": "test",
        "status": "success",
        "output": "测试完成"
    }, "test_task")
    
    safe_print(f"✅ final_output测试: {result}")
