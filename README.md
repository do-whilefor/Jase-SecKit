<div align="center">

# 🛡️ JaseSkills

### AI 驱动的漏洞挖掘与授权安全测试 Skill 集合

面向授权安全测试、AI 辅助渗透测试与漏洞研究的可复用 Security Skills 集合。

`Pentest` · `Security Research` · `Dynamic Validation` · `Claude Code Skills`

</div>

---

JaseSkills 是一套面向 AI 辅助渗透测试与漏洞研究的安全 Skill 项目。

项目以服务端安全边界、业务逻辑和动态验证为核心，帮助 AI 从攻击面分析、威胁建模、漏洞验证到证据整理，完成更接近真实安全测试的工作流。

核心内容包括：

* `Pentest-Lyan`：自主 Web 渗透测试与漏洞验证
* `security-hunt`：统一入口的专项漏洞挖掘框架
* 安全规则、漏洞研究方法与高质量案例知识库
* 面向 Claude Code 等 AI 编程工具的可复用 Skills

项目原则：

> 广泛探索，严格验证。
> 没有完整证据，不确认漏洞。

适用于授权渗透测试、SRC 漏洞挖掘、安全研究及 AI 安全能力构建。

---

## 🔧 个人维护命令

以下命令适用于 Windows 命令提示符（CMD），可直接逐段执行：

```cmd
git rev-parse --is-inside-work-tree

git branch --show-current
git remote -v

if exist ".git\index.lock" (
    echo 检测到 .git\index.lock
    echo 请先确认没有其他 Git 操作正在运行。
    echo 确认后可执行：del /f ".git\index.lock"
) else (
    echo 未检测到 .git\index.lock
)

git add -A -- . > "%TEMP%\git-add-log.txt" 2>&1

type "%TEMP%\git-add-log.txt"

git status --short

echo.
echo 前 50 个已暂存文件：
powershell -NoProfile -Command "git diff --cached --name-status | Select-Object -First 50"

git diff --cached --quiet

if errorlevel 1 (
    git commit -m "Update skills"
) else (
    echo.
    echo 没有需要提交的本地变更。
)

git pull --rebase origin main

git push origin main

git status
```

## 🔍 检查本地是否与 GitHub 同步

以下命令适用于直接粘贴到 Windows 命令提示符（CMD）中执行：

```cmd
git fetch origin

for /f %i in ('git rev-parse HEAD') do set "LOCAL_HASH=%i"
for /f %i in ('git ls-remote origin refs/heads/main') do set "REMOTE_HASH=%i"

echo 本地提交：%LOCAL_HASH%
echo 远程提交：%REMOTE_HASH%

if "%LOCAL_HASH%"=="%REMOTE_HASH%" (
    echo 本地已经与 GitHub 完全同步。
) else (
    echo 本地与 GitHub 不一致。
)

git status --short
```
