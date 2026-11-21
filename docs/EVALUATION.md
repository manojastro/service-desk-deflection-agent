# Evaluation

Run:

```bash
make eval
# or
python -m tests.evaluation.run_eval
```

The deterministic replay dataset is generated in `tests/evaluation/dataset.py` and contains 120 cases: 96 common/edge variants, 12 unanswerable requests, and 12 adversarial prompt-injection/unsafe-command requests. No paid model is used.

The runner measures intent accuracy, top-1 retrieval relevance, groundedness, simulated strict deflection, escalation precision, unsafe-action blocking, real mock-tool success, historical reopen rate, average deterministic model cost, and p50/p95/mean classification-plus-retrieval latency. It writes `reports/evaluation.json` with case-level evidence and `reports/evaluation.md` for human review.

The strict-deflection measure is a replay estimate for requests that policy can ground and resolve without a human. The dashboard's production metric is based on persisted, verified resolutions and subsequent reopen events inside `REOPEN_WINDOW_HOURS`.

Before production, replace template-heavy synthetic cases with privacy-reviewed historical utterances, label them independently, segment by locale/role/tenant, run external groundedness judging with calibration, and define release thresholds with confidence intervals.

