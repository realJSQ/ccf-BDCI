# JiuwenSwarm 源码贡献草案

这是现有两项 Rail 的可审查补丁，尚未发布官方 PR。它不是完整研究方法，也不能代替赛题要求的真实 PR 链接。

- 官方源码：<https://atomgit.com/openJiuwen/jiuwenswarm>
- 补丁基线：`fc18e5c572a6b3b62bb42ea843cce674140e4266`
- 补丁：`research-rails.patch`
- 维护者说明：`PR_DESCRIPTION.md`
- 上游使用说明：`upstream-usage.md`，补丁中目标为 `docs/research_rails.md`
- 验证记录：`validation.json`，记录补丁哈希、基线、应用结果及测试范围

补丁添加两个源文件、两份独立测试与一份使用说明；不包含 BDCI API 凭据、运行历史、第三方代码副本或论文。应用前先检查工作树，使用基线副本验证，避免覆盖已有同名新增文件：

```bash
git clone https://atomgit.com/openJiuwen/jiuwenswarm
cd jiuwenswarm
git checkout fc18e5c572a6b3b62bb42ea843cce674140e4266
git apply --check /path/to/research-rails.patch
git apply /path/to/research-rails.patch
```

测试要求和使用边界见 `docs/research_rails.md`。不修改全局 Git 配置。基线可应用不代表当前 develop 也无冲突，正式 PR 前仍需对最新上游复核与调整。

现有真实集成：smoke 在实验工具返回处接入 EvidenceRail；选题、pilot、paper 在模型调用处接入 BudgetRail。pilot/paper 的证据复核由应用层完成，不能写成每一阶段都已经启用 EvidenceRail。

后续若修改源码，必须重新生成补丁并重新应用、测试，不能只沿用旧验证 JSON。正式贡献最终由官方 PR 地址与状态证明；此目录不预填或伪造地址。

当前补丁允许显式以 `None` 关闭累计 token 停止阈值或提示字符启发式限制；默认值保持原样，调用次数、未决请求保护与 usage 记录继续生效。28 项离线检查包含实际 SDK 请求参数构造验证，不发起模型调用。
