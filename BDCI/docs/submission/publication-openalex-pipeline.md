# OpenAlex 文献证据与论文修订流程（2026-09-29）

本轮改进的是生成流程，未人工修改任何论文正文、`paper.json`、LaTeX 或 PDF。`BDCI/search_api.txt` 是本机凭据文件，Git 忽略；实际使用其中的 OpenAlex key。MiniMax 配置没有进入本轮文献检索或模型写作。

## 文献如何进入模型上下文

`openalex_literature.py` 对候选题名执行 OpenAlex Works 搜索，最多每题 10 条；若相关文献不在搜索前十条，按该 arXiv 编号的规范 DOI 直接查询 OpenAlex。只有 DOI/位置链接与 arXiv 编号吻合、固定版本 `arxiv.org/html/<编号>vN` 的标题和作者得到独立核验、正文足够长的文献，才进入可引用 `sources`。OpenAlex 的倒排摘要会重建并记录，但摘要和检索排名不作为具体方法论断的证据。每篇固定版本正文抽取约 11,000 字符的引言、方法、评估与局限段落，连同原始响应哈希、HTML 哈希和摘录位置进入运行归档。远端文本被标记为不可信数据，不作为指令执行。

正式输入包选择并验证了以下六篇（全部 `primary_fulltext`）：

| 固定版本 | OpenAlex Work ID | 用途 |
| --- | --- | --- |
| `2607.11098v1` | `W7168263593` | AgentCheck 单故障缓存干预 |
| `2608.12761v1` | `W7203447915` | 溯源完整性与缺失依赖声明 |
| `2604.16706v1` | `W7155074625` | AgentProp-Bench 的工具代理评估 |
| `2608.10502v1` | `W7202291452` | 记忆依赖图与选择性重放 |
| `2609.00243v1` | `W7206195005` | 跨 episode 缓存失效契约 |
| `2311.02384v1` | `W4388481513` | Web 应用缓存失效 |

两处索引差异被明确处理：Salas 的姓名有重音符号差异；`2604.16706v1` 在 OpenAlex 的标题与 arXiv 固定版本标题不同。流程用 DOI 核对索引身份，用固定版本原文确定最终引用标题。旧的三篇 `reading_note` 已被原文摘录替换；旧论文和旧证据包保持不变。

## 可复现的执行步骤

从项目根目录运行，`BDCI/search_api.txt` 保持本机文件，格式为 `openalex : <key>`，不要加入 Git。准备阶段进行联网检索和证据核验，但 **不调用写作模型**：

```bash
source BDCI/activate.sh
export PYTHONPATH="$PWD/BDCI/jiuwenswarm:$PWD/BDCI/research"
python BDCI/research/run_publication_revision.py \
  --source-run BDCI/research/replay_paper_runs/editorial-recovery-v2-20260929 \
  --output-run BDCI/research/replay_paper_runs/<new-run> \
  --prepare-only --openalex
```

检查 `<new-run>/literature_manifest.json`、`sources.json`、`prompt_writer.txt` 和 `prepared.json` 后，执行一次原生 JiuwenSwarm 三角色工作流：

```bash
python BDCI/research/run_publication_revision.py \
  --output-run BDCI/research/replay_paper_runs/<new-run> --live
```

工作流按 writer → reviewer → reviser 依次调用 `deepseek-flash`，每轮独立记录三次 admission/usage；模型自己生成与修订正文。行内 `[[cite:arxiv:...vN]]` / `[[citet:arxiv:...vN]]` 标记必须与各节 `source_ids` 一一对应；渲染器生成 ICLR 模板中的作者—年份引文、BibTeX 和数值结果表，阻止未知版本、裸露内部路径及无效引用。PDF 编译后用 `publication_quality.py` 诊断叙述式引用的明显主谓不一致、被引用文献缺失原文摘录以及稀疏尾页；此诊断不声称核验语义支持。配置未变时，`--resume <run>` 只复核已保存的三份原始回复和编译，不新增 API 调用。任何失败后的自动重发均关闭。

## 实际运行与边界

首次集成运行 `publication-openalex-20260929-b` 新增三篇原文，产生 7 页 PDF，三次模型调用共 96,078 tokens。检查发现原有三篇仍只有阅读笔记，因此升级为六篇原文输入。最终运行 `publication-openalex-fulltext-20260929-b` 从前一版**模型生成稿**出发，OpenAlex 检索共发现 56 条候选记录，六篇入选，提示中有 65,680 字符固定版本正文摘录；三次模型调用共 127,907 tokens，生成本地候选 `BDCI/research/replay_paper_runs/publication-openalex-fulltext-20260929-b/paper.pdf`（SHA-256 `b6a6c6172f4f0a1dce853af9ffd3c84f95e5116f889ccd8ca7c51c5b961069c3`）。PDF 为 6 页，六篇文献均在正文就近引用，文内作者—年份格式、参考文献版本与标题和内部路径检查通过。

第二轮内部模型审阅提出七项意见，修订模型逐项响应；独立的机械质量审计仍发现一处语法问题：单作者 Gurram 的 `[[citet:...]] study` 应由模型改为单数动词。这份 PDF 是**未提交的新候选稿**，没有新的外部评审分数或准入证明；上一版 PDF 的评审 token 不适用于它。原有实验没有新增模型规划试验，写作调用量与实验调用量分开记录。

局部验证：文献、渲染、修订和质量审计测试共 25 项通过。`publication_quality.py --run <run>` 可对现有模型稿单独复核，不修改论文。
