# 数据契约与运行命令

Python 3.10+；运行脚本只需标准库。用户只需提供材料与平台，以下中间数据由助手整理。`<skill>`、`<materials>`、`<task>` 是需替换的实际路径，路径含空格时加引号。`<task>` 应在原始材料与技能目录之外，每个案件版本使用独立目录。

```text
python <skill>/scripts/index_materials.py <materials> --output <task>/manifest.json
python <skill>/scripts/render_report.py --manifest <task>/manifest.json --case <task>/case.json --fields <task>/src_fields.json --profile <skill>/references/src/jd.json --output-dir <task>
```

登记后先阅读原件，编写事实记录并完成[筛选与评分评估](assessment.md)，再填 `src_fields.json`、运行渲染。线索案件的 fields/groups 可为空，但仍保留案件元数据和复核声明。`jd.json` 按所选平台替换。渲染器已调用检查器并核验原件哈希，无需重复运行检查；查看 `review_issues.json`、复核实际报告后修正，更新同一版本已有产物时显式加 `--overwrite`。需要单独诊断时可运行：

```text
python <skill>/scripts/check_report.py --manifest <task>/manifest.json --case <task>/case.json --fields <task>/src_fields.json --profile <skill>/references/src/jd.json --output <task>/review_issues.json
```

形式化结构见 [report-schema.json](report-schema.json)。该文件用于数据交换说明和支持 JSON Schema 的工具；运行校验器针对报告业务规则检查，不声称实现完整 JSON Schema 引擎。

## 整理杂乱材料

只有附件或对话说明时，在独立收集目录保存附件副本与用户原话，注明来源和已知时间，再登记。原件不改写，助手推断不写作用户证据。登记成功仅代表文件可追溯，先阅读清单中的 warnings，再逐个读取相关原件；图像看不清、压缩包内容尚未读取等都记录具体缺口。

按内容与依赖关系还原步骤，核对每个账号、对象、请求与响应的对应关系。不同时间/环境的响应不要强行合并；相互矛盾的材料保留双方引用。用户称“成功”但只有 PoC 时，记录用户自述，执行效果仍为未验证。不要把单次观察扩展成任意账号、全量数据或更高权限。材料不足仍编写草稿，只提出影响结论或必填字段的具体补证需求。

## PoC 取舍与全稿复核

由助手阅读原件后判断内容用途，再填写报告；检查器不理解业务语义，渲染器也不会自动清洗请求或代码。字段多、值长或名称常见，都不是可删除的依据。

| 材料内容 | 报告处理 |
| --- | --- |
| 触发条件、身份/对象关系、关键输入、判定结果、对照或反证，以及平台要求的完整 PoC/请求 | 保留必要结构、先后顺序和证据定位；真实敏感值使用一致代号。 |
| 材料已说明与复现无关的浏览器提示、工具横幅、进度输出、重复日志及大段无关响应 | 正文可省略或用定位引用；在内部复核记录中说明省略类别与依据，不改写原件。 |
| 作用不明的请求头、Cookie 项、业务参数、脚本依赖或初始化 | 保留在完整材料中，明确必要性未验证；正文可选取阅读摘录，但不能断言这些字段无用。 |

鉴权、会话、CSRF、Origin/Referer、Host、Content-Type/boundary、签名/时间戳、对象 ID 等可能影响触发；User-Agent、追踪字段也不能按固定黑名单删除。重复参数、空值、顺序、编码或字节差异可能正是漏洞条件，不擅自合并、解码、排序或格式化。脚本保留必要的导入、初始化、调用顺序和结果判定，不把自拟的精简代码当成用户原始 PoC。

区分**完整脱敏材料**与**阅读摘录**。摘录在代码块外注明省略范围、原件证据编号与定位，以及“未验证删减后可复现”；不在声称完整的请求中插入 `...`。没有用户提供的删减对照证据，不能称为“最小可复现 PoC”，也不运行 PoC 来验证删减。平台要求完整触发请求或完整 PoC 时，按对应字段/附件规则提供完整脱敏结构，正文避免重复整包；缺材料或超限时列具体缺口，不静默截断。

脱敏与精简都不能改变结论。替换值可能使签名、Content-Length 等与展示内容不再匹配，应在代码块外说明需按真实输入恢复/重算且未验证可重放；如果漏洞依赖原始长度、重复头或精确字节，保留这些关系及受控原件定位，不擅自“修正”异常。

