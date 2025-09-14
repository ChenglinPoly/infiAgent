# LLM 客户端配置指南

## 概述

新的 LLM 客户端支持三大主流厂商的 API：
- **OpenAI**: GPT-4o, GPT-4o-mini, O1 等模型
- **Claude**: Claude-3.5-Sonnet, Claude-4 等模型  
- **Gemini**: Gemini-2.5-Flash, Gemini-2.5-Pro 等模型

每个厂商都支持**官方 API** 和**自定义代理 API** 两种配置方式。

## 配置方式

### 1. 环境变量配置（推荐）

创建 `.env` 文件或设置系统环境变量：

```bash
# OpenAI 官方 API
export OPENAI_API_KEY="your_openai_api_key_here"

# Claude 官方 API  
export ANTHROPIC_API_KEY="your_anthropic_api_key_here"

# Gemini 官方 API
export GEMINI_API_KEY="your_gemini_api_key_here"

# 自定义代理 API 示例
export OPENAI_CUSTOM_API_KEY="your_custom_key"
export OPENAI_CUSTOM_BASE_URL="https://your-proxy.com/v1"
export OPENAI_CUSTOM_MODELS="gpt-4o,gpt-4o-mini,custom-model"
```

### 2. 配置文件

修改 `llm_config.yaml` 文件：

```yaml
# 官方 API 配置
openai:
  official:
    api_key: "your_openai_api_key"
    base_url: "https://api.openai.com/v1"
    models:
      - "gpt-4o"
      - "gpt-4o-mini"

claude:
  official:
    api_key: "your_anthropic_api_key"
    base_url: "https://api.anthropic.com"
    models:
      - "claude-3-5-sonnet-20241022"
      - "claude-3-7-sonnet-20250219"

gemini:
  official:
    api_key: "AIzaSyCgVOK3mtlF673k6n1nu-bx_kZ8JB5xe08"  # 已配置的 Gemini API 密钥
    base_url: "https://generativelanguage.googleapis.com"
    models:
      - "gemini-2.5-flash"
      - "gemini-2.5-pro"

# 自定义代理 API 配置
openai:
  custom:
    api_key: "your_custom_key"
    base_url: "https://your-proxy.com/v1"
    models:
      - "custom-model-1"
      - "custom-model-2"
```

## 使用示例

### 基本使用

```python
from baseService.llm_client import LLMClient, ChatMessage, ModelType

# 创建客户端
client = LLMClient()

# 发送消息
history = [
    ChatMessage(role="user", content="你好，请介绍一下你自己")
]

response = client.chat(
    history=history,
    model=ModelType.GEMINI_2_5_FLASH,
    tool_list=["file_write"]  # 可选：启用工具调用
)

print(f"回复: {response.output}")
```

### 使用自定义代理

```python
# 优先使用自定义代理 API
client = LLMClient(use_custom_apis=True)

response = client.chat(
    history=history,
    model=ModelType.GPT_4O,
)
```

### 强制工具调用

所有模型默认启用强制工具调用模式：

```python
response = client.chat(
    history=history,
    model=ModelType.CLAUDE_3_5_SONNET,
    tool_list=["file_write", "execute_shell"],
    tool_choice="any"  # 强制调用任意工具
)
```

## 环境变量说明

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `OPENAI_API_KEY` | OpenAI 官方 API 密钥 | `sk-...` |
| `ANTHROPIC_API_KEY` | Claude 官方 API 密钥 | `sk-ant-...` |
| `GEMINI_API_KEY` | Gemini 官方 API 密钥 | `AIzaSy...` |
| `*_CUSTOM_API_KEY` | 自定义代理 API 密钥 | `your_key` |
| `*_CUSTOM_BASE_URL` | 自定义代理 API 基础 URL | `https://api.example.com` |
| `*_CUSTOM_MODELS` | 自定义代理支持的模型列表 | `model1,model2,model3` |

## 特性

### 1. 原生 Gemini API 支持

使用 Google 官方的 `google-genai` SDK，支持：
- 原生工具调用
- 强制工具调用模式 (`mode=ANY`)
- 完整的响应处理

### 2. 智能客户端选择

- 优先使用官方 API（性能更好、更稳定）
- 自动回退到自定义代理 API
- 支持手动指定使用自定义 API

### 3. 统一的工具调用

所有厂商都支持强制工具调用：
- OpenAI: `tool_choice="required"`
- Claude: `tool_choice={"type": "any"}`
- Gemini: `mode="ANY"`

### 4. 错误处理和重试

- 详细的错误信息
- 网络超时处理
- API 密钥验证

## 迁移指南

### 从旧版本迁移

1. **移除硬编码的 API 信息**：
   ```python
   # 旧版本
   client = LLMClient(api_key="sk-...", base_url="https://...")
   
   # 新版本
   client = LLMClient()  # 从环境变量或配置文件读取
   ```

2. **设置环境变量**：
   ```bash
   export GEMINI_API_KEY="your_gemini_key"
   export OPENAI_API_KEY="your_openai_key"
   export ANTHROPIC_API_KEY="your_claude_key"
   ```

3. **更新模型调用**：
   ```python
   # 现在支持原生 Gemini API
   response = client.chat(
       history=history,
       model=ModelType.GEMINI_2_5_FLASH,  # 使用原生 API
       tool_list=["file_write"]
   )
   ```

## 故障排除

### 常见问题

1. **Gemini API 初始化失败**
   ```
   警告：未安装 google-genai 库
   ```
   解决：`pip install google-genai`

2. **API 密钥无效**
   ```
   error_information: "API密钥无效或未授权"
   ```
   解决：检查环境变量中的 API 密钥是否正确

3. **模型不可用**
   ```
   警告: 工具 'xxx' 未找到
   ```
   解决：检查 `agent_configs.yaml` 中的工具定义

### 调试模式

启用详细日志：

```python
import os
os.environ['DEBUG'] = '1'

client = LLMClient()
# 会输出详细的调试信息
```

## 开发指南

### 添加新的厂商支持

1. 在 `llm_config.yaml` 中添加配置
2. 在 `LLMConfigManager` 中添加环境变量处理
3. 实现对应的 `_call_with_xxx` 方法
4. 在 `chat` 方法中添加模型判断逻辑

### 自定义工具格式

不同厂商的工具格式略有不同：

```python
# OpenAI 格式
{
    "type": "function",
    "function": {
        "name": "tool_name",
        "description": "description",
        "parameters": {...}
    }
}

# Claude 格式  
{
    "name": "tool_name",
    "description": "description", 
    "input_schema": {...}
}

# Gemini 格式
{
    "name": "tool_name",
    "description": "description",
    "parameters_json_schema": {...}
}
```

工具管理器会自动处理格式转换。 