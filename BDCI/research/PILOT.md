# 修订、受控预实验与结果筛选

在用户确认的自动科研流程中加入真实预实验。研究问题和对照策略由修订 Agent 提出，程序提供可用实验能力并严格评分。原始候选没有被直接当作最终选题。

## 已完成的流程

上一轮批评与最近工作核对 → 修订 Agent → 计划门禁 → 独立 Critic → 记录实验计划及哈希 → 真实 peer 调用 → 真实 baseline 调用 → 真实 intervention 调用 → Python 精确评分 → 解读 Agent → 程序决定是否支持假设。

实验使用同一模型、同一批24题、相同自然peer答案和相同输出上限。两条件分别调用官方 TeamWorkerBackend / DeepAgent，只改变 Agent 提出的建议处理策略。没有用一次提示模拟整段多 Agent 对话，没有执行模型生成的Python或shell，也没有人为篡改真实peer答案。

当前执行器只支持 integer_arithmetic_v1。标准答案由本地整数运算产生，不进入三个实验角色的prompt。模型输出必须覆盖全部且唯一的ID，并给出整数答案；错误/漏项不自动修补或重试。这是能力受限的可行性预实验，不是跨任务科研结论。

## 本轮真实结果

运行目录：`pilot_runs/live-20260928T084134-196833/`。

Agent 将旧的“peer-resistance 与 self-confidence 预测比较”重写为：**先独立重算再采纳同伴建议，是否比一般性参考同伴建议减少与错误同伴答案一致的情况？** Agent 明确放弃原来的校准、验证器选择与跨模型家族主张，Critic批准这个小规模可行性探测。

| 指标 | 观测 |
| --- | --- |
| 实验题数 | 24 |
| 同伴自然错误 | 23 |
| Peer / 基线 / 干预精确正确数 | 均为1/24 |
| 配对胜 / 负 / 平 | 0 / 0 / 24 |
| 基线与干预在错误peer子集上的答案一致率 | 均为100% |
| 预注册的最小改进阈值 | 0.05 |
| 实际主指标改善 | 0 |
| 程序决定 | hypothesis_not_supported_in_pilot |
| 最终论文选题 | 尚未确定 |

这不是“证明策略无效”。三组准确率极低，任务难度可能产生地板效应；相同错误答案也不能证明因果性的复制。一个依赖批次没有统计独立性保证，报告不宣称显著性或新颖性。Agent的下一步建议是校准任务难度、加入无同伴对照、分开独立计算与接收建议，再跨种子复验。

另有明确记录的事后协议问题：生成的两段policy附带逐行输出格式，与执行器JSON契约冲突；实际响应都符合JSON，但原始冲突已保存在 `run_review.json`。之后修正了设计提示及执行器最终格式指令，仅用离线模式复验；**没有重跑真实API，也没有改写本轮原始prompt或结果**。

## 文献与新颖性边界

见 `prior_work/fulltext_check.md` / `.json`。最近的ACM工作仍只取得摘要及元数据，官方全文访问受限；不能因未取得全文就宣布存在研究空白。另一篇信任协调预印本的全文已通过web读取，状态明确为未同行评议，进一步支持C2与既有机制重叠的判断。没有绕过访问控制或声称下载到被拒绝的PDF。

## 资源与复现

本轮最多且实际使用6次请求：修订、评审、peer、基线、干预、解读各一次；其中实验调用3次。输入13,567 token，输出2,609 token，共 **16,176 token**；工作流约15.21秒（不含模块导入和前期资料核对），费用未核账单。

`pilot-v1-requests.jsonl` 持久记录准入/usage，整轮文件锁、每次2200输出token、累计usage停止阈值30000、总超时420秒，无SDK或workflow重试。usage阈值是反馈停止条件而非请求前硬费用上限。旧smoke/topic账本未重置。本轮已用完6次额度，重复`--live`会被阻止。

从 GitHub 项目根目录运行：

```bash
source BDCI/activate.sh
python -m unittest discover -s BDCI/research -p 'test_*.py' -v
python BDCI/research/run_pilot.py  # 默认离线，无API/密钥读取
```

本开发机复用了原环境：`BDCI/.venv` 和 `BDCI/apis.txt` 是本地忽略项；从干净clone安装依赖见根README。两个同名源码副本并存时，可显式令 `PYTHONPATH="$PWD/BDCI/jiuwenswarm"` 保证加载协作仓库的源码。后续开发以本协作仓库为主，原 `/home/jsqke/lpyproject/BDCI` 是先前环境与实验存档。

在普通本机终端运行框架集成；本会话的受限沙箱存在aiofiles线程唤醒问题，已在沙箱外完成验证。Offline响应是清楚标注的脚本化测试数据，不能转成真实实验结果；runner/state模式不一致会在模型调用前被拒绝。

## 验证结果

74项单元测试全部通过，覆盖计划门禁、模式隔离、答案格式、oracle不进入实验prompt、配对数据一致、负结果/不足样本判定和存档篡改拒绝。当前版本再次完成真实框架离线六角色执行。真实运行的24题存档重评分通过，未追加API调用。

## 可追溯产物

- `designer.json` / `critic.json`：修订方案与独立评审。
- `pre_registration.json`：请求实验前保存的计划、输入、oracle及生成器哈希、阈值、模型参数。
- `dataset_inputs.json` / `oracle_private.json`：公开题目与模型不可见的评分答案。private指对实验角色不可见，不是API凭据。
- `prompt_*.txt` / `raw_*.txt` / 各角色JSON：实际请求内容与原始响应。
- `metrics.json` / `decision.json` / `analyst.json`：确定性测量、程序判断与模型解读。
- `scoring_replay.json`：从存档答案重算全部24题并验证哈希，通过且不调用模型；不冒充模型独立重复实验。
- `next_iteration.json`：保留负结果和修改依据，不自动追加调用。
- `model_summary.json` / `summary.json` / `model_usage.jsonl` / 工作流journal：资源及执行记录。

下一步应先解决难度和对照设计，不能因流水线跑通就将这个普通提示策略对比包装成正式创新论文。
