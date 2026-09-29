# 恢复研究论文与候选材料

本路径将已保存的真实恢复实验接入 JiuwenSwarm 原生三角色写作。它不是新的科学实验，且当前没有证明依赖恢复优于原始模型方案。

## 已保存结果

- 实验：`replay_runs/live-20260928T144804-532140`，18 份模型计划、72 次 CPU 策略重放。
- 原始写作与后续角色续跑：`replay_paper_runs/live-20260928T150942-789171`、`live-20260928T151351-885403`、`live-20260928T151550-319349`。
- 最新修订：`replay_paper_runs/editorial-20260929`，4 页 PDF，零新增 API 请求。
- 原写作总计3次请求、24,015 tokens。实验18次请求、14,878 tokens，两者共21次、38,893 tokens；这不包含早期选题、协议与失败探索。
- 全历史42次请求、123,863 tokens；当前无经账单核实的货币费用。

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

## 能力边界

- 原生 workflow 调用 writer、reviewer、reviser；审稿绑定当前文稿与证据哈希，并要求问题引用原文。
- 结构校验并不证明审稿意见正确，也不证明修订实际解决了每个问题。
- 严格结果与事后兼容结果分别显示；后者仅对已有末尾 report 动作补 emit，不虚构恢复工作。
- 格式失败保留为不完成，不当作模型主动拒绝；6个实例和共享计划不能当作72个独立样本。
- 外部评审尚未进行。候选ZIP不含伪造Token/贡献PR/队伍名，标记为不可正式提交。
- 跨阶段仍是多个入口；需要继续完善统一编排、独立验证和正式材料验收。