交付前阅读全文，逐项确认内容是否支撑定位、前提、复现、结果、影响边界或平台要求；去掉无依据的泛化危害、套话、与已知问题无关的修复建议及无必要的重复叙述。同一请求在步骤中说明关键变化，在专用请求字段完整展示；平台独立必填字段需要重复时仍分别填写。失败对照、限制、未验证和冲突不可当作杂余删去。

将 PoC 保留/省略的类别、依据与原件定位，以及全稿检查结果简记到 `src_fields.json.content_review.notes`。不要求为了精简而删字段：全部保留或没有 PoC 时也说明理由；只记录实际完成的检查，不复制空泛的“已检查”。摘录标记、未验证条件和影响边界仍须出现在报告相应位置，不能只藏在内部记录里。

## manifest.json：材料登记

```json
{
  "schema_version": "1.0",
  "materials_root": "原始材料目录的绝对路径",
  "materials": [{
    "evidence_id": "E-内容哈希前16位",
    "sha256": "完整SHA256",
    "size_bytes": 123,
    "kind": "http",
    "mime_type": "text/plain",
    "paths": ["request.http", "copy/request.txt"]
  }],
  "warnings": []
}
```

内容完全相同才去重；不同格式但视觉相同的截图不会自动合并。文件种类仅是扩展名/MIME 分类，不说明文件已解析或内容可信。未知或无法读取的文件继续保留登记警告。

## case.json：事实与证据

必需顶层字段为 `schema_version`、`case_id`、`version`（从 1 开始）、`src`、`profile_version`、`target`、`identities`、`prerequisites`、`steps`、`observed_results`、`supported_impact`、`evidence`、`uncertainties`、`semantic_review`。

`target` 保存已知目标信息；不要仅凭域名猜业务归属。目标信息需要通过正文论断及证据建立依据。其余五个论断数组使用统一结构：

```json
{
  "id": "S1",
  "text": "所提供代码尝试查询另一个对象，但未见执行响应。",
  "verification": "unverified",
  "evidence_refs": ["E-登记生成的编号"]
}
```

`verification` 可为 `observed`、`inferred`、`unverified`、`conflicted`。描述代码内容本身可以是 observed；其预期的执行效果仍须另行标为 unverified。`supported_impact` 中允许记录尚未验证的可能影响，但不能因数组名称就宣称其成立。

`evidence` 提供引用定位，同一 evidence_id 可对应不同区域：

```json
{"evidence_id":"E-登记生成的编号","locator":"request.http 第1–8行","note":"已脱敏的具体观察"}
```

`uncertainties` 项包含 `id`、`description`、`affects`（受影响步骤/结论 ID）、`evidence_refs`。同一问题合并为一项，描述说明具体缺口、对相关结论的影响及所需补证，不能只写“待确认”。仅把同一缺口涉及的论断放入 `affects`；导出会将它们的状态和证据合并到该项，不再逐条复述原文。没有对应待确认项的未确认论断仍单独显示，完整原文保留在 case。

`semantic_review`：`{"status":"pending","notes":[],"reviewed_evidence_refs":[]}`。完成原件对照后改成 completed 并登记实际审阅的引用；这是宿主声明，程序无法独立认证。缺证据的结论保持 unverified 或 conflicted，不能为消除检查问题抬高其状态。

### 筛选与评分记录

新案件填写 `triage` 和 `cvss31`；为兼容旧案，Schema 不强制存在，检查器会提示尚未评估。旧案缺少 triage 时仍按原平台草稿导出，不表示筛选已通过；补证或改写时补齐评估。

```json
{
  "triage": {
    "status": "lead",
    "matched_rules": ["F1", "F8"],
    "reason": "只有 CORS 配置和扫描器提示，缺少跨来源读取非公开数据及复现结果。",
    "basis": {"boundary": [], "reproducibility": [], "impact": []}
  },
  "cvss31": {
    "vector": null,
    "rationale": {},
    "reason": "未证明边界失效及实际影响，暂不评分。"
  }
}
```

以上对象合并到 case 顶层，不替代已有事实字段。`triage.status` 为 pending/lead/supported；`matched_rules` 仅填实际命中的 F1–F8，可为空；`reason` 说明判断及缺口。`basis` 的三个数组引用已有论断 ID（不是证据 ID），各自支持边界失效、稳定复现及实际影响。supported 要求三类均有引用，且所指论断为 observed、有已登记及定位的证据，并完成覆盖这些证据的 `semantic_review`。引用存在不证明论断语义正确，不能将“扫描器命中”改成 observed 就据此升级漏洞。

