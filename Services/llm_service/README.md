# LLM Service

一个统一的 LLM 包装器服务，支持原生和基于提示词的工具调用。

## 特性

- 🚀 **统一接口**: 支持多种 LLM 提供商（OpenAI、Claude、Gemini、DeepSeek、Qwen 等）
- 🛠️ **双模式工具调用**: 
  - 原生工具调用（支持 function calling 的模型）
  - 基于提示词的工具调用（不支持原生工具调用的模型）
- 🌍 **多语言支持**: 中文和英文提示词
- ⚙️ **灵活配置**: 支持自定义 API 密钥、端点和参数
- 🔧 **类型安全**: 完整的类型注解支持
- 📊 **详细响应**: 包含 token 使用情况、完成原因等信息

## 快速开始

### 基本使用

```python
from Services.llm_service import LLMWrapper

# 初始化包装器
wrapper = LLMWrapper()

# 发送简单消息
messages = [{"role": "user", "content": "你好！"}]
response = wrapper.chat(
    messages=messages,
    model="gpt-3.5-turbo"  # 直接使用模型名称，无需前缀
)

print(f"回复: {response.output}")
```

### 原生工具调用

```python
# 定义工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称"}
                },
                "required": ["city"]
            }
        }
    }
]

# 使用原生工具调用
response = wrapper.chat(
    messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
    model="gpt-4",
    tools=tools,
    tool_call_capability=True  # 启用原生工具调用
)

if response.tool_calls:
    for tool_call in response.tool_calls:
        print(f"调用工具: {tool_call.name}")
        print(f"参数: {tool_call.arguments}")
```

### 基于提示词的工具调用

```python
# 对于不支持原生工具调用的模型
response = wrapper.chat(
    messages=[{"role": "user", "content": "请计算 15 * 23"}],
    model="some-model-without-native-tools",
    tools=tools,
    tool_call_capability=False,  # 禁用原生工具调用
    prompt_language="zh"  # 使用中文提示词
)

# 系统会自动解析模型输出中的工具调用格式
if response.tool_calls:
    print("解析出的工具调用:", response.tool_calls)
```

### 自定义 API 配置

```python
# 使用自定义 API 端点
response = wrapper.chat(
    messages=messages,
    model="custom-model",
    api_key="your-api-key",
    api_base="https://your-api-endpoint.com/v1",
    temperature=0.7,
    max_tokens=1000
)
```

## 工具调用格式

对于不支持原生工具调用的模型，系统会生成特殊的提示词，模型需要按以下格式返回：

```xml
<tool_name>工具名称</tool_name>
<tool_use:参数名1>参数值1</tool_use:参数名1>
<tool_use:参数名2>参数值2</tool_use:参数名2>
```

系统会自动解析这种格式并转换为标准的工具调用对象。

## 配置管理

```python
from Services.llm_service.config import LLMServiceConfig

# 加载配置
config = LLMServiceConfig()

# 获取可用模型
models = config.get_available_models()

# 获取特定提供商配置
openai_config = config.get_provider_config("openai")
```

## API 参考

### LLMWrapper

#### 初始化参数

- `timeout` (int): 请求超时时间，默认 1000 秒
- `num_retries` (int): 重试次数，默认 3 次
- `suppress_debug` (bool): 是否抑制调试信息，默认 True

#### chat 方法

- `messages` (List[Dict]): 消息列表
- `model` (str): 模型名称（直接使用，无需前缀）
- `api_key` (str, optional): API 密钥
- `api_base` (str, optional): API 基础 URL
- `temperature` (float): 温度参数，默认 0.0
- `max_tokens` (int, optional): 最大 token 数
- `tools` (List[Dict], optional): 工具列表
- `tool_choice` (str): 工具选择策略，默认 "auto"
- `tool_call_capability` (bool): 是否支持原生工具调用，默认 True
- `prompt_language` (str): 提示词语言，"zh" 或 "en"，默认 "zh"
- `parallel_tool_calls` (bool): 是否允许并行工具调用，默认 False

### LLMResponse

响应对象包含以下字段：

- `status` (str): 状态，"success" 或 "error"
- `output` (str): 模型输出内容
- `error_information` (str): 错误信息
- `model` (str): 使用的模型名称
- `usage` (Dict): token 使用情况
- `finish_reason` (str): 完成原因
- `tool_calls` (List[ToolCall]): 工具调用列表

### ToolCall

工具调用对象：

- `id` (str): 工具调用 ID
- `name` (str): 工具名称
- `arguments` (Dict): 工具参数

## 支持的模型

### OpenAI
- gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo
- o1, o1-mini, o1-preview, o3-mini, o4-mini
- chatgpt-4o-latest

### Anthropic
- claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022
- claude-3-7-sonnet-20250219, claude-4-sonnet-20250514
- claude-4-opus-20250514

### Google
- gemini-2.0-flash, gemini-2.5-flash, gemini-2.5-pro
- gemini-2.5-pro-preview-03-25

### DeepSeek
- deepseek-r1, deepseek-v3, deepseek-r1-250120
- deepseek-r1-250528, deepseek-v3-250324

### Qwen
- qwen-max-latest, qwen-plus-latest, qwen-turbo-latest
- qwen3-235b-a22b, qwen3-32b

## 错误处理

系统会自动分类和处理各种错误：

- 请求超时
- 网络连接错误
- API 密钥无效
- 速率限制
- 其他未知错误

所有错误信息都会在 `LLMResponse.error_information` 中返回。

## 许可证

MIT License
