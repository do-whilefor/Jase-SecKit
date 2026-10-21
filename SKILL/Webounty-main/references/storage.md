# 存储与提交格式

## 文件职责

以下路径均相对本轮 root：`<项目目录>/.webounty/<会话ID的SHA-256>/`。start 默认以调用时的工作目录作为项目目录，也可传 `--project-root`；后续命令直接沿用返回的 root。每个会话有独立状态、Wiki、原件和索引。

| 文件 | 职责 |
|---|---|
| session.json | 项目路径、会话 ID、run_id 与工作区归属 |
| state.json | 当前 Goal/Fact/Step/Finding/Capability/Chain 与实体、观察和工件索引 |
| evidence/ | 每次不可覆盖的观察 JSONL、可选原文件副本 |
| wiki/pages/ | 有稳定页面与块 ID 的 Markdown |
| wiki/manifest.json | 稳定页面/块定位、父页面 ID、哈希、来源修订、检索字段及可选知识注释 |
| wiki/index.md | 派生导航 |
| cache/page-checks.json | 可重建的首页检查缓存；不作为来源，不替代读取和审计 |
| cache/retrieval.sqlite | 词项、原件窗口、文档依赖与索引修订；资料提交后同步，失败单独警告，可重建 |
| cache/metadata.sqlite | 按 ID 读取的派生元数据、供需与反向关系索引；资料提交后更新变化对象，可重建 |
| .publication/ | 发布期间的暂存文件、备份和恢复日志；恢复完成后清理，不作为历史版本库 |
| .publication.lock | 会话发布与恢复的操作系统锁入口；文件存在不代表进程仍持锁 |
| logs/ | 操作记录，不复制凭据或完整流量 |

一个会话一份工作区，多轮对话持续更新；ID 不含实际凭据。记录是真实状态，页面是有来源的解释，检索结果是读取视图。不要手工改哈希或清单，也不要把 Wiki 当作新的原始证据。

## 提交一个 batch

record --input 接收 UTF-8 JSON 文件，或 `--input -` 从 stdin 读取。顶层包含 entities、observations、records、pages 四个数组；没有更新的数组可省略。每项由作者提供稳定 id，脚本生成 revision、来源定位、工件哈希和 Markdown 锚点。

示例见 [record-example.json](../assets/record-example.json)。第一次可只提交观察和对应事实；有价值的能力随理解形成再补充，不要求一次填全。

### 原始观察

```json
{
  "id": "O-001",
  "summary": "本次实际观察的简短描述",
  "subject_refs": ["E-API"],
  "content": {
    "environment": "lab-v1",
    "actor_ref": "E-USER",
    "session_generation": "1",
    "stage": "submit",
    "request": {"method": "POST", "url": "https://training.invalid/export"},
    "response": {"status": 202, "body": {"job_id": "DEMO-JOB"}}
  }
}
```

content 可保存 HTTP、日志、源码定位、用户输入等 JSON 对象，字段来自真实资料；上例为虚构格式。主体 ID 必须先登记或在同批 entities 中登记。没有主体时使用空数组，不编造。

按实际已知信息保存 environment、actor_ref、session_generation、credential_generation、target_version、observed_at、trace_ref、truncated。会话代次和凭据代次是不同字段；trace_ref 是原始执行记录的定位说明，不会被脚本自动抓取。原件取得后先入库，再写 summary；工具端已经截断的输出不能通过摘要补成完整证据。

source_path 可填写实际输入文件的绝对路径，脚本流式复制原件、计算哈希并登记来源；原路径不会删除。UTF-8 文本原件分段参与全文检索，二进制原件仅保存与验证。大响应、日志或源码文件优先从 source_path 导入，content 只写实际取得的请求、响应状态、环境等上下文字段；不要为缩短正文而编造摘要或条件。观察存为单独 JSONL，不允许重复覆盖 ID。证据更正用新观察和对应记录的更正关联表达。

可选 excerpt_selectors 在提交观察时选择紧凑视图需要保真的原文：

```json
{
  "id": "O-ERROR",
  "content": {"response": {"status": 403, "body": {"error": "CSRF token mismatch", "allowed": false}}},
  "excerpt_selectors": [{"pointer": "/response/body/error"}, {"pointer": "/response/body/allowed"}]
}
```

