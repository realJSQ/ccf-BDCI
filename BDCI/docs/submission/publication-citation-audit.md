# 已上传稿引用与表达核查（2026-09-29）

已上传PDF哈希：`2f28be6eae0d1464889f9f72021121ebafb1badff1e7a88fe2a0b3d845d96850`。用户报告已上传外审；Token单独保存在本地，不记录在本文。评审已完成，数值评分为4.4；该结果只对应已上传旧PDF，不能自动沿用到新稿。

## 具体问题与归因

1. 旧角色提示禁止内联来源标记，只允许section.source_ids，渲染器因此在整节末尾集中补citep。不能明确支持哪个句子，正文还残留裸arXiv编号。
2. BibTeX把完整个人姓名整体加保护括号，导致作者年引用显示全名。正确写法：`Mazumder, Aritra and Lia, Nusrat Jahan`、`Salas, Jesus`、`Gurram, Bhaskar`。
3. 历史目录、this adapter、Rendering mode、supplied reading notes等属于工程审计，不应进入论文正文。此前排版检查只检查溢出/裁切，未覆盖这种质量缺陷。
4. 模型审稿推动重复局限，渲染器又插入整段限制清单，使正文冗长而欠缺论述组织。

## 原始来源逐项核查

- [AgentCheck v1](https://arxiv.org/html/2607.11098v1)：§4.1/Algorithm 1支持单缓存响应干预；§5.3支持retry/schema/filter；§6说明未评估复合/级联故障。保留具体描述，把绝对的“not a published dependency-invalidation baseline”改成本文未复现该系统作baseline。
- [Salas v1](https://arxiv.org/html/2608.12761v1)：新版流程取得固定版本正文摘录，能够核对“缺失依赖边可能留下陈旧结果”等有限表述。旧阅读笔记中“声明依赖传递恢复”和“lineage不足时全重跑”的具体归因不能仅凭笔记进入论文；模型内部审阅已要求删除这些过强归因。
- [AgentProp-Bench v1](https://arxiv.org/html/2604.16706v1)：固定版本正文摘录支持工具参数干预、评估与经过调整的拦截器效果，不支持旧阅读笔记中拦截器组件列表的具体归因；新模型审阅要求替换。评判器验证与任务结果的区别不等于本文数值正确性与来源新鲜度，删除强类比。

三篇均真实。AgentCheck存在v3；AgentProp-Bench 的 OpenAlex 索引标题与所引固定 v1 原文标题也有差异，规范 DOI 与 arXiv 原文校验后以 v1 原文标题排参考文献，不无声换版本。Nusrat Jahan Lia 修正大小写。论文引用应紧随具体论述，预印本条目明确版本，不宣称发表或接受。完整六篇原文接入见 [OpenAlex 流程记录](publication-openalex-pipeline.md)。

## 修订边界

另存新版，保留原稿；实验数据和无增益结论不变。先准备提示及确定性引用检查，再调用原生写作角色。新的PDF不能自动沿用旧PDF的评审Token。
