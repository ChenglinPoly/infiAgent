# MLA V3 快速入门指南

5分钟快速上手 MLA Agent 系统。

---

## 🚀 快速开始（5分钟）
更多安装教程- [安装指南](INSTALL.md) - 安装和配置

### 步骤 1: 安装

```bash
cd /path/to/MLA_V3
pip install -e .
```

### 步骤 2: 配置 API Key

```bash
# 查看当前配置 默认了 openrouter 为 baseurl
mla-agent --config-show

# 设置 API Key
mla-agent --config-set api_key "sk-your-api-key-here"

# 设置 Base URL（可选）
mla-agent --config-set base_url "https://api.openai.com/v1"

# 设置模型列表（可选）(第一个前缀取决于你的 base_url提供的响应格式，如果是 openai格式则使用 openai 前缀，然后再写入模型名称)
mla-agent --config-set models "["openai/anthropic/claude-haiku-4.5"]"
```





### 步骤 3: 启动工具服务器

```bash
mla-tool-server start
```

### 步骤 4: 运行第一个任务

```bash
mkdir -p ~/my_first_task

mla-agent \
  --task_id ~/my_first_task \
  --user_input "查看工作目录内有什么文件夹"
```

**完成！** 🎉

---

## 📚 详细命令教程

### mla-tool-server - 工具服务器管理

#### 启动服务

```bash
# 后台启动（推荐）
mla-tool-server start

# 前台运行（查看日志）
mla-tool-server

# 自定义端口
mla-tool-server start --port 8002
```

#### 管理服务

```bash
# 查看状态
mla-tool-server status
# 输出:
# ✅ Tool Server 运行中
#    PID: 12345
#    地址: http://localhost:8001

# 停止服务
mla-tool-server stop

# 重启服务
mla-tool-server restart
```

---

### mla-agent - Agent 执行器

#### 基础用法

```bash
mla-agent \
  --task_id /absolute/path/to/workspace \
  --user_input "你的任务描述"
```

#### 完整参数

```bash
mla-agent \
  --task_id /path/to/workspace \
  --user_input "任务描述" \
  --agent_name writing_agent \
  --agent_system Test_agent \
  --jsonl \
  --force-new
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--task_id` | 工作空间绝对路径（必需） | - |
| `--user_input` | 任务描述（必需） | - |
| `--agent_name` | Agent 名称 | writing_agent |
| `--agent_system` | Agent 系统 | Test_agent |
| `--jsonl` | JSONL 输出模式 | false |
| `--force-new` | 强制新任务（清空状态） | false |

---

### 配置管理

```bash
# 查看配置
mla-agent --config-show

# 设置 API Key
mla-agent --config-set api_key "YOUR_KEY"

# 设置 Base URL
mla-agent --config-set base_url "https://api.openai.com/v1"

# 设置模型
mla-agent --config-set models "[gpt-4o,gpt-4o-mini]"

# 设置温度
mla-agent --config-set temperature "0.7"
```

---

## 🤖 可用 Agent

### Level 3 - 顶层 Agent

#### writing_agent ⭐ （默认）

**职责**: 科研助手，完成从学术论文到资料查找的全流程工作

**能力**:
- 学术论文写作（完整流程）
- 文献资料收集
- 实验设计与执行
- 数据分析与可视化
- 基于历史任务的互动协作

**典型工作流程**:
1. 调用 data_collection_agent 收集文献
2. 调用 get_idea_and_experiment_plan 获取实验方案
3. 调用 coder_agent 完成代码实验
4. 调用 data_to_figures_agent 生成图表
5. 调用 material_to_document_agent 撰写论文
6. 调用 judge_agent 验证质量
7. 使用 final_output 输出结果

**适用场景**:
- 学术论文写作
- 研究报告生成
- 文献综述
- 实验数据分析
- 一般性查询和互动

**示例**:
```bash
mla-agent \
  --task_id ~/research_project \
  --user_input "写一篇关于Transformer的综述论文"
```

---

### Level 2 - 功能 Agent

#### data_collection_agent

**职责**: 根据任务场景收集数据（论文、网页资料等）

