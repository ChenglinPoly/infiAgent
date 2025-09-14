import logging
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

# 获取项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 全局日志记录器
_main_logger = None
_detail_logger = None

def _setup_loggers() -> tuple[logging.Logger, logging.Logger]:
    """设置主日志和详细日志记录器。"""
    global _main_logger, _detail_logger
    
    if _main_logger is not None and _detail_logger is not None:
        return _main_logger, _detail_logger
    
    # 确保 logs 目录存在
    logs_dir = os.path.join(project_root, 'logs')
    details_dir = os.path.join(logs_dir, 'agent_details')
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(details_dir, exist_ok=True)
    
    # 创建日志文件名（按日期）
    date_str = datetime.now().strftime("%Y%m%d")
    main_log_file = os.path.join(logs_dir, f"agents_{date_str}.log")
    detail_log_file = os.path.join(details_dir, f"agents_detail_{date_str}.log")
    
    # 创建主日志记录器（简洁版）
    _main_logger = logging.getLogger("AgentSystem.Main")
    _main_logger.setLevel(logging.INFO)
    if _main_logger.handlers:
        _main_logger.handlers.clear()
    
    main_handler = logging.FileHandler(main_log_file, encoding='utf-8')
    main_handler.setLevel(logging.INFO)
    main_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    main_handler.setFormatter(main_formatter)
    _main_logger.addHandler(main_handler)
    
    # 创建详细日志记录器（完整版）
    _detail_logger = logging.getLogger("AgentSystem.Detail")
    _detail_logger.setLevel(logging.DEBUG)
    if _detail_logger.handlers:
        _detail_logger.handlers.clear()
    
    detail_handler = logging.FileHandler(detail_log_file, encoding='utf-8')
    detail_handler.setLevel(logging.DEBUG)
    detail_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    detail_handler.setFormatter(detail_formatter)
    _detail_logger.addHandler(detail_handler)
    
    return _main_logger, _detail_logger

def get_loggers() -> tuple[logging.Logger, logging.Logger]:
    """获取主日志和详细日志记录器实例。"""
    return _setup_loggers()

