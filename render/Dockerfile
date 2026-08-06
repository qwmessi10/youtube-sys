# Remotion 渲染服务镜像（流程一）。基于官方推荐 node:22-bookworm-slim + Chromium 依赖。
FROM node:22-bookworm-slim

# Chrome Headless Shell 运行所需系统库（Remotion 官方清单）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libdbus-1-3 libatk1.0-0 libgbm-dev libasound2 libxrandr2 \
    libxkbcommon-dev libxfixes3 libxcomposite1 libxdamage1 libatk-bridge2.0-0 \
    libpango-1.0-0 libcairo2 libcups2 \
    fonts-noto-color-emoji fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用层缓存）
COPY package.json ./
RUN npm install --no-audit --no-fund

# 让 Remotion 下载匹配的 Chrome Headless Shell
RUN npx remotion browser ensure

# 拷贝项目源码与渲染服务
COPY tsconfig.json remotion.config.ts server.mjs ./
COPY src ./src

ENV PORT=3000
EXPOSE 3000
CMD ["node", "server.mjs"]
