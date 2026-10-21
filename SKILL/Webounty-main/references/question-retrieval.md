# 问题级检索与补检索

## 选择入口

保留一个会话内的 Wiki、原始观察和派生索引。Claude 使用现有宿主能力理解问题、整理知识和决定下一步；脚本不调用独立 LLM、Embedding API 或向量服务，不读取其他会话资料。

`read` 用于已知 ID 的精读；`context --mode lexical` 用于定位事实和原件；默认 `context --mode combined` 同时发现能力关系；`discover` 用于缺失输入、新产物的消费者和变化后的旧阻塞点；`compare` 用于已有观察对照。模式由宿主根据任务显式选择，脚本不凭自然语言关键词猜测意图。

词法模式跳过能力图发现和 cursor 的 change_impact 构建，但仍检索全会话，保留来源、显式反证、强制上下文、原件校验及差量交付。空的 chain_discovery 表示本次没有执行发现，不表示无链可找。需要复核新能力时使用 combined 或 discover。该模式不保证固定倍数提速；文件巡检、证据哈希和大范围命中仍有成本。

## 明确问题和证据缺口

对于已有的 Question、Goal、Step 或其他待判断记录：

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/session.py" context \
  --root '本轮root' --run-id '本轮run_id' \
  --question-ref 'Q-REPORT' --cursor main
