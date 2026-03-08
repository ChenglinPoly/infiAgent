# MLA CLI 完整使用指南 💻

交互式命令行界面 (CLI) 完整教程。

---

## 📋 目录

- [启动 CLI](#启动-cli)
- [基础操作](#基础操作)
- [智能体切换](#智能体切换)
- [人机交互 HIL](#人机交互-hil)
- [工具执行确认](#工具执行确认)
- [任务管理](#任务管理)
- [CLI 命令](#cli-命令)

---

## 🚀 启动 CLI

### 方式 1: 本地安装

```bash
cd /your/workspace
mla-agent --cli
```

### 方式 2: Docker

```bash
cd /your/workspace
docker run -it --rm \
  -v $(pwd):/workspace \
  -v ~/.mla_v3:/root/mla_v3 \
  -v mla-config:/mla_config \
  -p 8002:8002 -p 9641:9641 \
  chenglinhku/mla:latest cli
```

### 启动参数

```bash
mla-agent --cli \
  --task_id /custom/path \        # 自定义工作空间
  --agent_system Researcher \     # 智能体系统
  --auto-mode true               # 工具自动执行
```

---

## 📝 基础操作

### 直接输入任务

```bash
[alpha_agent] > 列出当前目录的文件
```

CLI 会使用当前默认智能体（`alpha_agent`）执行任务。

### 多行输入

在任务描述中间按 Enter 不会提交，继续输入即可。完成后按 Enter 提交。

### 查看执行过程

```bash
[alpha_agent] > 分析 data.csv 文件

# 你会看到：
🤖 [alpha_agent] 初始规划: ...
🔧 调用工具: file_read
   参数: {"paths": ["data.csv"]}
✅ 工具执行成功
📊 [alpha_agent] 分析结果: ...
```

---

## 🤖 智能体切换

### 方法 1: 切换并执行

```bash
[alpha_agent] > @coder_agent 编写一个快速排序算法

# 输出：
✅ 已切换到: coder_agent
🤖 [coder_agent] 开始任务: 编写一个快速排序算法
```

### 方法 2: 仅切换默认智能体

```bash
[alpha_agent] > @coder_agent
✅ 已切换到: coder_agent

[coder_agent] > 现在所有任务都使用 coder_agent
```

### 查看可用智能体

```bash
[alpha_agent] > /agents

📋 可用 Agents:
  1. alpha_agent (当前)
  2. data_collection_agent
  3. coder_agent
  4. data_to_figures_agent
  5. material_to_document_agent
  6. get_idea_and_experiment_plan
  7. web_search_agent
```

---

## 🔔 人机交互（HIL）

当智能体需要人工输入时，CLI 会自动检测并提示。

### 触发场景

```bash
[alpha_agent] > 请用户确认后再继续

# 智能体内部调用 human_in_loop 工具
```

### 提示界面

```
🔔🔔🔔 检测到 HIL 任务！按回车处理... 🔔🔔🔔
================================================================================
🔔 人类交互任务（HIL）
================================================================================
📝 任务 ID：upload_file_20250127
📋 指令：请上传数据文件到 upload/ 目录，完成后确认...
================================================================================
💡 输入你的响应（任何文本）
   输入 /skip 跳过此任务
================================================================================

[alpha_agent] HIL 响应 > 文件已上传
✅ HIL 任务已响应
```

### 响应方式

- **确认完成**：输入任何文本（如"已完成"、"done"等）
- **跳过任务**：输入 `/skip`
- **提供详细说明**：输入多行文本

---

## ⚠️ 工具执行确认

在手动模式（`--auto-mode false`）下，每个工具执行需要确认。

### 启动手动模式

```bash
mla-agent --cli --auto-mode false
```

### 确认界面

```
⚠️⚠️⚠️ 检测到工具执行请求！按回车确认... ⚠️⚠️⚠️
================================================================================
⚠️  工具执行确认请求
================================================================================
🔧 工具名称：python_run
📝 确认 ID：confirm_12345
📋 参数：
     code: import pandas as pd...
     timeout: 300
================================================================================
💡 选择操作：
   yes / y - 批准执行
   no / n  - 拒绝执行
================================================================================

[alpha_agent] 确认 [yes/no] > yes
✅ 已批准执行工具：python_run
```

### 使用场景

**自动模式（默认）：** 适用于可信任务
```bash
[alpha_agent] > 分析数据并生成图表
# 自动执行所有工具，无需确认
```

**手动模式：** 适用于敏感操作
```bash
# 启动时指定
mla-agent --cli --auto-mode false

[alpha_agent] > 删除旧文件
# 每个文件操作都需要你确认
```

---

## 📋 CLI 命令

### 系统命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `/help` | 显示帮助 | `/help` |
| `/agents` | 列出可用智能体 | `/agents` |
| `/quit` | 退出 CLI | `/quit` 或 `/exit` |
| `/resume` | 恢复中断任务 | `/resume` |
| `Ctrl+C` | 中断当前任务 | - |
| `Ctrl+D` | 立即退出 | - |

### /help 输出

```
💡 MLA CLI 使用帮助
================================================================================
基础操作:
  直接输入任务             - 使用默认 Agent 执行
  @agent_name 任务        - 切换并执行任务
  @agent_name            - 仅切换默认 Agent

系统命令:
  /help                  - 显示此帮助
  /agents                - 列出所有可用 Agents
  /resume                - 恢复中断的任务
  /quit 或 /exit         - 退出 CLI
  Ctrl+C                 - 中断当前任务（保持在 CLI）
  Ctrl+D                 - 立即退出 CLI

人机交互:
  - 当出现 🔔 HIL 提示时，按回车进入响应模式
  - 输入响应内容完成任务

工具确认:
  - 手动模式下，工具执行需要确认
  - 输入 yes/y 批准，no/n 拒绝
================================================================================
```

---

## 🔄 任务管理

### 中断任务

```bash
[alpha_agent] > 写一篇很长的论文...
# 任务正在执行...

# 按 Ctrl+C
⚠️  正在中断任务...
✅ 任务已中断

💡 输入相同内容可续跑，输入新内容开始新任务
```

### 恢复任务

**方式 1: 输入相同任务描述**
```bash
[alpha_agent] > 写一篇很长的论文...
ℹ️  检测到相同任务，将续跑
▶️  从断点继续...
```

**方式 2: 使用 /resume 命令**
```bash
[alpha_agent] > /resume

📋 发现中断的任务
================================================================================
🤖 Agent: alpha_agent
📝 任务: 写一篇很长的论文...
⏸️  中断于: 2025-12-27 19:30:15
📊 栈深度: 2
================================================================================

是否恢复此任务？ [y/N]: y
▶️  恢复任务...
```

---

## 🎨 界面特性

### Rich 终端 UI

CLI 使用 `prompt_toolkit` 和 `rich` 提供：

- ✨ **语法高亮**
- 🎨 **彩色输出**
- 📊 **格式化表格**
- 🔔 **音频提醒**（HIL 任务）
- ⌨️ **历史记录**（上下键）
- 📝 **自动补全**（智能体名称）

### 启动画面

```
================================================================================
🤖 MLA Agent - 交互式 CLI 模式
================================================================================
📂 工作目录: /Users/username/project
🤖 默认Agent: alpha_agent
📋 可用Agents: alpha_agent, coder_agent, data_collection_agent...
────────────────────────────────────────────────────────────────────────────────
💡 使用说明:
  • 直接输入任务（使用默认 Agent）
  • @agent_name 任务（切换并使用指定 Agent）
  • 🔔 HIL 任务出现时会自动提示，输入响应内容即可
  • Ctrl+C 中断任务 | /resume 恢复 | /quit 退出 | /help 帮助
────────────────────────────────────────────────────────────────────────────────
```

---

## 💡 使用技巧

### 1. 快速文件操作

```bash
[alpha_agent] > 读取 file1.txt, file2.txt, file3.txt 的内容

# 智能体会使用批量读取，一次调用读取多个文件
```

### 2. 链式任务

```bash
[alpha_agent] > 先收集关于 Transformer 的论文，然后总结，最后写成综述

# 智能体会自动拆分为多个步骤执行
```

### 3. 使用子智能体

```bash
[alpha_agent] > @data_collection_agent 收集最近的 NLP 论文
# data_collection_agent 会自动调用 web_search_agent

[alpha_agent] > @coder_agent 实现论文中的算法
# coder_agent 会自动处理代码执行环境
```

### 4. 查看工作空间

```bash
[alpha_agent] > 查看 upload 目录有什么文件

# 智能体会列出文件并说明每个文件的用途
```

---

## 🐛 故障排除

### CLI 无法启动

```bash
# 直接启动 CLI（当前版本无需单独启动工具服务器）
mla-agent --cli
```

### 智能体无响应

```bash
# Ctrl+C 中断
# 检查配置
mla-agent --config-show

# 检查 API key 是否有效
```

### 历史对话混乱

```bash
# 强制开始新任务
mla-agent --cli --force-new

# 或清理历史
rm ~/.mla_v3/conversations/*_stack.json
rm ~/.mla_v3/conversations/*_share_context.json
```

---

## 📊 高级功能

### 自定义智能体系统

```bash
# 使用自定义 agent_system
mla-agent --cli --agent_system MyCustomSystem

# 需要先创建配置目录
# config/agent_library/MyCustomSystem/
```

### JSONL 输出模式

```bash
# 用于 IDE 集成
mla-agent --jsonl --task_id /workspace --user_input "任务"

# 输出 JSON Lines 格式
{"type":"start",...}
{"type":"token","text":"..."}
{"type":"result",...}
```

### 批量任务执行

```bash
# 脚本化执行多个任务
for task in "任务1" "任务2" "任务3"; do
  mla-agent --task_id ~/project --user_input "$task"
done
```

---

## 🎓 最佳实践

### 1. 任务描述清晰

```bash
# ✅ 好的任务描述
[alpha_agent] > 收集 2023-2024 年关于 Transformer 的 10 篇高引论文

# ❌ 模糊的任务描述
[alpha_agent] > 找点论文
```

### 2. 使用合适的智能体

```bash
# 文献收集 → data_collection_agent
# 代码开发 → coder_agent
# 数据可视化 → data_to_figures_agent
# 论文撰写 → material_to_document_agent
# 综合任务 → alpha_agent（自动编排）
```

### 3. 利用历史记忆

```bash
# 第一次对话
[alpha_agent] > 收集机器学习论文
# ... 智能体收集了 10 篇论文

# 第二次对话（几天后，同一工作空间）
[alpha_agent] > 总结之前收集的论文
# ✅ 智能体会记住并使用之前收集的论文
```

### 4. 工作空间管理

```bash
# 不同项目使用不同目录
cd ~/project_a && mla-agent --cli  # 项目 A
cd ~/project_b && mla-agent --cli  # 项目 B

# 对话历史自动隔离
```

---

## 🎬 实际案例

### 案例 1: 学术论文写作

```bash
cd ~/my_paper
mla-agent --cli

[alpha_agent] > 写一篇关于深度强化学习的综述论文

# 智能体会自动：
# 1. 调用 data_collection_agent 收集文献
# 2. 调用 get_idea_and_experiment_plan 设计结构
# 3. 调用 material_to_document_agent 撰写论文
# 4. 生成 LaTeX 文件到 upload/
```

### 案例 2: 数据分析

```bash
cd ~/data_project
mla-agent --cli

[alpha_agent] > @data_to_figures_agent
[data_to_figures_agent] > 分析 sales_data.csv 并生成月度趋势图

# 智能体会：
# 1. 读取 CSV 文件
# 2. 分析数据
# 3. 生成 matplotlib 图表
# 4. 保存为 PNG（300 DPI）
```

### 案例 3: 代码开发

```bash
cd ~/code_project
mla-agent --cli

[alpha_agent] > @coder_agent
[coder_agent] > 实现二叉树的三种遍历方法并编写测试

# 智能体会：
# 1. 编写代码
# 2. 创建虚拟环境
# 3. 运行测试
# 4. 调试错误
```

---

## 📚 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 提交当前输入 |
| `Ctrl+C` | 中断当前任务 |
| `Ctrl+D` | 退出 CLI |
| `↑` / `↓` | 浏览历史命令 |
| `Tab` | 自动补全（智能体名称） |

---

## 🎯 性能优化

### 减少 Token 消耗

```bash
# ✅ 批量操作
[alpha_agent] > 读取所有 txt 文件并总结

# ❌ 多次单独操作
[alpha_agent] > 读取 file1.txt
[alpha_agent] > 读取 file2.txt
[alpha_agent] > 读取 file3.txt
```

### 利用文件系统

```bash
# ✅ 使用文件传递数据
[alpha_agent] > 将分析结果保存到 result.txt
[alpha_agent] > 基于 result.txt 生成报告

# ❌ 直接在对话中返回大量数据
```

---

## 📖 相关文档

- [Docker 使用指南](DOCKER_GUIDE.md)
- [配置文件说明](../config/agent_library/Researcher/)
- Runtime tools are executed in-process via direct-tools; no standalone Tool Server is required.
- [主 README](../README.md)

---

**掌握 CLI，高效使用 MLA！** 💻
