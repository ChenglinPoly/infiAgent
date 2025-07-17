# Tool Server - API
## 概述

Tool Server 是一个专为 LLM Agent 设计的独立沙盒工具调用服务。所有工具都运行在一个安全的 Docker 容器中，通过统一的 API 接口进行调用。

## 快速启动

```bash
# 进入 docker_start 目录
cd docker_start

# 运行启动脚本 (服务将在 http://localhost:8001 启动)
./start.sh
```

## API 接口规范

### 统一请求格式

所有工具调用都使用相同的请求格式：

```json
{
  "task_id": "string",
  "tool_name": "string",
  "params": {
    // 工具特定参数
  }
}
```

### 统一响应格式

```json
{
  "success": true/false,
  "data": {
    // 工具返回的数据
  },
  "error": "错误信息（仅在失败时）",
  "timestamp": "2025-07-08T18:00:00.000000",
  "execution_time": 0.123,
  "task_id": "task_001",
  "tool_name": "file_upload"
}
```

---

## 任务管理 API

### 创建任务

**端点**: `POST /api/task/create`

**参数**:
- `task_id` (string, query): 唯一任务标识符
- `task_name` (string, query): 任务名称
- `requirements` (string, query, 可选): Python包依赖

**示例**:
```bash
curl -X POST "http://localhost:8001/api/task/create?task_id=my_task&task_name=My_Task"
```

### 列出所有任务

**端点**: `GET /api/task/list`

**示例**:
```bash
curl http://localhost:8001/api/task/list
```

### 获取任务状态

**端点**: `GET /api/task/{task_id}/status`

**示例**:
```bash
curl http://localhost:8001/api/task/my_task/status
```

### 删除任务

**端点**: `DELETE /api/task/{task_id}`

**示例**:
```bash
curl -X DELETE http://localhost:8001/api/task/my_task
```

---

## 可用工具 API

### 文件操作工具

#### 1. `file_upload`
**用途**: 上传一个或多个文件的内容到任务工作空间。
**参数**:
- `files` (List[Dict]): 文件列表，每个字典包含:
  - `filename` (str): 包含相对路径的文件名。
  - `content` (str): 文件内容，可以是文本或Base64编码的二进制数据。
  - `is_base64` (bool): 指示内容是否为Base64编码。
- `target_path` (str, 可选): 上传到的目标子目录，位于`upload/`下。

**示例**:
```bash
# 上传一个文本文件和一个图片文件
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "file_upload",
  "params": {
    "files": [
      {
        "filename": "config.json",
        "content": "{\\"name\\": \\"test\\"}",
        "is_base64": false
      },
      {
        "filename": "images/logo.png",
        "content": "iVBORw0KGgo...",
        "is_base64": true
      }
    ],
    "target_path": "project_files"
  }
}'
```

#### 2. `file_read`
**用途**: 读取指定文件的内容。
**参数**:
- `file_path` (str): 要读取的文件的路径（相对于任务根目录）。
- `start_line` (int, 可选): 读取的起始行号（从1开始）。
- `end_line` (int, 可选): 读取的结束行号。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "file_read",
  "params": {
    "file_path": "upload/config.json",
    "start_line": 1,
    "end_line": 10
  }
}'
```

#### 3. `file_write`
**用途**: 向指定文件写入内容。
**参数**:
- `file_path` (str): 要写入的文件的路径。
- `content` (str): 要写入的内容。
- `mode` (str, 可选): 写入模式，`"overwrite"`（默认）或 `"append"`。
- `is_base64` (bool, 可选): 内容是否为Base64编码。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "file_write",
  "params": {
    "file_path": "code_run/hello.py",
    "content": "print(\"Hello, World!\")",
    "mode": "overwrite"
  }
}'
```

