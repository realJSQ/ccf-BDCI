# 有界论文循环审查流程

`run_publication_loop.py` 在已核验的恢复研究论文和六篇固定版本原文基础上，使用 JiuwenSwarm 原生 team skill 运行 writer、reviewer、reviser。至少进行两轮内部审查；发现具体问题才修订，最多两次修订及三轮审查，总计至多六次模型调用。每份审查意见绑定当前草稿和实验数据哈希，需引用草稿中的原文片段；修订稿逐项回应。页数由论证需要决定，不设目标、字数或人为 token 停止阈值。模型输出仍须通过论文结构、行内引用、PDF 编译和机械质量检查；模型内部通过不等于外部论文质量认证。

本轮输入继承 `publication-openalex-fulltext-20260929-b` 的冻结 recovery-v2 数据及六篇文献。流程重新计算实验数据、核对 `sources.json` 与文献 manifest 及来源哈希；每篇文献均须有固定版本正文摘录。旧模型稿作为批评材料，质量审计会明确提示其单作者叙述式引用主谓不一致。结果表由验证后的实验数据渲染，论文文本和每轮修订只由 API 模型生成，开发者不直接修改正文。

从仓库根目录运行：

```bash
source BDCI/activate.sh
python BDCI/research/run_publication_loop.py \
  --source-run BDCI/research/replay_paper_runs/publication-openalex-fulltext-20260929-b \
  --output-run BDCI/research/replay_paper_runs/<new-run-name> --prepare-only
python BDCI/research/run_publication_loop.py \
  --source-run BDCI/research/replay_paper_runs/publication-openalex-fulltext-20260929-b \
  --output-run BDCI/research/replay_paper_runs/<new-run-name> --live
python BDCI/research/run_publication_loop.py --resume \
  BDCI/research/replay_paper_runs/<new-run-name>
```

`--prepare-only` 零 API 调用，生成准确的 writer 提示、角色模板、来源绑定和 `egress_manifest.json`。后续角色提示在获取当前模型输出后动态生成。`--offline` 使用本地脚本响应验证框架；它不是模型论文。`--resume` 只复验保存的原始响应和编译，不重发 API。运行目录有排他锁、逐次 admission/usage 记录和一次性执行栅栏，失败后不自动重试。`activate.sh` 会把本仓库 JiuwenSwarm 源码放在 Python 搜索路径前，避免共享虚拟环境加载另一个可编辑检出；当前受限沙箱的异步文件写入会停滞，因此原生工作流需在支持异步写入的本地执行环境运行。

本地离线运行 `publication-loop-offline-final-20260929` 已通过原生工作流、两轮审查、PDF 编译及零 API 重放；旧稿原有的引用语法缺陷如预期被机械质量检查报告，故离线产物不作为提交稿。完整研究测试集 295 项通过；后续新增循环上限测试和质量测试共 6 项通过。

正式请求已准备在 `BDCI/research/replay_paper_runs/publication-loop-live-20260929-b/`，writer 提示哈希为 `4eab66ae405867bfc7c2ca8d269ab2f5606e14f7f1131c8a3b070eac082e5f66`。它将把冻结合成实验数据、六篇公开论文摘录、旧模型稿及本地质量发现发送至 `https://api.deepseek.com` 的 `deepseek-flash`；后续请求还会包含该模型刚生成的草稿和审查历史。未发现 API 密钥、私人文件路径或外审 token 混入提示词。当前尚未执行这批真实请求，模型调用数为零：自动审批指出此前用户授权针对另一批冻结提示，需要本批具体外发授权。不得绕过该拒绝。

新 PDF 完成后，须按其实际内容复核并取得**匹配该 PDF** 的 Stanford Reviewer Access Token；旧 PDF 的 token 不可复用。`summary.json` 中的 `ready_for_external_review` 只代表内部审查与机械质量条件满足，`submission_ready` 在外审和正式材料齐备前保持 `false`。