pointer 使用 JSON Pointer，相对 content 定位，保留原值及类型，包括 false、0、null 和空字符串；它不是原始 JSON 排版字节。字节摘录使用 `{"offset":0,"length":64}`，相对 source_path 导入的文件，须与实际原件配合。选择范围应含必要条件或相邻解释。输出附 observation_ref、artifact_ref、source_sha256；字节范围另有 range_sha256。两类摘录都标为 independent_observation:false，不增加独立证据数量。已有观察不可改写选择器，用 read --pointer 或范围读取即可。

### 实体

实体字段为 id、kind、title/summary，按实际需要增加 aliases、source_refs、owner_ref、tenant_ref、asset_ref。后面三个字段引用实体；source_refs 引用研究记录。观察到、文档声明和推测关系的区别在事实及正文中说明，名字相同不是同一实体的证明。

### 研究记录

共同字段：id、kind、status、summary、subject_refs、observation_refs。kind 可用 Goal、Fact、Question、Step、Finding、Capability、Chain。其余字段按问题需要添加，如 title、conditions、limitations、reopen_when、change_reason、cvss。

| 类型 | 推荐用途与状态 |
|---|---|
| Goal | 目标、范围、完成条件；active/completed/blocked |
| Fact | 有条件的观察表述；observed |
| Question | 待回答问题与缺口；open/resolved/blocked |
| Step | 假设、缺口、下一验证；active/blocked/done |
| Finding | 候选漏洞及影响；candidate/verified/refuted/needs_review |
| Capability | 可供组合的能力与必要条件；observed/candidate/verified/refuted/needs_review |
| Chain | 组合及逐边状态；candidate/verified/refuted/needs_review |

记录关系 source_refs、requires、evidence_refs、supporting_fact_ids 等引用**记录 ID**。observation_refs 引用**观察 ID**。不要把原始观察 ID 填入 evidence_refs；Chain.links[].evidence_refs 是例外，专门引用连接观察。

capability.provides / capability.needs 是能力供需，不要混用记录级 requires 字段。详细结构见 [retrieval.md](retrieval.md)。

更新同一 ID 时，传入字段覆盖该字段，未传字段保留；嵌套对象和数组按整体替换，所以修改 capability 或 observation_refs 时传完整新值。用 change_reason 简要说明更正原因。脚本维护修订，不提供版本回滚。

Goal 可保存 hard_constraints（用户约束原文的字符串数组）、scope、active_question_ref、next_action；Question/Step 也可声明 next_action。start --constraint 可重复传入，重复 start 不覆盖已存目标或约束。task_core 每次从这些字段派生，不新建一份黑板文件，也不自动编造下一步。

顶层 conditions 保存此判断适用的共同执行条件，例如 `{"environment":"lab-v1","session_generation":"2","credential_generation":"3"}`。context/read/discover 的 --current-conditions 只检查本次显式传入的轴，值为字符串；缺少或未知返回 current_condition_unknown，不同返回 current_condition_conflict。它不修改存储状态、不自动探测环境。能力 provides/needs 中的 constraints 描述产物或输入，可合法指向其他身份，不被用作当前执行身份的替代。

修订时自动保存简短 history 条目，用于说明旧判断为何变化；其 record_refs / observation_refs 是历史定位，不加入当前必需证据。首页分区、发现详情、负结果和修订区的写法见 [Wiki 组织](wiki-layout.md)。

新反证可单独建记录并设 contradicts:[旧记录ID]。旧记录需要被修正时同时更新其 status 和关联；不要删除旧原件。来源、主体条件或反证变化沿依赖传播，未在本批显式更新的 Capability、Finding、Chain 转为 needs_review，并带 basis_status:needs_review；Fact、Question、Step 只标记 basis_status，保留历史或工作流 status。record 用 needs_review_record_ids 返回这些判断，并保留 needs_review_chain_ids。原始观察不因此被否定，read/context/discover 统一提示依据问题。