#### 4. `file_replace_lines`
**用途**: 替换文件中的指定行范围。
**参数**:
- `file_path` (str): 要修改的文件的路径。
- `start_line` (int): 替换的起始行号。
- `end_line` (int): 替换的结束行号。
- `new_content` (str): 用于替换的新内容。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "file_replace_lines",
  "params": {
    "file_path": "code_run/script.py",
    "start_line": 5,
    "end_line": 7,
    "new_content": "# 这是替换的新内容\\nprint(\"Updated code\")"
  }
}'
```

#### 5. `file_delete`
**用途**: 删除文件或目录。
**参数**:
- `file_path` (str): 要删除的文件或目录的路径。

#### 6. `file_move`
**用途**: 移动或重命名文件或目录。
**参数**:
- `src_path` (str): 源路径。
- `dest_path` (str): 目标路径。

#### 7. `dir_create`
**用途**: 创建目录，支持递归创建。
**参数**:
- `dir_path` (str): 要创建的目录路径。

#### 8. `dir_list`
**用途**: 列出目录内容。
**参数**:
- `dir_path` (str, 可选): 要列出的目录路径，默认为任务根目录。
- `recursive` (bool, 可选): 是否递归列出所有子目录内容，默认为`false`。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "dir_list",
  "params": {
    "dir_path": "upload",
    "recursive": true
  }
}'
```

### 代码与文档工具

#### 9. `execute_code`
**用途**: 在任务的独立虚拟环境中执行Python脚本。
**参数**:
- `file_path` (str): 要执行的Python脚本路径。
- `timeout` (int, 可选): 执行超时时间（秒），默认300。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "execute_code",
  "params": {
    "file_path": "code_run/hello.py",
    "timeout": 60
  }
}'
```

#### 10. `execute_shell`
**用途**: 在任务的工作目录中执行Shell命令。
**参数**:
- `command` (str): 要执行的Shell命令。
- `workdir` (str, 可选): 执行命令的工作目录，默认为`code_run/`。
- `timeout` (int, 可选): 超时时间（秒），默认60。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "execute_shell",
  "params": {
    "command": "ls -la",
    "workdir": "code_run",
    "timeout": 30
  }
}'
```

#### 11. `pip_install`
**用途**: 在任务的虚拟环境中安装Python包。
**参数**:
- `packages` (List[str]): 要安装的包名列表。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "pip_install",
  "params": {
    "packages": ["requests", "numpy", "pandas"]
  }
}'
```

#### 12. `git_clone`
**用途**: 克隆一个Git仓库到`upload/`目录。
**参数**:
- `repo_url` (str): 仓库的URL。
- `target_dir` (str, 可选): 克隆到的子目录名。
- `branch` (str, 可选): 要克隆的特定分支。
- `token` (str, 可选): 用于私有仓库的GitHub Token。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "git_clone",
  "params": {
    "repo_url": "https://github.com/user/repo.git",
    "target_dir": "my_repo",
    "branch": "main",
    "token": "your_github_token"
  }
}'
```

#### 13. `parse_document`
**用途**: 解析文档内容，支持PDF, Word, PPT, Markdown。
**参数**:
- `file_path` (str): 要解析的文档路径。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "parse_document",
  "params": {
    "file_path": "upload/document.pdf"
  }
}'
```

#### 14. `code_task_execute`
**用途**: 使用AI代码助手自动完成编程任务。
**参数**:
- `prompt` (str): 对AI助手的任务描述。
- `workspace_dir` (str, 可选): 任务的工作目录，默认`claude_workspace`。
- `api_key` (str): Claude API密钥。
- `max_turns` (int, 可选): 最大对话轮数，默认10。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "code_task_execute",
  "params": {
    "prompt": "创建一个简单的Python计算器程序，支持加减乘除运算",
    "workspace_dir": "claude_workspace",
    "api_key": "your_claude_api_key",
    "max_turns": 5
  }
}'
```

