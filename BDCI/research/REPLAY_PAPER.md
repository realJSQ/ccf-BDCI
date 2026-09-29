# 恢复研究论文与候选材料

本路径将已保存的真实恢复实验接入 JiuwenSwarm 原生三角色写作。它不是新的科学实验，且当前没有证明依赖恢复优于原始模型方案。

## 已保存结果

- 实验：`replay_runs/live-20260928T144804-532140`，18 份模型计划、72 次 CPU 策略重放。
- 原始写作与后续角色续跑：`replay_paper_runs/live-20260928T150942-789171`、`live-20260928T151351-885403`、`live-20260928T151550-319349`。
- 最新修订：`replay_paper_runs/editorial-20260929`，4 页 PDF，零新增 API 请求。
- 原写作总计3次请求、24,015 tokens。实验18次请求、14,878 tokens，两者共21次、38,893 tokens；这不包含早期选题、协议与失败探索。
- 截至2026-09-29归档的真实运行累计47次请求、192,805 tokens，包含后续两轮失败设计/审查的5次请求、68,942 tokens；当前无经账单核实的货币费用。

原 writer 为1681词，模型 reviser 为1752词，超过本地最终稿1600词限制。开发助手明确记录的本地编辑生成1264词初版，再补充模型配置、运行前冻结说明、失败执行范围与耗时口径。原始响应未被覆盖。此限制是工程设置，竞赛快照要求篇幅不限。

## 不调用模型的复验

在协作仓库根目录，使用已安装项目依赖的 Python：

```bash
source BDCI/activate.sh
python BDCI/research/analyze_replay.py BDCI/research/replay_runs/live-20260928T144804-532140 --verify-only
python BDCI/research/build_replay_bundle.py --paper-run BDCI/research/replay_paper_runs/editorial-20260929 --output /tmp/bdci-replay-candidate
python BDCI/research/build_replay_bundle.py --verify /tmp/bdci-replay-candidate/replay-candidate
```

输出目录中的目标包必须不存在；构建器拒绝覆盖。包内 `code/REPLAY_REPRODUCTION.md` 说明解包复验。官方框架仍从 AtomGit/GitCode 的固定提交安装，API 凭据和编译器缓存不随包分发。

新版资源报告从 `resource_runs.json` 显式清单中的原始 usage 逐条计算，校验 live 模式、token 算式、重复调用与摘要一致性。清单不是未来运行的自动发现器，新增真实运行必须登记；本地编辑或恢复目录中的副本不重复计数。包内 `resource_audit.json` 保存每项来源哈希和阶段时长，解包校验重新计算。当前论文实验/写作21次、38,893 tokens与全历史累计分别列出；阶段时长不可相加为全流程耗时。旧候选包仍是历史快照，应使用其包内版本的校验入口。

## 能力边界

- 原生 workflow 调用 writer、reviewer、reviser；审稿绑定当前文稿与证据哈希，并要求问题引用原文。
- 结构校验并不证明审稿意见正确，也不证明修订实际解决了每个问题。
- 严格结果与事后兼容结果分别显示；后者仅对已有末尾 report 动作补 emit，不虚构恢复工作。
- 格式失败保留为不完成，不当作模型主动拒绝；6个实例和共享计划不能当作72个独立样本。
- 外部评审尚未进行。候选ZIP不含伪造Token/贡献PR/队伍名，标记为不可正式提交。
- `run_replay_pipeline.py` 已串联已完成实验之后的复验、写作、打包与解包校验，见 [PIPELINE.md](PIPELINE.md)。选题/协议/实验仍是独立入口；独立科学验证和正式材料验收尚未完成。

## 显式实验输入与搬迁恢复（2026-09-29）

```bash
python BDCI/research/run_replay_paper.py --study-run BDCI/research/replay_runs/<completed-compatible-study>
python BDCI/research/run_replay_paper.py --resume BDCI/research/replay_paper_runs/<saved-writing-run> --study-run /new/location/study
```

新运行省略参数时仍默认历史实验；恢复/续跑则沿用保存的实验引用，不会因路径失效而回退到默认目录。仓库内部输入保存可搬迁的相对路径，外部输入可用显式参数重新定位；其证据和来源哈希必须一致。输入变化会在覆盖原文、来源及证据文件之前被拒绝。

目前只接受既有六实例恢复协议的完整真实实验及事后分析文件，不表示已支持任意科研协议，也未新增独立科学验证。打包入口也已支持 `--study-run` 并校验资源清单与完整原始证据绑定。已用独立目录的实验副本跑通原生离线三角色写作与PDF，缺失路径负例和搬迁后零API恢复均通过，详见 `../docs/submission/explicit-study-validation.json`。最新真实论文指针保持为已发布开发稿。
