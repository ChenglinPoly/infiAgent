#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MLA V3 - Multi-Level Agent System
安装配置
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取 README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding='utf-8') if readme_file.exists() else ""

# 读取依赖
requirements_file = Path(__file__).parent / "requirements.txt"
if requirements_file.exists():
    requirements = [
        line.strip() for line in requirements_file.read_text(encoding='utf-8').strip().split('\n')
        if line.strip() and not line.strip().startswith('#')
    ]
else:
    requirements = []

setup(
    name="mla-agent",
    version="3.0.0",
    author="Chenglin Yu",
    author_email="yuchenglin96@qq.com",
    description="Multi-Level Agent System for complex task automation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ChenglinPoly/Multi-Level-Agent",
    packages=find_packages(exclude=['test*', 'task_*', 'conversations']),
    py_modules=['start'],
    include_package_data=True,
    package_data={
        'MLA_V3': [
            'config/**/*.yaml',
            'tool_server_lite/**/*.py',
            'tool_server_lite/**/*.md',
            'tool_server_lite/requirements.txt',
        ],
    },
    install_requires=requirements,
    python_requires='>=3.9',
    entry_points={
        'console_scripts': [
            'mla-agent=start:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
)