#### 15. `tex2pdf_convert`
**用途**: 将包含LaTeX源文件的目录编译为PDF。
**参数**:
- `input_path` (str): 包含`.tex`文件的目录路径。
- `output_path` (str, 可选): PDF输出目录，默认与`input_path`相同。
- `engine` (str, 可选): LaTeX引擎，可选值：`pdflatex`（默认）、`xelatex`、`lualatex`。
- `clean_aux` (bool, 可选): 是否清理编译过程中的辅助文件，默认`true`。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "tex2pdf_convert",
  "params": {
    "input_path": "upload/tex",
    "output_path": "upload/pdf",
    "engine": "xelatex",
    "clean_aux": true
  }
}'
```

### Google 与 GitHub 工具

#### 16. `google_search`
**用途**: 执行Google搜索。
**参数**:
- `query` (str): 搜索关键词。
- `num_results` (int, 可选): 返回的结果数量，默认50。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "google_search",
  "params": {
    "query": "machine learning tutorials",
    "num_results": 20
  }
}'
```

#### 17. `crawl_page`
**用途**: 爬取指定URL的网页内容并保存为Markdown。
**参数**:
- `url` (str): 要爬取的网页URL。
- `output_dir` (str, 可选): 保存Markdown文件的目录，位于`upload/`下，默认`crawled_content`。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "crawl_page",
  "params": {
    "url": "https://example.com/article",
    "output_dir": "crawled_pages"
  }
}'
```

#### 18. `google_scholar_search`
**用途**: 执行Google Scholar搜索。
**参数**:
- `query` (str): 搜索关键词。
- `output_dir` (str, 可选): 保存结果的目录，位于`upload/`下，默认`scholar_results`。
- `pages` (int, 可选): 爬取的页数，默认1。
- `year_low` (int, 可选): 起始年份。
- `year_high` (int, 可选): 结束年份。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "my_task",
  "tool_name": "google_scholar_search",
  "params": {
    "query": "deep learning",
    "output_dir": "scholar_dl",
    "pages": 2,
    "year_low": 2020,
    "year_high": 2024
  }
}'
```

#### 19. `github_search_repositories`
**用途**: 搜索GitHub仓库（仅基于仓库名称搜索）。
**参数**:
- `query` (str): 搜索关键词（将只在仓库名称中搜索）。
- `sort` (str, 可选): 排序依据，可选值：`stars`（默认）、`forks`、`updated`。
- `order` (str, 可选): 排序顺序，可选值：`desc`（默认）、`asc`。
- `per_page` (int, 可选): 每页结果数量，默认10，最大100。
- `page` (int, 可选): 页码，从1开始，默认1。
- `token` (str, 可选): GitHub Token，如未提供则从环境变量`GITHUB_TOKEN`获取。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "github_test",
  "tool_name": "github_search_repositories",
  "params": {
    "query": "machine learning",
    "sort": "stars",
    "order": "desc",
    "per_page": 20,
    "page": 1,
    "token": "your_github_token"
  }
}'
```

#### 20. `github_get_repository_info`
**用途**: 获取指定GitHub仓库的详细信息。
**参数**:
- `full_name` (str): 仓库全名，格式为`owner/repo`（如`microsoft/vscode`）。
- `token` (str, 可选): GitHub Token，如未提供则从环境变量`GITHUB_TOKEN`获取。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "github_test",
  "tool_name": "github_get_repository_info",
  "params": {
    "full_name": "microsoft/vscode",
    "token": "your_github_token"
  }
}'
```

### RAG 向量搜索工具
> 这些工具用于与远程的ArXiv RAG服务交互，支持两级检索策略：摘要搜索和详细内容搜索。

#### 21. `rag_health_check`
**用途**: 检查RAG服务健康状态。
**参数**: 无需额外参数。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_health_check",
  "params": {}
}'
```

#### 22. `rag_get_stats`
**用途**: 获取RAG服务统计信息，包括论文数量、索引状态等。
**参数**: 无需额外参数。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_get_stats",
  "params": {}
}'
```

