# 已实现的工程改进与创新边界

本文相对链接以完整协作仓库为准；历史运行目录、设计稿与独立验证记录不保证全部收入每份 ZIP。压缩包内可用证据应以随包 manifest 的实际文件清单为准。

当前能够证明的是源码扩展和工程流程可运行，尚不能证明新的科学方法优于已有方法，也不能据此宣称论文创新已通过。本文区分已有实现、验证证据及待研究部分。

## JiuwenSwarm 源码扩展

| 改进 | 已实现行为与代码 | 当前证据与限制 |
| --- | --- | --- |
| 实验工具收据校验 | [ExperimentEvidenceRail](../../jiuwenswarm/jiuwenswarm/agents/harness/common/rails/research_evidence_rail.py)在工具返回后检查退出码、目录边界、文件哈希和有限数值，记录接受或拒绝 | [smoke 接入](../../validation/run_smoke.py)、[针对性测试](../../validation/test_research_evidence.py)。真实接入仅在 smoke 的固定队列实验工具；不证明科学正确性，未覆盖 pilot/paper |
| 跨运行持久化的请求准入 | [ResearchBudgetRail / ResearchRunBudget](../../jiuwenswarm/jiuwenswarm/agents/harness/common/rails/research_budget_rail.py)写入 admission/usage 配对记录、fsync，拒绝超次数、未完成请求及不合法 usage | [预算测试](../../research/test_budget.py)、[真实研究运行适配器](../../research/native_runner.py)。排他锁依赖调用方；token 是后反馈停止阈值，不是硬预付上限 |

这些修改位于 JiuwenSwarm 源码树，研究项目仍通过原生 SwarmFlow、TeamWorkerBackend 和 DeepAgent 调度。代码存在不等于官方已接受贡献；官方仓库 PR 和上游评审仍未完成。

## 已实现的科研流程工程

- **实验与文字分离。** [pilot_benchmark.py](../../research/pilot_benchmark.py)在本地生成真值并评分，[run_pilot.py](../../research/run_pilot.py)记录计划、输入、生成器和指标。保存响应可重算评分；这是结果完整性机制，不是对实验设计偏差的修复。
- **从存档证据生成论文。** [run_paper.py](../../research/run_paper.py)先复核存档，再组织作者、内部审稿和修订；[paper_render.py](../../research/paper_render.py)从已核验指标生成结果表，从已有来源生成参考文献。模型文本仍可能有语义错误，结构门禁不能替代学术审查。
- **保留失败与恢复记录。** 写作运行在本地篇幅门禁失败后，支持从三个已保存响应恢复校验和编译，无额外模型请求；保留原 failed 摘要。当前只支持这一范围的恢复，未实现全研究生命周期自动恢复。
- **可审计材料和复现。** [paper_bundle.py](../../research/paper_bundle.py)使用白名单、文件哈希和密钥样式检查生成验证 ZIP；[干净环境记录](clean-environment-validation.json)覆盖同主机隔离安装、107 项检查及离线框架流程。它不等价于新机器、多平台或模型结果完全可复现。

## 当前研究结论

新开发阶段增加了当前文档哈希与原文锚点约束，修复一次真实审稿误读旧版本的问题。仍有经绑定审查后漏掉的语义错误，不能把通过门禁当成方法正确。[新恢复实验](../../research/REVISION.md)保留8份缺少终止动作的原始计划和零 API 事后兼容重放；兼容后依赖恢复未超过模型原计划，不支持额外方法收益。这些是可审计的工程改进与负结果，不宣称依赖重放、哈希或格式兼容是新的科学算法。

[真实 pilot](../../research/pilot_runs/live-20260928T084134-196833/)对 24 道整数算术题作探索性比较，baseline 和 intervention 均仅答对 1 题，没有观测到改善。任务存在低准确率、缺少 no-peer 对照、协议格式冲突等局限；当前决策为 `hypothesis_not_supported_in_pilot`，没有最终选题或新颖性成立结论。

[已有论文](../../research/paper_runs/live-20260928T104912-411414/paper.pdf)是明确标注的流程验证稿。真实写作、引用检查、编译成功以及软件测试通过都不能替代论文质量、方法差异、实验有效性和外部评审证据。

## 后续待论证内容

[设计稿](../superpowers/specs/2026-09-28-submission-workflow-design.md)提出的统一编排、失败恢复方法与相关研究方向尚未实现和验证。后续需由 Agent 提出并检索论证具体研究问题，建立合理对照、消融、独立验证与不确定性分析，再依据真实结果决定论文主张；不能把新增规则、哈希、一次审稿或更长提示词直接称为科学创新。

正式材料仍需最终论文对应的真实 Stanford 外审 Token、官方贡献 PR、资源报告与队伍命名验收。当前不报告竞赛得分，也不把工程验证包标记为可正式提交。
