# Multi-Level Agent API Server Docker Image
FROM python:3.12-slim

# API导入 - Docker容器化部署配置

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

# 安装系统依赖（包括构建工具和时区数据）
RUN apt-get update && apt-get install -y \
    git \
    curl \
    procps \
    gcc \
    g++ \
    make \
    build-essential \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

# 复制requirements文件并安装Python依赖
COPY baseService/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 安装额外的依赖（分步安装避免构建问题）
RUN pip install --no-cache-dir flask flask-cors psutil tiktoken

# 安装litellm（可能需要编译，单独处理）
RUN pip install --no-cache-dir litellm || \
    pip install --no-cache-dir litellm --no-build-isolation || \
    pip install --no-cache-dir "litellm[proxy]" --no-deps

# 复制项目文件（完全排除所有配置文件）
COPY baseService/ /app/baseService/
COPY Services/ /app/Services/
COPY TestFolder/ /app/TestFolder/
COPY frontend/ /app/frontend/
COPY api_server.py /app/
COPY task_runner.py /app/
COPY start.py /app/
COPY LICENSE /app/
COPY README.md /app/
COPY API_README.md /app/

# 不复制任何配置文件！所有配置必须通过挂载提供

# 创建必要的目录
RUN mkdir -p /app/logs/api_state \
    && mkdir -p /app/conversations \
    && mkdir -p /app/config/run_env_config \
    && mkdir -p /app/config/agent_library

# 设置权限
RUN chmod +x /app/TestFolder/start.py \
    && chmod +x /app/api_server.py

# 创建配置文件挂载点
VOLUME ["/app/config/run_env_config", "/app/config/agent_library", "/app/logs"]

# 暴露端口
EXPOSE 5002

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5002/health || exit 1

# 启动脚本
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# 启动命令
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "api_server.py"] 