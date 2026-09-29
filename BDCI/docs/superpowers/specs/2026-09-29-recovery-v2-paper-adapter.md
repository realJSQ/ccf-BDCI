# 新研究接入论文与交付

延续已批准的选题到论文目标，复用既有原生 Writer → Reviewer → Reviser、Tectonic 和具名打包能力。本次已完成保留集实验与证据接口；论文仍是旧版本，不能把实验完成当最终作品完成。

## 现状与路线

直接向旧 `run_replay_paper.py --study-run` 传入新研究不可行：旧 evidence、renderer、角色提示、bundle 文件清单硬编码 6 个实例、18 个计划、A/B/C/D、strict/posthoc。旧运行还保留历史 token/字数阈值。复制全部流程会增加两套恢复与打包逻辑。采用显式版本 adapter，保留旧 profile 行为，为新研究提供独立的 evidence、render 和角色提示。

`recovery_v2_paper_evidence.build_evidence(run)` 已实现并经真实归档复验，输出 `recovery_v2_evidence/1`。36份真实计划、144次模型策略复放及36次独立G执行动态计算；主证据仅来自v2。旧实验只作为显式历史来源，未经旧verifier复核前不能把它标为已验证输入。

## 实施接口

1. `study_adapter.py` 按 `study_kind=replay_v1/recovery_v2` 显式分派。提供 evidence 构建、证据复制清单、renderer、skill 路径和复验命令。旧 provenance 缺 kind 时仅兼容为 v1；不得根据解析失败退回旧研究。
2. 新 renderer 使用20行场景/策略主表和9个基础实例配对表；复用公共TeX转义、引用及编译。旧renderer的输出不得变化，以保持旧PDF链的严格复验。
3. 新写作角色读取v2真实证据和已核验文献。完整报告G及E−A零增益，解释294对414调用不是E独有收益，不宣称统计等价或广泛泛化；不得把36plans/180执行混为180个独立样本。与旧10/18结果比较只能是研究历史，不能当单因素提升。
4. 新profile取消人为token、提示/回答字符及字数阈值，使用服务最大输出容量，保持usage和未知请求保护。保留旧profile默认参数供历史复现。新增独立写作campaign；writer/reviewer/reviser各一轮是流程设计，不是token限额。
5. 原有写作state、resume、输入provenance和pipeline checkpoint绑定kind、研究evidence哈希与profile哈希。不得续跑时换研究或交叉使用v1稿件。reviewer仍绑定当前draft/evidence哈希和逐条真实引文。
6. 打包按episode清单复制36组prompt/raw/plan/results、registration、sources、analysis和usage；排除SDK日志、runtime、ledger及凭据。包内复验调用v2冻结脚本。manifest记录kind和新PDF对应研究，不复用旧PDF作为新稿。
7. 资源清单现已登记36次新实验；后续新增写作及失败调用继续登记。G不产生模型调用；CPU重放不重复计算共享计划usage。正式外审Token须对应最后PDF哈希。

## 必要验证

- 旧已保存论文/旧ZIP复验继续通过。
- 新evidence的raw响应、G记录、场景和配对篡改均拒绝；已有8项测试。
- v2稿件不能绑定v1 evidence；resume不能换kind或研究。
- 原生离线v2写作→编译→打包→解包零API复验，离线稿仅为fixture。
- 真实写作完成后检查PDF文本与每页版面；核对引用、表格、无收益结论、开发助手介入说明。
- 最后补正式Reviewer Token、官方贡献PR及样例ZIP实际目录核对。已核实第五轮截止为北京时间2026-10-09 24:00。

这些是继续实施步骤，不是已完成能力声明。投稿、外审和官方PR仍需具体可审查材料及对应外部操作授权；当前实验请求授权已解决，无需再询问同一批36份提示。
