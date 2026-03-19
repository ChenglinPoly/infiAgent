#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档转换工具 - 调用远程 Pandoc API
舍弃，等待市面上出现免费的文档类型互转的高质量 api 吧。（tex 转万物或者 md 转万物）
"""

from pathlib import Path
from typing import Dict, Any
import requests
import yaml
import zipfile
import tempfile
import shutil
from .file_tools import BaseTool, get_abs_path


def load_convert_api_config() -> str:
    """读取文档转换 API 配置"""
    try:
        # 查找配置文件
        config_path = Path(__file__).parent.parent.parent / "config" / "run_env_config" / "document_convert_api.yaml"
        
        if not config_path.exists():
            return "如果有的话:8000/"  # 默认地址
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            api_server = config.get("api_server", "http://192.168.31.4:8000/")
            
            # 确保以 / 结尾
            if not api_server.endswith('/'):
                api_server += '/'
            
            return api_server
    except Exception:
        return "http://192.168.31.4:8000/"


class MarkdownToPdfTool(BaseTool):
    """Markdown 转 PDF 工具"""
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Markdown 转 PDF
        
        Parameters:
            source_path (str): Markdown 文件相对路径
            output_path (str, optional): 输出 PDF 相对路径
            engine (str, optional): PDF 引擎 (pdflatex/xelatex/lualatex)，默认 xelatex
        """
        try:
            source_path = parameters.get("source_path")
            output_path = parameters.get("output_path")
            engine = parameters.get("engine", "xelatex")
            
            if not source_path:
                return {
                    "status": "error",
                    "output": "",
                    "error": "source_path is required"
                }
            
            # 读取 Markdown 文件
            abs_source = get_abs_path(task_id, source_path)
            if not abs_source.exists():
                return {
                    "status": "error",
                    "output": "",
                    "error": f"Source file not found: {source_path}"
                }
            
            # 准备输出路径
            if not output_path:
                output_path = str(Path(source_path).with_suffix('.pdf'))
            
            abs_output = get_abs_path(task_id, output_path)
            abs_output.parent.mkdir(parents=True, exist_ok=True)
            
            # 调用转换 API
            api_server = load_convert_api_config()
            url = f"{api_server}convert/md-to-pdf"
            
            with open(abs_source, 'rb') as f:
                files = {'file': (abs_source.name, f, 'text/markdown')}
                params = {'engine': engine}
                
                response = requests.post(url, files=files, params=params, timeout=120)
                response.raise_for_status()
            
            # 保存 PDF
            with open(abs_output, 'wb') as f:
                f.write(response.content)
            
            file_size = abs_output.stat().st_size / 1024  # KB
            
            return {
                "status": "success",
                "output": f"PDF 已生成: {output_path} ({file_size:.1f} KB)",
                "error": ""
            }
            
        except requests.RequestException as e:
            return {
                "status": "error",
                "output": "",
                "error": f"API 调用失败: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }


class TexToPdfTool(BaseTool):
    """LaTeX 项目转 PDF 工具"""
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        LaTeX 项目转 PDF
        
        Parameters:
            project_dir (str): LaTeX 项目目录相对路径
            main_file (str): 主 tex 文件名（如 main.tex）
            output_path (str, optional): 输出 PDF 相对路径
            engine (str, optional): LaTeX 引擎，默认 xelatex
        """
        try:
            project_dir = parameters.get("project_dir")
            main_file = parameters.get("main_file")
            output_path = parameters.get("output_path")
            engine = parameters.get("engine", "xelatex")
            
            if not project_dir:
                return {
                    "status": "error",
                    "output": "",
                    "error": "project_dir is required"
                }
            
            if not main_file:
                return {
                    "status": "error",
                    "output": "",
                    "error": "main_file is required"
                }
            
            # 获取项目目录
            abs_project_dir = get_abs_path(task_id, project_dir)
            if not abs_project_dir.exists():
                return {
                    "status": "error",
                    "output": "",
                    "error": f"Project directory not found: {project_dir}"
                }
            
            # 检查主文件是否存在
            main_file_path = abs_project_dir / main_file
            if not main_file_path.exists():
                return {
                    "status": "error",
                    "output": "",
                    "error": f"Main file not found: {main_file} in {project_dir}"
                }
            
            # 创建 tmp 目录
            workspace = Path(task_id)
            tmp_dir = workspace / "tmp"
            tmp_dir.mkdir(exist_ok=True)
            
            # 打包项目为 ZIP
            zip_path = tmp_dir / f"{abs_project_dir.name}.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in abs_project_dir.rglob('*'):
                    if file_path.is_file():
                        # 计算相对路径
                        arcname = file_path.relative_to(abs_project_dir)
                        zipf.write(file_path, arcname)
            
            # 准备输出路径
            if not output_path:
                output_path = str(Path(project_dir) / f"{Path(main_file).stem}.pdf")
            
            abs_output = get_abs_path(task_id, output_path)
            abs_output.parent.mkdir(parents=True, exist_ok=True)
            
            # 调用转换 API
            api_server = load_convert_api_config()
            url = f"{api_server}convert/tex-zip-to-pdf"
            
            with open(zip_path, 'rb') as f:
                files = {'file': (zip_path.name, f, 'application/zip')}
                params = {
                    'main_file': main_file,
                    'engine': engine
                }
                
                response = requests.post(url, files=files, params=params, timeout=300)
                response.raise_for_status()
            
            # 保存 PDF
            with open(abs_output, 'wb') as f:
                f.write(response.content)
            
            file_size = abs_output.stat().st_size / 1024  # KB
            
            # 清理临时 ZIP 文件
            zip_path.unlink()
            
            return {
                "status": "success",
                "output": f"PDF 已生成: {output_path} ({file_size:.1f} KB)",
                "error": ""
            }
            
        except requests.RequestException as e:
            return {
                "status": "error",
                "output": "",
                "error": f"API 调用失败: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }


class MarkdownToDocxTool(BaseTool):
    """Markdown 转 Word 工具"""
    
    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Markdown 转 DOCX
        
        Parameters:
            source_path (str): Markdown 文件相对路径
            output_path (str, optional): 输出 DOCX 相对路径
        """
        try:
            source_path = parameters.get("source_path")
            output_path = parameters.get("output_path")
            
            if not source_path:
                return {
                    "status": "error",
                    "output": "",
                    "error": "source_path is required"
                }
            
            # 读取 Markdown 文件
            abs_source = get_abs_path(task_id, source_path)
            if not abs_source.exists():
                return {
                    "status": "error",
                    "output": "",
                    "error": f"Source file not found: {source_path}"
                }
            
            # 准备输出路径
            if not output_path:
                output_path = str(Path(source_path).with_suffix('.docx'))
            
            abs_output = get_abs_path(task_id, output_path)
            abs_output.parent.mkdir(parents=True, exist_ok=True)
            
            # 调用转换 API
            api_server = load_convert_api_config()
            url = f"{api_server}convert/md-to-doc"
            
            with open(abs_source, 'rb') as f:
                files = {'file': (abs_source.name, f, 'text/markdown')}
                
                response = requests.post(url, files=files, timeout=120)
                response.raise_for_status()
            
            # 保存 DOCX
            with open(abs_output, 'wb') as f:
                f.write(response.content)
            
            file_size = abs_output.stat().st_size / 1024  # KB
            
            return {
                "status": "success",
                "output": f"DOCX 已生成: {output_path} ({file_size:.1f} KB)",
                "error": ""
            }
            
        except requests.RequestException as e:
            return {
                "status": "error",
                "output": "",
                "error": f"API 调用失败: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e)
            }

