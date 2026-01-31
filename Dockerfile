# Stage 1: Build the React Frontend
FROM node:20-slim AS builder
WORKDIR /web

# Copy package.json and package-lock.json first to leverage Docker cache
COPY Tools/WebServer/package.json Tools/WebServer/package-lock.json ./

# Install dependencies
RUN npm ci

# Copy the rest of the frontend source code
COPY Tools/WebServer/ ./

# Build the frontend
RUN npm run build

# Stage 2: Final Python Image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV RUNNING_IN_DOCKER=true

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project definition and metadata required for build/sync
COPY pyproject.toml README.md LICENSE ./
# Using 'uv sync' will install dependencies from pyproject.toml. 
# We use --no-install-project because the source code is not yet copied.
RUN uv sync --no-install-project

# Copy project source code
COPY ainiee_cli.py ./
COPY ModuleFolders/ ./ModuleFolders/
COPY Resource/ ./Resource/
COPY PluginScripts/ ./PluginScripts/
COPY StevExtraction/ ./StevExtraction/
COPY I18N/ ./I18N/
COPY Tools/ ./Tools/

# Copy the built frontend assets from the builder stage
# This overwrites the empty/source Tools/WebServer/dist with the built one
COPY --from=builder /web/dist ./Tools/WebServer/dist

# Expose Web Server port
EXPOSE 8000

# Set entrypoint
ENTRYPOINT ["uv", "run", "ainiee_cli.py"]