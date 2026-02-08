#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MLA V3 启动脚本
使用新的XML结构化上下文系统
"""

import sys
import argparse
from pathlib import Path
import os
from datetime import datetime

# Windows控制台UTF-8编码支持（解决emoji显示问题）
if sys.platform == 'win32':
    try:
        # 设置控制台代码页为UTF-8
        import codecs
        # 使用line buffering确保每行立即输出
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
        # 强制无缓冲模式
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True, write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True, write_through=True)
    except Exception:
        pass

# 首次导入时检查PATH配置（仅在非导入模式下）
if __name__ == "__main__" and not hasattr(sys, '_mla_path_checked'):
    sys._mla_path_checked = True
    try:
        import site
        # 获取用户级 Scripts 目录
        if sys.platform == 'win32':
            user_base = site.USER_BASE
            if user_base:
                scripts_dir = os.path.join(user_base, 'Scripts')
            else:
                scripts_dir = None
        else:
            user_base = site.USER_BASE
            if user_base:
                scripts_dir = os.path.join(user_base, 'bin')
            else:
                scripts_dir = None
        
        if scripts_dir and os.path.exists(scripts_dir):
            # 检查是否在 PATH 中
            path_env = os.environ.get('PATH', '')
            path_dirs = path_env.split(os.pathsep)
            scripts_dir_normalized = os.path.normpath(scripts_dir).lower()
            in_path = any(os.path.normpath(p).lower() == scripts_dir_normalized for p in path_dirs)
            
            if not in_path:
                print("\n" + "="*80, file=sys.stderr)
                print("[提示] 要直接使用 'mla-agent' 命令，请运行: python check_path.py", file=sys.stderr)
                print("="*80 + "\n", file=sys.stderr)
    except Exception:
        pass

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.config_loader import ConfigLoader
from core.hierarchy_manager import get_hierarchy_manager
from core.agent_executor import AgentExecutor


def main():
    """主函数"""
    import time
    import uuid
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='MLA V3 - Multi-Level Agent System')
    
    # 子命令
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # respond 子命令（HIL 响应）
    respond_parser = subparsers.add_parser('respond', help='响应 HIL 任务')
    respond_parser.add_argument('hil_id', type=str, help='HIL 任务 ID')
    respond_parser.add_argument('response', type=str, help='用户响应内容（可以是任何文本）')
    # 主命令参数
    parser.add_argument('--task_id', type=str, help='任务ID（绝对路径，作为workspace）')
    parser.add_argument('--agent_system', type=str, default='Default', help='Agent系统名称')
    #parser.add_argument('--agent_system', type=str, default='Test_agent', help='Agent系统名称')
    parser.add_argument('--agent_name', type=str, default='alpha_agent', help='启动的Agent名称')
    parser.add_argument('--user_input', type=str, help='用户输入/任务描述')
    parser.add_argument('--jsonl', action='store_true', help='启用 JSONL 事件输出模式（用于 VS Code 插件集成）')
    parser.add_argument('--cli', action='store_true', help='启动交互式 CLI 模式')
    parser.add_argument('--test', action='store_true', help='运行默认测试任务')
    parser.add_argument('--config-show', action='store_true', help='显示当前配置')
    parser.add_argument('--config-set', nargs=2, metavar=('KEY', 'VALUE'), help='设置配置项（如 api_key "YOUR_KEY"）')
    parser.add_argument('--config-file', type=str, help='使用自定义配置文件路径')
    parser.add_argument('--force-new', action='store_true', help='强制清空所有状态，开始新任务')
    parser.add_argument('--auto-mode', type=str, choices=['true', 'false'], help='工具执行模式：true=自动执行，false=需要确认')
    parser.add_argument('--direct-tools', action='store_true', help='使用进程内直接调用工具（不依赖 ToolServer HTTP 服务）')
    
    args = parser.parse_args()
    
    # Windows命令行参数编码修复
    if sys.platform == 'win32' and args.user_input:
        try:
            # 尝试修复Windows命令行的编码问题
            # 场景：Windows cmd/PowerShell 可能将 UTF-8 字符错误解析为 Latin-1
            original = args.user_input
            fixed = args.user_input.encode('latin-1').decode('utf-8')
            # 只在修复后看起来更合理时才应用（避免破坏正常输入）
            if fixed != original:
                args.user_input = fixed
        except (UnicodeDecodeError, UnicodeEncodeError, AttributeError) as e:
            # 如果修复失败，保持原样（不影响正常使用）
            # 可选：记录日志用于调试
            # print(f"[调试] 编码修复失败: {e}", file=sys.stderr)
            pass
    
    # 处理 respond 命令
    if args.command == 'respond':
        import requests
        import yaml
        
        # 读取工具服务器地址
        config_path = Path(__file__).parent / "config" / "run_env_config" / "tool_config.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            tool_config = yaml.safe_load(f)
        server_url = tool_config.get('tools_server', 'http://127.0.0.1:8001').rstrip('/')
        
        # 调用 HIL 响应 API
        try:
            response = requests.post(
                f"{server_url}/api/hil/respond/{args.hil_id}",
                json={"response": args.response},
                timeout=5
            )
            result = response.json()
            
            if result.get('success'):
                print(f"✅ HIL 任务已响应: {args.hil_id}")
                print(f"   内容: {args.response}")
                return 0
            else:
                print(f"❌ 响应失败: {result.get('error', 'Unknown error')}")
                return 1 
        except Exception as e:
            print(f"❌ 连接工具服务器失败: {e}")
            return 1
    
    # 处理 CLI 模式
    if args.cli:
        from utils.cli_mode import start_cli_mode
        # 不传入 agent_system，让用户在 CLI 中选择
        start_cli_mode()
        return 0
    
    # 处理配置命令（优先）
    if args.config_show:
        from utils.config_manager import show_config
        show_config()
        return 0
    
    if args.config_set:
        from utils.config_manager import set_config
        set_config(args.config_set[0], args.config_set[1])
        return 0
    
    # 初始化事件发射器
    from utils.event_emitter import init_event_emitter
    emitter = init_event_emitter(enabled=args.jsonl)
    
    # JSONL 模式：将所有 print 重定向到 stderr
    if args.jsonl:
        sys.stdout_orig = sys.stdout
        sys.stderr_orig = sys.stderr
        # 所有 print 输出到 stderr
        sys.stdout = sys.stderr
    
    # 如果没有提供参数或指定了--test，使用默认测试
    if args.test or (not args.task_id and not args.user_input):
        if not args.jsonl:
            print("🧪 使用默认测试模式")
        # 跨平台默认task_id：使用用户主目录下的测试目录
        default_task_dir = Path.home() / "mla_v3" / "task_test"
        default_task_dir.mkdir(parents=True, exist_ok=True)
        args.task_id = args.task_id or str(default_task_dir)
        args.user_input = args.user_input or "刚才完成了什么任务？"
    
    # 检查必需参数
    if not args.task_id or not args.user_input:
        parser.error("需要提供 --task_id 和 --user_input，或使用 --test 运行默认测试")
        return 1
    
    # 生成 call_id
    call_id = f"c-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    t0 = time.time()
    
    # 发送开始事件
    if args.jsonl:
        emitter.start(call_id, args.task_id, args.agent_name, args.user_input)
    else:
        print("\n" + "="*100)
        print("🚀 MLA V3 - Multi-Level Agent System")
        print("="*100)
        print(f"📋 任务ID: {args.task_id}")
        print(f"🎛️  Agent系统: {args.agent_system}")
        print(f"🤖 启动Agent: {args.agent_name}")
        print(f"📝 用户输入: {args.user_input}")
        print("="*100 + "\n")
    
    try:
        # 初始化配置加载器
        if args.jsonl:
            emitter.token("加载配置...")
        else:
            print("📦 加载配置...")
        
        config_loader = ConfigLoader(args.agent_system)
        
        if args.jsonl:
            emitter.token(f"配置加载成功，共 {len(config_loader.all_tools)} 个工具/Agent")
            emitter.progress("init", 10)
        else:
            print(f"✅ 配置加载成功，共 {len(config_loader.all_tools)} 个工具/Agent")
        
        # 初始化层级管理器
        if not args.jsonl:
            print("\n📊 初始化层级管理器...")
        hierarchy_manager = get_hierarchy_manager(args.task_id)
        if not args.jsonl:
            print("✅ 层级管理器初始化成功")
        
        # 启动前清理状态
        if not args.jsonl:
            print("\n🧹 检查并清理状态...")

        # 重要：必须先清理，再注册本次用户指令
        # 否则 clean_before_start() 会把“刚写入的本次指令”误判为 last_input，导致 is_same_task 恒为 True，
        # 进而不会按“新任务”清空栈，留下上一轮中断的栈条目，造成任务结束后 stack 仍不为空。
        if args.force_new:
            if not args.jsonl:
                print("🗑️  --force-new: 清空所有状态，开始新任务")
            context = hierarchy_manager._load_context()
            context["current"] = {
                "instructions": [],
                "hierarchy": {},
                "agents_status": {},
                "start_time": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
            # 保留全局 history/agent_time_history 等其他字段不动
            hierarchy_manager._save_context(context)
            hierarchy_manager._save_stack([])
        else:
            from core.state_cleaner import clean_before_start
            clean_before_start(args.task_id, args.user_input)

        # 注册用户指令（清理后写入）
        if not args.jsonl:
            print(f"\n📝 注册用户指令...")
        instruction_id = hierarchy_manager.start_new_instruction(args.user_input)
        if not args.jsonl:
            print(f"✅ 指令已注册: {instruction_id}")
        
        # 获取Agent配置
        if not args.jsonl:
            print(f"\n🔍 查找Agent配置: {args.agent_name}")
        agent_config = config_loader.get_tool_config(args.agent_name)
        
        if agent_config.get("type") != "llm_call_agent":
            error_msg = f"❌ 错误: {args.agent_name} 不是一个LLM Agent"
            if args.jsonl:
                emitter.error(error_msg)
            else:
                print(error_msg)
            return
        
        if not args.jsonl:
            print(f"✅ Agent配置加载成功")
            print(f"   - Level: {agent_config.get('level', 'unknown')}")
            print(f"   - Model: {agent_config.get('model_type', 'unknown')}")
            print(f"   - Tools: {len(agent_config.get('available_tools', []))}")
            
            # 创建并运行Agent
            print(f"\n{'='*100}")
            print("▶️  开始执行任务")
            print(f"{'='*100}\n")
        
        
        
        agent = AgentExecutor(
            agent_name=args.agent_name,
            agent_config=agent_config,
            config_loader=config_loader,
            hierarchy_manager=hierarchy_manager,
            direct_tools=getattr(args, 'direct_tools', False)
        )
        
        # 设置工具执行权限模式
        if args.auto_mode is not None:
            auto_mode = args.auto_mode == 'true'
            agent.tool_executor.set_task_permission(args.task_id, auto_mode)
        
        result = agent.run(args.task_id, args.user_input)
        
        # 输出结果
        if args.jsonl:
            # JSONL 模式 - 发送 result 和 end 事件（完整输出）
            ok = result.get('status') == 'success'
            summary = result.get('output', '')  # 不截断
            emitter.result(ok, summary)
            emitter.end("ok" if ok else "error")
        else:
            # 普通模式
            print(f"\n{'='*100}")
            print("📊 执行结果")
            print(f"{'='*100}")
            print(f"状态: {result.get('status', 'unknown')}")
            print(f"输出: {result.get('output', 'N/A')}")
            if result.get('error_information'):
                print(f"错误信息: {result.get('error_information')}")
            print(f"{'='*100}\n")
        
        # 返回状态码
        if result.get('status') == 'success':
            return 0
        else:
            return 1
    
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断执行")
        return 130
    
    except Exception as e:
        if args.jsonl:
            emitter.error(str(e))
            emitter.end("error")
        else:
            print(f"\n\n❌ 执行失败: {e}")
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

