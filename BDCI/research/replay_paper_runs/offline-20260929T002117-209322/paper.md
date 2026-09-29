# Recovery replay: a development study

**Development study / internal draft**

Anonymous authors.

## Abstract

A scripted integration manuscript using saved measurements. It establishes no new research result.

## Introduction

This scripted section exercises the manuscript pipeline. Strict results and post-hoc diagnostic normalization remain separate. Selective replay showed no incremental benefit over model plans. The small self-authored sample provides no independent confirmation.

## Related Work

This scripted section exercises the manuscript pipeline. Strict results and post-hoc diagnostic normalization remain separate. Selective replay showed no incremental benefit over model plans. The small self-authored sample provides no independent confirmation.

References: ref0001,ref0002,ref0003

## Methods

This scripted section exercises the manuscript pipeline. Strict results and post-hoc diagnostic normalization remain separate. Selective replay showed no incremental benefit over model plans. The small self-authored sample provides no independent confirmation.

## Results

Rendering mode: offline_scripted. 

### Original strict execution

| Scenario | Policy | n | Correct | Wrong | Noncompletion | Calls |
|---|---|---:|---:|---:|---:|---:|
| clean | A | 6 | 6 | 0 | 0 | 0 |
| clean | B | 6 | 6 | 0 | 0 | 0 |
| clean | C | 6 | 6 | 0 | 0 | 0 |
| clean | D | 6 | 6 | 0 | 0 | 0 |
| update | A | 6 | 4 | 0 | 2 | 16 |
| update | B | 6 | 4 | 0 | 2 | 16 |
| update | C | 6 | 4 | 0 | 2 | 24 |
| update | D | 6 | 4 | 0 | 2 | 16 |
| incomplete lineage | A | 6 | 0 | 0 | 6 | 0 |
| incomplete lineage | B | 6 | 0 | 0 | 6 | 0 |
| incomplete lineage | C | 6 | 0 | 0 | 6 | 0 |
| incomplete lineage | D | 6 | 0 | 0 | 6 | 0 |

### Post-hoc compatibility replay (not preregistered)

| Scenario | Policy | n | Correct | Wrong | Noncompletion | Calls |
|---|---|---:|---:|---:|---:|---:|
| clean | A | 6 | 6 | 0 | 0 | 0 |
| clean | B | 6 | 6 | 0 | 0 | 0 |
| clean | C | 6 | 6 | 0 | 0 | 0 |
| clean | D | 6 | 6 | 0 | 0 | 0 |
| update | A | 6 | 6 | 0 | 0 | 24 |
| update | B | 6 | 6 | 0 | 0 | 24 |
| update | C | 6 | 6 | 0 | 0 | 36 |
| update | D | 6 | 6 | 0 | 0 | 24 |
| incomplete lineage | A | 6 | 6 | 0 | 0 | 24 |
| incomplete lineage | B | 6 | 6 | 0 | 0 | 24 |
| incomplete lineage | C | 6 | 6 | 0 | 0 | 36 |
| incomplete lineage | D | 6 | 6 | 0 | 0 | 24 |

Calls count replay tool executions; cached initial construction is shared and excluded. The two tables reuse the same model plans. Noncompletion includes malformed plan outputs and does not imply voluntary refusal. These are descriptive results on self-authored development instances. Shared model plans and repeated policies are not independent samples. The post-hoc compatibility replay reuses saved plans and is not a new model experiment or a preregistered result. Neither table establishes generalization, statistical equivalence, algorithmic novelty, or competition submission readiness. Original noncompletion reasons counted once per model-plan episode: missing_terminal_action: 8.

Recorded study resources: model calls: 18; total tokens: 14878; native study invocation wall time in seconds (excludes topic selection, literature and writing): 15.986; writing model calls: 3; writing total tokens: 6; post-hoc plans changed: 8

## Discussion

This scripted section exercises the manuscript pipeline. Strict results and post-hoc diagnostic normalization remain separate. Selective replay showed no incremental benefit over model plans. The small self-authored sample provides no independent confirmation.

## Conclusion

This scripted section exercises the manuscript pipeline. Strict results and post-hoc diagnostic normalization remain separate. Selective replay showed no incremental benefit over model plans. The small self-authored sample provides no independent confirmation.

## References

- [ref0001] AgentCheck: A Reproduce-Intervene-Mitigate Workbench for LLM Agents over MCP. Aritra Mazumder; Nusrat jahan Lia. 2026. https://arxiv.org/abs/2607.11098v1

- [ref0002] Correct Is Not Governed: Provenance Integrity in Agentic Workflows. Jesus Salas. 2026. https://arxiv.org/abs/2608.12761v1

- [ref0003] Evaluating Tool-Using Language Agents: Judge Reliability, Propagation Cascades, and Runtime Mitigation in AgentProp-Bench. Bhaskar Gurram. 2026. https://arxiv.org/abs/2604.16706v1
