#!/bin/bash
set -e

# API导入 - Docker启动脚本

echo "🐳 Multi-Level Agent API Server Docker 启动中..."
echo "📁 工作目录: $(pwd)"
echo "🔧 检查配置文件..."

# 检查并处理外部配置文件
CONFIG_DIR="/app/config/run_env_config"

# 检查tool_config.yaml
if [ ! -f "$CONFIG_DIR/tool_config.yaml" ]; then
    echo "⚠️ 未找到外部 tool_config.yaml，使用默认配置"
    # 检测宿主机地址
    HOST_IP=${TOOLS_SERVER_HOST:-192.168.31.211}
    cat > "$CONFIG_DIR/tool_config.yaml" << EOF
# 工具服务器配置（Docker环境）
tools_server: "http://${HOST_IP}:8001/"

# 其他配置项
# timeout: 30
# max_retries: 3
EOF
else
    echo "✅ 使用外部 tool_config.yaml"
    # 检查是否需要替换localhost地址
    if grep -q "127.0.0.1\|localhost" "$CONFIG_DIR/tool_config.yaml"; then
        echo "🔧 检测到localhost地址，建议使用环境变量 TOOLS_SERVER_HOST 指定宿主机地址"
        echo "   当前配置："
        grep "tools_server" "$CONFIG_DIR/tool_config.yaml" || echo "   未找到tools_server配置"
        echo "   建议配置：tools_server: \"http://host.docker.internal:8001/\""
    fi
fi

# 检查llm_config.yaml
if [ ! -f "$CONFIG_DIR/llm_config.yaml" ]; then
    echo "⚠️ 未找到外部 llm_config.yaml，使用默认配置"
    cat > "$CONFIG_DIR/llm_config.yaml" << EOF
# 基于 LiteLLM 的简化 LLM 配置文件
default:
  temperature: 0
  max_tokens: 0

environment_variables: {}

# 官方API配置
openai:
  official:
    api_key: ""
    models:
      - "gpt-4o"
      - "gpt-4o-mini"

claude:
  official:
    api_key: ""
    models:
      - "claude-3-5-sonnet-20241022"

# Custom API 配置
custom:
  openai_format:
    api_key: "\${CUSTOM_API_KEY:-}"
    base_url: "\${CUSTOM_BASE_URL:-https://openrouter.ai/api/v1}"
    models:
      - "google/gemini-2.5-flash"
EOF
else
    echo "✅ 使用外部 llm_config.yaml"
fi

# 检查Agent系统配置
AGENT_LIBRARY_DIR="/app/config/agent_library"
if [ ! -d "$AGENT_LIBRARY_DIR" ] || [ -z "$(ls -A $AGENT_LIBRARY_DIR)" ]; then
    echo "⚠️ 未找到Agent系统配置，复制默认配置"
    mkdir -p "$AGENT_LIBRARY_DIR"
    
    # 如果存在原始配置，复制到agent_library
    if [ -d "/app/config/agent_configs" ]; then
        cp -r "/app/config/agent_configs" "$AGENT_LIBRARY_DIR/infiHelper"
        echo "✅ 已复制默认Agent配置到 infiHelper 系统"
    fi
else
    echo "✅ 使用外部Agent系统配置"
fi

# 显示配置信息
echo "📋 配置文件状态:"
echo "   🔧 tool_config.yaml: $([ -f "$CONFIG_DIR/tool_config.yaml" ] && echo "✅" || echo "❌")"
echo "   🤖 llm_config.yaml: $([ -f "$CONFIG_DIR/llm_config.yaml" ] && echo "✅" || echo "❌")"
echo "   📚 Agent系统数量: $(ls -1 $AGENT_LIBRARY_DIR | wc -l)"

# 显示环境变量
echo "🌍 环境变量:"
echo "   CUSTOM_API_KEY: ${CUSTOM_API_KEY:+[已设置]} ${CUSTOM_API_KEY:-[未设置]}"
echo "   CUSTOM_BASE_URL: ${CUSTOM_BASE_URL:-[未设置]}"
echo "   OPENAI_API_KEY: ${OPENAI_API_KEY:+[已设置]} ${OPENAI_API_KEY:-[未设置]}"
echo "   ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:+[已设置]} ${ANTHROPIC_API_KEY:-[未设置]}"

# 确保日志目录权限
chmod -R 755 /app/logs

echo "🚀 启动 Multi-Level Agent API Server..."
echo "🌐 服务地址: http://localhost:5002"

# 执行传入的命令
exec "$@" 