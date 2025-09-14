#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-Level Agent API Server v3 (Fixed)
提供完整的Agent系统API接口

API导入 - 支持多级Agent系统的RESTful API服务
"""

import os
import sys
import json
import time
import threading
import subprocess
import signal
import atexit
import zipfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import psutil

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from baseService.agent_hierarchy import get_cached_hierarchy_manager
from task_runner import run_single_task, resume_task_from_stack, add_instruction_to_task

app = Flask(__name__)
CORS(app)

class TaskManager:
    """任务管理器，负责管理运行中的任务和历史记录"""
    
    def __init__(self):
        self.running_tasks = {}  # task_id -> {"process": subprocess, "thread": thread, "log_file": path}
        self.task_logs = {}     # task_id -> {"start_time": time, "log_file": path, "status": status}
        self.lock = threading.Lock()
        
        # 确保日志目录存在
        self.log_dir = os.path.join(project_root, 'logs', 'api_state')
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 加载持久化状态
        self._load_persistent_state()
        
        # 清理孤儿进程
        self._cleanup_orphaned_processes()
        
        # 注册退出清理
        atexit.register(self._cleanup_on_exit)
    
    def _load_persistent_state(self):
        """从文件加载持久化状态"""
        try:
            task_logs_file = os.path.join(self.log_dir, 'task_logs.json')
            if os.path.exists(task_logs_file):
                with open(task_logs_file, 'r', encoding='utf-8') as f:
                    self.task_logs = json.load(f)
        except Exception as e:
            print(f"加载持久化状态失败: {e}")
    
    def _save_persistent_state(self):
        """保存状态到文件"""
        try:
            # 保存任务日志
            task_logs_file = os.path.join(self.log_dir, 'task_logs.json')
            with open(task_logs_file, 'w', encoding='utf-8') as f:
                json.dump(self.task_logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存持久化状态失败: {e}")
    
    def _cleanup_orphaned_processes(self):
        """清理孤儿进程"""
        try:
            for task_id in list(self.running_tasks.keys()):
                task_info = self.running_tasks[task_id]
                if 'process' in task_info:
                    try:
                        process = task_info['process']
                        if process.poll() is not None:  # 进程已结束
                            del self.running_tasks[task_id]
                    except Exception:
                        del self.running_tasks[task_id]
        except Exception as e:
            print(f"清理孤儿进程失败: {e}")
    
    def _cleanup_on_exit(self):
        """程序退出时清理所有子进程"""
        for task_id, task_info in self.running_tasks.items():
            try:
                if 'process' in task_info:
                    process = task_info['process']
                    if process.poll() is None:  # 进程仍在运行
                        # 使用进程树终止方法
                        self._kill_process_tree(process.pid)
            except Exception as e:
                print(f"清理进程 {task_id} 失败: {e}")
    
    def _run_task_with_subprocess(self, task_id: str, agent_system_name: str, user_instructions: list, agent_name: str = "writing_agent", is_resume: bool = False):
        """使用subprocess运行任务并记录日志"""
        try:
            # 创建日志文件
            log_file = os.path.join(self.log_dir, f'{task_id}_console.log')
            
            # 在日志文件中添加分隔符和时间戳
            with open(log_file, 'a', encoding='utf-8') as log_f:
                log_f.write(f"\n{'='*80}\n")
                log_f.write(f"🚀 任务{'恢复' if is_resume else '启动'}时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_f.write(f"📋 任务ID: {task_id}\n")
                log_f.write(f"🤖 Agent系统: {agent_system_name}\n")
                if not is_resume:
                    log_f.write(f"📝 用户指令: {user_instructions}\n")
                else:
                    log_f.write(f"🔄 恢复模式: 从栈顶恢复\n")
                log_f.write(f"{'='*80}\n\n")
            
            # 准备命令参数
            if is_resume:
                cmd = [
                    sys.executable, 'TestFolder/start.py',
                    '--task_id', task_id,
                    '--agent_system_name', agent_system_name,
                    '--agent_name', agent_name,
                    '--resume_mode'
                ]
            else:
                cmd = [
                    sys.executable, 'TestFolder/start.py',
                    '--task_id', task_id,
                    '--agent_system_name', agent_system_name,
                    '--agent_name', agent_name,
                    '--user_instructions'
                ] + user_instructions  # 传递指令列表
            
            print(f"🚀 启动任务进程: {' '.join(cmd)}")
            
            # 启动子进程
            with open(log_file, 'a', encoding='utf-8') as log_f:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=os.getcwd()
                )
            
            # 等待进程完成
            return_code = process.wait()
            
            # 更新任务状态
            with self.lock:
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
                
                self.task_logs[task_id] = {
                    'start_time': datetime.now().isoformat(),
                    'log_file': log_file,
                    'status': 'completed' if return_code == 0 else 'error',
                    'return_code': return_code
                }
                self._save_persistent_state()
                
        except Exception as e:
            print(f"运行任务 {task_id} 失败: {e}")
            with self.lock:
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
                self.task_logs[task_id] = {
                    'start_time': datetime.now().isoformat(),
                    'log_file': log_file if 'log_file' in locals() else '',
                    'status': 'error',
                    'error': str(e)
                }
                self._save_persistent_state()
    
    def start_task(self, task_id: str, agent_system_name: str, user_instructions: list, agent_name: str = "writing_agent") -> Dict:
        """启动新任务"""
        print(f"🔧 [start_task] 参数检查:")
        print(f"   - task_id: {task_id}")
        print(f"   - agent_system_name: {agent_system_name}")
        print(f"   - agent_name: {agent_name}")
        print(f"   - user_instructions: {user_instructions}")
        
        with self.lock:
            if task_id in self.running_tasks:
                return {"status": "error", "message": f"任务 {task_id} 已在运行中"}
            
            # 启动子进程
            log_file = os.path.join(self.log_dir, f'{task_id}_console.log')
            
            # 准备命令
            cmd = [
                sys.executable, 'TestFolder/start.py',
                '--task_id', task_id,
                '--agent_system_name', agent_system_name,
                '--agent_name', agent_name,
                '--user_instructions'
            ] + user_instructions
            
            try:
                # 启动子进程，输出到日志文件
                with open(log_file, 'w', encoding='utf-8') as log_f:
                    log_f.write(f"🚀 任务启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    log_f.write(f"📋 任务ID: {task_id}\n")
                    log_f.write(f"🤖 Agent系统: {agent_system_name}\n")
                    log_f.write(f"📝 用户指令: {user_instructions}\n")
                    log_f.write(f"{'='*80}\n\n")
                
                with open(log_file, 'a', encoding='utf-8') as log_f:
                    process = subprocess.Popen(
                        cmd,
                        stdout=log_f,
                        stderr=subprocess.STDOUT,
                        text=True,
                        cwd=os.getcwd()
                    )
                
                # 保存任务元数据到文件（用于恢复）
                task_metadata = {
                    'task_id': task_id,
                    'agent_system_name': agent_system_name,
                    'agent_name': agent_name,
                    'user_instructions': user_instructions,
                    'created_time': datetime.now().isoformat(),
                    'log_file': log_file
                }
                
                metadata_file = os.path.join(self.log_dir, f'{task_id}_metadata.json')
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(task_metadata, f, indent=2, ensure_ascii=False)
                
                # 标记任务为运行中
                self.running_tasks[task_id] = {
                    'process': process,
                    'log_file': log_file,
                    'start_time': datetime.now().isoformat(),
                    'metadata_file': metadata_file
                }
                
                # 在新线程中等待进程完成
                def wait_for_completion():
                    try:
                        return_code = process.wait()
                        with self.lock:
                            if task_id in self.running_tasks:
                                del self.running_tasks[task_id]
                            
                            self.task_logs[task_id] = {
                                'start_time': datetime.now().isoformat(),
                                'log_file': log_file,
                                'status': 'completed' if return_code == 0 else 'error',
                                'return_code': return_code
                            }
                            self._save_persistent_state()
                    except Exception as e:
                        print(f"等待任务 {task_id} 完成失败: {e}")
                
                thread = threading.Thread(target=wait_for_completion)
                thread.start()
                
                return {"status": "success", "message": f"任务 {task_id} 已启动"}
                
            except Exception as e:
                return {"status": "error", "message": f"启动任务失败: {str(e)}"}
    
    def _kill_process_tree(self, pid: int):
        """终止进程树（类似Ctrl+C效果）"""
        try:
            import signal
            
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            
            print(f"🔄 向进程树发送SIGINT信号 (PID: {pid}, 子进程数: {len(children)})")
            
            # 先向所有子进程发送SIGINT（类似Ctrl+C）
            for child in children:
                try:
                    child.send_signal(signal.SIGINT)
                    print(f"   📤 向子进程发送SIGINT: PID {child.pid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # 向父进程发送SIGINT
            try:
                parent.send_signal(signal.SIGINT)
                print(f"   📤 向父进程发送SIGINT: PID {pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            
            # 等待进程优雅退出
            gone, alive = psutil.wait_procs(children + [parent], timeout=5)
            print(f"   ✅ {len(gone)} 个进程已优雅退出")
            
            # 如果还有进程存活，强制终止
            if alive:
                print(f"   ⚠️ {len(alive)} 个进程未退出，强制终止")
                for proc in alive:
                    try:
                        proc.kill()
                        print(f"     💀 强制终止进程: PID {proc.pid}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                        
            print(f"✅ 成功终止进程树: PID {pid}")
            return True
            
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"⚠️ 进程 {pid} 不存在或无权限访问: {e}")
            return True  # 进程已经不存在，认为成功
        except Exception as e:
            print(f"❌ 终止进程树失败: {e}")
            return False

    def pause_task(self, task_id: str) -> Dict:
        """暂停任务"""
        print(f"⏸️ [pause_task] 参数检查:")
        print(f"   - task_id: {task_id}")
        
        with self.lock:
            if task_id not in self.running_tasks:
                return {"status": "error", "message": f"任务 {task_id} 未在运行"}
            
            try:
                task_info = self.running_tasks[task_id]
                process = task_info['process']
                
                # 记录暂停信息
                log_file = task_info.get('log_file', os.path.join(self.log_dir, f'{task_id}_console.log'))
                with open(log_file, 'a', encoding='utf-8') as log_f:
                    log_f.write(f"\n⏸️ 任务暂停时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    log_f.write(f"📋 任务ID: {task_id}\n")
                    log_f.write(f"🔄 暂停方式: 终止进程树 (PID: {process.pid})\n")
                    log_f.write(f"{'='*80}\n\n")
                
                # 终止进程树（类似Ctrl+C效果）
                self._kill_process_tree(process.pid)
                
                # 删除运行标记
                del self.running_tasks[task_id]
                self._save_persistent_state()
                
                print(f"⏸️ 任务 {task_id} 进程树已终止 (PID: {process.pid})")
                
                return {"status": "success", "message": f"任务 {task_id} 已暂停"}
            except Exception as e:
                return {"status": "error", "message": f"暂停任务失败: {str(e)}"}
    
    def resume_task(self, task_id: str, agent_system_name: str = 'infiHelper') -> Dict:
        """恢复任务 - 从元数据文件读取原始参数重新启动"""
        # 检查是否有待恢复的工作
        if not self._check_task_has_pending_work(task_id):
            return {"status": "error", "message": f"任务 {task_id} 没有待恢复的工作"}
        
        with self.lock:
            if task_id in self.running_tasks:
                return {"status": "error", "message": f"任务 {task_id} 已在运行中"}
        
        # 从元数据文件读取原始参数
        metadata_file = os.path.join(self.log_dir, f'{task_id}_metadata.json')
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    task_metadata = json.load(f)
                
                original_instructions = task_metadata.get('user_instructions', [])
                original_agent_system = task_metadata.get('agent_system_name', agent_system_name)
                original_agent_name = task_metadata.get('agent_name', 'writing_agent')
                
                print(f"🔄 恢复任务 {task_id}，从元数据文件读取原始参数")
                print(f"📝 原始指令: {original_instructions}")
                print(f"🤖 原始Agent系统: {original_agent_system}")
                print(f"🎯 原始Agent名称: {original_agent_name}")
                
                # 使用原始参数重新启动（程序会自动从文件恢复状态）
                return self.start_task(task_id, original_agent_system, original_instructions, original_agent_name)
                
            except Exception as e:
                return {"status": "error", "message": f"读取任务元数据失败: {str(e)}"}
        else:
            return {"status": "error", "message": f"任务 {task_id} 的元数据文件不存在，无法恢复"}
    
    def is_task_running(self, task_id: str) -> bool:
        """检查任务是否在运行"""
        with self.lock:
            return task_id in self.running_tasks
    
    def get_task_logs(self, task_id: str) -> Dict:
        """获取任务日志"""
        with self.lock:
            if task_id in self.task_logs:
                log_info = self.task_logs[task_id]
                log_content = ""
                if os.path.exists(log_info.get('log_file', '')):
                    try:
                        with open(log_info['log_file'], 'r', encoding='utf-8') as f:
                            log_content = f.read()
                    except Exception as e:
                        log_content = f"读取日志失败: {e}"
                
                return {
                    "status": "success",
                    "log_info": log_info,
                    "log_content": log_content
                }
            else:
                return {"status": "error", "message": f"任务 {task_id} 的日志不存在"}
    
    def _check_task_has_pending_work(self, task_id: str) -> bool:
        """检查任务是否有未完成的工作"""
        # 检查share_context文件
        share_context_file = os.path.join(project_root, f'{task_id}_share_context.json')
        if not os.path.exists(share_context_file):
            share_context_file = os.path.join(project_root, 'conversations', f'{task_id}_share_context.json')
        
        if os.path.exists(share_context_file):
            try:
                with open(share_context_file, 'r', encoding='utf-8') as f:
                    context_data = json.load(f)
                
                # 检查current字段是否有内容
                current = context_data.get('current', {})
                if current.get('agents_status') or current.get('hierarchy'):
                    return True
            except Exception:
                pass
        
        # 检查栈文件是否为空
        stack_file = os.path.join(project_root, f'{task_id}_stack.json')
        if not os.path.exists(stack_file):
            stack_file = os.path.join(project_root, 'conversations', f'{task_id}_stack.json')
        
        if os.path.exists(stack_file):
            try:
                with open(stack_file, 'r', encoding='utf-8') as f:
                    stack_data = json.load(f)
                
                # 检查栈是否为空
                if stack_data.get('stack'):
                    return True
            except Exception:
                pass
        
        return False
    
    def _add_instruction_to_existing_task(self, task_id: str, new_instruction: str) -> Dict:
        """向现有任务添加新指令"""
        try:
            # 使用hierarchy_manager添加新指令
            from baseService.agent_hierarchy import get_cached_hierarchy_manager
            hierarchy_manager = get_cached_hierarchy_manager(task_id)
            
            # 添加新指令
            instruction_id = hierarchy_manager.start_new_instruction(new_instruction)
            
            return {
                "status": "success", 
                "message": f"指令已添加到任务 {task_id}",
                "instruction_id": instruction_id
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "message": f"添加指令失败: {str(e)}"
            }
    


# 全局任务管理器
task_manager = TaskManager()

@app.route('/api/task/create', methods=['POST'])
def create_task():
    """创建并启动新任务"""
    try:
        data = request.json
        task_id = data.get('task_id')
        agent_system_name = data.get('agent_system_name', 'infiHelper')
        agent_name = data.get('agent_name', 'writing_agent')
        user_input = data.get('user_input')
        
        if not task_id or not user_input:
            return jsonify({"status": "error", "message": "缺少必要参数: task_id 或 user_input"}), 400
        
        # 检查任务是否已在运行
        if task_manager.is_task_running(task_id):
            return jsonify({"status": "error", "message": f"任务 {task_id} 已在运行中"}), 400
        
        # 启动任务（传递指令列表和Agent名称）
        result = task_manager.start_task(task_id, agent_system_name, [user_input], agent_name)
        
        if result["status"] == "success":
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "message": f"创建任务失败: {str(e)}"}), 500

@app.route('/api/task/pause', methods=['POST'])
def pause_task():
    """暂停任务"""
    try:
        data = request.json
        task_id = data.get('task_id')
        
        if not task_id:
            return jsonify({"status": "error", "message": "缺少必要参数: task_id"}), 400
        
        result = task_manager.pause_task(task_id)
        
        if result["status"] == "success":
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "message": f"暂停任务失败: {str(e)}"}), 500

@app.route('/api/task/resume', methods=['POST'])
def resume_task():
    """恢复任务"""
    try:
        data = request.json
        task_id = data.get('task_id')
        agent_system_name = data.get('agent_system_name', 'infiHelper')
        
        if not task_id:
            return jsonify({"status": "error", "message": "缺少必要参数: task_id"}), 400
        
        result = task_manager.resume_task(task_id, agent_system_name)
        
        if result["status"] == "success":
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "message": f"恢复任务失败: {str(e)}"}), 500

@app.route('/api/task/conversation_history/<task_id>', methods=['GET'])
def get_conversation_history(task_id: str):
    """获取任务的历史对话"""
    try:
        # 读取share_context文件（检查多个可能的位置）
        share_context_file = os.path.join(project_root, f'{task_id}_share_context.json')
        if not os.path.exists(share_context_file):
            # 尝试在conversations目录下查找
            share_context_file = os.path.join(project_root, 'conversations', f'{task_id}_share_context.json')
        
        if not os.path.exists(share_context_file):
            return jsonify({"status": "error", "message": f"任务 {task_id} 的上下文文件不存在"}), 404
        
        with open(share_context_file, 'r', encoding='utf-8') as f:
            context_data = json.load(f)
        
        # 收集所有指令和agent消息
        messages = []
        
        # 处理当前指令
        current_instructions = context_data.get('current', {}).get('instructions', [])
        for instruction in current_instructions:
            messages.append({
                'type': 'user',
                'content': instruction['instruction'],
                'timestamp': instruction['start_time'],
                'instruction_id': instruction['instruction_id']
            })
        
        # 处理历史指令
        history = context_data.get('history', [])
        for hist_item in history:
            for instruction in hist_item.get('instructions', []):
                messages.append({
                    'type': 'user',
                    'content': instruction['instruction'],
                    'timestamp': instruction['start_time'],
                    'instruction_id': instruction['instruction_id']
                })
        
        # 收集所有agent的进度消息
        def collect_agent_messages(agents_status: Dict, timestamp_base: str):
            agent_messages = []
            for agent_id, agent_info in agents_status.items():
                if agent_info.get('agent_name') == 'judge_agent':
                    continue  # 跳过judge_agent
                
                start_time = agent_info.get('start_time')
                end_time = agent_info.get('end_time')
                progress = agent_info.get('progress', '')
                
                if start_time:
                    # 如果有结束时间，使用完整进度内容作为最终输出
                    if end_time:
                        agent_messages.append({
                            'type': 'assistant',
                            'content': progress,  # 完整的progress内容
                            'timestamp': end_time,
                            'agent_id': agent_id,
                            'agent_name': agent_info.get('agent_name'),
                            'progress': progress,  # 显式添加progress字段
                            'status': agent_info.get('status', 'completed')
                        })
                    else:
                        # 没有结束时间，使用当前进度
                        agent_messages.append({
                            'type': 'assistant',
                            'content': progress if progress else f"{agent_info.get('agent_name')} 已启动，正在处理任务...",
                            'timestamp': start_time,
                            'agent_id': agent_id,
                            'agent_name': agent_info.get('agent_name'),
                            'progress': progress,  # 显式添加progress字段
                            'status': agent_info.get('status', 'waiting')
                        })
            return agent_messages
        
        # 收集当前agent消息
        current_agents = context_data.get('current', {}).get('agents_status', {})
        messages.extend(collect_agent_messages(current_agents, 'current'))
        
        # 收集历史agent消息
        for hist_item in history:
            hist_agents = hist_item.get('agents_status', {})
            messages.extend(collect_agent_messages(hist_agents, 'history'))
        
        # 按时间排序
        messages.sort(key=lambda x: x['timestamp'])
        
        return jsonify({
            "status": "success",
            "task_id": task_id,
            "messages": messages,
            "total_count": len(messages)
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"获取对话历史失败: {str(e)}"}), 500

@app.route('/api/task/add_message', methods=['POST'])
def add_message():
    """添加新的用户消息 - 简化逻辑"""
    try:
        data = request.json
        task_id = data.get('task_id')
        new_message = data.get('message')
        agent_system_name = data.get('agent_system_name', 'infiHelper')
        agent_name = data.get('agent_name', 'writing_agent')
        
        print(f"📝 [add_message] 参数检查:")
        print(f"   - task_id: {task_id}")
        print(f"   - agent_system_name: {agent_system_name}")
        print(f"   - agent_name: {agent_name}")
        print(f"   - new_message: {new_message[:50]}...")
        
        if not task_id or not new_message:
            return jsonify({"status": "error", "message": "缺少必要参数: task_id 或 message"}), 400
        
        # 检查栈文件判断是否有任务存在
        stack_file = os.path.join(project_root, 'conversations', f'{task_id}_stack.json')
        has_existing_task = False
        
        if os.path.exists(stack_file):
            try:
                with open(stack_file, 'r', encoding='utf-8') as f:
                    stack_data = json.load(f)
                # 检查是否有待恢复的工作（栈非空或current有内容）
                has_existing_task = task_manager._check_task_has_pending_work(task_id)
            except:
                has_existing_task = False
        
        if has_existing_task:
            # 情况1: 有任务存在（运行中或已暂停）
            print(f"📝 检测到现有任务 {task_id}，添加新指令")
            
            # 统一先暂停（即使已经暂停也没关系）
            if task_manager.is_task_running(task_id):
                pause_result = task_manager.pause_task(task_id)
                if pause_result["status"] != "success":
                    return jsonify({"status": "error", "message": f"暂停任务失败: {pause_result['message']}"}), 400
                time.sleep(1)  # 等待暂停完成
            
            # 从元数据文件读取并更新指令列表
            metadata_file = os.path.join(task_manager.log_dir, f'{task_id}_metadata.json')
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    task_metadata = json.load(f)
                
                # 添加新指令到列表末尾（JSON数组保持顺序）
                user_instructions = task_metadata.get('user_instructions', [])
                user_instructions.append(new_message)
                
                # 更新元数据文件
                task_metadata['user_instructions'] = user_instructions
                task_metadata['last_modified'] = datetime.now().isoformat()
                # 如果元数据中没有agent_name，使用传入的agent_name
                if 'agent_name' not in task_metadata:
                    task_metadata['agent_name'] = agent_name
                
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(task_metadata, f, indent=2, ensure_ascii=False)
                
                print(f"📝 已添加指令到列表: {user_instructions}")
                
                # 使用更新后的指令列表重新启动
                original_agent_system = task_metadata.get('agent_system_name', agent_system_name)
                original_agent_name = task_metadata.get('agent_name', agent_name)
                result = task_manager.start_task(task_id, original_agent_system, user_instructions, original_agent_name)
                action = "添加指令并重新启动任务"
            else:
                return jsonify({"status": "error", "message": f"任务 {task_id} 的元数据文件不存在"}), 400
                
        else:
            # 情况2: 无任务存在，新建任务
            print(f"🆕 创建新任务 {task_id}")
            result = task_manager.start_task(task_id, agent_system_name, [new_message], agent_name)
            action = "创建新任务"
        
        if result["status"] == "success":
            return jsonify({
                "status": "success",
                "message": f"消息已添加，{action}",
                "action": action,
                "had_existing_task": has_existing_task
            }), 200
        else:
            return jsonify(result), 400
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"添加消息失败: {str(e)}"}), 500

@app.route('/api/systems/list', methods=['GET'])
def list_agent_systems():
    """获取所有可用的Agent系统列表"""
    try:
        agent_library_path = os.path.join(project_root, 'config', 'agent_library')
        
        if not os.path.exists(agent_library_path):
            return jsonify({"status": "success", "systems": []}), 200
        
        systems = []
        for item in os.listdir(agent_library_path):
            item_path = os.path.join(agent_library_path, item)
            if os.path.isdir(item_path):
                # 检查是否有配置文件
                has_configs = any(
                    f.endswith('.yaml') or f.endswith('.yml')
                    for f in os.listdir(item_path)
                    if f != 'merged_agent_configs.yaml'
                )
                
                systems.append({
                    'name': item,
                    'path': item_path,
                    'has_configs': has_configs,
                    'config_count': len([
                        f for f in os.listdir(item_path)
                        if (f.endswith('.yaml') or f.endswith('.yml')) and f != 'merged_agent_configs.yaml'
                    ])
                })
        
        return jsonify({
            "status": "success",
            "systems": systems,
            "total_count": len(systems)
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"获取系统列表失败: {str(e)}"}), 500

@app.route('/api/systems/upload', methods=['POST'])
def upload_agent_system():
    """上传Agent系统配置包"""
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "没有上传文件"}), 400
        
        file = request.files['file']
        system_name = request.form.get('system_name')
        
        if not system_name:
            return jsonify({"status": "error", "message": "缺少系统名称"}), 400
        
        if file.filename == '':
            return jsonify({"status": "error", "message": "文件名为空"}), 400
        
        if not file.filename.endswith('.zip'):
            return jsonify({"status": "error", "message": "只支持ZIP压缩包"}), 400
        
        # 创建目标目录
        target_dir = os.path.join(project_root, 'config', 'agent_library', system_name)
        os.makedirs(target_dir, exist_ok=True)
        
        # 保存并解压文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
            file.save(tmp_file.name)
            
            try:
                with zipfile.ZipFile(tmp_file.name, 'r') as zip_ref:
                    # 只解压yaml文件
                    for file_info in zip_ref.infolist():
                        if file_info.filename.endswith(('.yaml', '.yml')):
                            # 提取文件名（去掉路径）
                            filename = os.path.basename(file_info.filename)
                            if filename:  # 确保不是目录
                                target_path = os.path.join(target_dir, filename)
                                with zip_ref.open(file_info) as source, open(target_path, 'wb') as target:
                                    target.write(source.read())
                
                # 触发配置合并
                from baseService.config_merger import merge_agent_configs
                merge_agent_configs(system_name)
                
                # 统计解压的文件
                yaml_files = [f for f in os.listdir(target_dir) 
                             if f.endswith(('.yaml', '.yml')) and f != 'merged_agent_configs.yaml']
                
                return jsonify({
                    "status": "success",
                    "message": f"Agent系统 '{system_name}' 上传成功",
                    "system_name": system_name,
                    "extracted_files": yaml_files,
                    "file_count": len(yaml_files)
                }), 200
                
            finally:
                os.unlink(tmp_file.name)  # 删除临时文件
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"上传系统配置失败: {str(e)}"}), 500

@app.route('/api/task/status/<task_id>', methods=['GET'])
def get_task_status(task_id: str):
    """获取任务状态"""
    try:
        # 检查是否在运行
        is_running = task_manager.is_task_running(task_id)
        
        # 读取share_context文件（检查多个可能的位置）
        share_context_file = os.path.join(project_root, f'{task_id}_share_context.json')
        if not os.path.exists(share_context_file):
            # 尝试在conversations目录下查找
            share_context_file = os.path.join(project_root, 'conversations', f'{task_id}_share_context.json')
        
        context_data = None
        if os.path.exists(share_context_file):
            with open(share_context_file, 'r', encoding='utf-8') as f:
                context_data = json.load(f)
        
        # 获取日志信息
        log_info = None
        if task_id in task_manager.task_logs:
            log_info = task_manager.task_logs[task_id]
        
        return jsonify({
            "status": "success",
            "task_id": task_id,
            "is_running": is_running,
            "context_data": context_data,
            "log_info": log_info
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"获取任务状态失败: {str(e)}"}), 500

@app.route('/api/task/logs/<task_id>', methods=['GET'])
def get_task_logs_api(task_id: str):
    """获取任务的控制台日志"""
    result = task_manager.get_task_logs(task_id)
    if result["status"] == "success":
        return jsonify(result), 200
    else:
        return jsonify(result), 404

@app.route('/api/task/metadata/<task_id>', methods=['GET'])
def get_task_metadata(task_id: str):
    """获取任务的元数据信息"""
    try:
        metadata_file = os.path.join(task_manager.log_dir, f'{task_id}_metadata.json')
        
        if not os.path.exists(metadata_file):
            return jsonify({
                "status": "error", 
                "message": f"任务 {task_id} 的元数据文件不存在"
            }), 404
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        print(f"📋 [get_task_metadata] 返回元数据:")
        print(f"   - task_id: {metadata.get('task_id')}")
        print(f"   - agent_system_name: {metadata.get('agent_system_name')}")
        print(f"   - agent_name: {metadata.get('agent_name')}")
        print(f"   - user_instructions: {metadata.get('user_instructions')}")
        print(f"   - created_time: {metadata.get('created_time')}")
        
        return jsonify({
            "status": "success",
            "task_id": task_id,
            "metadata": metadata
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"读取任务元数据失败: {str(e)}"
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "running_tasks": len(task_manager.running_tasks),
        "total_task_logs": len(task_manager.task_logs)
    }), 200

if __name__ == '__main__':
    print("🚀 Multi-Level Agent API Server v3 (Fixed) 启动中...")
    print(f"📁 项目根目录: {project_root}")
    print(f"📝 日志目录: {task_manager.log_dir}")
    print("🌐 API服务器已启动，访问 http://localhost:5002")
    
    app.run(host='0.0.0.0', port=5002, debug=True, threaded=True) 