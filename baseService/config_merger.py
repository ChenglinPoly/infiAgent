#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置文件合并工具
将 config/agent_configs/ 目录下的所有 YAML 文件合并到 baseService/agent_configs.yaml
"""

import os
import yaml
import glob
from typing import Dict, Any
from pathlib import Path


def represent_str(dumper, data):
    """自定义字符串表示器，对多行字符串使用 | 样式"""
    if '\n' in data:
        # 确保字符串末尾有换行符，这样使用 | 样式时格式会正确
        if not data.endswith('\n'):
            data = data + '\n'
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


# 创建自定义的 Dumper 类
class CustomYamlDumper(yaml.SafeDumper):
    def choose_scalar_style(self):
        # 重写标量样式选择逻辑
        if self.analysis is None:
            self.analysis = self.analyze_scalar(self.event.value)
        
        # 如果是多行字符串，强制使用字面量样式
        if self.event.tag == 'tag:yaml.org,2002:str' and '\n' in self.event.value:
            return '|'
        
        # 其他情况使用默认逻辑
        return super().choose_scalar_style()


def represent_multiline_str(dumper, data):
    """专门处理多行字符串的表示器，强制使用字面量样式"""
    if '\n' in data:
        # 强制使用 | 样式处理多行字符串，不管内容多复杂
        # 这会覆盖YAML库的默认启发式选择
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


# 注册自定义表示器到自定义 Dumper，使用更高的优先级
CustomYamlDumper.add_representer(str, represent_multiline_str)


def merge_agent_configs(agent_system_name: str = None):
    """
    将指定Agent系统的配置文件合并到对应的目标位置
    
    Args:
        agent_system_name (str): Agent系统名称，如'infiHelper'。如果为None，使用默认的config/agent_configs/
    """
    # 获取项目根目录
    current_dir = os.path.dirname(__file__)
    project_root = os.path.dirname(current_dir)
    
    # 如果没有指定agent_system_name，默认使用infiHelper
    if not agent_system_name:
        agent_system_name = "infiHelper"
    
    # 使用指定的Agent系统配置
    source_dir = os.path.join(project_root, 'config', 'agent_library', agent_system_name)
    # 为每个Agent系统创建独立的配置文件
    target_file = os.path.join(project_root, 'config', 'agent_library', agent_system_name, 'merged_agent_configs.yaml')
    
    # 检查源目录是否存在
    if not os.path.exists(source_dir):
        print(f"警告：源目录 {source_dir} 不存在")
        return
    
    merged_config = {}
    
    # 获取目录下所有yaml文件
    yaml_files = glob.glob(os.path.join(source_dir, '*.yaml')) + \
                 glob.glob(os.path.join(source_dir, '*.yml'))
    
    # 排除merged_agent_configs.yaml文件，避免循环引用
    yaml_files = [f for f in yaml_files if not f.endswith('merged_agent_configs.yaml')]
    
    # 按文件名排序，确保合并顺序一致
    yaml_files.sort()
    
    for yaml_file in yaml_files:
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if config:
                    # 合并配置
                    for key, value in config.items():
                        if key in merged_config and isinstance(merged_config[key], dict) and isinstance(value, dict):
                            # 如果是字典类型，进行深度合并
                            merged_config[key].update(value)
                        else:
                            merged_config[key] = value
            # print(f"已合并配置文件: {os.path.basename(yaml_file)}")
        except Exception as e:
            print(f"警告：加载配置文件 {yaml_file} 时出错: {e}")
    
    # 写入合并后的配置到目标文件
    try:
        # 确保目标目录存在
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        
        with open(target_file, 'w', encoding='utf-8') as f:
            yaml.dump(merged_config, f, 
                     Dumper=CustomYamlDumper,
                     default_flow_style=False, 
                     allow_unicode=True, 
                     indent=2,
                     width=float('inf'),  # 防止自动换行
                     sort_keys=False)  # 保持原始键的顺序
        
        # print(f"配置文件已成功合并到: {target_file}")
        # print(f"合并了 {len(yaml_files)} 个配置文件")
        
    except Exception as e:
        print(f"错误：写入合并配置文件时出错: {e}")


def ensure_merged_config(agent_system_name: str = None):
    """
    确保指定Agent系统的配置文件是最新的合并版本
    
    Args:
        agent_system_name (str): Agent系统名称
    """
    try:
        merge_agent_configs(agent_system_name)
    except Exception as e:
        print(f"警告：合并配置文件时出错: {e}")

def get_agent_config_path(agent_system_name: str = None) -> str:
    """
    获取指定Agent系统的配置文件路径
    
    Args:
        agent_system_name (str): Agent系统名称，如果为None则默认使用infiHelper
        
    Returns:
        str: 配置文件路径
    """
    current_dir = os.path.dirname(__file__)
    project_root = os.path.dirname(current_dir)
    
    # 如果没有指定agent_system_name，默认使用infiHelper
    if not agent_system_name:
        agent_system_name = "infiHelper"
    
    return os.path.join(project_root, 'config', 'agent_library', agent_system_name, 'merged_agent_configs.yaml')


if __name__ == "__main__":
    merge_agent_configs() 