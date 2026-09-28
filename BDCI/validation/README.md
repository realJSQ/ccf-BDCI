# 初步框架验证

这是已获用户授权的最小验证，不是正式竞赛论文或完整自动科研系统。

执行路径：Swarm Skill 工作流脚本 → 官方 SwarmFlow 引擎 → 角色路由 → 官方 TeamWorkerBackend → TeamHarness / DeepAgent → 固定实验工具与 JiuwenSwarm 源码 Rail。

实验是固定短作业的 FIFO / SJF 排程数值模拟，仅用于检查真实工具执行、指标留存和写作链路，不提出算法创新。两个模型角色为实验员和作者；协调、证据复核、表格和编译由确定性代码完成。

预算：单并发，最多 3 次模型调用，每次输出最多 512 token，模型和工作流自动重试关闭；另有总 Token 停止条件与总运行超时。API 密钥运行时从 `BDCI/apis.txt` 读取，不复制到技能、源码或报告。默认离线执行不会读取密钥，实跑须显式 `--live`。

验收：工作流正常结束、实验工具确实执行、Rail 接收到真实回调、模型 usage 可追溯、证据重新校验通过、英文说明与确定性结果表生成、轻量 LaTeX 编译得到可解析 PDF。先离线核查真实框架路径，再做一次受限 API 实跑。

边界：未验证完整文献检索、开放式代码生成、长期任务恢复或任意课题泛化；没有在 Web UI 中测试 Leader 自动选择技能。此处明确指定技能脚本与角色，而非依赖模型临时生成编排。

## 2026-09-28 实跑结果

- 离线真实框架路径通过；只替换模型响应，工具与 Rail 均真实执行。
- DeepSeek `deepseek-flash` 实跑通过：3 次请求，输入 1,188 token、输出 310 token，共 1,498 token；工作流阶段约 4.79 秒（不含 Python 启动、模块导入及 PDF 编译）。费用未查询，不将 token 估算冒充账单。
- 运行目录：`runs/live-20260928T080913-827750/`。`summary.json`、`model_usage.jsonl`、`workflow_events.jsonl`、`workflow_journal.json`、`evidence.jsonl` 和实验原始输出可追溯。
- 固定模拟结果：FIFO 平均完成时间 16.2，SJF 11.0，单位是抽象服务时间，不能当作真实系统性能提升。
- 源码新增 `jiuwenswarm/agents/harness/common/rails/research_evidence_rail.py`，通过实际 after_tool_call 接收执行回执，校验退出码、路径、SHA-256 和有限数值指标。这里只证明记录完整性，不证明科研结论正确。
- `report.pdf` / `report.tex` 为英文验证报告，采用普通 article；另在 `../validation/latex/iclr-build/iclr-tectonic.pdf` 完成官方 ICLR 2026 模板兼容编译。正式论文模板年份须以比赛要求为准。

预算拒绝集成测试也通过：临时将额度降为 2，真实 Rail 在作者发起第三次请求前抛出取消，已记录请求和响应均为 2，没有产生作者报告。证据 Rail 的 9 项单元测试通过。报告 PDF 已编译、离线复编、文本解析及单页视觉检查。

## 复现

在项目根目录：

```bash
source BDCI/activate.sh
python BDCI/validation/run_smoke.py                 # 离线，无 API 消费
python -m unittest discover -s BDCI/validation -p 'test_research_evidence.py' -v
BDCI/tools/compile-latex.sh --only-cached --keep-logs \
  BDCI/validation/runs/live-20260928T080913-827750/report.tex
```

本轮 API 配额已经使用完毕。`--live` 的 admission 记录在 `live_requests.jsonl`，重复运行会被阻止；失败请求同样计入额度，不自动清空或无限重试。下一轮实验应先制定新预算。

当前工具执行沙箱中，最小 aiofiles 写入也会等待线程唤醒；同一离线脚本在沙箱外正常完成。这是本执行环境限制，未修改上游文件 I/O 来掩盖它。必要时在普通本机终端运行。预算保护使用源码已有 Rail hooks；工作流默认重试通过固定版本私有 `_rt` 在开始事件关闭，升级 agent-core 后需重新核验。

## 与竞赛要求的关系及下一步

本轮落实了 skill/team 工作流、JiuwenSwarm 源码增强、真实工具证据与资源记录、英文 PDF 编译这几个基础环节。它不是完整参赛系统，也没有形成贡献 PR。尚未实现文献检索与引用核验、选题筛选、开放实验生成、多轮修订、长任务恢复、Stanford 评审接入和最终提交包。

后续先选择可在当前电脑 + 模型 API 上验证、具有研究价值的具体问题，确定基线和评价指标，再将检索、实验、审稿等角色逐个加入。根据比赛论文质量占 60% 的权重，以结果可靠性和研究价值为主线；源码贡献围绕实际遇到的执行或恢复问题深化，避免只增加角色数量。