**工作流程**:
1. 使用 web_search_agent 搜索相关文献
2. 使用 get_searchPdf_by_doi_or_title 下载 PDF
3. 使用 judge_agent 验证收集质量

**适用场景**:
- 学术文献收集
- 网页资料搜集
- 特定主题的资料整理

**示例**:
```bash
mla-agent \
  --task_id ~/literature_review \
  --agent_name data_collection_agent \
  --user_input "收集2020-2024年关于强化学习的论文"
```

---

#### get_idea_and_experiment_plan

**职责**: 基于现有资料生成研究方向和实验方案

**核心理念**:
- 聚焦1-3篇文章的方向
- 研究问题单一、明确、可实现
- 考虑实际计算资源限制

**工作流程**:
1. 使用 summary_from_one_paper 总结论文
2. 使用 answer_from_one_paper 获取详细知识
3. 设计具体实验方案（包括数据、baseline、分析）
4. 必要时使用 human_in_loop 请求用户提供资源
5. 输出 JSON/Markdown 格式的实验计划

**输出内容**:
- 研究 idea
- 实验方案
- 实验数据设计
- 预期结果
- 数据表格结构

**示例**:
```bash
mla-agent \
  --task_id ~/experiment_design \
  --agent_name get_idea_and_experiment_plan \
  --user_input "基于已收集的文献，设计A*算法改进实验"
```

---

#### coder_agent

**职责**: 完成代码实验和编程任务

**能力**:
- Python 代码编写
- 实验代码实现
- 单元测试编写
- 代码调试和优化

**工作流程**:
1. 分析实验计划
2. 编写代码实现
3. 执行测试
4. 优化和调试

**示例**:
```bash
mla-agent \
  --task_id ~/coding_project \
  --agent_name coder_agent \
  --user_input "实现A*算法的三种启发函数并进行性能测试"
```

---

#### data_to_figures_agent

**职责**: 将实验数据转换为学术图表

**能力**:
- 数据可视化
- 生成高质量图表（300 DPI）
- 多种图表类型（折线图、柱状图、散点图等）

**输出**:
- PNG 格式图表
- 图表描述文档

**示例**:
```bash
mla-agent \
  --task_id ~/data_visualization \
  --agent_name data_to_figures_agent \
  --user_input "将实验结果数据生成对比图表"
```

---

#### material_to_document_agent

**职责**: 将材料整合为学术文档

**能力**:
- 论文写作（LaTeX/Markdown）
- 内容整合
- 引用管理
- 格式规范

**适用场景**:
- 学术论文撰写
- 技术报告生成
- 实验报告整理

**示例**:
```bash
mla-agent \
  --task_id ~/paper_writing \
  --agent_name material_to_document_agent \
  --user_input "基于实验数据和图表撰写论文"
```

---

## 💡 使用场景示例

### 场景 1: 完整学术论文写作

```bash
# 1. 启动服务
mla-tool-server start

# 2. 创建项目目录
mkdir -p ~/my_research_paper

# 3. 运行 writing_agent（自动编排全流程）
mla-agent \
  --task_id ~/my_research_paper \
  --user_input "写一篇关于深度强化学习的综述论文"

# 4. 查看结果
ls ~/my_research_paper/upload/
# 预期输出: paper.tex, references.bib, figures/

或者：
  mlag-agent --cli 运行 cli 工具
  （如果遇到了人机交互任务，打开新的 bash 窗口使用
  mla-agent confirm read_project_files_20251020 --result "已完成阅读"
  确认任务完成。）

```

---

### 场景 2: 文献收集

```bash
mla-agent \
  --task_id ~/literature \
  --agent_name data_collection_agent \
  --user_input "收集Transformer模型相关的10篇近期论文"
```

---

### 场景 3: 实验设计

```bash
mla-agent \
  --task_id ~/experiment \
  --agent_name get_idea_and_experiment_plan \
  --user_input "设计一个对比不同优化器性能的实验"
```

---

### 场景 4: 数据可视化

```bash
mla-agent \
  --task_id ~/visualization \
  --agent_name data_to_figures_agent \
  --user_input "将 CSV 数据生成性能对比图表"
```

---

### 场景 5: VS Code 插件集成（JSONL 模式）

