# Bounds

Six sequential model requests maximum, 2200 output tokens each, usage stop30000,
no retries, no tools, one DeepSeek model, 420s total workflow timeout. Campaign
pilot-v1 persists admission and usage; caller holds an exclusive run lock.
Designer/critic may decline before any experimental request. Ground truth is not
included in solver prompts. Same held-out tasks and actual peer answers go to both
conditions. Parse failures stop; do not replace failed answers or inject errors.