```

question-ref 必须是当前会话已有的记录 ID，自动加入 anchor，可与 query 和其他 anchor 一起使用。简单事实查询不必为使用此功能新建问题记录。

`question_context` 在差量裁剪前根据本次当前资料生成，每次完整返回这份机械检查报告。它不依赖 Claude 是否还记得旧正文，也不把未命中材料当作不存在：

| 字段 | 含义 |
| --- | --- |
| source_observation_refs | 沿该记录已声明的来源关系找到、可读取的观察；其中可能包含前提或历史依据，不表示直接证明了答案 |
| source_artifact_refs | 沿该记录及上游来源的 artifact_refs 找到、通过完整性和定位检查的原件 ID；可用 read 精读，不表示已核实答案 |
| source_issues | 来源缺失、旧修订、待复核状态、显式更正等诊断 |
| competing_record_refs | 指向竞争判断或更正的精读入口，不自动接受其中任何一方 |
| declared_conditions | 问题记录声明的条件；传入 --current-conditions 时检查对应轴，其他适用性仍由宿主核对 |
| requirements.status | not_declared、not_checked、unresolved 或 candidate_complete |
| requirements.missing_preconditions | 代表方案中尚未覆盖的输入，含上游输入、条件和候选引用 |
| next_actions | 精读、检查前提或针对缺口检索的建议；query 缺省时由 Claude 根据具体缺口填写 |
| answer_support | 固定 not_assessed：没有自动判断这些材料能否支持答案 |

needs 未填写时返回 not_declared；词法模式没有检查 needs 时返回 not_checked，并建议 combined。单输入也使用递归前提规划，不能因直接提供者存在就忽略它自己的前提。多输入复用现有 AND/OR 组合规划。candidate_complete 仅说明选中的候选方案通过已声明条件检查，仍须验证实际产物被消费、身份和版本适用，以及最终结果。代表方案有缺口时，也不能据此否定所有 OR 备选。

显式引用的原件损坏或行位置失效时，该来源不能用于补齐候选方案；诊断同时出现在来源检查和候选链中。只引用原件而未建立观察的记录不会被误报为没有任何来源，next_actions 会包含相应原件 ID。

若返回包不可用、存在材料遗漏或问题记录未被返回，检查报告明确标为 question_context_incomplete，不把截断后的空列表解释成没有前提或证据。报告本身参与显式字符预算；装不下时返回 budget_exhausted，不推进 cursor。

同一个 cursor 的 task_core 每次保留目标与硬约束；来源诊断也不会因记录正文进入 unchanged_refs 而消失。上游改动可使旧 Fact/Question/Step 的 basis_status 成为 needs_review，即使其作者 status 仍是 verified、open 或 done，也须先处理来源问题。unknown 与 unknown 不能构成 candidate_complete。

## 缺口驱动的下一步

示例：问题是“先前失败的报表读取能否继续”。

1. 查旧问题记录，区分失败原因、现有依据和缺失前提。
2. 精读已有观察。创建任务成功只能说明获得了任务，不说明下载成功。
3. 对未解决输入单独检索，例如“哪个已观察步骤提供下载授权”。已知输入对应记录时用 discover 的 anchor，不重复泛搜同一漏洞名称。
4. 找到候选后读双方原件并核对条件。若需要新实验才能判断，就取得新观察，再 record 更新原问题及其依据。

旧失败的 reopen_when、未决输入和业务字段可成为下一次查询的具体词。环境、会话或凭据改变时显式传入当前已知条件，避免把原先受阻/成功的观察直接套用到新环境。恢复压缩后的上下文时更新 --context-epoch 或使用 --refresh，再开始判断。

只有在资料确实回答问题、反证得到处理且适用条件被核实时，Claude 才形成相应结论。脚本不会自动提交 verified，也不将派生报告另存为原始证据。

## 停止原样重复查询

带 cursor 的 context 返回 `retrieval_progress`：

- inspect_material：尚未向这个 cursor 交付相同请求及相同当前结果，先读材料。
- stop_repeating_query：此 cursor 曾收到相同请求及当前结果；停止原样重查，精读已有引用、改写具体缺口，或取得所缺的新观察。
- resolve_incomplete_retrieval：读取或交付不完整，先处理诊断，不将失败登记成已经完成的检索。

请求签名包含 query、anchors、mode、question_ref、方法选择及显式预算等选项；结果签名包含当前状态修订和返回内容。换到另一个问题后再回来，仍能识别此前交付过的相同请求。无关提交改变状态修订也会重新提示读取，因此这是保守的重复交付检查，不是语义等价查询识别或全局知识变化日志。

签名只存在当前会话的 cursor 缓存中，不存第二份证据。缓存丢失后重新交付。不同读取者使用不同 cursor；上下文压缩后执行 `--refresh`，清除该 cursor 的交付及请求记忆并重发当前问题。停止提示不代表证据充分、不存在其他材料或全部路径失败；脚本不会阻止后续调用，也不增加循环次数或模型 Token 硬上限。

## 用现有 Wiki 字段改善召回

写入时保留 summary、questions、keywords、aliases 和标题路径之间的区别。summary 描述已观察事实及适用对象；questions 保存可能需要查询的问题；aliases 仅保存确实同义的名称。让原始 `job_id` 带上已知的接口、身份和业务背景，但不要把“能否下载”改写成“已经可以下载”。新表述需通过 record 入库，沿用原有增量索引。

这些字段与少量本地中英术语扩展共同改善召回，词表之外仍不能保证找回没有共同词项、别名或显式关系的语义近似内容。查询扩展只增加候选，不改变已声明的能力类型；需要精确字符串时使用引号或反引号。显式传入 current-conditions 可辅助排序，但不能替代对照观察、否定条件和现场验证。具体规则和命中理由见 [检索与链路组合](retrieval.md)。

## 验证

`python3 -B -m unittest discover -s tests -p 'test_local_*.py'` 验证无模型查询扩展、短语排序、缓存更新、条件匹配、镜像去重、反证补齐和原件校验。`python3 -B tests/evaluate_local_ranking.py` 在固定虚构案例上报告排序与召回指标；通过 `--scripts-dir '旧版scripts目录'` 使用同一语料对照。案例覆盖范围和样本量有限，不表示真实研究准确率。

`python3 -B -m unittest discover -s tests -p 'test_question_workflow.py'` 回放前提缺失、新提供者、更正、单输入上游检查、词法模式反证补齐、重复查询、refresh、会话隔离、预算不足和原件篡改；同时验证问题元数据参与召回而不改变证据状态。

沿用 `tests/evaluate_retrieval.py` 和 `tests/replay_session.py` 比较现有召回与多轮交付。它们和新增回放均为离线合成验证，不能证明 Claude 在真实研究中必然选对入口、读懂材料或停止循环。真实会话还需检查实际工具调用顺序、引用是否支持结论，以及是否遗漏前提或反证。