#### 23. `rag_search_abstracts`
**用途**: 在论文摘要中搜索相关论文（第一级检索）。
**参数**:
- `query` (str): 搜索查询关键词。
- `k` (int, 可选): 初始检索数量，默认10。
- `m` (int, 可选): rerank后返回数量，默认5。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_search_abstracts",
  "params": {
    "query": "transformer attention mechanism",
    "k": 20,
    "m": 10
  }
}'
```

#### 24. `rag_search_abstracts_filtered`
**用途**: 在论文摘要中搜索相关论文，支持年份过滤。
**参数**:
- `query` (str): 搜索查询关键词。
- `k` (int, 可选): 初始检索数量，默认10。
- `m` (int, 可选): rerank后返回数量，默认5。
- `publish_year_filter` (str, 可选): 年份过滤，如"2023"。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_search_abstracts_filtered",
  "params": {
    "query": "large language model",
    "k": 15,
    "m": 8,
    "publish_year_filter": "2023"
  }
}'
```

#### 25. `rag_search_details`
**用途**: 在指定论文中搜索详细内容（第二级检索）。
**参数**:
- `query` (str): 搜索查询关键词。
- `file_id` (str): 论文ID（从Abstract搜索结果获取）。
- `k` (int, 可选): 初始检索chunks数量，默认10。
- `m` (int, 可选): rerank后返回chunks数量，默认3。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_search_details",
  "params": {
    "query": "attention mechanism implementation",
    "file_id": "2017.03762v7",
    "k": 15,
    "m": 5
  }
}'
```

#### 26. `rag_get_paper_content`
**用途**: 获取指定论文的完整内容。
**参数**:
- `file_id` (str): 论文ID。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_get_paper_content",
  "params": {
    "file_id": "2017.03762v7"
  }
}'
```

#### 27. `rag_get_paper_chunks`
**用途**: 获取论文的chunks信息，包括chunk数量和结构。
**参数**:
- `file_id` (str): 论文ID。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_get_paper_chunks",
  "params": {
    "file_id": "2017.03762v7"
  }
}'
```

#### 28. `rag_get_specific_content`
**用途**: 获取指定chunks的具体内容。
**参数**:
- `file_id` (str): 论文ID。
- `doc_ids` (List[str], 可选): 指定的chunk ID列表。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_get_specific_content",
  "params": {
    "file_id": "2017.03762v7",
    "doc_ids": ["chunk_001", "chunk_002"]
  }
}'
```

#### 29. `rag_cache_stats`
**用途**: 获取RAG服务的缓存统计信息。
**参数**: 无需额外参数。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_cache_stats",
  "params": {}
}'
```

#### 30. `rag_cache_clear`
**用途**: 清空RAG服务的缓存。
**参数**: 无需额外参数。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_cache_clear",
  "params": {}
}'
```

#### 31. `rag_service_info`
**用途**: 获取RAG服务的基本信息，包括版本、配置等。
**参数**: 无需额外参数。

**示例**:
```bash
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_test",
  "tool_name": "rag_service_info",
  "params": {}
}'
```

## RAG 使用流程示例

RAG服务采用两级检索策略，典型使用流程如下：

1. **第一级：摘要搜索** - 使用`rag_search_abstracts`或`rag_search_abstracts_filtered`搜索相关论文
2. **获取file_id** - 从搜索结果中获取感兴趣论文的`file_id`
3. **第二级：详细内容搜索** - 使用`rag_search_details`在特定论文中搜索详细内容
4. **获取完整内容** - 使用`rag_get_paper_content`或`rag_get_specific_content`获取完整内容

**完整示例**:
```bash
# 1. 搜索相关论文
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_demo",
  "tool_name": "rag_search_abstracts",
  "params": {
    "query": "transformer attention mechanism"
  }
}'

# 2. 在特定论文中搜索详细内容（假设从上一步得到file_id）
curl -X POST "http://localhost:8001/api/tool/execute" \
-H "Content-Type: application/json" \
-d '{
  "task_id": "rag_demo",
  "tool_name": "rag_search_details",
  "params": {
    "query": "multi-head attention",
    "file_id": "2017.03762v7"
  }
}'
```