已有 basis_status:needs_review 不会因普通字段更新解除。复核后提交 reviewed:true、change_reason，并重新绑定当前 source_refs 的 revision、更新必要的 observation_refs；Capability/Finding/Chain 同时设置合适的 status。reviewed 是提交指令，不写入存储。来源仍过期、缺失或上游待复核时拒绝解除；它检查引用，不证明作者的复核结论正确。保留真实反证关系，不为清除提示而删除反证。

曾取得的能力后来撤销或过期时，保留历史取得观察，新增当前失效观察，并修订该能力的当前可用性。摘要与 change_reason 说明反证针对的是“现在仍可使用”，不否定过去确实取得；尚未确认失效时保留待复核状态。

新记录的 contradicts 与旧记录对应的 contradicted_by 可以同时登记，表达同一反证关系；检索保留两端和原始观察。无需为反向查找重复登记。真正的 source_refs、requires 等循环依赖仍会被拒绝。

### 页面

不传 pages 时，每个新增/更新记录自动生成其主页 `WK-记录ID`。需要合并实体解释、业务流程或多个相关事实时，可显式提交：

```json
{
  "id": "WK-FLOW",
  "kind": "flow",
  "title": "报表生成与下载流程",
  "record_refs": ["F-001", "C-001"],
  "blocks": [{
    "id": "B-SUBMIT",
    "title": "提交响应能证明什么",
    "text": "受理响应提供任务标识，尚不能证明后台处理或下载成功。",
    "source_refs": ["F-001", "C-001"]
  }]
}
```

页面 kind 为 entity/flow/capability/question/chain。record_refs 是页面依据，块的 source_refs 可进一步缩小到其实际依赖。省略 blocks 则从记录生成可阅读块。

一块表达一个完整判断，条件、否定和结论不要切散。需要依赖其他块时用 required_block_refs:[{page_id,block_id}]。可选 knowledge 支持已有 boundary、controls、experiments、capability_links 和 lifecycle；详见 [知识注释 schema](wiki-knowledge.schema.json)。基础写入不要求填复杂注释。

页面可设 `parent_page_id` 指向同会话已有页面，或同批提交的页面；根页省略此字段或设为 `null`。目录关系只用于导航与检索，不增加事实依赖，也不意味着父页结论适用于所有子页。不存在的父页和循环关系会令提交失败。

页面和块均可提交 `summary`、`questions`、`keywords`、`aliases`；也可用 `retrieval` 对象组织已有检索字段。`summary` 使用简短文本，其余用字符串数组。问题优先取实际会话提问或当前已明确的缺口；仅有问题不能证明答案或能力已成立，不需要每轮为整个 Wiki 生成问答。检索字段写入 manifest，正文和原始证据仍各自保留；它们不替代来源和适用条件。

```json
{
  "id": "WK-FLOW",
  "parent_page_id": "WK-REPORTS",
  "questions": ["提交得到的任务标识能否满足下载流程的前提？"],
  "keywords": ["导出", "任务标识"]
}
```

已有页面只提交 `id` 加标题、父 ID、kind 或上述检索字段时，执行元数据更新：保留原块、稳定锚点、来源修订和已审阅集合。标题改变只更新页首；移动目录不改正文。祖先标题路径由当前父子关系派生，仅在可重建检索缓存中保存投影；索引根据变化路径更新受影响条目。改名或移动不代表已复核旧解释，待复核状态不会因此消失。

提交 `blocks` 或 `record_refs` 时仍是完整页面编辑，应提供完整的新解释及实际来源；需要保留的父关系与检索字段也一并传入。自动从记录生成的块由脚本标为 `representation: record`，使紧凑读取能避免重复返回同一记录正文；作者块不能自行声明这个标记。

同一判断保持主要页面，其余页面用链接。脚本只刷新提交的页面或自动主页，不会冒充读懂所有相关新证据；未复核的新资料应保持 review_required 提示。

发布时按需读取页面和原件。首页检查复用上一轮与当前依赖签名、相关文件元数据均相同的结果；新反证、来源修订、主体候选变化和适用条件变化会使相关检查失效。显式 `required_block_refs` 指向的解释待复核时，引用它的页面也显示待复核。新增资料不会自动加入旧页的已审阅集合。

仅改名或移动页面时校验页面内容，不重新展开未变化的证据。当前状态、清单和候选签名仍会参与本次计算，首页仍按当前状态重写；局部更新指减少无关页面与原件读取，并不声称所有处理都是常数成本。

