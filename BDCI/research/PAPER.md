# 先跑通流程：从存档实验到论文 PDF 和材料包

按用户要求，本阶段不做更多模型能力、题目难度测试或任务校准。复用上一轮真实pilot记录，验证：写作 → 内部审稿 → 修订 → 引用/结构校验 → ICLR LaTeX/BibTeX → PDF → 材料ZIP。

## 实际产物

真实写作运行：`paper_runs/live-20260928T104912-411414/`。

- `paper.pdf`：3页英文ICLR格式流程验证稿，显著标为Workflow validation draft，不是正式参赛论文。
- `paper.json` / `paper.tex` / `references.bib`：结构化修订稿、转义后的TeX和由已知来源构建的参考文献。
- `writer.json` / `reviewer.json` / `reviser.json`：初稿、独立内部评审和逐项回应。内部reviewer为单独角色调用，同模型不保证消除共同偏差；不是Stanford Agentic Reviewer。
- `workflow-validation.zip`：按赛题形状组织的流程验收材料包，含论文、内部审稿、源码与框架扩展、官方基线获取说明、证据及资源记录。
- `delivery/workflow-validation/manifest.json`：明确not_submission_ready。外审Token/真实外审、上游贡献PR、科学质量与最终队伍信息等仍未完成，未伪造占位凭据。

正文保留既有负结果与局限。结果表由代码读取已验证的metrics生成；模型不能提供可执行TeX或任意参考文献。引用存在性、结构和修订回应覆盖通过不代表语义全部正确、审稿意见全部合理或修订已经获得学术认可。

## 调用与恢复

时间字段说明：后续运行使用 `invocation_to_pdf_seconds` 与 `invocation_timing_scope`，计量本次入口开始校验到 PDF 检查完成的耗时，不含打包；恢复时也不含原始模型调用。历史存档里的 `end_to_end_duration_seconds` 实际为同一局部区间，字段名有误，保留原记录以便审计，不能用作完整科研流程耗时。

最多且实际3次模型请求（作者、内部审稿、修订各一次），输入17,170 token、输出4,114 token，共 **21,284 token**。新增实验调用为 **0**。API阶段约18.32秒，不含模块导入与本地编译；费用未查询，usage不是账单。

修订稿1246词触发初版内部1200词门禁，原SwarmFlow因这个本地校验报错停止。赛题并无该篇幅限制，因此将防止异常大输出的上限调整为1600词，保留原文、原始响应、失败journal和usage。通过新增 `--resume-run` 从存档响应重新校验、编译、打包，**恢复时无模型调用，也不再读取密钥**。`model_summary.json`保留原failed状态；`recovery.json`和最终`summary.json`明确记录恢复，不将失败轨迹伪装为从未发生。

`paper-v1-requests.jsonl`预算已耗尽，不自动清空。每请求3200输出token，总usage停止阈值30000是后反馈阈值，不能当硬费用上限。SDK/工作流重试关闭。

## 使用

从协作仓库根目录，使用已经配置好的环境：

```bash
source BDCI/activate.sh
python BDCI/research/run_paper.py  # 脚本化写作，复用真实存档实验，离线且不读密钥
# 仅恢复已有草稿的本地校验/编译/打包，不再调用模型：
python BDCI/research/run_paper.py --resume-run BDCI/research/paper_runs/<existing-run>
```

入口只读取已有pilot，不调度新的实验。默认pilot目录见 `run_paper.py`，可用 `--pilot-run`指定兼容存档。Tectonic使用 `--only-cached`；新机器需按根README安装编译器并提前缓存所需模板字体。当前本地编译器/缓存通过忽略的符号链接复用原环境，不上传。

已生成delivery的目录不重复覆盖打包；需要重打包时先显式归档已有生成物。恢复校验会比较原输入provenance哈希，原实验记录若变化则拒绝继续。

## 代码与边界

- `run_paper.py`：读取并校验既有pilot，驱动三个角色，支持纯本地恢复，调用PDF和打包步骤。
- `skills/paper-workflow/`：原生Swarm Skill工作流和角色说明。
- `paper_contracts.py`：引用、正文结构、内部审稿标记、逐项回应门禁。
- `paper_render.py`：TeX转义、固定真值表和真实来源BibTeX；覆盖ICLR模板默认“已发表”页眉。
- `paper_bundle.py`：白名单打包，拒绝密钥样式内容和符号链接，保留官方AtomGit基线来源，不携带Git、venv、runtime或下载缓存。

流程中的内部审稿与规则检查已经接通；外部Stanford评审需要真实服务入口/账号及访问Token，目前未调用，也没有声称完成该环节。本次没有正式投稿、向比赛上传或自动推送GitHub。

## 验收记录

- 真实写作仅3次API，引用检查、3页PDF文本解析与逐页排版检查通过。
- ZIP条目路径/文件哈希和实际密钥扫描通过。
- 将包解压到独立临时目录，复用本机已有依赖、官方基线和TeX缓存，成功执行脚本化写作、本地恢复、PDF和再次打包；不声称已在全新机器联网重装。
- 修复了ZIP解压丢失shell脚本可执行位的问题：编译入口显式通过bash调用。
- 恢复与解包验收均未追加真实模型调用或实验。
