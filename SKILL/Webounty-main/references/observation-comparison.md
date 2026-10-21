# 本地观察对照

用于核对已保存的正负样本、不同身份的同一操作，以及变更前后的实际响应。
比较器只读取本轮两个观察及其关联原件，不连接目标、不生成请求、不修改记录状态。

```bash
python scripts/session.py compare --root /absolute/path/to/run --run-id RUN-EXAMPLE \
  --left O-BEFORE --right O-AFTER \
  --field response.body.status --field response.body.result.owner_id
```

Python 接口：`compare(corpus, left_id, right_id, fields=())`，其中 corpus 是本轮
`rag.Corpus`。例如 `compare(corpus, "O-A", "O-B", ["response.body.status"])`。
发布输入的 `content` 已由存储器展开；比较器读取观察原件顶层的 `request`、`response`
和条件字段。没有该字段的源码、日志等观察会显示缺口，不伪造 HTTP 数据。

输出包括来源 ID、修订与定位，已记录的身份和条件，请求变化路径，HTTP 状态，body
摘要和选定业务字段。观察及关联原件沿用 `Corpus.observation` 的封存、哈希和 run
校验；校验失败返回 `status: unavailable`，保留来源问题且不比较内容。
未知 ID、非法点路径及错误的 request/response 对象格式抛出 `RetrievalError`。

- `assessment: comparison_only` 表示差异视图；`status: ready` 仅表示资料可读取。
- `changed_paths` 使用 JSON Pointer，如 `/response/body/status`；`~` 和 `/` 分别转义
  为 `~0` 和 `~1`，因此字段名含斜线时仍可精确定位。数组使用索引。
- `--field` 使用点路径，数组可写 `response.body.rows.0.owner_id`。此接口不转义键名
  中的点；此类字段可从来源原件读取。重复选择会去重。
- 选定业务叶字段返回真实值；缺失使用 `present: false`，与已记录的 `null` 区分。
  整个 body、对象和数组只返回摘要，不复制或截断正文。确实选中的字符串叶字段保留全值。
- 字符串 body 的哈希及 `byte_length` 基于已保存字符串的 UTF-8 字节；结构化 body
  基于键排序、无额外空白的 JSON，并标注 `canonical-json`，不是网络原始报文字节。
  内容相同只说明记录的 body 相同；原件可用 `read` 按来源 ID 回取。
- 缺失身份、环境、会话代次及 HTTP 字段会单列。`controls_not_established` 和
  `business_outcome_not_established` 提醒把这份局部视图放回实验记录核对，不能据此
  宣称整轮没有对照，也不意味着作者已记录的结果被否定。

先明确预期差异和对照是否有效，再读差异。存在性问题需确认正负样本的成员关系；
授权问题需核对身份、租户、对象和适用权限规则；修复复测需保留原复现与当前合法操作
基线。HTTP 200/403、长度或单次耗时变化都不自动说明漏洞、反证或修复。即使
`response.body.status` 不同，也要结合其业务定义和实际读回结果；身份、环境同时变化
时，应先解释这些条件对可比性的影响。

## 原脚本的复用取舍

方法来源为上传的 `Jase-SecKit-main/SKILL/Web-Vulnhunt`。以下是静态检查后的迁移
范围，来源提供设计线索和归属，不作为本轮目标证据；本地比较器没有复制自动判定代码。

| 原脚本 | 本轮复用方式 | 修正或未直接带入的实际原因 |
|---|---|---|
| `cvss31-calculator.js` | 已修正后保留为独立离线评分器，见 [scoring.md](scoring.md) | 修正 Scope Changed 与 Roundup 等正确性问题，评分依据 FIRST CVSS 3.1 |
| `negative-control-harness.sh` | 提取正负样本与语义字段对照，见 [observer-validity.md](methods/observer-validity.md) | 原实现精确比较单次 `time_total`，噪声即可触发差异判断；随机标识也不能证明样本不存在 |
| `authz-matrix.sh` | 提取身份—操作—对象维度供本地观察比较，见 [authorization-context.md](methods/authorization-context.md) | 原实现使用占位参数及统一 `{}` 请求，并按状态码分类，不能验证有效业务授权 |
| `patch-verify.sh` | 提取变更前后、部署与正常业务基线对照，见 [patch-differential.md](methods/patch-differential.md) | 原实现跨租户复用一个 token，并将 403 标为 patched，缺少有效正常对照 |
| `path-bypass-fuzzer.sh` | 不直接带入，保留 [controller-reach.md](methods/controller-reach.md) 的判断方法 | 原实现把部分 200/400/405 与内容片段当作到达控制器信号，不能证明授权绕过 |
| `sinkhole-detector.sh` | 不直接带入，保留 [asset-attribution.md](methods/asset-attribution.md) 的归属核对方法 | 原 IPv4 正则超出所称 `/15` 范围；`dig +short` 空输出也不能单独证明 NXDOMAIN |

前三个 HTTP 辅助脚本还会在退出时清理临时原件。本技能保存观察来源，再生成局部差异
视图，后续结论通过正式记录表达。原脚本路径和已有方法卡的来源哈希见
[methods/catalog.json](methods/catalog.json)。
