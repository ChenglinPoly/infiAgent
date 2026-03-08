#!/bin/bash
# 启动 Web UI 服务器（direct-tools 模式）

# 设置 UTF-8 编码（兼容 macOS）
export LANG=${LANG:-en_US.UTF-8}
export LC_ALL=${LC_ALL:-en_US.UTF-8}

# 获取脚本所在目录（server 目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 切换到 server 目录
cd "$SCRIPT_DIR"

# 检查 conda 环境（抑制所有警告和错误信息）
if ! command -v conda &> /dev/null 2>&1; then
    printf "❌ 未找到 conda 命令\n"
    exit 1
fi

# 抑制 conda 相关的警告和错误
export CONDA_AUTO_UPDATE_CONDA=false
export PYTHONWARNINGS="ignore::FutureWarning"
export CONDARC=/dev/null 2>/dev/null

# 激活 conda 环境（如果存在，抑制所有输出）
if conda env list 2>/dev/null | grep -q "paper_agent"; then
    # 初始化 conda（抑制所有输出）
    eval "$(conda shell.bash hook 2>/dev/null)" 2>/dev/null
    if [ -f "$(conda info --base 2>/dev/null)/etc/profile.d/conda.sh" ]; then
        source "$(conda info --base 2>/dev/null)/etc/profile.d/conda.sh" 2>/dev/null
    fi
    # 激活环境（抑制所有输出）
    conda activate paper_agent 2>/dev/null || true
fi

# 检查端口是否被占用
WEB_PORT=${PORT:-22228}

if lsof -ti:$WEB_PORT &> /dev/null; then
    printf "⚠️  Web UI 端口 %s 已被占用\n" "$WEB_PORT"
    printf "💡 使用以下命令停止现有服务器：\n"
    printf "   ./stop.sh\n"
    exit 1
fi

PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# 询问用户 workspace 路径
printf "\n"
printf "📂 设置工作空间路径（Workspace Root）\n"
printf "   💡 直接回车将使用当前目录作为工作空间（与 CLI 模式相同）\n"
printf "   💡 输入绝对路径可指定自定义工作空间\n"
read -p "   请输入工作空间路径 (回车使用当前目录): " workspace_input

# 处理用户输入
if [ -z "$workspace_input" ]; then
    # 用户直接回车，使用当前工作目录（和 CLI 模式一样）
    WORKSPACE_ROOT=$(pwd)
    printf "   ✅ 使用当前目录作为工作空间: %s\n" "$WORKSPACE_ROOT"
else
    # 用户输入了路径
    workspace_input=$(printf "%s" "$workspace_input" | xargs)  # 去除首尾空格
    if [ -z "$workspace_input" ]; then
        # 输入全是空格，当作回车处理
        WORKSPACE_ROOT=$(pwd)
        printf "   ✅ 使用当前目录作为工作空间: %s\n" "$WORKSPACE_ROOT"
    else
        # 检查路径是否存在或是有效路径
        if [ -d "$workspace_input" ] || mkdir -p "$workspace_input" 2>/dev/null; then
            # 转换为绝对路径
            WORKSPACE_ROOT=$(cd "$workspace_input" 2>/dev/null && pwd || printf "%s" "$workspace_input")
            printf "   ✅ 使用指定工作空间: %s\n" "$WORKSPACE_ROOT"
        else
            # 路径无效，使用当前目录
            WORKSPACE_ROOT=$(pwd)
            printf "   ⚠️  输入路径无效，使用当前目录作为工作空间: %s\n" "$WORKSPACE_ROOT"
        fi
    fi
fi

# 启动 Web UI 服务器
printf "\n"
printf "🚀 启动 Web UI 服务器...\n"
printf "📂 服务器工作目录: %s\n" "$SCRIPT_DIR"
printf "📂 用户工作空间: %s\n" "$WORKSPACE_ROOT"
printf "🌐 Web UI 地址: http://localhost:%s\n" "$WEB_PORT"
printf "\n"
printf "💡 提示: 使用 Ctrl+C 停止服务器，或运行 ./stop.sh\n"
printf "\n"

WORKSPACE_ROOT="$WORKSPACE_ROOT" PORT=$WEB_PORT python server.py

