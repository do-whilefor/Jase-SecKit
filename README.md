## 个人维护命令

如果本地内容就是最终内容，推荐使用：

cd ~/文档/skills

# 确认当前目录是 Git 仓库
git rev-parse --is-inside-work-tree

# 查看当前分支和远程仓库
git branch --show-current
git remote -v

# 检查是否存在 Git 锁文件
if [ -f ".git/index.lock" ]; then
    echo "检测到 .git/index.lock"
    echo "请先确认没有其他 Git 操作正在运行。"
    echo "确认后可执行：rm -f .git/index.lock"
    exit 1
fi

# 添加全部新增、修改和删除的文件
git add -A -- . 2>&1 | tee /tmp/git-add-log.txt

# 查看将要提交的内容
git status --short

echo
echo "前 50 个已暂存文件："
git diff --cached --name-status | head -n 50

# 有变更才创建提交
if git diff --cached --quiet; then
    echo
    echo "没有需要提交的本地变更。"
else
    git commit -m "Update skills"
fi

# 获取 GitHub 上的最新提交，并将本地提交变基到最新版本
git pull --rebase origin main

# 推送到 GitHub
git push origin main

# 检查最终状态
git status

如果需要确认 GitHub 是否与本地一致：

cd ~/文档/skills

git fetch origin

LOCAL_HASH=$(git rev-parse HEAD)
REMOTE_HASH=$(git ls-remote origin refs/heads/main | cut -f1)

echo "本地提交：$LOCAL_HASH"
echo "远程提交：$REMOTE_HASH"

if [ "$LOCAL_HASH" = "$REMOTE_HASH" ]; then
    echo "本地已经与 GitHub 完全同步。"
else
    echo "本地与 GitHub 不一致。"
fi

git status --short
---
