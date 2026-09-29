# 实际依赖恢复研究

本入口实现 Agent 后续提案经开发助手修正的具体协议，不把开发工作归为 Agent 自主发现，也不声称提出了优于传统增量计算的新算法。规范见 `../docs/superpowers/specs/2026-09-29-recovery-v2-execution.md`。

```bash
source BDCI/activate.sh
# 原生 JiuwenSwarm，36 个开发集脚本计划，零模型 API
PYTHONPATH="$PWD/BDCI/jiuwenswarm" python BDCI/research/run_recovery_v2.py
# 一次前瞻保留集研究，36 次真实计划；已有调用账本时拒绝重新开始
PYTHONPATH="$PWD/BDCI/jiuwenswarm" python BDCI/research/run_recovery_v2.py --live
# 零 API：逐份重算、绑定提示/原始响应、校验 usage
python BDCI/research/run_recovery_v2.py --verify-run RUN_DIRECTORY
```

默认仅运行开发集。`--live --prepare-only` 只生成保留输入和冻结快照，不请求模型、不评分；不是后续恢复入口。源码变化后，使用 `RUN_DIRECTORY/frozen_source/research/run_recovery_v2.py --verify-run RUN_DIRECTORY` 复验对应历史版本。不要删除或清空请求账本。当前不支持中断后自动续发；失败部分必须保留，先确定请求是否终止，不能换新目录重跑研究。

三领域各自保留直接源行 oracle，分片完整键，避免把同一实体的不同修订分到不同检索组。开发/保留图结构分开；这是同作者自建的结构保留集，不是外部基准，也不能证明广泛泛化。缓存预热每个基础实例一次，四场景共享。实际图来自工具静态读取定义，所有策略和规划模型均可见；没有未知依赖发现机制。

策略 A 原计划、D 声明闭包补全、E 实际闭包补全、F 有变化时全量重放，四者共享同一模型计划并尊重无效/拒绝。G 独立执行实际闭包，无需模型，模型拒绝不会使其失败。F 是模型计划门控的全量对照，并非无模型全量系统。每份计划采样只计一次 API，不能按四次复放重复计费；G 的部署模型成本为零。所有策略工具尝试均计数，错误样本也进入分母。

新入口没有 token 停止阈值、提示字符或回答字符阈值。输出参数采用服务元数据容量，防止默认 8192 截断；请求数量 36 来自实验设计。计量和未决请求保护继续生效。36 个脚本调用的 72 模拟 tokens 不能混入真实资源总量。

模型输出非法 JSON 会保存原文并转为结构失败记录；不会补 emit。格式错误、主动拒绝和执行失败在 termination_reasons 中分别统计。来源新鲜度与数值正确性分别统计，数值偶然相等不等于来源已刷新。每个基础实例的四场景配对结果单独列出，不将场景或策略当作独立样本。

时长边界：model_summary.duration_seconds 是原生 workflow invocation，包括该调用期间的模型等待、框架和策略复放；不含此前缓存预热/冻结、之后归档、写作或外审。单策略 duration_seconds 仅执行器计时。工具次数不等同 FLOPs 或实际费用。框架原始用量是 API 用量记录，不是账单。

当前后半段旧论文流水线使用旧实验契约，新研究尚需接入论文证据、自动写作和具名包，不能把旧 PDF 当作新结果论文。正式外审 Token、官方贡献 PR、当轮规则与样例核实仍待完成。