class AgentLogger:
    """Agent专用的日志记录器，支持分级日志记录。"""
    
    def __init__(self, agent_name: str, task_id: str):
        self.agent_name = agent_name
        self.task_id = task_id
        self.main_logger, self.detail_logger = get_loggers()
    
    def start(self, original_instruction: str, additional_info: Optional[Dict[str, Any]] = None):
        """记录 Agent 启动信息。"""
        # 主日志：简洁信息
        self.main_logger.info(f"🚀 [{self.agent_name}] 启动任务 - ID: {self.task_id}")
        self.main_logger.info(f"📝 [{self.agent_name}] 任务: {original_instruction[:100]}{'...' if len(original_instruction) > 100 else ''}")
        
        # 详细日志：完整信息
        self.detail_logger.info("=" * 100)
        self.detail_logger.info(f"AGENT START - {self.agent_name.upper()}")
        self.detail_logger.info("=" * 100)
        self.detail_logger.info(f"Agent名称: {self.agent_name}")
        self.detail_logger.info(f"任务ID: {self.task_id}")
        self.detail_logger.info(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.detail_logger.info(f"完整指令: {original_instruction}")
        
        if additional_info:
            self.detail_logger.info("附加信息:")
            for key, value in additional_info.items():
                if isinstance(value, (dict, list)):
                    self.detail_logger.info(f"  {key}: {json.dumps(value, ensure_ascii=False, indent=2)}")
                else:
                    self.detail_logger.info(f"  {key}: {value}")
        self.detail_logger.info("-" * 100)
    
    def end(self, result: Dict[str, Any], end_reason: str = "completed"):
        """记录 Agent 结束信息。"""
        status = result.get("status", "unknown")
        output_preview = result.get("output", "")[:100]
        if len(result.get("output", "")) > 100:
            output_preview += "..."
        
        # 主日志：简洁信息
        self.main_logger.info(f"✅ [{self.agent_name}] 任务完成 - 状态: {status.upper()}")
        self.main_logger.info(f"📄 [{self.agent_name}] 结果: {output_preview}")
        
        # 详细日志：完整信息
        self.detail_logger.info("=" * 100)
        self.detail_logger.info(f"AGENT END - {self.agent_name.upper()}")
        self.detail_logger.info("=" * 100)
        self.detail_logger.info(f"Agent名称: {self.agent_name}")
        self.detail_logger.info(f"任务ID: {self.task_id}")
        self.detail_logger.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.detail_logger.info(f"结束原因: {end_reason}")
        self.detail_logger.info(f"完整结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        self.detail_logger.info("=" * 100)
    
    def turn_start(self, turn_num: int, max_turns: int):
        """记录轮次开始。"""
        # 主日志：简洁信息
        self.main_logger.info(f"🔄 [{self.agent_name}] 第 {turn_num}/{max_turns} 轮")
        
        # 详细日志：完整信息
        self.detail_logger.info("=" * 80)
        self.detail_logger.info(f"[{self.agent_name}] 第 {turn_num}/{max_turns} 轮处理开始 - 任务: {self.task_id}")
        self.detail_logger.info("=" * 80)
    
    def llm_request(self, model: str, system_prompt: str, user_input: str, available_tools: list):
        """记录 LLM 请求。"""
        # 主日志：简洁信息
        self.main_logger.info(f"🤖 [{self.agent_name}] LLM请求 - 模型: {model}")
        
        # 详细日志：完整信息
        self.detail_logger.info(f"[{self.agent_name}] LLM请求 - 任务: {self.task_id}")
        self.detail_logger.info(f"[{self.agent_name}] 使用模型: {model}")
        self.detail_logger.info(f"[{self.agent_name}] 系统提示: {system_prompt}")
        self.detail_logger.info(f"[{self.agent_name}] 用户输入: {user_input}")
        self.detail_logger.info(f"[{self.agent_name}] 可用工具: {available_tools}")
    
    def llm_response(self, response_data: Dict[str, Any]):
        """记录 LLM 响应。"""
        status = response_data.get("status", "unknown")
        finish_reason = response_data.get("finish_reason", "unknown")
        has_tools = bool(response_data.get("tool_calls"))
        
        # 主日志：简洁信息
        if has_tools:
            tool_names = [call.name for call in response_data.get("tool_calls", [])]
            self.main_logger.info(f"🔧 [{self.agent_name}] LLM响应 - 工具调用: {tool_names}")
        else:
            self.main_logger.info(f"💬 [{self.agent_name}] LLM响应 - 状态: {status}")
        
        # 详细日志：完整信息
        self.detail_logger.info(f"[{self.agent_name}] LLM响应 - 任务: {self.task_id}")
        self.detail_logger.info(f"[{self.agent_name}] 响应状态: {status}")
        self.detail_logger.info(f"[{self.agent_name}] 使用模型: {response_data.get('model', 'unknown')}")
        self.detail_logger.info(f"[{self.agent_name}] 完成原因: {finish_reason}")
        if response_data.get("output"):
            self.detail_logger.info(f"[{self.agent_name}] 响应内容: {response_data['output']}")
        if response_data.get("tool_calls"):
            self.detail_logger.info(f"[{self.agent_name}] 工具调用: {[call.name for call in response_data['tool_calls']]}")
    
    def tool_execution(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any]):
        """记录工具执行。"""
        status = result.get("status", "unknown")
        
        # 主日志：简洁信息
        self.main_logger.info(f"⚙️ [{self.agent_name}] 工具 '{tool_name}' - 状态: {status}")
        
        # 详细日志：完整信息
        self.detail_logger.info(f"[{self.agent_name}] 工具执行 - 任务: {self.task_id}")
        self.detail_logger.info(f"[{self.agent_name}] 工具名称: {tool_name}")
        self.detail_logger.info(f"[{self.agent_name}] 工具参数: {json.dumps(arguments, ensure_ascii=False, indent=2)}")
        self.detail_logger.info(f"[{self.agent_name}] 执行状态: {status}")
        self.detail_logger.info(f"[{self.agent_name}] 工具结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    
    def tool_error(self, tool_name: str, error_msg: str):
        """记录工具错误。"""
        # 主日志：简洁信息
        self.main_logger.warning(f"⚠️ [{self.agent_name}] 工具 '{tool_name}' 错误: {error_msg[:50]}{'...' if len(error_msg) > 50 else ''}")
        
        # 详细日志：完整信息
        self.detail_logger.error(f"[{self.agent_name}] 工具错误 - 任务: {self.task_id}")
        self.detail_logger.error(f"[{self.agent_name}] 工具名称: {tool_name}")
        self.detail_logger.error(f"[{self.agent_name}] 错误信息: {error_msg}")
    
    def thinking(self, content: str):
        """记录思考过程。"""
        # 主日志：简洁信息
        self.main_logger.info(f"💭 [{self.agent_name}] 正在思考...")
        
        # 详细日志：完整信息
        self.detail_logger.info(f"[{self.agent_name}] 思考过程 - 任务: {self.task_id}")
        self.detail_logger.info(f"[{self.agent_name}] 思考内容: {content}")
    
    def decision(self, decision_type: str, content: str):
        """记录决策。"""
        # 主日志：简洁信息
        self.main_logger.info(f"⚖️ [{self.agent_name}] 决策: {decision_type.upper()}")
        
        # 详细日志：完整信息
        self.detail_logger.info(f"[{self.agent_name}] 最终决策 - 任务: {self.task_id}")
        self.detail_logger.info(f"[{self.agent_name}] 决策类型: {decision_type}")
        self.detail_logger.info(f"[{self.agent_name}] 决策内容: {content}")
    
    def info(self, message: str):
        """记录一般信息。"""
        # 主日志：简洁信息
        self.main_logger.info(f"ℹ️ [{self.agent_name}] {message[:100]}{'...' if len(message) > 100 else ''}")
        
        # 详细日志：完整信息
        self.detail_logger.info(f"[{self.agent_name}] {message} - 任务: {self.task_id}")
    
    def warning(self, message: str):
        """记录警告。"""
        # 主日志和详细日志都记录警告
        self.main_logger.warning(f"⚠️ [{self.agent_name}] {message}")
        self.detail_logger.warning(f"[{self.agent_name}] {message} - 任务: {self.task_id}")
    
    def error(self, error_type: str, message: str):
        """记录错误。"""
        # 主日志和详细日志都记录错误
        self.main_logger.error(f"❌ [{self.agent_name}] {error_type}: {message}")
        self.detail_logger.error(f"[{self.agent_name}] 错误类型: {error_type} - 任务: {self.task_id}")
        self.detail_logger.error(f"[{self.agent_name}] 错误信息: {message}")

# 保持向后兼容的函数
def get_logger() -> logging.Logger:
    """获取主日志记录器实例（向后兼容）。"""
    main_logger, _ = get_loggers()
    return main_logger

def log_agent_start(agent_name: str, task_id: str, original_instruction: str, 
                   additional_info: Optional[Dict[str, Any]] = None):
    """记录 Agent 启动信息（向后兼容）。"""
    agent_logger = AgentLogger(agent_name, task_id)
    agent_logger.start(original_instruction, additional_info)

def log_agent_end(agent_name: str, task_id: str, result: Dict[str, Any], 
                 end_reason: str = "completed"):
    """记录 Agent 结束信息（向后兼容）。"""
    agent_logger = AgentLogger(agent_name, task_id)
    agent_logger.end(result, end_reason) 