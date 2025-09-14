import requests
import yaml
import os
import json
from typing import Dict, Any

# 尝试导入chardet，如果没有安装则使用备用方案
try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False
    print("注意：未安装chardet库，将使用基础编码检测。建议安装: pip install chardet")

_BASE_URL = None
_TASK_CACHE = {}

def _detect_encoding(content: bytes) -> str:
    """检测文本内容的编码格式"""
    if HAS_CHARDET:
        try:
            result = chardet.detect(content)
            encoding = result.get('encoding', 'utf-8')
            confidence = result.get('confidence', 0)
            
            # 如果置信度太低，使用常见的中文编码尝试
            if confidence < 0.7:
                for enc in ['gbk', 'gb2312', 'utf-8', 'latin1']:
                    try:
                        content.decode(enc)
                        return enc
                    except:
                        continue
            return encoding
        except:
            pass
    
    # 备用方案：尝试常见编码
    for encoding in ['utf-8', 'gbk', 'gb2312', 'big5', 'latin1']:
        try:
            content.decode(encoding)
            return encoding
        except:
            continue
    
    return 'utf-8'

def _safe_decode_text(content: bytes) -> str:
    """安全解码文本内容，支持多种编码格式"""
    if isinstance(content, str):
        return content
    
    # 首先尝试UTF-8
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        pass
    
    # 使用编码检测
    encoding = _detect_encoding(content)
    try:
        return content.decode(encoding)
    except:
        pass
    
    # 尝试常见的中文编码
    for encoding in ['gbk', 'gb2312', 'big5', 'latin1']:
        try:
            return content.decode(encoding)
        except:
            continue
    
    # 最后使用错误处理模式
    return content.decode('utf-8', errors='ignore')

def _load_config():
    """从环境变量或配置文件加载工具服务器的URL。"""
    global _BASE_URL
    # 优先从环境变量获取
    _BASE_URL = os.environ.get('TOOL_SERVER_URL')
    if _BASE_URL:
        return
    # 获取项目根目录并构建新的配置文件路径
    current_dir = os.path.dirname(__file__)
    project_root = os.path.dirname(current_dir)
    config_path = os.path.join(project_root, 'config', 'run_env_config', 'tool_config.yaml')
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
    # 确保URL末尾没有斜杠，避免双斜杠问题
    return _BASE_URL.rstrip('/') if _BASE_URL else None

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
        # 确保请求使用UTF-8编码
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json; charset=utf-8'
        }
        
        print(f"🔧 调用工具服务器: {execute_url}")
        print(f"🔧 工具: {tool_name}, 任务: {task_id}")
        
        response = requests.post(
            execute_url, 
            json=payload, 
            headers=headers,
            timeout=1000000
        )
        response.raise_for_status()
        
        # 处理响应编码
        if response.content:
            try:
                # 尝试直接解析JSON
                tool_server_response = response.json()
            except json.JSONDecodeError:
                # 如果JSON解析失败，尝试编码检测
                decoded_content = _safe_decode_text(response.content)
                tool_server_response = json.loads(decoded_content)
        else:
            tool_server_response = {}

        if tool_server_response.get("success"):
            # 确保输出内容的中文正确显示
            output_data = tool_server_response.get("data", {})
            return {
                "status": "success",
                "output": json.dumps(output_data, indent=2, ensure_ascii=False),
                "error_information": ""
            }
        else:
            error_msg = tool_server_response.get("error", "工具服务器返回未知错误。")
            # 如果错误信息中包含编码错误，提供更友好的提示
            if "codec can't decode" in str(error_msg):
                error_msg = f"文件编码错误：{error_msg}。建议检查文件是否为中文编码（如GBK）格式。"
            
            return {
                "status": "error",
                "output": "",
                "error_information": error_msg
            }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "output": "",
            "error_information": f"调用工具服务器失败: {e}"
        }
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "output": "",
            "error_information": f"解析工具服务器响应失败，不是有效的JSON: {e}"
        }
    except Exception as e:
        return {
            "status": "error",
            "output": "",
            "error_information": f"执行工具时发生未知错误: {e}"
        } 