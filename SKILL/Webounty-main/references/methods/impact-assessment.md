# 影响评估与 CVSS 3.1

## 适用情境

解释当前发现的影响、为评分准备证据，或判断一项能力在组合链中的作用时使用。具体计算见 [scoring.md](../scoring.md)，调用修正后的 `scripts/cvss31-calculator.js`。方法卡本身不是当前目标证据。

## 评估方式

先说明得到的能力、受影响对象、实际结果、范围与前提，再为各指标给出当前会话证据。区分合理推测、已经观察到的结果和待补条件。保留反例及对照；HTTP 成功、单次异常或凭证存在不直接证明最终影响。

单项 CVSS 与链价值分别记录。检查上一步输出是否满足下一步的输入、身份、对象和环境条件；不因单项分数低而排除组合机会。链缺少连接或结果证据时保留候选状态，列出下一步验证。计算器只计算提供的向量，不验证漏洞，也不自动升级状态。

新证据反驳指标依据时更新评估，保留原始观察。此前缺失的输入变得可用时重开相关假设，不继续沿用旧的“无法验证”结论。

## Source attribution

以下原始路径及 `catalog.json` 中的来源引用用于记录归属，不代表其中的数学或案例结论正确：

- Web-Vulnhunt `references/cvss-scoring-methodology.md`：证据驱动评分的参考来源；错误的 S:C 公式及固定凭证评级捷径已移除。
- Web-Vulnhunt `scripts/cvss31-calculator.js`：本地计算器的上游实现，已修正并用官方固定样例验证。
- Web-Vulnhunt `references/report-structure.md`：报告中的对照证据及影响解释参考。

数学及指标定义以 [FIRST CVSS 3.1 规范](https://www.first.org/cvss/v3.1/specification-document) 为准；组合评分参考 [FIRST User Guide §3.4](https://www.first.org/cvss/v3.1/user-guide#3-4-Vulnerability-Chaining)。
