# 已完成实验到候选包的协调入口

`run_replay_pipeline.py` 串联兼容恢复实验复验、原生三角色写作或存稿复用、候选打包、包内独立校验。当前范围从已完成的六实例恢复实验开始；尚不自动串联选题、方法提案、新协议执行与正式外审，不能称为完整自主科研闭环。

## 从真实存稿生成可复验候选

在仓库根目录，使用一个尚不存在的输出目录：

```bash
source BDCI/activate.sh
python BDCI/research/run_replay_pipeline.py \
  --study-run BDCI/research/replay_runs/live-20260928T144804-532140 \
  --paper-run BDCI/research/replay_paper_runs/editorial-20260929 \
  --output /tmp/my-research-delivery
```

此命令不调用模型。输出包含 `pipeline.json` 检查点和 `bundle/replay-candidate.zip`，同时保留解包目录。包的资源报告区分选定研究阶段与历史累计，仍标记 `submission_ready=false`。这些检查证明保存产物的一致性，不证明科学新颖性或外部评审通过。

## 运行原生写作与轻量编译

省略 `--paper-run`，会调用原生 JiuwenSwarm writer/reviewer/reviser，默认使用离线脚本响应。论文生成到 `replay_paper_runs/offline-pipeline-*`；状态为 `integration_candidate_verified`，包内也标为 `integration_only`。三次脚本调用不是模型API消耗，也不是新科学观测。不会修改真实论文的 latest 指针。

只有显式 `--live` 才使用真实模型和现有写作campaign；该历史campaign额度已经用完，不能直接拿此参数获得新额度，也不得清空账本。新真实实验/写作必须登记到 `resource_runs.json` 才能打包，防止历史报告漏计。此入口不擅自增加预算。轻量Tectonic及字体缓存沿用现有环境。

## 恢复

```bash
python BDCI/research/run_replay_pipeline.py \
  --study-run BDCI/research/replay_runs/live-20260928T144804-532140 \
  --output /tmp/my-research-delivery --resume
```

恢复使用保存的写作模式，不再传 `--live`。实验路径可以显式搬迁，但内容哈希必须相同；输入缺失或变化不会回退历史目录。已完成阶段重新校验稿件、原始响应、来源与ZIP哈希，不只检查 completed 字段。

若写作请求状态不明且没有完整三角色原始响应和usage，恢复停止，不自动重发；完整响应则调用原写作入口零API重建。协调器锁和由子进程继承的写作锁阻止并发恢复。部分打包目录不会自动删除或覆盖；需要保留证据后检查失败原因。源码更改后要生成新版本包，应使用新的输出目录，旧检查点只恢复原有产物。

## 实验与资源绑定

写作和打包使用同一显式实验输入。打包器也可单独使用 `--study-run`，或从论文来源记录读取路径；不再固定挑选旧实验。已登记实验的异地副本需要完整允许证据逐字节一致，归入原清单位置，避免复制后重复计费或覆写历史。

当前只支持既有恢复协议，新的任务结构须先实现实验/报告适配器。正式参赛仍缺研究质量改进、前半段自动编排、外审Token、官方贡献PR、团队名和当前提交周期/模板核对。
