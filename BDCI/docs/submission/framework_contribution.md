# 框架贡献状态

现有实现向 JiuwenSwarm 源码添加 `ExperimentEvidenceRail` 和 `ResearchBudgetRail`。前者在选定实验工具返回时验证收据与数值文件；后者通过持久 admission/usage 配对记录限制顺序模型请求，并对未确定结果的请求停止后续准入。详细适用范围见 [源码贡献说明](../../contribution/README.md)。

已准备 [research-rails.patch](../../contribution/research-rails.patch)，包含两个源文件、28项测试和上游使用说明。补丁在官方固定提交 `fc18e5c572a6b3b62bb42ea843cce674140e4266` 的独立副本上应用成功，28项测试通过。具体哈希与验证范围见 [validation.json](../../contribution/validation.json)；[PR文案](../../contribution/PR_DESCRIPTION.md)已准备。

尚未发布官方 PR，无 PR URL，也没有维护者接受记录。本文件不能代替赛题所需的真实 PR 链接。正式提交前须对最新官方分支复核、完成 PR 并记录状态；不能用 GitHub 协作提交地址冒充官方社区贡献。

这是现有工程扩展的贡献草案，不宣称新的研究方法已成立。当前证据 Rail 尚未绑定预期 run 身份，预算 Rail 仅适用于由调用方持锁的顺序、无工具模型调用。完整限制写入补丁文档，避免把本地契约检查解释为科研结果正确性保证。
