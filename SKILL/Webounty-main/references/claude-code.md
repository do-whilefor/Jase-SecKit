# Claude Code 接入

## 安装与依赖

把完整 webounty 文件夹放入个人目录 `~/.claude/skills/webounty/` 或项目目录 `.claude/skills/webounty/`，确保 SKILL.md 直接位于该目录，不要多套一层目录。

需要 Python 3.10+；仅 CVSS 需要 Node.js 18+。Python 只用标准库，无需 pip、向量数据库、独立模型 API 或固定 MCP。系统使用 python 命令时，确认它是 Python 3 后替换示例中的 python3。

在 Claude Code 输入 `/webounty` 并说明目标，也可由 Claude 按描述加载。`${CLAUDE_SKILL_DIR}` 和 `${CLAUDE_SESSION_ID}` 是技能正文替换变量，不是要求用户自己设置的 shell 环境变量。手动终端运行时填写实际目录和会话 ID。

其他宿主不支持替换变量时，显式填写技能目录，直接用 UUID 为本次研究生成一次随机会话 ID，无需询问用户或其他 Agent，后续沿用。此时仅支持脚本工作流，不承诺其他宿主自动接入。

## 会话语义

- start 在当前工作目录下创建 `.webounty/<会话ID的SHA-256>/`；`--project-root PATH` 可指定项目目录。路径以返回的 project_root/root 为准，不自动向上查找 Git 根目录。
- 同一项目和会话复用工作区；不同项目或不同会话分别隔离。session.json 登记项目归属，后续命令按 root 定位，切换工作目录不改变已创建会话的位置。
- 工作区属于整个研究会话，多个发现、Step、查询和子任务共享。start 重复调用不改写已有目标。
- 上下文压缩后保留 session_id/root/run_id；宿主能维护上下文代次时给同一 context 游标传新的 --context-epoch，不能维护时加 --refresh 重发当前问题的完整视图。task_core 每次保留目标与硬约束；按 ID 补读活动 Step，再继续 discover。脚本不自动检测压缩。
- 目录已清理则原证据不可恢复；新会话不自动加载其他会话数据。
- finish 只删除归属匹配的会话子目录，项目、`.webounty/` 中其他会话和原始用户文件保持不变。需要导出时使用本会话目录之外的新目录。
- 本包不安装 hook 或修改客户端配置。普通回复结束不是会话结束；异常退出可能在项目下残留会话资料。
- 将来若接宿主自动清理，应处理真实会话结束。Claude Code 的 Stop 是一次回复结束，不能用于清理本轮知识。

恢复调用仍需 query、anchor 或 question-ref 之一。暂时只记得 root/run_id 时，可用 `context --root '本轮root' --run-id '本轮run_id' --anchor G-001 --cursor main --context-epoch E2` 先恢复目标，再从 goals[].active_question_ref 按 ID 补读当前问题。query 为空且没有任何定位条件会报错，不会自动猜测上一问题。

## 命令

运行 `python3 scripts/session.py --help`，每个子命令也支持 --help。

| 命令 | 用途 |
|---|---|
| start | 创建或复用会话；可重复 --constraint 保存用户硬约束 |
| record | 提交观察、记录和 Wiki，同步词法索引并返回相关连接与待复核判断 |
| context | 紧凑知识、task_core 与来源引用；--cursor 跨轮差量，--context-epoch / --refresh 恢复当前视图 |
| discover | 全会话能力供需检索、候选路径、多输入组合与表达复核 |
| read | 按 ID 读取资料；--pointer 精读观察 JSON 字段，--offset / --length 读取工件字节范围 |
| compare | 并列比较两份已存观察的条件、响应和业务字段 |
| methods | 读取固定方法，不创建会话 |
| audit | 检查存储和引用 |
| wiki audit / wiki knowledge | 检查语义块或读取知识视图 |
| finish | 明确收尾；可显式导出快照 |

辅助脚本不扫描网络或执行攻击。实际取证沿用宿主工具及当前任务授权。

context/read/discover 均支持 --current-conditions 传入已知执行条件，值为 JSON 字符串对象。仅作本次资料适用性检查，不探测目标、不改变既有观察。

更新此包时替换完整技能目录，保留项目内当前研究的 .webounty 目录；不要把运行中的证据混入技能包。旧状态可读取，缓存自动按需重建，旧游标首次使用会重新交付。

## 本地检查

在技能目录运行：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

测试使用虚构资料和临时目录，覆盖本地检索、Wiki 来源、证据完整性与上下文交付等行为，不代表所有真实目标上的链路发现效果。

固定检索案例可另运行 `python3 -B tests/evaluate_local_ranking.py`。它报告 MRR、Recall@5、Precision@5、nDCG@5 和无答案案例表现；候选相关性不等于答案正确性，来源闭包由独立回归覆盖。可用 `--scripts-dir` 对照其他代码版本，`--output` 保存报告。日常 context 耗时写入本会话 `logs/operations.jsonl` 的 elapsed_ms，不记原始查询内容。

record/context/discover/read 等命令的本地日志还记录 metrics.stages_ms 与 counts：状态读取、索引、来源验证、候选发现、装包、视图处理、变化影响及发布检查分别计时；CLI 的 response 日志补充最终序列化与实际输出字符数。阶段是包含子阶段的耗时，不能相加当总耗时。files_read 统计 Corpus 的内容读取，snapshot_files_checked 统计一致性文件指纹检查，range_bytes_read 统计范围读取字节；publish_evidence_files_read 统计发布验证读取的不同会话内证据文件，排除待写材料，后续索引读取另计。record 返回的 retrieval_index 包含更新数，不把本机耗时写入模型的检索正文。

`python3 -B tests/benchmark_retrieval_efficiency.py --documents 100 10000 --repeats 5` 检查热缓存的稀疏倒排查询和依赖查找，报告本机耗时及 SQLite VM 步数。它不包含完整 context 的文件巡检、哈希校验或装包成本，不代表端到端延迟。

`test_source_chunk_boundaries.py` 覆盖 UTF-8 原文字节窗口、长标识符及中文切词；`test_query_literals.py` 覆盖引号、路径和标识符保护，均检查冷/热/重建索引。`test_retrieval_cache_recovery.py` 检查派生 SQLite 损坏恢复和非损坏错误保留。

`test_context_delivery_limits.py` 检查最终字符预算、完整来源交付、游标确认与损坏恢复；`test_wiki_review_integrity.py` 检查问题导航、文件来源复核和二进制附件。这些测试包含在上述 unittest 命令中，不测宿主理解或实际 token 消耗。

官方依据：[Skills](https://code.claude.com/docs/en/skills)；[Hooks](https://code.claude.com/docs/en/hooks)。