```bash
mla-agent \
  --task_id $(pwd) \
  --user_input "优化代码性能" \
  --jsonl 2>/dev/null
```

**输出**（每行一个 JSON）:
```jsonl
{"type":"start",...}
{"type":"token","text":"加载配置..."}
{"type":"progress","phase":"init","pct":10}
{"type":"token","text":"[writing_agent] 初始规划: ..."}
{"type":"token","text":"调用工具: dir_list"}
{"type":"result","ok":true,"summary":"..."}
{"type":"end","status":"ok","duration_ms":5432}
```

---

## 🔄 中断与恢复

### 中断任务

任何时候按 `Ctrl+C` 安全中断：

```bash
mla-agent --task_id ~/project --user_input "长时间任务"
# ... 按 Ctrl+C
# 状态已自动保存
```

### 恢复任务（相同输入）

```bash
mla-agent --task_id ~/project --user_input "长时间任务"
# 输出: ℹ️ 检测到相同任务，将续跑
# 自动从断点继续
```

### 新任务（不同输入）

```bash
mla-agent --task_id ~/project --user_input "完全不同的任务"
# 中断的任务自动归档到 history
# 新任务可参考历史上下文
```

### 强制新任务

```bash
mla-agent --task_id ~/project --user_input "任务" --force-new
# 清空所有状态，从头开始
```

---

## 🤝 人机交互（Human-in-Loop）

### 触发场景

Agent 在需要时会自动调用 `human_in_loop` 工具，暂停执行等待用户操作。

### 完整示例（JSONL 模式）

#### 步骤 1: Agent 触发 HIL

```bash
mla-agent \
  --task_id ~/project \
  --user_input "请求用户先阅读完项目内的文件再继续" \
  --jsonl 2>/dev/null
```

**JSONL 输出**:
```jsonl
{"type":"start","call_id":"c-1760936557-474c43","project":"~/project","agent":"writing_agent","task":"请求用户先阅读完..."}
{"type":"token","text":"[writing_agent] 初始规划: ..."}
{"type":"token","text":"调用工具: dir_list\n参数: {\n  \"path\": \".\",\n  \"recursive\": true\n}"}
{"type":"token","text":"工具 dir_list 完成: success - ..."}
{"type":"token","text":"调用工具: human_in_loop\n参数: {\n  \"hil_id\": \"read_project_files_20251020\",\n  \"instruction\": \"请阅读完项目内的所有文件后再继续...文件清单如下：...\"\n}"}
```

**关键**: 此时 Agent 会阻塞等待，但 JSONL 事件已发出 `human_in_loop`

#### 步骤 2: 用户操作（VS Code 插件处理）

插件解析到 `human_in_loop` 事件后：
- 提取 `hil_id`: `read_project_files_20251020`
- 提取 `instruction`: "请阅读完项目内的所有文件后再继续..."
- 显示 UI 给用户（对话框/侧边栏）

#### 步骤 3: 完成 HIL 任务

用户确认后，插件调用：

```bash
mla-agent confirm read_project_files_20251020 --result "已完成阅读"
```

**输出**:
```
✅ HIL 任务已完成: read_project_files_20251020
   结果: 已完成阅读
```

#### 步骤 4: Agent 继续执行

原 Agent 进程自动解除阻塞，继续输出 JSONL 事件：

```jsonl
{"type":"token","text":"工具 human_in_loop 完成: success - 人类任务已完成: 已完成阅读"}
{"type":"token","text":"调用工具: final_output\n参数: {...}"}
{"type":"result","ok":true,"summary":"任务完成..."}
{"type":"end","status":"ok","duration_ms":58451}
```

### HIL 工具参数

Agent 调用 `human_in_loop` 时的参数：

```json
{
  "hil_id": "unique-id",          // 唯一标识
  "instruction": "给用户的说明",   // 任务描述
  "timeout": null                  // 超时时间（null=无限等待）
}
```

### VS Code 插件集成代码

