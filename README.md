# CCF BDCI：基于 JiuwenSwarm 的自动科研原型

当前项目实现了真实框架的实验—写作验证，以及由 Agent 提出候选课题、检索文献并独立评审的自动选题流程。**尚未完成正式竞赛论文，当前候选均未获准进入预实验。**

## 当前进展

- 基于官方 SwarmFlow → TeamWorkerBackend → TeamHarness / DeepAgent。
- 新增 JiuwenSwarm 源码 `ExperimentEvidenceRail` 与 `ResearchBudgetRail`，用于实验凭据核验和持久化调用额度控制。
- 实验/写作闭环：3 次模型请求、1,498 token，真实固定实验、英文报告与 PDF 编译通过。
- 自动选题：3 次模型请求、13,480 token，4 次检索、19 条去重论文元数据、2 个 Agent 提出的候选。评审结果分别为修改和否决，未执行候选预实验。
- 44 项选题模块单元测试、真实框架离线流程及额度阻断验证通过；前阶段证据 Rail 9 项单元测试通过。
- 轻量 LaTeX 使用 Tectonic，安装二进制及按需缓存约70 MiB；下载内容不纳入仓库。

## 目录与结果

| 路径 | 内容 |
| --- | --- |
| [BDCI/research](BDCI/research/README.md) | 自动选题 skill、检索、筛选、预算控制及测试 |
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
python -m pip install -r BDCI/setup/requirements.repro.txt
python -m pip check
python -m unittest discover -s BDCI/research -p 'test_*.py' -v
python BDCI/research/run_topics.py               # 离线，不读取密钥、不调用 API
python BDCI/research/check_topic_integration.py  # 真实框架额度阻断验证，无 API
python BDCI/validation/run_smoke.py              # 离线实验/写作验证
```

`requirements.repro.txt` 将环境快照中的上游 editable 安装替换为本仓库源码，保留 agent-core 与 agent-protocol 的固定提交。尚未在另一台全新机器完整重装；当前验证基于原开发环境。

编译 PDF：

```bash
bash BDCI/setup/latex-install.sh
BDCI/tools/compile-latex.sh --keep-logs \
  BDCI/validation/runs/live-20260928T080913-827750/report.tex
```

首次安装/编译需要网络；缓存齐全后可加 `--only-cached`。Web UI 的前端构建与服务初始化步骤见环境说明。

## 模型凭据与预算

`BDCI/apis.txt`、虚拟环境、运行时配置、下载缓存和生成日志未上传。需要真实模型调用时，在本地参考 `BDCI/apis.example.txt` 配置凭据；不要提交密钥。

本仓库保留两次真实实验已用完的 admission 记录，防止直接运行 `--live` 继续消耗额度。下一轮先明确新预算，再实现独立计量；不要清空已有记录伪装为未消费。离线模式可直接运行。费用未核账单，报告只陈述实际返回的 token usage。

## 来源与项目边界

JiuwenSwarm 基于官方 `develop` 提交 `fc18e5c572a6b3b62bb42ea843cce674140e4266`，本仓库采用源码快照，不携带上游 Git 历史或作为嵌套 submodule。来源和变更见 [UPSTREAM.md](UPSTREAM.md)，上游 LICENSE 及第三方许可说明保留在源码中。

下一阶段是依据评审批评修订提案、核对全文和开展真实预实验，再接入完整实验与 ICLR 论文写作。目前没有正式竞赛评分、Reviewer Token 或已提交的框架贡献 PR。
