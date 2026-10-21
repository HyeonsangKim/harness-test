# Tool-free inference-time harness techniques (small/open models, 2023 to Oct 2026)

Scope: things you can wrap around the model with no domain tools: sampling and selection, decomposition, self-correction, constrained output, and automatic prompt or harness optimization.
Target setting: stdlib-only, air-gapped harness. GLM-5.3-Flash through a LiteLLM gateway that starts returning 429 after about 35 calls in a few minutes. Qwen3.5-9B on a 24GB Mac at about 26 tok/s.
Cost notation: "×k calls" means LLM calls per task compared with one plain call.
Evidence status: every number below was read in the primary source (an arXiv abstract or HTML page, or an official blog), unless it is marked otherwise. All results are self-reported by the authors unless a note says otherwise.

## Sampling + selection (self-consistency, best-of-N, verifiers, repeated sampling, test-time compute scaling)

### Takeaway
This is the best-evidenced family. Majority vote over N sampled chain-of-thought answers gives large gains on tasks with a short, checkable answer. Those gains plateau around N≈64. Verifier-guided search (a PRM with beam search or DVTS) is what lets 1B–3B models beat 8B–70B ones, but it needs a separate reward model and a verifiable domain. For an open-ended task with no verifier, coverage (pass@k) rises log-linearly with N, while selection without a verifier plateaus. The harness therefore gains most when it has a cheap automatic check, such as tests, a parser, or constraints.

