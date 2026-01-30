<<<<<<< Updated upstream
# 使用Python 3.12官方镜像作为基础镜像
FROM python:3.12-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
=======

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV RUNNING_IN_DOCKER=true
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
>>>>>>> Stashed changes
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*
<<<<<<< Updated upstream

# 安装uv包管理器
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# 复制项目依赖文件
COPY pyproject.toml ./

# 安装Python依赖
RUN uv sync --frozen

# 复制项目源代码
=======
    
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml ./
RUN uv sync --frozen
>>>>>>> Stashed changes
COPY ainiee_cli.py ./
COPY ModuleFolders/ ./ModuleFolders/
COPY Resource/ ./Resource/
COPY PluginScripts/ ./PluginScripts/
COPY StevExtraction/ ./StevExtraction/
COPY I18N/ ./I18N/
<<<<<<< Updated upstream

# 暴露Web服务器端口
EXPOSE 8000

# 设置容器入口点
=======
EXPOSE 8000
>>>>>>> Stashed changes
ENTRYPOINT ["uv", "run", "ainiee"]