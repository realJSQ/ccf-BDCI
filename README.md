# CCF BDCI：基于 JiuwenSwarm 的自动科研原型

当前项目实现了真实框架的实验—写作验证，以及由 Agent 提出候选课题、检索文献并独立评审的自动选题流程。**尚未完成正式竞赛论文。首个修订提案已完成受控预实验，但没有观察到策略改进，最终选题仍未确定。**

## 当前进展

最新阶段已在不增加实验的情况下跑通写作、内部审稿、修订、ICLR PDF和材料打包，见 [论文流程说明](BDCI/research/PAPER.md)。产生3页验证稿，仍非正式投稿。

- 基于官方 SwarmFlow → TeamWorkerBackend → TeamHarness / DeepAgent。
- 新增 JiuwenSwarm 源码 `ExperimentEvidenceRail` 与 `ResearchBudgetRail`，用于实验凭据核验和持久化调用额度控制。
- 实验/写作闭环：3 次模型请求、1,498 token，真实固定实验、英文报告与 PDF 编译通过。
- 自动选题：3 次模型请求、13,480 token，4 次检索、19 条去重论文元数据、2 个 Agent 提出的候选。评审结果分别为修改和否决，未执行候选预实验。
- 新增修订—评审—真实配对预实验—结果解读闭环：6次请求、16,176 token，24题测量结果不支持本轮假设；保留负结果与后续修改依据。
- 选题、预算、预实验数据隔离和评分模块有完整单元测试，真实框架离线流程及额度阻断验证通过；前阶段证据 Rail 9 项单元测试通过。
- 轻量 LaTeX 使用 Tectonic，新 GNU 二进制及本次按需缓存约98 MiB；下载内容不纳入仓库。

## 目录与结果

| 路径 | 内容 |
| --- | --- |
| [BDCI/research](BDCI/research/README.md) | 自动选题 skill、检索、筛选、预算控制及测试 |
| [当前架构](BDCI/docs/submission/architecture.md) / [模块调用](BDCI/docs/submission/module_call.md) | 真实接入点、模式、预算、恢复边界及证据索引 |
| [贡献补丁草案](BDCI/contribution/README.md) | 两个源码 Rail、24 项测试、上游使用说明与待发布 PR 文案 |
| [论文流程](BDCI/research/PAPER.md) | 复用既有实验的三角色写作、PDF与验收包 |
| [预实验阶段](BDCI/research/PILOT.md) | 修订提案、真实配对测量与负结果分析 |
| [BDCI/validation](BDCI/validation/README.md) | 固定实验与英文报告闭环验证 |
| [BDCI/jiuwenswarm](BDCI/jiuwenswarm) | 官方源码快照及本项目 Rail 扩展 |
| [题目与评分要求](BDCI/任务要求.md) | 本地竞赛网页整理的要求与评分 |
| [自动选题结果](BDCI/research/runs/live-20260928T081927-158480/report.md) | 候选、评审及门禁结果 |
| [验证报告 PDF](BDCI/validation/runs/live-20260928T080913-827750/report.pdf) | 英文框架验证报告，非参赛论文 |
| [轻量 LaTeX](BDCI/setup/latex-environment.md) | 编译器来源、安装及模板验证 |

保留 `BDCI/` 这一层目录，已有命令可以从仓库根目录运行。部分历史日志摘要引用原开发机绝对路径；这些是原始运行证据，不表示克隆后的安装位置。`环境说明.md` 记录初次搭建时的状态，后续实现以 research/validation 文档为准。

## 本地复现（Linux / WSL）

已验证 Python 3.13；上游支持范围为 >=3.11,<3.14。环境快照包含平台相关依赖，其他系统可能需要调整。

```bash
python3.13 -m venv BDCI/.venv
source BDCI/activate.sh
python -m pip install --no-deps -r BDCI/setup/requirements.repro.txt
python -m pip check
python -m unittest discover -s BDCI/research -p 'test_*.py' -v
python BDCI/research/run_topics.py               # 离线，不读取密钥、不调用 API
python BDCI/research/check_topic_integration.py  # 真实框架额度阻断验证，无 API
python BDCI/validation/run_smoke.py              # 离线实验/写作验证
```

`requirements.repro.txt` 是完整依赖快照，将上游 editable 安装替换为本仓库源码，并固定 agent-core 与 agent-protocol 的提交。安装时使用 `--no-deps` 避免上游元数据里的分支 URL 与同一包的固定提交 URL 发生解析冲突；随后必须执行 `pip check` 检查缺失包和版本冲突，不能跳过。干净环境复验结果见后续安装记录，不将本机复验等同于跨平台验证。

已在同一 Linux/WSL 主机的独立源码副本与新虚拟环境中完成复验：228 个包版本及两个官方 GitCode 提交核对一致、`pip check` 和107项软件测试通过，原生离线预实验及写作—PDF—ZIP通过；新装 GNU Tectonic 从空缓存编译成功。详见[复验记录](BDCI/docs/submission/clean-environment-validation.json)。未复用旧安装包或旧 TeX 缓存；Python 下载缓存可复用。离线模型响应是脚本数据，不构成新增科学实验。

编译 PDF：

```bash
bash BDCI/setup/latex-install.sh
bash BDCI/tools/compile-latex.sh --keep-logs \
  BDCI/validation/runs/live-20260928T080913-827750/report.tex
```

首次安装/编译需要网络；缓存齐全后可加 `--only-cached`。Web UI 的前端构建与服务初始化步骤见环境说明。

## 模型凭据与预算

`BDCI/apis.txt`、虚拟环境、运行时配置、下载缓存和生成日志未上传。需要真实模型调用时，在本地参考 `BDCI/apis.example.txt` 配置凭据；不要提交密钥。

本仓库保留已用完的 admission 记录，防止直接运行 `--live` 继续消耗额度。下一轮先明确新预算，再实现独立计量；不要清空已有记录伪装为未消费。离线模式可直接运行。费用未核账单，报告只陈述实际返回的 token usage。

## 来源与项目边界

JiuwenSwarm 基于官方 `develop` 提交 `fc18e5c572a6b3b62bb42ea843cce674140e4266`，本仓库采用源码快照，不携带上游 Git 历史或作为嵌套 submodule。来源和变更见 [UPSTREAM.md](UPSTREAM.md)，上游 LICENSE 及第三方许可说明保留在源码中。

下一阶段是根据首轮真实预实验的负结果校准难度、改进对照并复验，继续核对全文，再接入完整实验与 ICLR 论文写作。目前没有正式竞赛评分、Reviewer Token 或已提交的框架贡献 PR。
