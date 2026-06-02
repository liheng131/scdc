# 修复 Docker 构建缓存未更新导致旧代码部署

## 问题诊断

`docker compose build backend frontend` 重建镜像后，容器内仍报相同的 `intent_classifier.py` f-string 语法错误。

**根因**：Docker 构建缓存机制导致 `COPY . .` 层被缓存，修复后的代码没有被包含进新镜像。Docker 通过文件哈希判断是否重建层，Windows 下 `COPY . .` 有时缓存判断不准确。

## 修复方案

使用 `--no-cache` 强制无缓存重建后端镜像，确保所有层重新构建并包含最新代码。

## 实施步骤

### 步骤 1：确认本地源码已修复

```powershell
# 验证 intent_classifier.py 第 80 行不是 f-string 开头
Select-String -Path "backend\app\services\intent_classifier.py" -Pattern '^\s*template\s*=\s*"""'
```

### 步骤 2：无缓存重建后端镜像

```powershell
docker compose build --no-cache backend
```

### 步骤 3：重启后端容器

```powershell
docker compose up -d backend
```

### 步骤 4：验证容器内代码

```powershell
# 检查容器内 intent_classifier.py 第 80 行
docker exec scdc-backend grep -n 'template\s*=' /app/app/services/intent_classifier.py | head -1
```

## 涉及文件
- 无代码修改，仅为构建流程调整