可评分时 `cvss31.vector` 填完整八项 Base 向量，`rationale` 对 AV/AC/PR/UI/S/C/I/A 各填 `{"reason":"该值的具体依据","claim_refs":["实际论断ID"]}`，`reason` 说明整体评估范围。每项须引用有证据支持的 observed 论断。缺依据时保持 vector 为 null，reason 说明缺口，不填 0 分。只保存向量与依据，分数与严重性由检查器重新计算；提交手填 score 不会成为评分依据。公式/版本/指标错误以及筛选或引用缺口会被指出，不输出没有依据的分数。

筛选、评分文字及所引用的论断都属于拟分享内容，必须一致脱敏。只作为线索的案件不要求填满平台必填字段，但已填写字段仍受类型、枚举、引用等检查；原始字段仍留在本地供补证复用，不显示为已确认漏洞。

## src_fields.json：平台字段

```json
{
  "schema_version": "1.0",
  "case_id": "example-case",
  "case_version": 1,
  "src": "jd",
  "profile_version": "2026-10-03.1",
  "fields": {},
  "groups": {},
  "redaction_review": {"status":"pending","notes":[]},
  "content_review": {"status":"pending","notes":[]}
}
```

每个字段值包装成 `{"value":null,"status":"missing","evidence_refs":[]}`，可附 `notes`。状态含义：

| status | 含义 |
| --- | --- |
| supported | 值有材料或直接用户说明支持；脚本不认证其语义。 |
| inferred | 合理推测，字段正文也应明确标注。 |
| missing | 缺失或待核对，value 使用 null。 |
| manual | 用户在提交时完成，如验证码、协议、实际密码、FLAG。 |
| not_applicable | 条件明确不成立；说明依据，不能绕开必填字段。 |

普通字段放 `fields.<field_id>`；重复组放 `groups.<group_id>[行号].<field_id>`。京东有 `test_ips`、`test_accounts`、`request_packets`，每组至少一行。`flag` 是可选模块，可省略或为空数组。组内条件引用本行字段，然后才考虑顶层字段，不能将一个请求包的危害类型套给所有包。

正文以对应平台的 `body_sections` 为结构，包含必要前提、操作、实际结果及影响边界，逐步关联证据；同一事实在最相关小节展开，其他位置只作必要简述，导出不会再重复整份 case。推测、未验证与冲突也要在字段文案中明确，而非仅在 JSON 标记；修复建议明确为建议。未知字段选项留 missing，验证码、协议、实际凭证等留 manual。

`kind=multiline` 的请求字段在 `value` 中只放请求/链接文本，不嵌套 Markdown 代码围栏；摘录范围、脱敏和未验证说明放在该字段的 `notes`，渲染后位于代码块外。`richtext` 正文可自行使用代码围栏。

级联选择 `value` 是完整路径数组；美团两级下拉则是两个字符串字段。布尔项用 JSON 布尔；京东“是否核心内网”保留“是”/“否”字符串。未核对的三级分类不能填作确定枚举。页面默认值只记为平台提示，不自动代表用户选择。

附件字段的 value 为 `[{"path":"相对原始材料目录的文件路径","evidence_id":"E-登记编号","purpose":"用途"}]`。路径须为已登记的原件或已单独登记的派生材料；使用该字段不会自动上传。暂未有合规附件时保留 missing 或不适用说明，不伪造压缩包。

`redaction_review` 仅在宿主审阅实际输出文本及所有拟分享图片后改为 completed。令牌等原值留在受控原件；在分享字段中用一致的替代符，并把需恢复值的位置记为人工事项。原始截图检查或制作脱敏副本后才用于分享；脱敏请求不保证可直接重放，脚本也不保证自动脱敏。

`content_review` 是助手对当前报告完成上述取舍与全稿复核的声明，`status` 为 pending/completed，`notes` 为字符串数组。首次渲染使用 pending，阅读实际报告、修正内容后记录具体说明并改为 completed，再渲染确认最终输出。后续改变内容需重新置 pending 并复核。旧数据未提供此对象时仍可渲染，但会提示内容复核未完成；completed 且没有非空说明也会提示。程序只检查声明，不认证取舍正确性或 PoC 可复现性；内部 notes 不自动加入正文。

## review_issues.json 与导出

问题包含 `code`、`level`（error/warning/manual）、`path`、`message`。`needs_revision` 表示仍有错误；`draft` 表示仍有警告或人工事项；`checked` 只表示本轮程序检查未报问题。脚本的 `semantic_verified` 为 false，不代表对漏洞真实性作出否定或肯定。

