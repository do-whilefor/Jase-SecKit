# CVSS 3.1 评分

仅在分析影响或撰写发现时加载。本模块基于上传的 Web-Vulnhunt 计算器修正：采用 FIRST 的 Scope Changed 公式和 Roundup，并检查版本、指标取值及重复项。历史案例用于说明方法，不作为当前目标证据。

```bash
node scripts/cvss31-calculator.js --json 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N'
```

在 skill 目录执行，或使用脚本绝对路径。省略 `--json` 输出计算过程；也可通过 stdin 输入。仅计算 Base，不接收 Temporal/Environmental 指标。返回 `vector`、`baseScore`、`severity` 和中间数值。

为 AV/AC/PR/UI/S/C/I/A 逐项写明理由、证据引用和尚未验证的条件，然后计算；保留完整向量、分数和等级。条件未落实时标记条件性评估，评分不改变发现的验证状态。

- PR 看攻击前所需权限；UI 看攻击者之外的用户交互。
- AC 不直接由特殊配置或同一子网决定；S 判断安全权限域是否变化。
- C/I/A 根据可支持的影响分别判断。凭证存在、可用或休眠没有固定的影响等级映射。
- 数学分数不决定研究优先级。低分能力仍可能补齐其他假设的前提。

单漏洞保留自己的评分。对确实可组合的链，另列成员、连接证据、剩余前提及链向量；分数不相加或平均。候选链不因算出分数而成为已验证链。

权威依据：[FIRST 3.1 规范 §2、§7 与附录 A](https://www.first.org/cvss/v3.1/specification-document)、[漏洞链评分说明 §3.4](https://www.first.org/cvss/v3.1/user-guide#3-4-Vulnerability-Chaining)。CVSS 由 FIRST.Org, Inc. 所有并经许可使用。
