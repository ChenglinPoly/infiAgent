#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人类交互工具
"""

from pathlib import Path
from typing import Dict, Any
import asyncio
from .file_tools import BaseTool
from utils.event_emitter import get_event_emitter

# 全局 HIL 任务状态存储
HIL_TASKS = {}

# 全局工具确认请求存储（与 HIL 分开）
TOOL_CONFIRMATIONS = {}


class HumanInLoopTool(BaseTool):
    """人类交互工具 - 挂起等待人类完成任务（异步，不阻塞服务器）"""
    
    async def execute_async(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        人类交互 - 挂起等待人类完成
        
        Parameters:
            hil_id (str): 人类任务唯一ID
            instruction (str): 给人类的指令
            timeout (int, optional): 超时时间（秒），默认 None（无限等待）
        """
        try:
            hil_id = parameters.get("hil_id")
            instruction = parameters.get("instruction")
            timeout = parameters.get("timeout")  # 默认 None
            
            if not hil_id:
                return {
                    "status": "error",
                    "output": "",
                    "error": "hil_id is required"
                }
            
            if not instruction:
                return {
                    "status": "error",
                    "output": "",
                    "error": "instruction is required"
                }
            
            # 注册 HIL 任务
            HIL_TASKS[hil_id] = {
                "status": "waiting",
                "instruction": instruction,
                "task_id": task_id,
                "result": None
            }

            try:
                get_event_emitter().human_in_loop(
                    hil_id=hil_id,
                    title="Human-in-Loop",
                    message=instruction,
                    ui={"type": "text"},
                    timeout_sec=int(timeout) if timeout is not None else 1800,
                    resume_hint="请在前端或 CLI 中直接回复该请求",
                )
            except Exception:
                pass
            
            # 异步轮询等待完成
            start_time = asyncio.get_event_loop().time()
            check_interval = 2  # 每2秒检查一次
            
            while True:
                # 检查是否超时
                if timeout is not None:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > timeout:
                        HIL_TASKS[hil_id]["status"] = "timeout"
                        return {
                            "status": "error",
                            "output": "",
                            "error": f"Human task timeout ({timeout}s)"
                        }
                
                # 检查任务状态
                task = HIL_TASKS.get(hil_id)
                if task and task["status"] == "completed":
                    result = task.get("result", "任务已完成")
                    # 清理任务
                    del HIL_TASKS[hil_id]
                    return {
                        "status": "success",
                        "output": f": 用户回复：{result}",
                        "error": ""
                    }
                
                # 异步等待（不阻塞服务器）
                await asyncio.sleep(check_interval)
                
        except Exception as e:
            # 清理任务
            if hil_id in HIL_TASKS:
                del HIL_TASKS[hil_id]
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }


def get_hil_status(hil_id: str) -> Dict[str, Any]:
    """获取 HIL 任务状态"""
    task = HIL_TASKS.get(hil_id)
    if not task:
        return {
            "found": False,
            "error": f"HIL task not found: {hil_id}"
        }
    
    return {
        "found": True,
        "hil_id": hil_id,
        "status": task["status"],
        "instruction": task["instruction"],
        "task_id": task["task_id"]
    }


def respond_hil_task(hil_id: str, response: str) -> Dict[str, Any]:
    """响应 HIL 任务（用户可以回复任何内容）"""
    task = HIL_TASKS.get(hil_id)
    if not task:
        return {
            "success": False,
            "error": f"HIL task not found: {hil_id}"
        }
    
    # 标记为完成，并保存用户响应
    HIL_TASKS[hil_id]["status"] = "completed"
    HIL_TASKS[hil_id]["result"] = response
    
    return {
        "success": True,
        "message": f"HIL task {hil_id} responded with: {response[:100]}"
    }


def list_hil_tasks() -> Dict[str, Any]:
    """列出所有 HIL 任务"""
    tasks = []
    for hil_id, task in HIL_TASKS.items():
        tasks.append({
            "hil_id": hil_id,
            "status": task["status"],
            "instruction": task["instruction"],
            "task_id": task["task_id"]
        })
    
    return {
        "total": len(tasks),
        "tasks": tasks
    }


def get_hil_task_for_workspace(task_id: str) -> Dict[str, Any]:
    """获取指定 workspace 的 HIL 任务（如果有）"""
    for hil_id, task in HIL_TASKS.items():
        if task["task_id"] == task_id and task["status"] == "waiting":
            return {
                "found": True,
                "hil_id": hil_id,
                "instruction": task["instruction"],
                "task_id": task["task_id"]
            }
    
    return {
        "found": False
    }


# ========== 工具确认相关函数 ==========

def create_tool_confirmation(confirm_id: str, task_id: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """创建工具确认请求"""
    TOOL_CONFIRMATIONS[confirm_id] = {
        "status": "waiting",
        "task_id": task_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "result": None  # "approved" or "rejected"
    }

    try:
        get_event_emitter().emit({
            "type": "tool_confirmation",
            "confirm_id": confirm_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "task_id": task_id,
        })
    except Exception:
        pass
    
    return {
        "success": True,
        "message": f"Tool confirmation created: {confirm_id}"
    }


def get_tool_confirmation_status(confirm_id: str) -> Dict[str, Any]:
    """获取工具确认状态"""
    confirmation = TOOL_CONFIRMATIONS.get(confirm_id)
    if not confirmation:
        return {
            "found": False,
            "error": f"Tool confirmation not found: {confirm_id}"
        }
    
    return {
        "found": True,
        "confirm_id": confirm_id,
        "status": confirmation["status"],
        "tool_name": confirmation["tool_name"],
        "arguments": confirmation["arguments"],
        "task_id": confirmation["task_id"],
        "result": confirmation.get("result")
    }


def respond_tool_confirmation(confirm_id: str, approved: bool) -> Dict[str, Any]:
    """响应工具确认请求"""
    confirmation = TOOL_CONFIRMATIONS.get(confirm_id)
    if not confirmation:
        return {
            "success": False,
            "error": f"Tool confirmation not found: {confirm_id}"
        }
    
    # 标记为完成
    TOOL_CONFIRMATIONS[confirm_id]["status"] = "completed"
    TOOL_CONFIRMATIONS[confirm_id]["result"] = "approved" if approved else "rejected"
    
    return {
        "success": True,
        "message": f"Tool confirmation {confirm_id}: {'approved' if approved else 'rejected'}"
    }


def get_tool_confirmation_for_workspace(task_id: str) -> Dict[str, Any]:
    """获取指定 workspace 的工具确认请求（如果有）"""
    for confirm_id, confirmation in TOOL_CONFIRMATIONS.items():
        if confirmation["task_id"] == task_id and confirmation["status"] == "waiting":
            return {
                "found": True,
                "confirm_id": confirm_id,
                "tool_name": confirmation["tool_name"],
                "arguments": confirmation["arguments"],
                "task_id": confirmation["task_id"]
            }
    
    return {
        "found": False
    }


def list_tool_confirmations() -> Dict[str, Any]:
    """列出所有工具确认请求"""
    confirmations = []
    for confirm_id, confirmation in TOOL_CONFIRMATIONS.items():
        confirmations.append({
            "confirm_id": confirm_id,
            "status": confirmation["status"],
            "tool_name": confirmation["tool_name"],
            "task_id": confirmation["task_id"]
        })
    
    return {
        "total": len(confirmations),
        "confirmations": confirmations
    }