检查缓存保存在 `cache/page-checks.json`，可删除后由下次提交重建。文件大小、修改时间、变更时间等用于发现普通外部修改，相关检查会重新读取并验证哈希。缓存只供首页发布复用；`read / recall / audit` 仍独立验证所需内容，完整 `audit` 保持全量。缓存和其他派生文件不能导入为原始证据。

## Chain 记录

Chain.steps 是拓扑有序记录 ID，links 描述前面的能力如何提供后面步骤的输入。一个步骤可有多个必要输入和多条入边，仍须满足全部前提。

```json
{
  "id": "CH-001", "kind": "Chain", "status": "candidate",
  "summary": "研究导出产物能否进入下载流程",
  "steps": ["C-001", "C-002"],
  "conditions": {"environment": "lab-v1"},
  "links": [{
    "producer_ref": "C-001", "consumer_ref": "C-002",
    "provide_index": 0, "need_index": 0,
    "assessment": "candidate", "evidence_refs": [],
    "conditions": {"environment": "lab-v1"},
    "note": "仍缺实际消费证据"
  }],
  "observation_refs": []
}
```

provide_index 和 need_index 从 0 开始。连接 assessment 为 candidate/verified/refuted。已验证连接需有双方原始观察及实际消费说明；最终 observation_refs 单独引用整链结果。脚本检查来源覆盖与明确条件冲突，不能判断作者写下的消费说明是否真实。

已具备的起始能力可写 needs:[]，明确能力已经取得的观察和适用条件；不能为了让整链通过而删除尚未满足的前提。只有实际验证后才提交 verified。

## 读取与复核

```bash
python3 scripts/session.py read --root '本轮root' --run-id '本轮run_id' --id C-001 --id WK-FLOW
python3 scripts/session.py read --root '本轮root' --run-id '本轮run_id' --id SRC-O-001 --offset 0 --length 65536
python3 scripts/session.py read --root '本轮root' --run-id '本轮run_id' --id O-ERROR --pointer /response/body/error
python3 scripts/session.py audit --root '本轮root' --run-id '本轮run_id'
```

数据不正确时先修正当前 batch，命令失败后不要重放外部取证动作。提交从读取现有状态起持有会话级操作系统锁，检查结构和来源后，先暂存完整新文件和所需旧文件备份；大型原件继续流式复制。恢复日志就绪后才依次安装状态、Wiki、观察等文件，全部安装完成后记录提交标记。进程结束会释放锁；同会话仍应由一个执行者组织提交。

安装中途失败时恢复到该批次开始前的文件；进程中断后，下一次 start 复用或资料读取会先尝试恢复。恢复本身中断时保留备份以便重试；已提交批次只清理残留，不撤销已提交观察。不要手动删除 `.publication/` 或发布锁文件。若恢复日志、备份或目标文件不满足校验，报告错误并保留现场，不猜测覆盖。此机制不保留已完成批次的历史快照，也不提供历史版本回滚。

`publication_status: committed` 表示本次资料已安装，不表示所有后续工作都成功。检查 `warnings`：页面检查缓存、词法/元数据索引、提交后关系分析或日志失败均单独报告，不撤销本次资料；不要仅因这些警告重交同一不可变观察。索引同步成功时，`retrieval_index` 区分本次重建、重用、删除、签名检查和原件分段数；同步未完成时，后续查询按当前资料重新核对或重建缓存。

`publication_cleanup_pending` 表示资料已提交，但暂存残留未清理；读取仍检查当前资料，后续写入须先完成清理。`publication_durability_uncertain` 表示提交标记已安装，但其后的目录同步失败；保留警告并重新打开核对当前状态，不能把它当作未写入而盲目重试，也不能据此承诺掉电后持久性。

读取入口会拒绝其他执行者正在安装的批次，并用文件指纹检查已有读取是否跨越修订；检测到变化时重新读取。各文件仍依次替换，直接打开目录中的文件不享有整体原子快照。恢复依赖可读取的日志和备份，不保证任意磁盘损坏或掉电场景都能恢复。派生缓存可重建，权威 state/manifest/原件损坏不能靠重建缓存修复。
