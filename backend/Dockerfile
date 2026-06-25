# 多阶段构建：第一阶段编译依赖，第二阶段运行环境
# 为什么使用多阶段构建：
# - 最终镜像不包含 gcc/build-essential 等编译工具，减小镜像体积
# - 第一阶段编译生成 wheels，第二阶段直接安装预编译包，加快启动速度

# ===== 构建阶段 =====
FROM python:3.11-slim as builder

WORKDIR /app
# 使用阿里云镜像加速 apt 源
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true
# 安装编译依赖（gcc、头文件等），用于编译 psycopg2 等 C 扩展库
RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 使用清华 pip 镜像加速依赖下载
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# ===== 运行阶段 =====
FROM python:3.11-slim

WORKDIR /app
# 使用阿里云镜像加速 apt 源
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

# 安装运行时依赖：
#   libpq5          - psycopg2 运行时库
#   chromium        - HTML→PPT/PDF 渲染引擎（Chromium 内核，与 Edge 同源）
#   chromium-sandbox - Chromium 沙箱（安全运行所需）
#   fonts-*         - 中日韩字体，确保 PDF/PPT 中文正常显示
#   libnss3 等      - Chromium 运行所需的共享库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    chromium \
    chromium-sandbox \
    fonts-wqy-microhei \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

# 环境变量：跳过 Playwright 内置浏览器下载（使用系统 Chromium）
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
# 指定系统 Chromium 路径（供 PlaywrightRenderer 使用）
ENV SYSTEM_CHROMIUM_PATH=/usr/bin/chromium

# 从构建阶段复制预编译的 wheels
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache -i https://pypi.tuna.tsinghua.edu.cn/simple /wheels/*

# 复制应用代码
COPY . .

EXPOSE 8000

# 使用 Uvicorn 启动 FastAPI，监听所有网络接口
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