```typescript
// 解析 JSONL 事件
child.stdout.on('data', (data) => {
  data.toString().split('\n').forEach(line => {
    if (!line.trim()) return;
    
    const event = JSON.parse(line);
    
    if (event.type === 'token' && event.text.includes('调用工具: human_in_loop')) {
      // 提取参数（从 text 中解析或等待后续事件）
      const match = event.text.match(/hil_id.*?:\s*"([^"]+)"/);
      if (match) {
        const hilId = match[1];
        const instruction = extractInstruction(event.text);
        
        // 显示 UI
        showHILDialog(hilId, instruction);
      }
    }
  });
});

// 显示 HIL 对话框
async function showHILDialog(hilId: string, instruction: string) {
  const result = await vscode.window.showInformationMessage(
    instruction,
    '确认', '取消'
  );
  
  // 用户确认后，完成 HIL
  if (result === '确认') {
    spawn('mla-agent', ['confirm', hilId, '--result', '用户已确认']);
  } else {
    spawn('mla-agent', ['confirm', hilId, '--result', '用户取消']);
  }
}
```

### 命令行测试 HIL

#### 1. 手动触发 HIL（API）

```bash
curl -X POST http://localhost:8001/api/tool/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "/path",
    "tool_name": "human_in_loop",
    "params": {
      "hil_id": "TEST-001",
      "instruction": "请确认是否继续"
    }
  }' &
```

#### 2. 查看 HIL 状态

```bash
curl http://localhost:8001/api/hil/TEST-001 | jq
# {"found":true,"hil_id":"TEST-001","status":"waiting",...}
```

#### 3. 完成 HIL

```bash
mla-agent confirm TEST-001 --result "已确认"
```

### HIL 超时设置

```json
{
  "hil_id": "timeout-test",
  "instruction": "请在5分钟内确认",
  "timeout": 300  // 5分钟后自动失败
}
```

### 最佳实践

**hil_id 命名建议**:
```python
# 使用时间戳 + 任务描述
hil_id = f"upload_file_{datetime.now().strftime('%Y%m%d%H%M')}"
hil_id = f"confirm_action_{uuid.uuid4().hex[:8]}"
```

**instruction 内容建议**:
- 清晰说明需要用户做什么
- 提供必要的上下文信息
- 包含文件列表、选项等

**超时设置**:
- 文件上传：`timeout: 3600`（1小时）
- 简单确认：`timeout: 300`（5分钟）
- 长时间操作：`timeout: null`（无限等待）

---

## 📂 文件位置

### 工作空间结构

```
{task_id}/                     (您指定的绝对路径)
├── upload/                    (上传/下载文件)
├── code_run/                  (代码执行目录)
└── code_env/                  (Python 虚拟环境)
```

### 对话历史

```
~/mla_v3/                      (用户主目录)
└── conversations/             (所有任务的对话历史)
    ├── {hash}_project_stack.json
    ├── {hash}_project_share_context.json
    └── {hash}_project_agent_xxx_actions.json
```

**跨平台**:
- macOS/Linux: `~/mla_v3/`
- Windows: `C:\Users\用户名\mla_v3\`

---

## 🛠️ 常见任务

### 配置新的 LLM

```bash
# 使用 OpenAI
mla-agent --config-set base_url "https://api.openai.com/v1"
mla-agent --config-set api_key "sk-xxx"
mla-agent --config-set models "[gpt-4o,gpt-4o-mini]"

# 使用 Claude
mla-agent --config-set base_url "https://api.anthropic.com"
mla-agent --config-set api_key "sk-ant-xxx"
mla-agent --config-set models "[claude-3-7-sonnet-20250219]"
```

### 查看配置文件位置

```bash
mla-agent --config-show
# 显示配置文件路径
```

### 清理对话历史

```bash
# 查看
ls ~/mla_v3/conversations/

# 清理特定任务
rm ~/mla_v3/conversations/{hash}_project_*

