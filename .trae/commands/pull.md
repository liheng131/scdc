# /pull 命令

## 描述
从代码仓库拉取最新代码，支持指定分支。

## 使用方法
- `/pull` - 默认拉取 main 分支
- `/pull 分支名` - 拉取指定分支

## 执行步骤

### 1. 检查远程仓库绑定状态
```bash
git remote -v
```

### 2. 判断远程仓库
**如果没有任何远程仓库输出**：
- 停止执行
- 提示用户：`未检测到远程仓库绑定。请提供远程仓库地址（如：https://github.com/yourname/repo.git 或 git@github.com:yourname/repo.git）`
- 等待用户输入后执行：`git remote add origin <用户提供的地址>`

**如果有远程仓库**：
- 继续使用已绑定的 `origin` 远程仓库

### 3. 确定拉取分支
- **如果用户指定了分支**（如 `/pull develop`）：使用用户指定的分支
- **如果用户未指定分支**：默认使用 `main` 分支

### 4. 获取远程分支列表
```bash
git fetch origin
```

### 5. 检查本地是否存在该分支
```bash
git branch --list <分支名>
```

### 6. 拉取代码
**如果本地已存在该分支**：
```bash
git pull origin <分支名>
```

**如果本地不存在该分支**：
```bash
git checkout -b <分支名> origin/<分支名>
```

### 7. 反馈结果
- 成功：显示拉取的分支、更新的文件数量和提交信息
- 冲突：显示冲突文件列表，提示用户需要手动解决
- 失败：显示错误信息（如分支不存在、网络问题等）

### 8. 检查拉取结果
```bash
git status
git log --oneline -5
```
显示最近 5 条提交记录，确认拉取成功。
