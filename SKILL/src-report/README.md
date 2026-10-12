# src-report

一个用于整理 SRC 漏洞报告的 AI 助手 skill。将已有截图、PoC、HTTP 请求与响应、测试笔记整理为带证据引用的 Markdown 报告，适配 **京东、美团、快手、字节、腾讯、360、小米、OPPO、蚂蚁、百度** 的独立提交字段。

## 功能

- 登记与去重材料，串联复现步骤、实际结果和影响范围。
- 根据证据筛选漏洞线索，辅助评估 CVSS 3.1 Base 分数。
- 按平台字段撰写报告，支持补证修订和平台转换。
- 证据不足时输出线索记录和具体补证项，保留未验证结论与冲突。

## 使用示例

在已加载此 skill 的助手中，提供材料位置和目标平台：

```text
使用 $src-report，把 /path/to/materials 中的截图、请求响应和测试笔记
整理成京东 SRC 报告；缺少的证据请明确列出。
```

默认交付 `report.md`，中间数据由助手整理，无需手动填写 JSON。脚本需要 **Python 3.10+**，仅使用标准库。

此 skill 用于整理已有证据，不执行 PoC、主动扫描或自动提交漏洞。CVSS 分数不替代 SRC 平台等级，程序检查通过也不代表漏洞已确认。

## 文档与测试

- [技能说明](SKILL.md)
- [数据契约与运行命令](references/data-contract.md)
- [漏洞筛选与 CVSS 评估](references/assessment.md)

在仓库根目录运行测试：

```bash
python -m unittest discover -s tests
```

## 许可证

[Apache-2.0](LICENSE)