### Cited Findings
- **Self-consistency** (Wang et al., ICLR 2023; arXiv v1 2022-03-21). It improves over CoT by +17.9% on GSM8K, +11.0% on SVAMP, +12.2% on AQuA, +6.4% on StrategyQA, and +3.9% on ARC-challenge. The models and sample count (believed to be 40) were not on the abstract page, so they are unverified here. — [arXiv 2203.11171](https://arxiv.org/abs/2203.11171)
- **Self-consistency vs multi-agent debate at equal response counts** (GSM8K, GPT-3.5, from Huang et al. Table 7). Standard 76.7. SC@3 82.5. Debate round 1 (6 responses) 83.2 vs SC@6 85.3. Debate round 2 (9 responses) 83.0 vs SC@9 88.2. At matched cost, self-consistency beats debate. — [arXiv 2310.01798 HTML](https://arxiv.org/html/2310.01798v2)
- **Large Language Monkeys** (Brown et al., v1 2024-07-31, v3 2024-12-30). DeepSeek-Coder-V2-Instruct on SWE-bench Lite rose from 15.9% solved with one sample to 56% with 250 samples, against a single-attempt SOTA of 43%. Coverage scales over 4 orders of magnitude, often log-linearly (an exponentiated power law). Without automatic verifiers, "majority voting and reward models plateau beyond several hundred samples." — [arXiv 2407.21787](https://arxiv.org/abs/2407.21787)
- **Snell et al., "Scaling LLM test-time compute optimally"** (2024-08-06). Allocating compute per prompt is ">4x" more efficient than best-of-N. Under matched FLOPs, test-time compute beats a "14x larger" model, but only on problems where the small model already has "somewhat non-trivial success rates." Gains depend on difficulty. (The base model, believed to be PaLM 2-S, was not confirmed on the abstract page.) — [arXiv 2408.03314](https://arxiv.org/abs/2408.03314)
- **Hugging Face "Scaling test-time compute" blog** (Dec 2024; code released 2024-12-16)
  - Setup: Llama-3.2-1B-Instruct and 3B-Instruct, with the RLHFlow/Llama3.1-8B-PRM-Deepseek-Data PRM. MATH-500, T=0.8, up to 2048 tokens, N from 1 to 256, 5 seeds.
  - Majority vote plateaus after N≈64. Weighted best-of-N beats vanilla best-of-N. Best-of-N at N=256 still trails Llama 8B.
  - Beam search at N=4 equals best-of-N at N=16, and beam search at N=16 equals best-of-N at N=256. Beam search at N=32 equals Llama-3.1-8B. The 1B model reaches "nearly 55%" on MATH-500.
  - The 3B model with compute-optimal scaling beats Llama-3.1-70B-Instruct.
  - **Failure modes:** beam search is worse than best-of-N or majority vote on easy problems and at large N, because the tree collapses onto one trace. DVTS fixes this at large N and on easy or medium problems.
  - Results depend on verifier quality. Open PRMs are rare. Self-verification is hard. The demonstrations are in math and code only.
  - Exact per-method accuracies appear only in the charts, so they are not transcribed here.
  - Sources: [HF blog](https://huggingfaceh4-blogpost-scaling-test-time-compute.hf.space/); [search-and-learn repo](https://github.com/huggingface/search-and-learn)
- **"Can 1B LLM surpass 405B?"** (Liu et al., 2025-02-10). Under compute-optimal test-time scaling, 1B beats 405B on MATH-500, 0.5B beats GPT-4o on MATH-500 and AIME24, 3B beats 405B, and 7B beats o1 and DeepSeek-R1. The strategy is "highly dependent on the choice of policy model, PRM, and problem difficulty." — [arXiv 2502.06703](https://arxiv.org/abs/2502.06703)

### Inferences
- **Call budget at the GLM gateway:** SC@N costs ×N calls. With 429s at about 35 calls, SC@5 already caps throughput at about 7 tasks per burst window. Use small N (3–5), back off and retry on 429, and stop early when the first k samples agree, which saves calls on easy items.
- **Call budget on local Qwen3.5-9B:** cost is token-bound, not call-bound. At about 26 tok/s, one 1,500-token CoT takes about 1 minute, so SC@5 takes about 5 minutes per task if run sequentially. Feasible for a batch run overnight, but not for interactive use.
- PRM search (beam search, DVTS) needs an extra reward model. It is impractical in a stdlib-only, air-gapped harness unless the same LLM serves as judge, which the HF blog itself flags as hard ("self-verification").
- Ranking for this harness:
  1. Programmatic verifier + resample, best when available.
  2. Majority vote for short answers.
  3. LLM-as-judge best-of-N, weakest evidence (see Gaps).

### Gaps
- No primary-source numbers were found for LLM-as-judge best-of-N with ≤35B models on open-ended tasks.
- No test-time scaling data was found for GLM-5.3-Flash or Qwen3.5-9B (including thinking mode vs SC).
- HF per-method accuracies were not transcribed because they appear only in the charts.

## Decomposition / planning prompts (plan-and-solve, least-to-most, plan-then-execute)

### Takeaway
No reliable 2025–2026 controlled evaluation was found showing that explicit plan-and-solve or least-to-most prompting helps (or hurts) ≤35B models. The original strong results come from large 2022-era models. Treat decomposition as unproven for small models and A/B test it locally.

### Cited Findings
- **Least-to-most** (2022). code-davinci-002 solved SCAN at ≥99% with 14 exemplars, vs 16% for CoT. This is a large model, not a small one. This came from a search-result snippet, not the original least-to-most paper (arXiv 2205.10625), so it is unverified. — [search result](https://arxiv.org/pdf/2209.15003.pdf)
- **Plan-and-solve** is described as merging plan generation and plan execution into one output, which makes it more efficient than least-to-most (secondary description). — [arXiv 2401.14043](https://arxiv.org/pdf/2401.14043v1)
- A 2026 blog claims modern reasoning models decompose internally, so explicit decomposition helps mainly on unfamiliar compositional tasks. This is opinion, not a controlled evaluation. — [adaline.ai](https://www.adaline.ai/blog/least-to-most-prompting)

### Inferences
- Single-call plan-and-solve costs ×1 calls with more output tokens, which makes it cheap under the GLM rate limit. Multi-call plan-then-execute costs ×(1 + number of steps).
- For Qwen3.5-9B with a thinking mode, an explicit plan prompt may be redundant with its native reasoning. This is untested.

### Gaps
- No 2025–2026 primary study of plan-and-solve, least-to-most, or plan-then-execute on ≤35B models was located within the call budget.

## Self-correction (intrinsic vs external feedback; Self-Refine)

### Takeaway
Intrinsic self-correction (the model reviews itself with no external signal) does not help on reasoning, and it hurts small models badly: Llama-2 drops from 62.0 to 36.5 on GSM8K. Gains appear only with oracle or external feedback. Self-Refine's roughly +20% comes from GPT-3.5 and GPT-4 on mostly open-ended generation tasks. Use a refinement loop only when there is an external signal, such as a parse error, a failed test, or a constraint violation.

### Cited Findings
- **Huang et al., "LLMs Cannot Self-Correct Reasoning Yet"** (ICLR 2024; v1 2023-10-03). Intrinsic self-correction at 1 / 3 / 5 calls:

  | Model | GSM8K | CommonSenseQA | HotpotQA |
  |---|---|---|---|
  | GPT-3.5 | 75.9 → 75.1 → 74.7 | 75.8 → 38.1 → 41.8 | 26.0 → 25.0 → 25.0 |
  | GPT-4 | 95.5 → 91.5 → 89.0 | 82.0 → 79.5 → 80.0 | 49.0 → 49.0 → 43.0 |
  | Llama-2 | 62.0 → 43.5 → 36.5 | 64.0 → 37.5 → 36.5 | not reported |

  — [arXiv 2310.01798 HTML](https://arxiv.org/html/2310.01798v2)
- **Same paper, with oracle labels (stop when correct):** GPT-3.5 goes from 75.9 to 84.3 on GSM8K and from 75.8 to 89.7 on CommonSenseQA. GPT-4 goes from 95.5 to 97.5 on GSM8K. The gain depends on knowing the ground truth. — [same](https://arxiv.org/html/2310.01798v2)
- **Self-Refine** (Madaan et al., v1 2023-03-30). About 20% absolute average improvement across 7 tasks (dialog through math) with GPT-3.5, ChatGPT, and GPT-4. The same LLM generates, gives feedback, and refines. The abstract page lists no venue, and no claim about weaker models appears there. — [arXiv 2303.17651](https://arxiv.org/abs/2303.17651)

### Inferences
- Each refine round costs ×2 calls (critique + revise). On Huang's call counting, round 2 costs 5 calls in total. This is poor value under a 35-call burst limit unless it is triggered by an external failure signal.
- A small model (Qwen3.5-9B) is closer to Llama-2's regime than GPT-4's. Expect intrinsic "review your answer" steps to flip correct answers to wrong ones.

### Gaps
- No 2025–2026 primary results were found for intrinsic self-correction on Qwen3-class or GLM-class models. The memory that Self-Refine fails on Vicuna-13B is unverified, because it was not on the abstract page.

## Structured output / constrained decoding

### Takeaway
The claim that JSON or format constraints hurt reasoning (Tam et al. 2024) is disputed. dottxt's re-run with Llama-3-8B, using matched prompts and better parsing, found structured generation equal or slightly better on all three tasks. The practical rule: put the reasoning field before the answer field, keep the prompts identical, and parse robustly.

### Cited Findings
- **"Let Me Speak Freely?"** (Tam et al., v1 2024-08-05, v3 2024-10-14). Reports a "significant decline in LLMs reasoning abilities" under format restrictions, with stricter formats degrading more. Numbers and models were not on the abstract page. — [arXiv 2408.02442](https://arxiv.org/abs/2408.02442)
- **dottxt rebuttal "Say What You Mean"** (Will Kurt; undated on the page, late 2024)
  - Critique: the paper's prompts differed between conditions, and its JSON prompt for Last Letter gave no schema. It used Claude-3-Haiku as a "perfect" answer parser, and that parser was imperfect: on Last Letter, strict regex scored 0.35, the AI parser 0.57, and a flexible regex 0.61. It also conflated JSON mode with constrained decoding.
  - Re-run with Llama-3-8B-Instruct, unstructured vs structured: GSM8K 0.77 vs 0.78, Last Letter 0.73 vs 0.77, Shuffled Objects 0.41 vs 0.44.
  - This is an independent party, but a vendor with a stake (Outlines).
  - Source: [dottxt blog](https://blog.dottxt.ai/say-what-you-mean.html)

### Inferences
- Constrained decoding costs ×1 calls and is free under the rate limit. Server-side grammar support (vLLM, llama.cpp GBNF, XGrammar) must be exposed through LiteLLM. A stdlib-only alternative is to ask for JSON, validate it with `json.loads`, and re-ask only on failure. That is an external-feedback loop of the kind Huang's results support.

### Gaps
- No independent third study settling the dispute was fetched. No numbers were found for XGrammar's or GBNF's accuracy effects on ≤35B models.

## Automatic prompt / harness optimization (DSPy MIPROv2, GEPA, TextGrad, Meta-Harness)

### Takeaway
GEPA (reflective prompt evolution) gives the strongest small-open-model evidence: Qwen3 8B rises from an aggregate of 45.23 to 54.85 across 6 tasks, beating MIPROv2 (47.84) and GRPO (48.91, using 24k rollouts) with about 1.8k–7k rollouts. Meta-Harness (Mar 2026) searches harness code itself and reports +4.7 points of average math gain transferred across models, but it relies on a frontier coding agent as the proposer. Both are offline, one-time costs. The optimized prompt or harness is then cheap at runtime.

### Cited Findings
- **GEPA** (Agrawal et al., v1 2025-07-25, v2 2026-02-14; ICLR 2026 Oral)
  - Abstract: beats GRPO by 6% on average and by up to 20%, with up to 35x fewer rollouts. Beats MIPROv2 by >10%, including +12% on AIME-2025.
  - Qwen3 8B (Table 1), scores in the order baseline / MIPROv2 / GRPO / GEPA:

    | Task | Baseline | MIPROv2 | GRPO | GEPA |
    |---|---|---|---|---|
    | HotpotQA | 42.33 | 55.33 | 43.33 | 62.33 |
    | IFBench | 36.90 | 36.22 | 35.88 | 38.61 |
    | HoVer | 35.33 | 47.33 | 38.67 | 52.33 |
    | PUPA | 80.82 | 81.55 | 86.66 | 91.85 |
    | AIME-2025 | 27.33 | 20.00 | 38.00 | 32.00 |
    | LiveBench-Math | 48.70 | 46.60 | 51.26 | 51.95 |
    | Aggregate | 45.23 | 47.84 | 48.91 | 54.85 |

  - Note: MIPROv2 hurt AIME (27.33 → 20.00), and GRPO beats GEPA on AIME.
  - Budget: GEPA's total budget per task was 6,871 / 3,593 / 7,051 / 2,426 / 1,839 / 1,839 rollouts, against 24,000 for GRPO. Most of GEPA's budget is validation; train rollouts needed only 79–737 to reach the optimum.
  - Source: [arXiv 2507.19457](https://arxiv.org/abs/2507.19457); [HTML](https://arxiv.org/html/2507.19457v2)
- **Meta-Harness** (Lee, Nair, Zhang, K. Lee, Khattab, Finn; arXiv 2603.28052, Mar 2026)
  - Method: outer-loop search over harness code. The proposer is Claude Code with Opus 4.6, which reads the source, scores, and raw execution traces of earlier candidates through the filesystem. A typical run evaluates about 60 harnesses over 20 iterations and takes "a few hours." No dollar cost is reported.
  - **Math:** 200 held-out IMO-level problems, pass@1 averaged over 3 samples. The discovered harness is BM25 retrieval over ≥500k solved problems, with a lexical router.

    | Model | No retriever | Meta-Harness |
    |---|---|---|
    | GPT-5.4-nano | 23.0 | 31.7 |
    | GPT-5.4-mini | 28.8 | 30.4 |
    | Gemini-3.1-Flash-Lite | 28.6 | 34.9 |
    | Gemini-3-Flash | 42.6 | 46.3 |
    | GPT-OSS-20B | 47.6 | 50.6 |
    | Average | 34.1 | 38.8 (+4.7) |

    GPT-OSS-20B was the model used during search. Plain BM25 averaged 37.5 and dense retrieval 38.1, so most of the gain is retrieval itself.
  - **Text classification** (GPT-OSS-120B): 48.6% vs ACE 40.9% with about 11.4K vs 50.8K context tokens. 73.1% vs 70.2% on 9 OOD datasets. Removing raw traces from the proposer lowered results substantially.
  - **TerminalBench-2:** Opus 4.6 scores 76.4% and Haiku 4.5 scores 37.6%. Search and test used the same 89 tasks, so there is an overfitting risk.
  - Source: [arXiv 2603.28052 HTML](https://arxiv.org/html/2603.28052v1)

### Inferences
- GEPA-style optimization at 1.8k–7k rollouts is infeasible on the rate-limited GLM gateway: at about 35 calls per few minutes, that is hours to days.
- On local Qwen3.5-9B at 26 tok/s, 2k rollouts of about 500 tokens is roughly 11 hours. It is feasible as an overnight job outside the air gap. The optimized prompt text can then be carried inside, which fits the "clone the repo" workflow.
- Meta-Harness needs a frontier coding agent as the proposer. It could only be done outside the air gap with the result committed. Its math gain is mostly retrieval over a large corpus, which is out of scope for "no domain tools."

### Gaps
- No TextGrad or DSPy MIPROv2 small-model numbers were fetched beyond GEPA's MIPROv2 baseline.
- No evidence was found that a prompt optimized for Qwen3 transfers to GLM. Meta-Harness reports cross-model transfer of harness code for math only.

## Majority vote / ensembling of multiple small models vs one larger model

### Takeaway
Sampling-and-voting with more agents of the same model scales performance, and gains grow with task difficulty (TMLR). No primary numbers were verified for an ensemble of different small models beating one larger model.

### Cited Findings
- **"More Agents Is All You Need"** (Agent Forest; TMLR; v1 2024-02-03, v2 2024-10-11). Performance "scales with the number of agents" using plain sampling-and-voting, and the gain "is correlated to the task difficulty." There were no numbers on the abstract page. The claim that Llama2-13B matches 70B is unverified. — [arXiv 2402.05120](https://arxiv.org/abs/2402.05120)
- At matched response counts, self-consistency beats multi-agent debate (GSM8K: 88.2 vs 83.0 at 9 responses). — [arXiv 2310.01798](https://arxiv.org/html/2310.01798v2)
- Test-time scaling with PRM search lets 1B–3B models beat 8B–70B or 405B ones on math (see the first section). This is search with a verifier, not ensembling. — [HF blog](https://huggingfaceh4-blogpost-scaling-test-time-compute.hf.space/); [arXiv 2502.06703](https://arxiv.org/abs/2502.06703)

### Inferences
- A practical ensemble here would be GLM-5.3-Flash plus Qwen3.5-9B voting. It costs ×(N_glm + N_qwen) calls but splits the load across the rate-limited gateway and the local machine. It is unproven, so A/B test it.
- Debate costs ×(agents × rounds) and loses to plain SC at equal cost, so skip it.

### Gaps
- No verified 2025–2026 primary numbers were found for heterogeneous small-model ensembles vs a single larger model.
- More Agents' per-benchmark numbers were not read.
