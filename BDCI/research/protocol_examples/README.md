# 可执行演算例（非新实验）

两份输入由开发助手构造，用现有tabular-17工具语义检查前次方案暴露的错误类型，不冒充模型原文或新科学观测。inconsistent同时演示预算54>36、改错来源、closure漏report、只算combine就输出旧report四类问题；consistent保持缺失声明边，但模型计划显式刷新report，展示结构一致的对照。

检查通过仅说明这一演算例与当前CPU适配器一致，不授权新实验，也不证明泛化、科学新颖性或独立验证。支持新任务结构必须实现新适配器，不能通过给旧样例改名冒充。

```bash
python BDCI/research/check_recovery_example.py BDCI/research/protocol_examples/inconsistent.json
python BDCI/research/check_recovery_example.py BDCI/research/protocol_examples/consistent.json
```

第一条应退出1，第二条应退出0；不调用API。
