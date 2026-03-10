#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill 部署工具 - 将 skill 从全局仓库复制到 workspace
"""

import shutil
from pathlib import Path
from typing import Dict, Any

from .file_tools import BaseTool, get_abs_path
from utils.user_paths import get_user_skills_library_root


class LoadSkillTool(BaseTool):
    """
    Skill 部署工具 - 将指定 skill 从主 skills 目录（默认 ~/.agent/skills）复制到 workspace/.skills/
    
    部署后 Agent 可以通过 file_read 读取 .skills/{skill_name}/SKILL.md 获取详细指令，
    并通过 execute_command 运行 .skills/{skill_name}/scripts/ 中的脚本。
    """
    
    def __init__(self):
        super().__init__()
        self.skills_library = get_user_skills_library_root()
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 skill 从全局仓库部署到 workspace
        
        Parameters:
            skill_name (str): 要部署的 skill 名称（对应 skills_library 下的文件夹名）
        
        Returns:
            status: "success" 或 "error"
            output: 部署结果信息
        """
        try:
            skill_name = parameters.get("skill_name")
            
            if not skill_name:
                return {
                    "status": "error",
                    "output": "",
                    "error": "缺少必需参数: skill_name"
                }
            
            # 源路径
            source_dir = self.skills_library / skill_name
            source_skill_md = source_dir / "SKILL.md"
            
            if not source_dir.is_dir() or not source_skill_md.exists():
                # 列出可用的 skills
                available = []
                if self.skills_library.exists():
                    for d in sorted(self.skills_library.iterdir()):
                        if d.is_dir() and (d / "SKILL.md").exists():
                            available.append(d.name)
                
                available_str = ", ".join(available) if available else "（无可用 skill）"
                return {
                    "status": "error",
                    "output": "",
                    "error": f"Skill '{skill_name}' 不存在。可用的 skills: {available_str}"
                }
            
            # 目标路径：workspace/.skills/{skill_name}/
            target_dir = get_abs_path(task_id, f".skills/{skill_name}")
            
            # 如果已存在，先删除（更新部署）
            if target_dir.exists():
                shutil.rmtree(target_dir)
            
            # 复制整个 skill 文件夹
            shutil.copytree(source_dir, target_dir)
            
            # 统计复制的文件
            file_count = sum(1 for _ in target_dir.rglob("*") if _.is_file())
            
            # 列出 skill 内容结构
            structure_parts = []
            for item in sorted(target_dir.rglob("*")):
                rel = item.relative_to(target_dir)
                if item.is_dir():
                    structure_parts.append(f"  [dir] {rel}/")
                else:
                    size_kb = item.stat().st_size / 1024
                    structure_parts.append(f"  [file] {rel} ({size_kb:.1f}KB)")
            
            structure_str = "\n".join(structure_parts) if structure_parts else "  (空)"
            
            output = (
                f"✅ Skill '{skill_name}' 已部署到 workspace\n"
                f"   位置: ./.skills/{skill_name}/\n"
                f"   文件数: {file_count}\n"
                f"   结构:\n{structure_str}\n\n"
                f"📖 下一步: 使用 file_read 读取 ./.skills/{skill_name}/SKILL.md 获取详细指令"
            )
            
            skill_md_text = source_skill_md.read_text(encoding='utf-8')
            return {
                "status": "success",
                "output": output,
                "error": "",
                "_skill_name": skill_name,
                "_skill_abs_path": str(source_dir),
                "_workspace_skill_path": str(target_dir),
                "_skill_md_text": skill_md_text
            }
        
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": f"部署 skill 失败: {str(e)}"
            }


class OffloadSkillTool(BaseTool):
    """
    Skill 卸载工具 - 仅从当前运行上下文中卸载 skill.md 的注入内容。
    不删除磁盘上的 skill 文件。
    """

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        skill_name = str(parameters.get("skill_name") or "").strip()
        if not skill_name:
            return {
                "status": "error",
                "output": "",
                "error": "缺少必需参数: skill_name"
            }
        return {
            "status": "success",
            "output": f"已请求从当前上下文卸载 skill: {skill_name}",
            "error": "",
            "_offload_skill_name": skill_name
        }


class FreshTool(BaseTool):
    """
    Fresh 工具 - 请求在安全点刷新运行时配置/工具注册/提示词缓存。
    支持可选 task_id：
    - 不传：fresh 当前 task
    - 传入 task_id：fresh 对应 task；若不在运行则后台 resume
    """

    name = "fresh"

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        reason = str(parameters.get("reason") or "").strip()
        target_task_id = str(parameters.get("task_id") or "").strip()
        effective_task_id = target_task_id or task_id
        if effective_task_id == task_id:
            output = "已请求 fresh，系统将在安全点重载配置并续跑当前任务。"
        else:
            output = f"已请求 fresh task: {effective_task_id}。若该任务未在运行，将重载配置后后台 resume。"
        return {
            "status": "success",
            "output": output,
            "error": "",
            "_fresh_requested": True,
            "_fresh_reason": reason,
            "_fresh_task_id": effective_task_id
        }