# 清理所有
rm -rf ~/mla_v3/conversations/*
```

### 卸载

```bash
pip uninstall mla-agent
rm -rf ~/mla_v3/  # 可选：删除用户数据
```

---

## 💻 VS Code 插件集成

### TypeScript 示例

```typescript
import { spawn } from 'child_process';

// 启动 Agent（JSONL 模式）
function runAgent(workspacePath: string, userInput: string) {
  const child = spawn('mla-agent', [
    '--task_id', workspacePath,
    '--user_input', userInput,
    '--jsonl'
  ]);
  
  // 解析 JSONL 事件
  child.stdout.on('data', (data) => {
    data.toString().split('\n').forEach(line => {
      if (!line.trim()) return;
      
      const event = JSON.parse(line);
      
      switch (event.type) {
        case 'start':
          console.log(`任务开始: ${event.task}`);
          break;
        case 'token':
          console.log(event.text);
          break;
        case 'result':
          console.log(`结果: ${event.summary}`);
          break;
        case 'end':
          console.log(`完成 (${event.duration_ms}ms)`);
          break;
      }
    });
  });
  
  // 日志记录到文件
  child.stderr.pipe(logStream);
}
```

---

## ⚠️ 常见问题

### Q: 命令未找到
```bash
# 验证安装
pip list | grep mla-agent

# 重新安装
cd /path/to/MLA_V3
pip install -e . --force-reinstall
```

### Q: 工具服务器连接失败
```bash
# 检查服务器
mla-tool-server status

# 如果未运行
mla-tool-server start

# 等待2秒后重试
sleep 2 && mla-agent ...
```

### Q: API Key 未设置
```bash
# 错误信息: API key is required
mla-agent --config-set api_key "YOUR_KEY"
```

### Q: 任务没有续跑
```bash
# 确保使用完全相同的 user_input
mla-agent --task_id /path --user_input "完全一样的任务描述"

# 或强制新任务
mla-agent --task_id /path --user_input "新任务" --force-new
```

---

## 📖 进阶主题

### 使用不同 Agent

```bash
# 只收集文献
mla-agent --agent_name data_collection_agent --user_input "收集论文"

# 只设计实验
mla-agent --agent_name get_idea_and_experiment_plan --user_input "设计实验"

# 只编程
mla-agent --agent_name coder_agent --user_input "实现算法"

# 只生成图表
mla-agent --agent_name data_to_figures_agent --user_input "生成图表"

# 只写文档
mla-agent --agent_name material_to_document_agent --user_input "写论文"
```

### 多任务管理

```bash
# 不同项目使用不同 task_id
mla-agent --task_id ~/project_A --user_input "任务A"
mla-agent --task_id ~/project_B --user_input "任务B"

# 对话历史独立存储
ls ~/mla_v3/conversations/
# {hashA}_project_A_*
# {hashB}_project_B_*
```

### JSONL 输出处理

```bash
# 保存到文件
mla-agent --task_id /path --user_input "任务" --jsonl > output.jsonl 2>debug.log

# 实时解析
mla-agent --task_id /path --user_input "任务" --jsonl 2>/dev/null | jq .type

# 只看结果
mla-agent --task_id /path --user_input "任务" --jsonl 2>/dev/null | jq 'select(.type=="result")'
```

---

## 🎯 最佳实践

### 1. task_id 使用建议

```bash
# ✅ 推荐：有意义的路径
--task_id ~/research/transformer_survey
--task_id ~/experiments/rl_benchmark

# ❌ 避免：临时目录
--task_id /tmp/task  # 可能被清理
```

### 2. 任务描述建议

```bash
# ✅ 清晰具体
--user_input "收集2020-2024年关于Transformer的10篇高引论文"

# ❌ 模糊不清
--user_input "找点论文"
```

### 3. Agent 选择建议

```bash
# 综合任务 → writing_agent（自动编排）
mla-agent --user_input "完成一篇综述论文"

# 单一功能 → 对应的 Level 2 Agent
mla-agent --agent_name data_collection_agent --user_input "收集文献"
```

### 4. 服务器管理

```bash
# 开发时：后台启动
mla-tool-server start

# 调试时：前台运行（查看日志）
mla-tool-server

# 完成后：记得停止
mla-tool-server stop
```

---

## 📝 下一步

- [安装指南](INSTALL.md) - 安装和配置
- [工具文档](tool_server_lite/README.md) - 19个工具的详细说明
- [HIL API](tool_server_lite/HIL_API.md) - 人机交互集成

---

**开始使用 MLA V3 ，加速您的研究工作！** 🚀

