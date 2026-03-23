#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码执行工具
"""

from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import subprocess
import sys
import re
import time
import os
import shlex
import uuid
from datetime import datetime
from .file_tools import BaseTool, get_abs_path

#def _create_venv(self, venv_path: Path) -> Tuple[bool, str]:重复两遍要记得同时维护。
#为了美观，def _create_venv还是重复写两次吧，这样一个一个类比较独立。

# 全局后台进程注册表
# 格式: {process_id: {task_id, pid, command, output_file, start_time, process_obj}}
BACKGROUND_PROCESSES = {}
TERMINAL_SESSION_WINDOW_ID = None
TERMINAL_SESSION_TAB_PREFIX = "infiAgent-exec"
TERMINAL_SESSION_TAB_TITLE = f"{TERMINAL_SESSION_TAB_PREFIX}-{uuid.uuid4().hex[:6]}"
TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH = False


def has_running_background_processes(task_id: str = None) -> bool:
    """检查是否存在仍在运行的后台进程。"""
    stale = []
    for proc_id, info in BACKGROUND_PROCESSES.items():
        process = info.get("process_obj")
        if info.get("mode") == "system_terminal":
            exit_file = info.get("exit_file")
            running = not (exit_file and Path(exit_file).exists())
        else:
            running = bool(process and process.poll() is None)

        if not running:
            stale.append(proc_id)
            continue

        if task_id is None or str(info.get("task_id")) == str(task_id):
            return True

    for proc_id in stale:
        BACKGROUND_PROCESSES.pop(proc_id, None)
    return False


class ExecuteCodeTool(BaseTool):
    """代码执行工具（支持虚拟环境）"""
    
    def _create_venv(self, venv_path: Path) -> Tuple[bool, str]:
        """
        创建虚拟环境（兼容 Anaconda 和标准 Python）
        
        策略：
        1. 优先尝试标准 venv（CPython）
        2. 失败时尝试 virtualenv（兼容 Anaconda）
        
        Returns:
            (是否成功创建, 错误信息)
        """
        import os
        venv_path.parent.mkdir(parents=True, exist_ok=True)
        
        #print(f"[DEBUG] 开始创建虚拟环境: {venv_path}")
        #print(f"[DEBUG] Python 解释器: {sys.executable}")
        
        def _run_cmd(cmd):
            """运行命令并返回 (成功?, 错误信息)"""
            # 设置环境变量，确保编码正确初始化
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUTF8", "1")
            
            # Windows 下不使用 close_fds，避免标准句柄问题
            close_fds = (sys.platform != "win32")
            
            res = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=300,  # 增加超时时间
                env=env,
                close_fds=close_fds
            )
            ok = (res.returncode == 0)
            err = (res.stderr or "") if res.stderr else (res.stdout or "")
            return ok, err
        
        # 方法 1: 标准 venv
        venv_cmd = [sys.executable, "-m", "venv", str(venv_path)]
        print(f"[DEBUG] 方法1 - 尝试标准 venv: {' '.join(venv_cmd)}")
        ok, err1 = _run_cmd(venv_cmd)
        print(f"[DEBUG] venv 结果: {'成功' if ok else '失败 - ' + err1[:100]}")
        if ok:
            return True, ""
        
        # 方法 2: virtualenv
        virtualenv_cmd = [sys.executable, "-m", "virtualenv", str(venv_path)]
        print(f"[DEBUG] 方法2 - 尝试 virtualenv: {' '.join(virtualenv_cmd)}")
        ok, err2 = _run_cmd(virtualenv_cmd)
        print(f"[DEBUG] virtualenv 结果: {'成功' if ok else '失败 - ' + err2[:100]}")
        if ok:
            return True, ""
        
        # 都失败
        print(f"[DEBUG] ❌ 两种方法都失败")
        return False, f"venv: {err1[:400]} | virtualenv: {err2[:400]}"
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 Python 代码
        
        Parameters:
            code (str, optional): 代码内容
            file_path (str, optional): 代码文件相对路径
            working_dir (str, optional): 执行目录相对路径，默认为code_run目录
            use_venv (bool, optional): 是否使用虚拟环境，默认True
            timeout (int, optional): 超时时间（秒），默认30，后台执行时忽略
            background (bool, optional): 是否后台执行（不阻塞），默认False
            output_file (str, optional): 输出重定向到文件（相对路径），后台执行时必需
        """
        try:
            code = parameters.get("code")
            file_path = parameters.get("file_path")
            working_dir = parameters.get("working_dir", "code_run")
            use_venv = parameters.get("use_venv", True)
            timeout = parameters.get("timeout", 30)
            background = parameters.get("background", False)
            output_file = parameters.get("output_file")
            
            # 后台执行时必须指定输出文件
            if background and not output_file:
                return {
                    "status": "error",
                    "output": "",
                    "error": "output_file is required when background=True"
                }
            
            workspace = Path(task_id)
            exec_dir = get_abs_path(task_id, working_dir)
            
            # 准备代码文件
            if code:
                # 创建临时文件
                code_dir = workspace / "code_run"
                code_dir.mkdir(parents=True, exist_ok=True)
                temp_file = code_dir / "temp_code.py"
                
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write(code)
                
                exec_file = temp_file
            elif file_path:
                exec_file = get_abs_path(task_id, file_path)
                if not exec_file.exists():
                    return {
                        "status": "error",
                        "output": "",
                        "error": f"Code file not found: {file_path}"
                    }
            else:
                return {
                    "status": "error",
                    "output": "",
                    "error": "Either 'code' or 'file_path' must be provided"
                }
            
            # 执行 Python 代码
            if background:
                # 后台执行
                output = self._execute_python_background(
                    workspace, exec_file, exec_dir, use_venv, output_file
                )
            else:
                # 直接执行
                output = self._execute_python(
                    workspace, exec_file, exec_dir, use_venv, timeout, output_file
                )
            
            return {
                "status": "success",
                "output": output,
                "error": ""
            }
            
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "output": "",
                "error": f"Execution timeout ({timeout}s)"
            }
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }
    
    def _get_python_exec(self, workspace: Path, use_venv: bool) -> Path:
        """获取 Python 解释器路径"""
        env_dir = workspace / "code_env"
        
        if use_venv:
            venv_path = env_dir / "venv"
            if not venv_path.exists():
                venv_created, error_msg = self._create_venv(venv_path)
                if not venv_created:
                    print(f"⚠️ venv 创建失败，使用系统 Python: {error_msg[:100]}")
                    return Path(sys.executable)
                else:
                    if sys.platform == "win32":
                        return venv_path / "Scripts" / "python.exe"
                    else:
                        return venv_path / "bin" / "python"
            else:
                if sys.platform == "win32":
                    return venv_path / "Scripts" / "python.exe"
                else:
                    return venv_path / "bin" / "python"
        else:
            return Path(sys.executable)
    
    def _execute_python(self, workspace: Path, code_file: Path, exec_dir: Path, use_venv: bool, timeout: int, output_file: str = None) -> str:
        """执行Python代码（直接模式）"""
        python_exec = self._get_python_exec(workspace, use_venv)
        
        # 如果指定了输出文件，重定向输出
        if output_file:
            output_path = get_abs_path(str(workspace), output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as out_f:
                result = subprocess.run(
                    [str(python_exec), str(code_file)],
                    stdout=out_f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=timeout,
                    cwd=str(exec_dir),
                    stdin=subprocess.DEVNULL
                )
            
            output = f"代码执行完成，输出已保存到: {output_file}\n"
            output += f"Exit code: {result.returncode}"
            
            # 读取部分输出用于显示
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    content = f.read(1000)  # 读取前1000字符
                    if len(content) == 1000:
                        output += f"\n\n输出预览（前1000字符）:\n{content}\n..."
                    else:
                        output += f"\n\n完整输出:\n{content}"
            except Exception:
                pass
            
            return output
        else:
            # 不重定向，直接捕获输出
            result = subprocess.run(
                [str(python_exec), str(code_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(exec_dir),
                stdin=subprocess.DEVNULL
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if result.returncode != 0:
                output += f"\nExit code: {result.returncode}"
            
            return output
    
    def _execute_python_background(self, workspace: Path, code_file: Path, exec_dir: Path, use_venv: bool, output_file: str) -> str:
        """执行Python代码（后台模式，不阻塞）"""
        python_exec = self._get_python_exec(workspace, use_venv)
        
        # 输出文件路径
        output_path = get_abs_path(str(workspace), output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 打开输出文件
        out_f = open(output_path, 'w', encoding='utf-8')
        
        # 跨平台后台执行
        if sys.platform == "win32":
            # Windows: 使用 CREATE_NO_WINDOW + DETACHED_PROCESS
            CREATE_NO_WINDOW = 0x08000000
            DETACHED_PROCESS = 0x00000008
            
            process = subprocess.Popen(
                [str(python_exec), str(code_file)],
                stdout=out_f,
                stderr=subprocess.STDOUT,
                cwd=str(exec_dir),
                stdin=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                close_fds=False
            )
        else:
            # Unix/Linux/Mac: 使用 start_new_session
            process = subprocess.Popen(
                [str(python_exec), str(code_file)],
                stdout=out_f,
                stderr=subprocess.STDOUT,
                cwd=str(exec_dir),
                stdin=subprocess.DEVNULL,
                start_new_session=True
            )
        
        # 生成进程ID并注册
        process_id = f"bg_{int(time.time())}_{process.pid}"
        BACKGROUND_PROCESSES[process_id] = {
            "task_id": str(workspace),
            "pid": process.pid,
            "command": str(code_file),
            "output_file": output_file,
            "start_time": datetime.now().isoformat(),
            "process_obj": process
        }
        
        # 不等待进程结束，立即返回
        output = f"✅ 代码已在后台启动\n"
        output += f"   Process ID: {process_id}\n"
        output += f"   PID: {process.pid}\n"
        output += f"   输出文件: {output_file}\n"
        output += f"   提示: 使用 file_read 读取 {output_file} 查看执行结果\n"
        output += f"   管理: 使用 execute_command 运行 `ps`/`kill` 或停止任务以终止进程"
        
        return output
    


class PipInstallTool(BaseTool):
    """pip 包安装工具"""
    
    def _create_venv(self, venv_path: Path) -> Tuple[bool, str]:
        """
        创建虚拟环境（兼容 Anaconda 和标准 Python）
        与 ExecuteCodeTool 使用相同的策略
        
        Returns:
            (是否成功创建, 错误信息)
        """
        import os
        venv_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"[DEBUG] 开始创建虚拟环境: {venv_path}")
        print(f"[DEBUG] Python 解释器: {sys.executable}")
        
        def _run_cmd(cmd):
            """运行命令并返回 (成功?, 错误信息)"""
            # 设置环境变量，确保编码正确初始化
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUTF8", "1")
            
            # Windows 下不使用 close_fds，避免标准句柄问题
            close_fds = (sys.platform != "win32")
            
            res = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=180,  # 增加超时时间
                env=env,
                close_fds=close_fds
            )
            ok = (res.returncode == 0)
            err = (res.stderr or "") if res.stderr else (res.stdout or "")
            return ok, err
        
        # 方法 1: 标准 venv
        venv_cmd = [sys.executable, "-m", "venv", str(venv_path)]
        print(f"[DEBUG] 方法1 - 尝试标准 venv: {' '.join(venv_cmd)}")
        ok, err1 = _run_cmd(venv_cmd)
        print(f"[DEBUG] venv 结果: {'成功' if ok else '失败 - ' + err1[:100]}")
        if ok:
            return True, ""
        
        # 方法 2: virtualenv
        virtualenv_cmd = [sys.executable, "-m", "virtualenv", str(venv_path)]
        print(f"[DEBUG] 方法2 - 尝试 virtualenv: {' '.join(virtualenv_cmd)}")
        ok, err2 = _run_cmd(virtualenv_cmd)
        print(f"[DEBUG] virtualenv 结果: {'成功' if ok else '失败 - ' + err2[:100]}")
        if ok:
            return True, ""
        
        # 都失败
        print(f"[DEBUG] ❌ 两种方法都失败")
        return False, f"venv: {err1[:400]} | virtualenv: {err2[:400]}"
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        在虚拟环境中安装 Python 包
        
        Parameters:
            packages (list or str): 要安装的包列表或单个包名
            timeout (int, optional): 超时时间（秒），默认300
        """
        try:
            packages = parameters.get("packages")
            timeout = parameters.get("timeout", 300)
            
            if not packages:
                return {
                    "status": "error",
                    "output": "",
                    "error": "packages is required"
                }
            
            # 转换为列表
            if isinstance(packages, str):
                packages = [packages]
            
            workspace = Path(task_id)
            env_dir = workspace / "code_env"
            venv_path = env_dir / "venv"
            
            # 检查并创建虚拟环境
            if not venv_path.exists():
                venv_created, error_msg = self._create_venv(venv_path)
                if not venv_created:
                    return {
                        "status": "error",
                        "output": "",
                        "error": f"无法创建虚拟环境: {error_msg}"
                    }
            
            # 获取虚拟环境的 pip
            if sys.platform == "win32":
                pip_exec = venv_path / "Scripts" / "pip.exe"
            else:
                pip_exec = venv_path / "bin" / "pip"
            
            # 安装包
            results = []
            for package in packages:
                # 设置环境变量，避免 Bad file descriptor
                import os
                env = os.environ.copy()
                env.setdefault("PYTHONIOENCODING", "utf-8")
                env.setdefault("PYTHONUTF8", "1")
                
                # Windows 下不使用 close_fds
                close_fds = (sys.platform != "win32")
                
                result = subprocess.run(
                    [str(pip_exec), "install", package],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                    close_fds=close_fds
                )
                
                if result.returncode == 0:
                    results.append(f"✅ {package}: installed")
                else:
                    results.append(f"❌ {package}: {result.stderr.strip()[:200]}")
            
            output = "\n".join(results)
            
            return {
                "status": "success",
                "output": output,
                "error": ""
            }
            
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "output": "",
                "error": f"Installation timeout ({timeout}s)"
            }
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }


class ExecuteCommandTool(BaseTool):
    """命令行执行工具（仅限安全的只读命令）"""
    
    # 白名单：只允许安全的只读命令
    ALLOWED_COMMANDS = {
        # 文件查看和搜索
        'ls', 'dir',           # 列出目录内容
        'cat', 'type',         # 显示文件内容
        'head', 'tail',        # 显示文件开头/结尾
        'grep', 'findstr',     # 文本搜索
        'find', 'where',       # 查找文件
        'tree',                # 显示目录树
        
        # 系统信息
        'pwd', 'cd',           # 显示/切换目录（cd仅用于显示）
        'whoami',              # 当前用户
        'hostname',            # 主机名
        'date',                # 日期时间
        'echo',                # 输出文本
        
        # 文件信息
        'wc',                  # 统计行数/字数
        'diff',                # 比较文件
        'file',                # 文件类型
        'stat',                # 文件状态
        'du',                  # 磁盘使用
        'df',                  # 磁盘空间
        
        # 其他只读命令
        'which',               # 查找命令路径
        'env', 'set',          # 显示环境变量
        'python', 'python3',   # Python解释器（用于查看版本等）
        'pip',                 # pip命令（仅限list/show等）
        'git',                 # git命令（仅限status/log等）
    }
    
    # 危险参数黑名单（即使命令在白名单中，如果包含这些参数也拒绝）
    DANGEROUS_PATTERNS = [
        'rm ', 'del ',         # 删除
        'mv ', 'move ',        # 移动/重命名
        'cp ', 'copy ',        # 复制
        'chmod', 'chown',      # 修改权限
        '>', '>>',             # 重定向（可能覆盖文件）
        'sudo', 'su',          # 提权
        'format', 'mkfs',      # 格式化
        'kill', 'pkill',       # 结束进程
        '--force', '-f',       # 强制操作
        'install', 'uninstall', # 安装/卸载
    ]
    
    def _is_command_safe(self, command: str) -> tuple[bool, str]:
        """
        检查命令是否安全
        
        Returns:
            (是否安全, 错误信息)
        """
        return True,"不检查"
        command = command.strip()
        
        if not command:
            return False, "空命令"
        
        # 提取命令的第一个词（命令名）
        cmd_parts = command.split()
        if not cmd_parts:
            return False, "无效命令"
        
        base_command = cmd_parts[0]
        
        # Windows下可能带.exe后缀
        if base_command.endswith('.exe'):
            base_command = base_command[:-4]
        
        # 检查基础命令是否在白名单中
        if base_command not in self.ALLOWED_COMMANDS:
            #return False, f"命令 '{base_command}' 不在允许列表中。仅允许只读命令如: ls, cat, grep, find, pwd, tree 等"
            pass
        # 检查是否包含危险模式
        command_lower = command.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in command_lower:
                return False, f"命令包含危险操作 '{pattern}'，已被拒绝"
        
        # git 命令特殊检查：只允许只读操作
        if base_command == 'git':
            git_readonly_cmds = ['status', 'log', 'diff', 'show', 'branch', 'remote', 'config', '--version']
            if len(cmd_parts) < 2 or not any(ro_cmd in command_lower for ro_cmd in git_readonly_cmds):
                return False, "git 命令仅允许只读操作（如 status, log, diff, show 等）"
        
        # pip 命令特殊检查：只允许只读操作
        if base_command in ['pip', 'pip3']:
            pip_readonly_cmds = ['list', 'show', 'search', 'freeze', '--version', '-V']
            if len(cmd_parts) < 2 or not any(ro_cmd in command for ro_cmd in pip_readonly_cmds):
                return False, "pip 命令仅允许只读操作（如 list, show, freeze 等）"
        
        return True, ""

    def _use_system_terminal_mode(self) -> bool:
        """macOS only: optionally route execute_command through Terminal.app."""
        mode = str(os.environ.get("MLA_EXECUTE_COMMAND_MODE", "direct")).strip().lower()
        return sys.platform == "darwin" and mode == "system_terminal"

    def _escape_applescript_str(self, s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    def _run_osascript(self, script: str, timeout: int = 10) -> str:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(err or "unknown osascript error")
        return (result.stdout or "").strip()

    def _find_idle_terminal_window_id(self) -> Optional[int]:
        """
        Find an existing dedicated Terminal window whose tagged tab is idle.

        We only reuse tabs that are not busy. Otherwise, commands like `sleep`
        would keep consuming the shell input buffer and block every following
        execute_command routed through Terminal.app.
        """
        title = self._escape_applescript_str(TERMINAL_SESSION_TAB_TITLE)
        script = (
            'tell application "Terminal"\n'
            'repeat with w in windows\n'
            'repeat with t in tabs of w\n'
            f'if (custom title of t) is "{title}" then\n'
            'if (busy of t) is false then return (id of w) as string\n'
            'end if\n'
            'end if\n'
            'end repeat\n'
            'end repeat\n'
            'return ""\n'
            'end tell'
        )
        out = self._run_osascript(script, timeout=10).strip()
        if not out:
            return None
        return int(out)

    def _terminal_window_exists(self, window_id: int) -> bool:
        script = (
            'tell application "Terminal"\n'
            f'return (exists window id {int(window_id)}) as string\n'
            'end tell'
        )
        try:
            return self._run_osascript(script, timeout=5).strip().lower() == "true"
        except Exception:
            return False

    def _close_tagged_terminal_windows(self) -> None:
        """
        Close every Terminal window carrying our dedicated custom title.

        This keeps the desktop side to a single managed Terminal window even if
        earlier retries/timeouts already spawned multiple dedicated windows.
        """
        title = self._escape_applescript_str(TERMINAL_SESSION_TAB_TITLE)
        script = (
            'tell application "Terminal"\n'
            'set targetIds to {}\n'
            'repeat with w in windows\n'
            'set shouldClose to false\n'
            'repeat with t in tabs of w\n'
            f'if (custom title of t) is "{title}" then\n'
            'set shouldClose to true\n'
            'exit repeat\n'
            'end if\n'
            'end repeat\n'
            'if shouldClose then set end of targetIds to (id of w)\n'
            'end repeat\n'
            'repeat with wid in targetIds\n'
            'try\n'
            'close (window id (contents of wid)) saving no\n'
            'end try\n'
            'end repeat\n'
            'return ""\n'
            'end tell'
        )
        try:
            self._run_osascript(script, timeout=10)
        except Exception:
            pass

    def _list_tagged_terminal_ttys(self) -> list[str]:
        title = self._escape_applescript_str(TERMINAL_SESSION_TAB_TITLE)
        script = (
            'tell application "Terminal"\n'
            'set ttyList to {}\n'
            'repeat with w in windows\n'
            'repeat with t in tabs of w\n'
            f'if (custom title of t) is "{title}" then\n'
            'set ttyValue to (tty of t) as string\n'
            'if ttyValue is not "" then set end of ttyList to ttyValue\n'
            'exit repeat\n'
            'end if\n'
            'end repeat\n'
            'end repeat\n'
            'set AppleScript\'s text item delimiters to "\\n"\n'
            'set outText to ttyList as text\n'
            'set AppleScript\'s text item delimiters to ""\n'
            'return outText\n'
            'end tell'
        )
        try:
            raw = self._run_osascript(script, timeout=10)
        except Exception:
            return []
        return [line.strip() for line in str(raw or "").splitlines() if line.strip()]

    def _force_reset_tagged_terminal_windows(self) -> None:
        """
        Force-stop processes running in dedicated Terminal windows, then close them.

        Closing a busy Terminal window directly is unreliable because Terminal may
        keep the session alive while a foreground process is still attached to the
        TTY. We explicitly terminate the TTY session first so the desktop side can
        go back to a single managed window.
        """
        tty_paths = self._list_tagged_terminal_ttys()
        for tty_path in tty_paths:
            tty_name = Path(tty_path).name.strip()
            if not tty_name:
                continue
            for signal_name in ("-TERM", "-KILL"):
                try:
                    subprocess.run(
                        ["pkill", signal_name, "-t", tty_name],
                        capture_output=True,
                        text=True,
                        timeout=3,
                        stdin=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
                time.sleep(0.15)
        self._close_tagged_terminal_windows()

    def _wait_for_terminal_window_idle(
        self,
        window_id: int,
        timeout: float = 0.8,
        poll_interval: float = 0.1,
    ) -> bool:
        """
        Give Terminal a short grace period to return to the prompt.

        Even fast commands like `pwd` briefly keep the tab marked as busy after
        the child process exits. Without this grace period, the next command can
        incorrectly decide the dedicated tab is still occupied and open a fresh
        Terminal window every time.
        """
        title = self._escape_applescript_str(TERMINAL_SESSION_TAB_TITLE)
        deadline = time.time() + max(0.0, float(timeout))

        while time.time() < deadline:
            script = (
                'tell application "Terminal"\n'
                f'set w to window id {int(window_id)}\n'
                'repeat with t in tabs of w\n'
                f'if (custom title of t) is "{title}" then\n'
                'return ((busy of t) is false) as string\n'
                'end if\n'
                'end repeat\n'
                'return "false"\n'
                'end tell'
            )
            try:
                out = self._run_osascript(script, timeout=5).strip().lower()
            except Exception:
                return False
            if out == "true":
                return True
            time.sleep(max(0.01, float(poll_interval)))
        return False

    def _get_tagged_terminal_tty(self, window_id: int) -> Optional[str]:
        title = self._escape_applescript_str(TERMINAL_SESSION_TAB_TITLE)
        script = (
            'tell application "Terminal"\n'
            f'set w to window id {int(window_id)}\n'
            'repeat with t in tabs of w\n'
            f'if (custom title of t) is "{title}" then return (tty of t) as string\n'
            'end repeat\n'
            'return ""\n'
            'end tell'
        )
        try:
            out = self._run_osascript(script, timeout=5).strip()
        except Exception:
            return None
        return out or None

    def _interrupt_terminal_window_processes(self, window_id: int) -> bool:
        """
        Interrupt the currently running command in our dedicated Terminal tab.

        We keep the parent shell alive and only terminate child processes bound
        to the same TTY. This avoids the user-facing "close running process"
        dialog while still letting the next command reuse the same Terminal
        window.
        """
        tty_path = self._get_tagged_terminal_tty(window_id)
        if not tty_path:
            return False

        tty_name = Path(tty_path).name.strip()
        if not tty_name:
            return False

        try:
            result = subprocess.run(
                ["ps", "-t", tty_name, "-o", "pid=,ppid=,comm="],
                capture_output=True,
                text=True,
                timeout=5,
                stdin=subprocess.DEVNULL,
            )
        except Exception:
            return False

        processes = []
        for line in (result.stdout or "").splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[0])
                ppid = int(parts[1])
            except Exception:
                continue
            comm = parts[2] if len(parts) > 2 else ""
            processes.append((pid, ppid, comm))

        if not processes:
            return self._wait_for_terminal_window_idle(window_id, timeout=0.5)

        pid_set = {pid for pid, _, _ in processes}
        root_candidates = [pid for pid, ppid, _ in processes if ppid not in pid_set]
        keep_pid = min(root_candidates) if root_candidates else min(pid_set)
        target_pids = [pid for pid, _, _ in processes if pid != keep_pid]

        if not target_pids:
            return self._wait_for_terminal_window_idle(window_id, timeout=1.0)

        for sig in ("-TERM", "-KILL"):
            for pid in target_pids:
                try:
                    subprocess.run(
                        ["kill", sig, str(pid)],
                        capture_output=True,
                        text=True,
                        timeout=3,
                        stdin=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
            if self._wait_for_terminal_window_idle(window_id, timeout=1.0):
                return True
            time.sleep(0.2)

        return self._wait_for_terminal_window_idle(window_id, timeout=0.5)

    def _get_or_create_terminal_window_id(self, force_new: bool = False) -> int:
        """
        Reuse one idle dedicated Terminal tab/window.

        If every dedicated Terminal tab is still busy, create a new dedicated
        window so that a hung command does not head-of-line block later commands.
        """
        global TERMINAL_SESSION_WINDOW_ID, TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH

        if force_new:
            self._force_reset_tagged_terminal_windows()
            TERMINAL_SESSION_WINDOW_ID = None

        if not force_new and TERMINAL_SESSION_WINDOW_ID is not None:
            cached_id = int(TERMINAL_SESSION_WINDOW_ID)
            if self._terminal_window_exists(cached_id):
                return cached_id
            TERMINAL_SESSION_WINDOW_ID = None

        # Do not reuse leftover tagged windows from previous desktop/backend
        # sessions. To keep the UX predictable, once the current process loses
        # its cached window reference we rebuild a single clean dedicated
        # Terminal window instead of attaching to historical ones.
        self._force_reset_tagged_terminal_windows()
        TERMINAL_SESSION_WINDOW_ID = None

        title = self._escape_applescript_str(TERMINAL_SESSION_TAB_TITLE)
        script = (
            'tell application "Terminal"\n'
            'do script ""\n'
            'set targetWin to front window\n'
            f'set custom title of selected tab of targetWin to "{title}"\n'
            'return id of targetWin\n'
            'end tell'
        )
        out = self._run_osascript(script, timeout=10)
        wid = int(out)
        TERMINAL_SESSION_WINDOW_ID = wid
        TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH = False
        return wid

    def _launch_terminal_script(self, script_path: Path) -> int:
        """
        Ask Terminal.app to execute the generated shell script.
        Reuse one dedicated Terminal tab/window.
        """
        window_id = self._get_or_create_terminal_window_id()
        if not self._wait_for_terminal_window_idle(window_id, timeout=1.5):
            reset_ok = False
            if TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH:
                reset_ok = self._interrupt_terminal_window_processes(window_id)
            else:
                reset_ok = self._wait_for_terminal_window_idle(window_id, timeout=1.0)
            if not reset_ok:
                raise RuntimeError("Dedicated Terminal session is still busy; please retry after the current command finishes.")
        cmd = f'/bin/bash {shlex.quote(str(script_path))}'
        esc_cmd = self._escape_applescript_str(cmd)
        title = self._escape_applescript_str(TERMINAL_SESSION_TAB_TITLE)
        apple_script = (
            'tell application "Terminal"\n'
            f'set w to window id {window_id}\n'
            'set targetTab to missing value\n'
            'repeat with t in tabs of w\n'
            f'if ((custom title of t) is "{title}") and ((busy of t) is false) then\n'
            'set targetTab to t\n'
            'exit repeat\n'
            'end if\n'
            'end repeat\n'
            'if targetTab is missing value then\n'
            'do script ""\n'
            'set w to front window\n'
            'set targetTab to selected tab of w\n'
            f'set custom title of targetTab to "{title}"\n'
            'end if\n'
            f'do script "{esc_cmd}" in targetTab\n'
            'return id of w\n'
            'end tell'
        )
        try:
            out = self._run_osascript(apple_script, timeout=10)
            if out:
                global TERMINAL_SESSION_WINDOW_ID
                TERMINAL_SESSION_WINDOW_ID = int(out)
                return int(out)
        except Exception as e:
            # If cached window was closed by user, reset cache and retry once.
            if "Can’t get window id" in str(e) or "can't get window id" in str(e).lower():
                TERMINAL_SESSION_WINDOW_ID = None
                window_id = self._get_or_create_terminal_window_id()
                retry_script = (
                    'tell application "Terminal"\n'
                    f'set w to window id {window_id}\n'
                    'set targetTab to missing value\n'
                    'repeat with t in tabs of w\n'
                    f'if ((custom title of t) is "{title}") and ((busy of t) is false) then\n'
                    'set targetTab to t\n'
                    'exit repeat\n'
                    'end if\n'
                    'end repeat\n'
                    'if targetTab is missing value then\n'
                    'do script ""\n'
                    'set w to front window\n'
                    'set targetTab to selected tab of w\n'
                    'end if\n'
                    f'set custom title of targetTab to "{title}"\n'
                    f'do script "{esc_cmd}" in targetTab\n'
                    'return id of w\n'
                    'end tell'
                )
                out = self._run_osascript(retry_script, timeout=10)
                if out:
                    TERMINAL_SESSION_WINDOW_ID = int(out)
                    return int(out)
                return window_id
            raise RuntimeError(f"Failed to launch Terminal command: {str(e)}")
        return window_id

    def _build_terminal_paths(self, workspace: Path, output_path: Optional[Path]) -> tuple[Path, Path, Path]:
        token = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        runtime_dir = workspace / "temp" / "terminal_exec"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        script_path = runtime_dir / f"run_{token}.sh"
        if output_path is None:
            output_path = runtime_dir / f"output_{token}.log"
        exit_path = runtime_dir / f"exit_{token}.txt"
        return script_path, output_path, exit_path

    def _write_terminal_script(
        self,
        script_path: Path,
        abs_working_dir: Path,
        command: str,
        output_path: Path,
        exit_path: Path,
    ) -> None:
        shell = (
            "#!/bin/bash\n"
            f"cd {shlex.quote(str(abs_working_dir))} || exit 1\n"
            f"{{ {command}; }} > {shlex.quote(str(output_path))} 2>&1\n"
            f'echo "$?" > {shlex.quote(str(exit_path))}\n'
        )
        script_path.write_text(shell, encoding="utf-8")
        script_path.chmod(0o755)

    def _run_via_terminal_foreground(
        self,
        workspace: Path,
        abs_working_dir: Path,
        command: str,
        timeout: int,
        output_file: Optional[str],
    ) -> Dict[str, Any]:
        user_output_path = get_abs_path(str(workspace), output_file) if output_file else None
        if user_output_path:
            user_output_path.parent.mkdir(parents=True, exist_ok=True)

        script_path, output_path, exit_path = self._build_terminal_paths(workspace, user_output_path)
        self._write_terminal_script(script_path, abs_working_dir, command, output_path, exit_path)
        terminal_window_id = self._launch_terminal_script(script_path)
        global TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH

        deadline = time.time() + max(1, int(timeout))
        while time.time() < deadline:
            if exit_path.exists():
                break
            time.sleep(0.2)

        if not exit_path.exists():
            TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH = True
            return {
                "status": "error",
                "output": "",
                "error": (
                    f"Command timeout ({timeout}s) in system_terminal mode. "
                    "The command may still be running in Terminal.app."
                ),
            }

        try:
            exit_code = int(exit_path.read_text(encoding="utf-8").strip() or "1")
        except Exception:
            exit_code = 1

        # Wait briefly for Terminal to return to an idle prompt so the next
        # short command can reuse the same dedicated tab instead of creating a
        # fresh window every time.
        idle_ready = self._wait_for_terminal_window_idle(terminal_window_id)
        TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH = not idle_ready

        content = ""
        try:
            content = output_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            content = ""

        if output_file:
            msg = f"命令执行完成（system_terminal），输出已保存到: {output_file}\nExit code: {exit_code}"
            if content:
                preview = content[:1000]
                msg += "\n\n输出预览（前1000字符）:\n" + preview + ("\n..." if len(content) > 1000 else "")
            return {"status": "success", "output": msg, "error": ""}

        if exit_code != 0:
            content = (content or "") + f"\nExit code: {exit_code}"
        return {"status": "success", "output": content, "error": ""}

    def _run_via_terminal_background(
        self,
        workspace: Path,
        abs_working_dir: Path,
        command: str,
        output_file: str,
    ) -> Dict[str, Any]:
        output_path = get_abs_path(str(workspace), output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        script_path, _, exit_path = self._build_terminal_paths(workspace, output_path)
        self._write_terminal_script(script_path, abs_working_dir, command, output_path, exit_path)
        self._launch_terminal_script(script_path)

        global TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH
        TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH = True

        process_id = f"bg_term_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        BACKGROUND_PROCESSES[process_id] = {
            "task_id": str(workspace),
            "pid": None,
            "command": command,
            "output_file": output_file,
            "start_time": datetime.now().isoformat(),
            "process_obj": None,
            "mode": "system_terminal",
            "exit_file": str(exit_path),
        }

        return {
            "status": "success",
            "output": (
                "✅ 命令已在后台启动（system_terminal）\n"
                f"   Process ID: {process_id}\n"
                "   PID: terminal-managed\n"
                f"   输出文件: {output_file}\n"
                f"   提示: 使用 file_read 读取 {output_file} 查看执行结果\n"
                "   提示: system_terminal 模式下建议直接在 Terminal 中终止对应命令"
            ),
            "error": "",
        }
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行安全的只读命令
        
        Parameters:
            command (str): 要执行的命令（仅限白名单中的安全命令）
            working_dir (str, optional): 工作目录相对路径，默认为workspace根目录
            timeout (int, optional): 超时时间（秒），默认30
            background (bool, optional): 是否后台执行（不阻塞），默认False。后台执行时必须指定 output_file。
            output_file (str, optional): 输出重定向到文件（相对路径）。后台执行时必需；非后台执行时可选。
        """
        try:
            command = parameters.get("command")
            working_dir = parameters.get("working_dir", ".")
            timeout = parameters.get("timeout", 30)
            background = parameters.get("background", False)
            output_file = parameters.get("output_file")
            
            if not command:
                return {
                    "status": "error",
                    "output": "",
                    "error": "command parameter is required"
                }

            # 后台执行时必须指定输出文件
            if background and not output_file:
                return {
                    "status": "error",
                    "output": "",
                    "error": "output_file is required when background=True"
                }
            
            # 安全检查
            is_safe, error_msg = self._is_command_safe(command)
            if not is_safe:
                return {
                    "status": "error",
                    "output": "",
                    "error": f"命令安全检查失败: {error_msg}"
                }
            
            abs_working_dir = get_abs_path(task_id, working_dir)
            
            # 确保工作目录在 workspace 内
            workspace = Path(task_id)
            try:
                abs_working_dir.resolve().relative_to(workspace.resolve())
            except ValueError:
                return {
                    "status": "error",
                    "output": "",
                    "error": f"工作目录必须在 workspace 内: {working_dir}"
                }
            
            if not abs_working_dir.exists():
                return {
                    "status": "error",
                    "output": "",
                    "error": f"Working directory not found: {working_dir}"
                }
            
            workspace = Path(task_id)

            # macOS only: optionally proxy through Terminal.app to align with terminal-side permissions
            if self._use_system_terminal_mode():
                if background:
                    return self._run_via_terminal_background(
                        workspace=workspace,
                        abs_working_dir=abs_working_dir,
                        command=command,
                        output_file=output_file,
                    )
                return self._run_via_terminal_foreground(
                    workspace=workspace,
                    abs_working_dir=abs_working_dir,
                    command=command,
                    timeout=timeout,
                    output_file=output_file,
                )

            # 输出重定向到文件
            if output_file:
                output_path = get_abs_path(str(workspace), output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                if background:
                    # 后台执行：Popen + 输出到文件
                    out_f = open(output_path, "w", encoding="utf-8")

                    if sys.platform == "win32":
                        CREATE_NO_WINDOW = 0x08000000
                        DETACHED_PROCESS = 0x00000008
                        process = subprocess.Popen(
                            command,
                            shell=True,
                            stdout=out_f,
                            stderr=subprocess.STDOUT,
                            text=True,
                            cwd=str(abs_working_dir),
                            stdin=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                            close_fds=False,
                        )
                    else:
                        process = subprocess.Popen(
                            command,
                            shell=True,
                            stdout=out_f,
                            stderr=subprocess.STDOUT,
                            text=True,
                            cwd=str(abs_working_dir),
                            stdin=subprocess.DEVNULL,
                            start_new_session=True,
                        )

                    process_id = f"bg_cmd_{int(time.time())}_{process.pid}"
                    BACKGROUND_PROCESSES[process_id] = {
                        "task_id": str(workspace),
                        "pid": process.pid,
                        "command": command,
                        "output_file": output_file,
                        "start_time": datetime.now().isoformat(),
                        "process_obj": process,
                    }

                    return {
                        "status": "success",
                        "output": (
                            "✅ 命令已在后台启动\n"
                            f"   Process ID: {process_id}\n"
                            f"   PID: {process.pid}\n"
                            f"   输出文件: {output_file}\n"
                            f"   提示: 使用 file_read 读取 {output_file} 查看执行结果\n"
                            "   终止: 使用 execute_command 运行 `ps`/`kill` 或在桌面端停止任务"
                        ),
                        "error": "",
                    }
                else:
                    # 非后台：run + 输出到文件
                    with open(output_path, "w", encoding="utf-8") as out_f:
                        result = subprocess.run(
                            command,
                            shell=True,
                            stdout=out_f,
                            stderr=subprocess.STDOUT,
                            text=True,
                            timeout=timeout,
                            cwd=str(abs_working_dir),
                            stdin=subprocess.DEVNULL,
                        )

                    output = f"命令执行完成，输出已保存到: {output_file}\nExit code: {result.returncode}"
                    # 读取部分预览
                    try:
                        with open(output_path, "r", encoding="utf-8") as f:
                            content = f.read(1000)
                        if content:
                            output += "\n\n输出预览（前1000字符）:\n" + content + ("\n..." if len(content) == 1000 else "")
                    except Exception:
                        pass

                    return {"status": "success", "output": output, "error": ""}

            # 不重定向：直接捕获输出
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(abs_working_dir),
                stdin=subprocess.DEVNULL,
            )

            output = result.stdout or ""
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if result.returncode != 0:
                output += f"\nExit code: {result.returncode}"

            return {"status": "success", "output": output, "error": ""}
            
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "output": "",
                "error": f"Command timeout ({timeout}s)"
            }
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }


class GrepTool(BaseTool):
    """文本搜索工具（跨平台grep实现）"""
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        在文件中搜索匹配的文本模式（跨平台实现）
        
        Parameters:
            pattern (str): 要搜索的正则表达式模式
            search_path (str, optional): 搜索路径相对路径，默认为当前工作区根目录
            file_pattern (str, optional): 文件名匹配模式（支持通配符），如 "*.py", "*.txt"
            recursive (bool, optional): 是否递归搜索子目录，默认True
            case_sensitive (bool, optional): 是否大小写敏感，默认True
            show_line_number (bool, optional): 是否显示行号，默认True
            max_results (int, optional): 最大结果数量，默认100
            context_lines (int, optional): 显示匹配行前后的上下文行数，默认0
        """
        try:
            pattern = parameters.get("pattern")
            if not pattern:
                return {
                    "status": "error",
                    "output": "",
                    "error": "pattern is required"
                }
            
            search_path = parameters.get("search_path", ".")
            file_pattern = parameters.get("file_pattern", "*")
            recursive = parameters.get("recursive", True)
            case_sensitive = parameters.get("case_sensitive", True)
            show_line_number = parameters.get("show_line_number", True)
            max_results = parameters.get("max_results", 100)
            context_lines = parameters.get("context_lines", 0)
            
            # 获取绝对路径，确保只在 workspace 内搜索
            abs_search_path = get_abs_path(task_id, search_path)
            workspace = Path(task_id)
            
            # 安全检查：确保搜索路径在 workspace 内
            try:
                abs_search_path.resolve().relative_to(workspace.resolve())
            except ValueError:
                return {
                    "status": "error",
                    "output": "",
                    "error": f"Search path must be within workspace: {search_path}"
                }
            
            if not abs_search_path.exists():
                return {
                    "status": "error",
                    "output": "",
                    "error": f"Search path not found: {search_path}"
                }
            
            # 编译正则表达式
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                return {
                    "status": "error",
                    "output": "",
                    "error": f"Invalid regex pattern: {str(e)}"
                }
            
            # 执行搜索
            results = []
            total_matches = 0
            files_searched = 0
            
            # 获取要搜索的文件列表
            if abs_search_path.is_file():
                files_to_search = [abs_search_path]
            else:
                if recursive:
                    files_to_search = list(abs_search_path.rglob(file_pattern))
                else:
                    files_to_search = list(abs_search_path.glob(file_pattern))
                
                # 只保留文件（排除目录）
                files_to_search = [f for f in files_to_search if f.is_file()]
            
            # 搜索每个文件
            for file_path in files_to_search:
                if total_matches >= max_results:
                    break
                
                try:
                    # 尝试读取文件（跳过二进制文件）
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    
                    files_searched += 1
                    matches_in_file = []
                    
                    for line_num, line in enumerate(lines, 1):
                        if total_matches >= max_results:
                            break
                        
                        if regex.search(line):
                            total_matches += 1
                            
                            # 计算相对路径（相对于 workspace）
                            try:
                                relative_path = file_path.relative_to(workspace)
                            except ValueError:
                                relative_path = file_path
                            
                            # 构建输出行
                            if show_line_number:
                                match_line = f"{relative_path}:{line_num}: {line.rstrip()}"
                            else:
                                match_line = f"{relative_path}: {line.rstrip()}"
                            
                            # 添加上下文行
                            if context_lines > 0:
                                context = []
                                # 前面的行
                                for i in range(max(0, line_num - context_lines - 1), line_num - 1):
                                    context.append(f"{relative_path}:{i+1}- {lines[i].rstrip()}")
                                
                                context.append(match_line)
                                
                                # 后面的行
                                for i in range(line_num, min(len(lines), line_num + context_lines)):
                                    context.append(f"{relative_path}:{i+1}- {lines[i].rstrip()}")
                                
                                matches_in_file.append("\n".join(context))
                            else:
                                matches_in_file.append(match_line)
                    
                    if matches_in_file:
                        results.extend(matches_in_file)
                
                except (UnicodeDecodeError, PermissionError):
                    # 跳过无法读取的文件（二进制文件或权限问题）
                    continue
                except Exception:
                    # 跳过其他错误的文件
                    continue
            
            # 构建输出
            if results:
                output = "\n".join(results)
                summary = f"\n\n搜索完成: 在 {files_searched} 个文件中找到 {total_matches} 处匹配"
                if total_matches >= max_results:
                    summary += f" (已达到最大结果数 {max_results})"
                output += summary
            else:
                output = f"未找到匹配项。已搜索 {files_searched} 个文件。"
            
            return {
                "status": "success",
                "output": output,
                "error": ""
            }
            
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }


class CodeProcessManagerTool(BaseTool):
    """后台代码进程管理工具"""
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        管理后台执行的代码进程
        
        Parameters:
            action (str): 操作类型 'list' 或 'kill'
            process_id (str, optional): 进程ID（kill 时需要）
        """
        try:
            action = parameters.get("action", "list")
            
            if action == "list":
                return self._list_processes(task_id)
            elif action == "kill":
                process_id = parameters.get("process_id")
                if not process_id:
                    return {
                        "status": "error",
                        "output": "",
                        "error": "process_id is required for kill action"
                    }
                return self._kill_process(task_id, process_id)
            else:
                return {
                    "status": "error",
                    "output": "",
                    "error": f"Unknown action: {action}. Use 'list' or 'kill'"
                }
        
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }
    
    def _list_processes(self, task_id: str) -> Dict[str, Any]:
        """列出指定 workspace 的后台进程"""
        workspace_processes = []
        
        # 清理已结束的进程
        finished_ids = []
        for proc_id, info in BACKGROUND_PROCESSES.items():
            process = info.get("process_obj")
            if process and process.poll() is not None:
                # 进程已结束
                finished_ids.append(proc_id)
        
        for proc_id in finished_ids:
            del BACKGROUND_PROCESSES[proc_id]
        
        # 筛选当前 workspace 的进程
        for proc_id, info in BACKGROUND_PROCESSES.items():
            if info["task_id"] == task_id:
                process = info.get("process_obj")
                if info.get("mode") == "system_terminal":
                    exit_file = info.get("exit_file")
                    status = "finished" if (exit_file and Path(exit_file).exists()) else "running"
                else:
                    status = "running" if process and process.poll() is None else "finished"
                
                workspace_processes.append({
                    "process_id": proc_id,
                    "pid": info["pid"],
                    "command": info["command"],
                    "output_file": info["output_file"],
                    "start_time": info["start_time"],
                    "status": status
                })
        
        if not workspace_processes:
            output = "当前 workspace 没有后台运行的代码进程"
        else:
            output = f"后台代码进程列表（共 {len(workspace_processes)} 个）:\n\n"
            for i, proc in enumerate(workspace_processes, 1):
                output += f"{i}. Process ID: {proc['process_id']}\n"
                output += f"   PID: {proc['pid']}\n"
                output += f"   命令: {proc['command']}\n"
                output += f"   输出: {proc['output_file']}\n"
                output += f"   启动: {proc['start_time']}\n"
                output += f"   状态: {proc['status']}\n\n"
        
        return {
            "status": "success",
            "output": output,
            "error": ""
        }
    
    def _kill_process(self, task_id: str, process_id: str) -> Dict[str, Any]:
        """终止指定的后台进程"""
        # 检查进程是否存在
        if process_id not in BACKGROUND_PROCESSES:
            return {
                "status": "error",
                "output": "",
                "error": f"Process not found: {process_id}"
            }
        
        info = BACKGROUND_PROCESSES[process_id]
        
        # 安全检查：只能终止本 workspace 的进程
        if info["task_id"] != task_id:
            return {
                "status": "error",
                "output": "",
                "error": f"Permission denied: Process belongs to another workspace"
            }
        
        process = info.get("process_obj")
        pid = info["pid"]

        if info.get("mode") == "system_terminal":
            return {
                "status": "error",
                "output": "",
                "error": "system_terminal 模式下不支持通过 manage_code_process 终止。请在 Terminal.app 中手动终止命令。"
            }
        
        # 检查进程是否还在运行
        if process and process.poll() is None:
            # 进程仍在运行，尝试终止
            try:
                process.terminate()
                
                # 等待最多 3 秒
                try:
                    process.wait(timeout=3)
                    status = "terminated"
                except subprocess.TimeoutExpired:
                    # 强制 kill
                    process.kill()
                    process.wait(timeout=1)
                    status = "killed"
                
                # 从注册表移除
                del BACKGROUND_PROCESSES[process_id]
                
                output = f"✅ 进程已终止\n"
                output += f"   Process ID: {process_id}\n"
                output += f"   PID: {pid}\n"
                output += f"   状态: {status}\n"
                output += f"   输出文件: {info['output_file']}"
                
                return {
                    "status": "success",
                    "output": output,
                    "error": ""
                }
            
            except Exception as e:
                return {
                    "status": "error",
                    "output": "",
                    "error": f"终止进程失败: {str(e)}"
                }
        else:
            # 进程已结束
            del BACKGROUND_PROCESSES[process_id]
            
            return {
                "status": "success",
                "output": f"进程已结束（无需终止）\n   Process ID: {process_id}\n   输出文件: {info['output_file']}",
                "error": ""
            }
