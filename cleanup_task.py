#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# API导入 - 任务清理工具

import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.agent_hierarchy import get_cached_hierarchy_manager

def cleanup_task(task_id: str):
    """清理指定任务的所有状态"""
    print(f"🧹 开始清理任务: {task_id}")
    
    # 获取层级管理器
    manager = get_cached_hierarchy_manager(task_id)
    
    # 打印当前状态
    print("\n📊 清理前状态:")
    manager.print_hierarchy_tree()
    
    # 修复状态不一致
    manager.fix_inconsistent_state()
    
    # 强制清理current任务
    print("\n🔄 强制清理current任务...")
    manager.clear_current_task()
    
    # 清理文件
    print("\n🗑️ 清理相关文件...")
    manager.cleanup_files()
    
    print(f"\n✅ 任务 {task_id} 清理完成")

if __name__ == '__main__':
    task_id = "example_test_16"
    cleanup_task(task_id) 