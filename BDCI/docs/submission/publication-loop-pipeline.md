# 有界论文循环审查与提交候选包

`run_publication_loop.py` 使用 JiuwenSwarm 原生 team skill 驱动 writer、reviewer、reviser。流程至少做两轮内部审查；有具体问题才修订，最多两次修订和三轮审查。每份审查意见绑定当前草稿与实验数据哈希，并附草稿原文锚点；修订稿逐项回应。确定性引用语法和 PDF 质量检查可要求模型继续修订，开发者不直接改论文正文。页数由内容需要决定，没有人为 token 上限。

研究数据来自冻结的 recovery-v2 实验。OpenAlex 负责发现文献，引用必须进一步核验固定版本的 arXiv 原文及作者、题名、版本哈希。最终文献集合为九篇，包含增量构建、自调整计算和增量视图维护的三篇补充原文。模型必须在正文使用行内引用标记；渲染器生成作者年份格式的引用和 BibTeX，并由保存的实验数据生成结果表。机械检查不保证每个文献都支持相邻论断，模型的两轮内部审查也不等于独立外审。

从仓库根目录运行（路径仅作复现示例；已有运行目录不能覆盖）：

```bash
source BDCI/activate.sh
python BDCI/research/run_publication_loop.py \
  --source-run BDCI/research/replay_paper_runs/publication-external-followup-20260929-a \
  --output-run BDCI/research/replay_paper_runs/<new-run-name> --prepare-only
python BDCI/research/run_publication_loop.py \
  --source-run BDCI/research/replay_paper_runs/publication-external-followup-20260929-a \
  --output-run BDCI/research/replay_paper_runs/<new-run-name> --live
python BDCI/research/run_publication_loop.py --resume \
  BDCI/research/replay_paper_runs/<new-run-name>
```

`--prepare-only` 零 API 调用，写出提示、角色模板、来源绑定和 `egress_manifest.json`；后续角色提示在前一角色响应后动态生成。`--resume` 只复验保存的原始响应和编译，不重发 API。一次性执行栅栏、排他锁和逐次 usage 记录防止静默重试。`activate.sh` 优先加载本仓库 JiuwenSwarm 源码。

历史运行保留用于审计。`publication-loop-live-20260929-b` 的两轮模型审查均通过，但确定性检查发现引用语法问题。`publication-loop-live-20260929-c` 完成三轮审查仍有未解决的问题；`-d` 的失败调用保留了原始记录；`-e` 修复了引用语法，但版面仍需处理。随后一份旧 PDF 获得 Stanford Agentic Reviewer 外审；报告批评样本小、自编任务及相关工作覆盖不足。该外审只对应旧 PDF，不能冒充新稿评价。`prepare_publication_followup.py` 将其去敏的批评和三篇新核验文献绑定到旧稿，模型在 `publication-external-followup-20260929-a` 写出修订稿，`publication-loop-external-followup-20260929-a` 再完成两轮零问题内部审查。

当前本地候选 PDF 是 `publication-loop-external-followup-20260929-a/paper.pdf`，共 7 页、正文引用九篇文献，SHA-256 为 `f51b9deefb08c282b228ff9fa08e3643922567e608d376d984ded8282418a75b`。`publication-nine-final-20260929` 保留同一 PDF 的确定性排版；`publication-nine-bundle-20260929-d/真没招了.zip` 包含完整研究、文献、提示、原始回复、内部审查、代码和用量审计。选定研究及稿件链共记录 62 次模型调用、1,236,637 tokens；这不是整个开发项目的总资源账。

此候选包的 `submission_ready=false`：新 PDF 尚无与其哈希匹配的 Stanford Reviewer Access Token，上游 JiuwenSwarm PR 链接也未取得。旧 PDF 的 token 被严格排除。外审上传需要联系人邮箱；在用户明确授权邮箱使用前不得再次上传或自动从 Git 配置读取邮箱。Git 提交及推送若会使用用户邮箱，同样须先征得授权。
