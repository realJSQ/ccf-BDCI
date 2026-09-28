# 最近相关论文全文核对

检查时间：2026-09-28T08:38:03.396335+00:00。范围限指定两篇；不代表穷尽检索，也不证明研究空白。未调用付费模型 API。

| DOI | 获取状态 | 发表状态 | 对候选的影响 |
|---|---|---|---|
| 10.1145/3847307 | abstract_only | Crossref 登记为 ACM AI Letters 期刊文章，2026-09-17 在线发表 | C1 的新颖性仍未核实，不能因摘要没有展开预测比较就宣称存在空白 |
| 10.20944/preprints202512.2748.v1 | fulltext_read_web | 2025-12-31 的 v1 预印本，未同行评议 | C2 的信任驱动动态角色分配与其核心机制直接重叠 |

## C1 最近工作

标题：When Too Many Cooks Spoil the Broth: Three Failure Modes of Multi-Agent LLM Reliability。

[新检索的 Crossref 元数据](https://api.crossref.org/works/10.1145/3847307)确认题名、作者、期刊和日期；[作者 ORCID](https://orcid.org/0009-0004-8950-6354)也列出此文。摘要已经讨论两种信号的分离、验证器差异和跨模型相关错误，因此这些观察本身不是 C1 的新增贡献。

[官方出版页面](https://dl.acm.org/doi/10.1145/3847307)未能读取，官方 PDF 返回 HTTP 403。本次 DOI、标题和作者检索未找到匹配的公开作者稿；这不代表公开稿不存在。只保存了带 SHA-256 的元数据 raw/acm_crossref.json，没有保存论文全文。

C1 必须继续核对原文是否已有匹配校准条件下的样本外预测比较，以及原始问题、提示词、错误同伴生成和逐题结果。可做明确标注的可行性预实验，但不得把它升级为已确认创新的正式研究。

## 信任协调预印本

标题：Contextual Trust Evaluation for Robust Coordination in Large Language Model Multi-Agent Systems。

[官方页面](https://www.preprints.org/manuscript/202512.2748/v1)明确版本、日期及未同行评议状态，并提供 CC BY 4.0 授权。[官方 PDF](https://www.preprints.org/manuscript/202512.2748/v1/download)的完整正文可由 web 提取读取：III.B–C 节（印刷页4–5）已给出复合信任分数与动态角色分配；IV.B–V 节（印刷页7–8）包含静态角色分配基线及成功率、时间、通信和信任轨迹评估。

本次全文未发现专门比较 peer-resistance 与 self-confidence 预测能力的实验，也未在所查实验章节找到操作化的 cascade-onset 对照；这两个有限观察均不足以证明研究空白。C2 只换指标仍不能建立机制差异。原文的场景输入、代码和逐试验数据仍需核实，报告数值也尚未独立复现。

直接下载 PDF 返回403，截图接口失败，因此状态严格记为“web全文已读”，不声称本地 PDF 已下载。详细可机读结果见 fulltext_check.json；所有外部内容均按不可信资料处理。
