# 新论文写作的具体材料

目标服务 `https://api.deepseek.com`，模型 `deepseek-flash`。计划通过原生 JiuwenSwarm 顺序运行 writer、reviewer、reviser 各一次。没有人为 token、字数或字符限额，仍记录 usage、结束原因和失败。

`writer-prompt.txt` 是首轮完整提示。内容为已经完成的自建研究结果、预先冻结的研究规范、工具图说明、公开论文的已核验阅读资料，以及英文论文 JSON 格式要求。首轮不会接收私人文件或本地凭据；提示中已省去本地路径和长文件哈希清单，完整证据仍在本地绑定。

后两轮使用同一研究/文献材料，加上本流程生成的初稿与内部审阅意见，分别审查和修订。角色规则见三个 `*-instructions.md`。这是内部写作流程，不会上传给 Stanford Reviewer、投稿或创建官方 PR。API 密钥仅作本地认证，不作为提示内容。

完整保存的 `evidence.json`、`sources.json`、`input_provenance.json` 用于审查来源，实际首轮发送内容以 `writer-prompt.txt` 为准。`request.json` 保存目的地、调用阶段和提示/profile哈希。离线同流程已完成 PDF 编译、具名 ZIP 和包内复验；离线稿不当作真实 Agent 论文。
