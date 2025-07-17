import requests
import yaml
import os
import json
from typing import Dict, Any

_BASE_URL = None
_TASK_CACHE = {}

def _load_config():
    """从配置文件加载工具服务器的URL。"""
    global _BASE_URL
    config_path = os.path.join(os.path.dirname(__file__), 'tool_config.yaml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            _BASE_URL = config.get('tools_server')
        if not _BASE_URL:
            raise ValueError("在 tool_config.yaml 中未找到 'tools_server' 配置项")
    except FileNotFoundError:
        print(f"错误: 配置文件未找到于 {config_path}")
        _BASE_URL = "http://localhost:8001"  # 提供一个默认的备用地址
    except Exception as e:
        print(f"加载配置时出错: {e}")
        _BASE_URL = "http://localhost:8001"  # 提供一个默认的备用地址

def _get_base_url():
    """获取工具服务器的基础URL。"""
    if _BASE_URL is None:
        _load_config()
    return _BASE_URL

def _ensure_task_exists(task_id: str):
    """检查任务是否存在，如果不存在则创建它。"""
    if task_id in _TASK_CACHE:
        return

    base_url = _get_base_url()
    try:
        status_url = f"{base_url}/api/task/{task_id}/status"
        response = requests.get(status_url, timeout=5)
        if response.status_code == 200:
            _TASK_CACHE[task_id] = True
            return
        
        create_url = f"{base_url}/api/task/create"
        params = {"task_id": task_id, "task_name": f"AutoGen-{task_id}"}
        create_response = requests.post(create_url, params=params, timeout=10)
        
        if create_response.status_code == 200 and create_response.json().get('success'):
            print(f"任务 '{task_id}' 已成功创建。")
            _TASK_CACHE[task_id] = True
        else:
            print(f"警告: 创建或验证任务 '{task_id}' 失败。 服务器响应: {create_response.text}")
    except requests.exceptions.RequestException as e:
        print(f"检查/创建任务 '{task_id}' 时出错: {e}")

def execute_tool(tool_name: str, params: Dict[str, Any], task_id: str = "default_agent_task") -> Dict:
    """
    在工具服务器上执行一个工具，并以标准格式返回结果。
    在执行前确保任务存在。
    """
    base_url = _get_base_url()
    if not base_url:
        return {
            "status": "error",
            "output": "",
            "error_information": "工具服务器URL未配置。"
        }

    _ensure_task_exists(task_id)
    
    execute_url = f"{base_url}/api/tool/execute"
    
    payload = {
        "task_id": task_id,
        "tool_name": tool_name,
        "params": params
    }
    
    try:
        response = requests.post(execute_url, json=payload, timeout=120)
        response.raise_for_status()
        tool_server_response = response.json()

        if tool_server_response.get("success"):
            return {
                "status": "success",
                "output": json.dumps(tool_server_response.get("data", {}), indent=2, ensure_ascii=False),
                "error_information": ""
            }
        else:
            return {
                "status": "error",
                "output": "",
                "error_information": tool_server_response.get("error", "工具服务器返回未知错误。")
            }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "output": "",
            "error_information": f"调用工具服务器失败: {e}"
        }
    except json.JSONDecodeError:
        return {
            "status": "error",
            "output": "",
            "error_information": "解析工具服务器响应失败，不是有效的JSON。"
        } 