`review.triage` 包含声明的 `status`、依据校验是否通过的 `passed`、是否显式提供筛选记录的 `explicit`。`review.cvss31` 为重新计算的 Base 结果或 null；原件哈希改变、丢失等完整性检查错误会撤销通过状态及分数。`passed` 只表示所要求的声明与证据引用通过程序检查，不等于动态验证成功。

格式或文件解析失败时检查命令返回非零；合法数据即使含业务问题也可产出 review，调用方必须读取 status 与 issues。渲染器保留这些问题，不因草稿存在缺口拒绝全部交付。

`report.md` 是主要交付。显式筛选未通过时输出线索记录；通过时按原站独立字段和重复组输出，并展示漏洞评估、有效 CVSS 结果和指标依据。两种输出都保留证据定位、未确认论断及具体缺口。筛选状态与程序检查状态分别表达，不因 checked 就认证漏洞。完整事实与程序诊断留在 `case.json`、`review_issues.json`，不重复堆进正文。`manifest.json`、`src_fields.json` 及 `attachments.md` 同样留作本地追溯记录，默认无需逐个交付；其中可能含原始文件名或路径，分享前另行检查。程序不会上传、自动打包或执行 PoC。

补证时递增 case 版本，重新登记并复核受影响的论断与字段，未变内容的证据 ID 保持不变。切换平台复用同一事实记录，更新 `src`、`profile_version` 并重新映射字段，不为适配平台改写事实。

## 新增平台

在 `references/src/` 增加同名 `<src>.json` 和 `<src>.md`，并在 `SKILL.md` 平台表加入入口。JSON 参照现有配置，保留唯一 `id`、版本、来源及核对日期；按实际表单定义 `fields`、`groups`、`body_sections`，未知规则留空或明确待核对。Markdown 只记录该平台的写作差异和规则盲区。

新增字段尽量使用已有 kind、枚举、分组和条件规则；检查器与渲染器按配置处理，无需添加平台名称分支。仅当表单出现当前契约无法表达的控件时扩展脚本并补测试。增加该平台的采集回归测试后运行 `python -m unittest discover -s tests`；通用配置测试会自动覆盖目录内的新平台。

条件字段用 `when: {"field":"父字段ID","equals":"选项"}`，或 `when: {"field":"父字段ID","in":["选项A","选项B"]}` 表示任一选项激活；`equals` 与 `in` 必须且只能存在一个。值可为字符串、布尔或完整分类路径；`equals:["一级","二级"]` 是一条路径，多个路径用 `in:[["一级","二级"],["其他一级","其他二级"]]`。`in` 不能为空。父字段缺失或仍待人工确认时，条件保持未知，不能作为无需填写的依据。

多个条件组合用 `when: {"all":[条件,...]}`（全部满足）或 `when: {"any":[条件,...]}`（任一满足），可以递归嵌套，数组不能为空；同一层不能混用组合操作符和字段比较。`all` 中任一明确为假则整体为假，`any` 中任一明确为真则整体为真，其余缺失信息保留未知。每个父字段先取当前重复行，再取顶层；检查与渲染使用同一判定。受一级分类控制的二次选项，须把一级分类也纳入组合条件，避免切换分类后残留的二次选项误激活字段。

`options_by_parent` 只记录已核对的父分支，键须属于父字段的 `options`；缺失映射表示子选项待核对，检查器保留 `parent_option_unknown` 警告，不将该分支的所有子选项误判为非法。

`max_length` 默认表示 DOM `maxlength`，按 UTF-16 单元检查，超限为错误；仅观察到编辑器计数器时添加 `length_basis:"editor_counter"`，超阈值只提示警告，须在页面核对实际计数方式。两种情况都保留原文，不静默截断；没有观察到限制时不自行配置。

附件统一大小规则使用 `size_limit`；同一控件按格式分别限额时使用 `size_limits_by_extension`，键为小写扩展名（如 `.pdf`、`.zip`），值仍为 `{label,bytes,inclusive,basis,scope}` 规则。匹配按文件扩展名忽略大小写，优先使用格式规则，未匹配时回退到 `size_limit`；没有规则表示未验证限制。`bytes` 为非负整数，`inclusive` 表示能否等于阈值；`scope` 支持 `per_file` 或 `unknown`。`basis=conservative_decimal` 或未知作用范围的超限仅提示需核验，不宣称服务端必定拒绝。格式规则不替代 `extensions` 的允许格式检查。
