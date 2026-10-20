# Effective (Usable) Context Length of LLMs — Small/Local Models & Cheap Measurement (as of Oct 2026)

Tags: [V] = verified this session against the primary source page; [S] = from a search snippet or secondary summary, primary not opened; [U] = unverified or from background knowledge, so check before relying on it. (pre-2025) marks older work.

## 1. Evidence: claimed vs effective context

### Takeaway
Advertised windows overstate usable context by about 2–4x on easy synthetic retrieval (RULER) and by 30–100x on retrieval without literal overlap (NoLiMa). For 4–9B models, RULER effective length is about 32K–64K out of a claimed 128K–1M. On NoLiMa, Llama-3.1-8B's effective length is only about 1K. A 50–60% budget ratio is therefore optimistic for small models unless it is calibrated per model and per task.

### Cited Findings
- **RULER definition**: effective length is the longest length at which the model's score exceeds Llama-2-7B's 4K score (85.6%) — [RULER GitHub](https://github.com/NVIDIA/RULER) [V]
- **RULER leaderboard, small models** (claimed → effective; scores at 4K/8K/16K/32K/64K/128K) — [RULER GitHub](https://github.com/NVIDIA/RULER) [V]:
  - Qwen3-4B*: 128K → 64K; 95.1/93.6/91.0/87.8/77.8/66.0
  - Qwen3-8B*: 128K → 64K; 96.3/96.0/91.8/91.2/82.1/77.4
  - Qwen3-14B*: 128K → >128K; 98.0/97.8/96.4/96.1/94.0/85.1
  - Qwen2.5-7B-Instruct-1M*: 1M → >128K; 96.8/95.3/93.0/91.1/90.4/84.4
  - Llama-3.1-8B: 128K → 32K; 95.5/93.8/91.6/87.4/84.7/77.0
  - GLM4-9B: 1M → 64K; 94.7/92.8/92.1/89.9/86.7/83.1
  - GLM3-6B: 128K → 4K; 87.8/…/42.0 at 128K
  - Phi3-mini (3.8B): 128K → 32K; 92.2/91.5/90.7/87.5/80.6/66.7
  - Phi3-medium (14B): 128K → 32K; 128K = 46.1
  - EXAONE-4.0-1.2B*: 64K → 32K
  - Mistral-7B: 32K → 16K; 13.8 at 128K
  - \* = scores reported by the model authors, not the RULER team, so they may be optimistic. No Gemma and no Phi-4-mini entries on the leaderboard.
- **Gemma 3 (Table 15)**: RULER at 32K/128K is 4B-IT 61.4/46.8, 12B-IT 80.3/57.1, 4B-PT 67.1/51.7, 12B-PT 90.6/80.7. Instruction tuning lowered long-context scores. The model claims 128K — [Gemma 3 Tech Report](https://arxiv.org/pdf/2503.19786) [S, via search summary]
- **RULER original paper** (pre-2025, Apr 2024): 17 models, almost all of which degrade sharply even though they claim ≥32K. Vanilla NIAH misses multi-hop tracing and aggregation, and RULER adds both — [arXiv 2404.06654](https://arxiv.org/abs/2404.06654v2) [S]
- **NoLiMa** (Feb 2025, ICML 2025): the needle and the question share minimal lexical overlap, so the model has to make a latent association (e.g., "Semper Opera House" → Dresden). Effective length is the largest length scoring ≥85% of the model's own short-context base score. 11 of 13 models fall to ≤50% of base by 32K — [NoLiMa HTML](https://arxiv.org/html/2502.05167) [V]
  - Llama-3.1-8B: claimed 128K, effective **1K**. Base 76.7; 65.7 (1K), 54.4 (2K), 44.1 (4K), 31.9 (8K), 22.6 (16K), 14.2 (32K)
  - GPT-4o: effective 8K (99.3 base → 69.7 at 32K). GPT-4o-mini: <1K. Gemini 2.0 Flash (1M claimed): 4K. Llama-3.3-70B: 2K. Claude 3.5 Sonnet: 4K
- **BABILong** (pre-2025, NeurIPS 2024): popular LLMs "effectively utilize only 10-20% of the context", and performance falls sharply as reasoning complexity increases. RAG reaches about 60% on single-fact QA regardless of length — [arXiv 2406.10149](https://arxiv.org/abs/2406.10149) [S]
- **Chroma "Context Rot"** (14 July 2025): 18 models from Anthropic, OpenAI, Google and Alibaba (Qwen3 included), up to 8 lengths × 11 needle positions, 194,480 calls. Performance "grows increasingly unreliable as input length grows" even on trivial tasks — [Chroma](https://www.trychroma.com/research/context-rot) [V]
  - Needles with lower question similarity degrade faster as length grows
  - One distractor already lowers accuracy and four lower it further. The distractors' effects are uneven
  - Shuffled (incoherent) haystacks scored *higher* than coherent ones for all 18 models
  - LongMemEval, 306 prompts: focused (~300 tokens) beat full (~113K tokens) for every model
  - Repeated-words copy task (25–10,000 words): accuracy falls with length, so degradation also hits output generation, not only retrieval
- **HELMET** (pre-2025, Oct 2024 / ICLR 2025): "synthetic tasks like NIAH do not reliably predict downstream performance". The seven categories correlate weakly with each other. Open models trail closed ones on full-context reasoning, and the gap grows with length. The authors recommend the RAG tasks as a fast, predictive proxy — [arXiv 2410.02694](https://arxiv.org/abs/2410.02694) [V, abstract]
- **LongBench v2** (pre-2025, Dec 2024): 503 multiple-choice questions over 8K to 2M words. Humans score 53.7% (15-minute limit), the best direct-answer model 50.1%, o1-preview 57.7%, random guessing 25% — [arXiv 2412.15204](https://arxiv.org/abs/2412.15204v1) [S]
- **Michelangelo / Latent Structure Queries** (pre-2025, Sep 2024, Google DeepMind): the model must "chisel away" irrelevant context to recover a latent structure. Three diagnostic tasks across code and natural language, with "significant room for improvement" — [arXiv 2409.12640](https://arxiv.org/abs/2409.12640) [V, abstract only]. I could not verify task names (MRCR, Latent List, IDK) or curve shapes from the abstract [U].

### Inferences
- The effective length you measure depends on the task. The same model can have about 64K on RULER, a few K on NoLiMa-style latent matching, and less still on multi-hop reasoning. A profile should store more than one number.
- For 4–8B local models, plan around a 16K–32K working budget for retrieval-style use and about 4K–8K when the answer needs non-literal association or multi-hop reasoning over the context. This holds even when the model advertises 128K. Measure before trusting any of these figures.
- For the ~1M-context source model, RULER-style effective lengths reported for GLM4-9B (64K of 1M) and Qwen2.5-7B-1M (>128K) suggest the usable window is a small fraction of 1M. A 50–60% ratio applied to 1M would be far too high.

### Gaps
- No primary RULER/NoLiMa numbers for Phi-4-mini, and none for Gemma 3 in RULER's own leaderboard.
- I could not find a primary source for "GLM-5.3-Flash" or its ~1M claim. A search for GLM-5 RULER/MRCR results returned nothing primary. One third-party blog on GLM-5.2 mentions sparse attention and indexing costs at million-token scale ([Braintrust](https://www.braintrust.dev/evals/glm-52-vs-opus-48-technical-report), [S], weak). Treat GLM-specific long-context claims as [U] and measure them directly.
- Not opened this session: the full Michelangelo paper, LongMemEval original paper, BABILong per-model tables.

## 2. What degrades first (retrieval vs multi-hop vs instruction following vs tool calling)

### Takeaway
Order of fragility, from most robust to least: literal single-needle retrieval, then multi-needle/aggregation, then non-literal (semantic) retrieval, then multi-hop reasoning. Tool calling and instruction following also degrade measurably with more tools, longer tool outputs and longer histories. Reasoning models delay the decline but do not remove it.

### Cited Findings
- On NoLiMa with Llama-3.3-70B at 4K/8K/16K/32K: one-hop questions without CoT score 90.3/84.1/73.2/56.2, while two-hop questions without CoT score 70.7/57.4/42.7/25.9. Two-hop questions with CoT still score only 56.7 at 16K and 34.3 at 32K — [NoLiMa HTML](https://arxiv.org/html/2502.05167) [V]
- On NoLiMa-Hard (the 10 hardest pairs), all reasoning models fall below 50% of base by 32K. o1 drops from 99.9 to 31.1, o3-mini from 98.8 to 18.9, and DeepSeek-R1-Distill-Llama-70B from 99.9 to 20.7. o3-mini is already at 52.8 by 4K — [NoLiMa HTML](https://arxiv.org/html/2502.05167) [V]
- In Context Rot's LongMemEval runs, thinking mode raised scores on both focused and full prompts, but the gap between them remained — [Chroma](https://www.trychroma.com/research/context-rot) [V]
- On LongBench v2, inference-time reasoning (o1-preview, 57.7) beat the best direct-answer model (50.1) — [arXiv 2412.15204](https://arxiv.org/abs/2412.15204v1) [S]
- **Tool calling, LongFuncEval** (May 2025): accuracy drops 7–85% as the number of tools grows (catalogs of about 65K–120K tokens). Answer retrieval drops 7–91% as tool responses get longer, and accuracy drops 13–40% over longer multi-turn conversations. Granite-3.1-8B shows a lost-in-the-middle pattern by tool position. At 120K, Mistral-Large hallucinated function names. GPT-4o stayed comparatively robust — [arXiv 2505.10570](https://arxiv.org/abs/2505.10570v1) [S]
- **Tool-DC** (2026): on BFCL, going from fewer than 10 to 20 candidate tools degrades all LLMs, smaller models most. The authors attribute part of this to confusion between semantically similar tools with different arguments — [arXiv 2603.11495](https://arxiv.org/html/2603.11495v1) [S]
- Claims that Anthropic's internal testing showed degradation past 30–50 tools, and that LangChain's ReAct benchmark saw GPT-4o fall to 2% across seven domains, come only from secondary blogs — [StackOne blog](https://www.stackone.com/blog/agent-tool-count-ceiling/) [U, not verified at primary source]
- **Instruction following**: LIFBench (ACL 2025) has 2,766 instructions across 3 long-context scenarios and 11 tasks, and measures stability as well as accuracy as input grows — [arXiv 2411.07037](https://alphaxiv.org/abs/2411.07037) [S]. VerIFY (EACL 2026 Findings, Google DeepMind and Vanderbilt) studies instruction compliance in long multi-turn conversations and reports up to 79% improvement from mitigations — [ACL Anthology](https://preview.aclanthology.org/ingest-eacl/2026.findings-eacl.254.pdf) [S]
- In the Gemma 3 report, the IT models score lower than the PT models at long context. 12B: 80.7 (PT) vs 57.1 (IT) on RULER at 128K — [Gemma 3](https://arxiv.org/pdf/2503.19786) [S]

### Inferences
- An agent harness consumes context through a long system prompt, tool schemas, tool outputs and history, so it is exposed to all of these failure modes at once. Keep the tool list short (≲10–20 for small models) and the tool outputs truncated. These are probably larger levers than the raw window size.
- The probe should test tool-call validity (JSON parses, correct name, correct arguments) at increasing filler lengths, in addition to retrieval.

### Gaps
- I could not find a BFCL "long-context" subset with per-model numbers. BFCL v3/v4 multi-turn categories exist, but I did not verify any long-context category this session [U].
- No primary data on how GLM models specifically degrade on tool calling with long context.

## 3. Position effects

### Takeaway
Lost-in-the-middle is real but secondary. Total length matters more than where the needle sits, especially in NoLiMa and Chroma. Put critical instructions and the current task at the end of the prompt (and repeat them there) and keep the system prompt at the start. Tool-catalog position also matters for some small models.

### Cited Findings
- Lost in the Middle (Liu et al., TACL 2024, pre-2025): accuracy is U-shaped, highest when the relevant information is at the start or end of the context — [arXiv 2307.03172](https://arxiv.org/abs/2307.03172) [U, not re-fetched this session]
- NoLiMa: a lost-in-the-middle dip appears at 32K, but in the last-2K analysis the main limiting factor is context length, not needle depth. For two-hop questions, longer contexts drag performance down at every position — [NoLiMa HTML](https://arxiv.org/html/2502.05167) [V]
- Context Rot: needle position had no notable effect in the similarity experiments, while length, distractors and haystack coherence did — [Chroma](https://www.trychroma.com/research/context-rot) [V]
- LongFuncEval: Granite-3.1-8B does well when the correct tool is at the start or end of the catalog and poorly in the middle — [arXiv 2505.10570](https://arxiv.org/abs/2505.10570v1) [S]

### Inferences
- In the probe, sample depths of at least 0.1, 0.5 and 0.9, and report the minimum across depths, not the mean.

### Gaps
- I did not verify 2025–26 follow-ups on positional bias (e.g., "Found in the Middle" calibration) this session.

## 4. Practical, cheap measurement protocol for the probe (stdlib, OpenAI-compatible API)

### Takeaway
Run 3–4 task families at 6 lengths × 3 depths with about 5 trials each. That is roughly 300–400 calls per model, and it can be done with `urllib` and `json`. For each task family, store the largest length where accuracy is at least 85–90% of that model's own short-context baseline (the NoLiMa-style relative threshold) and at least an absolute floor. Then set the budget from the minimum across the families the harness relies on.

### Cited Findings (design basis)
- Relative threshold: score ≥85% of the model's own base score at ≤1K (NoLiMa) — [NoLiMa](https://arxiv.org/html/2502.05167) [V]. Absolute threshold: score > 85.6% (RULER) — [RULER](https://github.com/NVIDIA/RULER) [V]
- Use non-literal needles because literal NIAH saturates and overstates usability — [NoLiMa](https://arxiv.org/abs/2502.05167) [V]; [HELMET](https://arxiv.org/abs/2410.02694) [V]
- Distractors and low needle-question similarity are the cheap ways to make the test realistic — [Chroma](https://www.trychroma.com/research/context-rot) [V]
- Multi-hop variable tracing and aggregation (common/frequent words) are the RULER task types that go beyond NIAH — [RULER](https://arxiv.org/abs/2404.06654v2) [S]
- RAG-style QA predicts downstream behavior better than NIAH — [HELMET](https://arxiv.org/abs/2410.02694) [V]
- Chroma's harness is open source and can serve as a reference for haystack construction — [Chroma](https://www.trychroma.com/research/context-rot) [V]

### Proposed minimal protocol (inference; design recommendation, not sourced)
- **Lengths**: 1K (baseline), 4K, 8K, 16K, 32K, 64K, plus 128K only if the profile claims it. Lengths are in measured tokens; see section 5.
- **Depths**: 0.1, 0.5 and 0.9.
- **Trials**: 5 per (task, length, depth) cell at temperature 0, varying needle content and seed.
- **Tasks** (one short generator function each):
  1. T1 literal NIAH with 3 distractors, e.g. "The access code for 서버-B is 4821" alongside similar codes for 서버-A/C/D. This is the floor. If it fails, stop.
  2. T2 non-literal (NoLiMa-style). The needle is "민지는 작년에 경주 불국사 옆으로 이사했다." and the question is "Which character lives in 경상북도?" Build pairs from a hand-written table of about 20 entity→category facts the model knows at 1K. Before using a pair, check that it passes at 1K.
  3. T3 multi-hop variable tracing: VAR_A=VAR_B, VAR_B=VAR_C, …, VAR_E=73915 scattered through the haystack. Ask for VAR_A.
  4. T4 tool call under load: the system prompt carries N tool schemas (N = 5, 15, 30) and the filler is long fake history or tool output. The final user request needs a specific tool and arguments. Score = valid JSON + correct name + exact arguments.
  5. Optional T5 aggregation: count occurrences, or list all items tagged X.
- **Haystack**: use in-house Korean and English documents (coherent text; Chroma found it harder than shuffled text) plus a Korean variant of each task.
- **Cost**: 4 tasks × 6 lengths × 3 depths × 5 trials = 360 calls. Most of the tokens are in the 32K/64K cells, about 6M prompt tokens in total. On a local GPU, time is dominated by prefill at the long lengths. To save time, run the full grid only up to the first failing length plus one more.
- **Profile fields** (suggested):
  - `effective_ctx.{literal,semantic,multihop,tool}` = largest L where acc ≥ max(0.85×base, 0.80) at every depth
  - `context_tokens_safe` = min over the task families the harness uses
  - `chars_per_token.{ko,en,code}`
  - `max_tools_reliable`
  - `probe_date`, `probe_version`
  - `context_budget_ratio` derived as context_tokens_safe / claimed rather than a fixed 0.5–0.6

### Gaps
- No published standard for trial counts at this scale. Five trials give coarse estimates (±20% per cell), so pool depths and use the minimum, or raise trials to 10 at the boundary length.

## 5. Token estimation without a tokenizer (incl. Korean)

### Takeaway
Calibrate per model from `usage.prompt_tokens`. Korean costs about 2.5–3x more tokens per character than English in byte-level BPE tokenizers (≈1.3–1.4 chars/token for Korean vs ≈4 for English), and the figure varies by tokenizer. Calibrate separately for Korean, English and code, and keep a 10–15% safety margin.

### Cited Findings
- Qwen3-8B ≈1.34 Korean characters per token, DeepSeek-V3 ≈1.40, Mixtral-8x7B ≈0.91, measured on a single paragraph. Hangul syllables are 3 bytes in UTF-8 and can split into up to 3 tokens when no merge exists — [youngju.dev blog](https://www.youngju.dev/blog/ai-papers/2026-08-12-model-internals-tokenizer-internals.en) [S, single-sample, indicative]
- A.X K1 report: on the same Korean general-domain samples, Qwen3 used about 906 tokens, o200k about 812, and A.X K1 (Korean-optimized) about 527, so tokenizers differ by up to ~1.7x — [arXiv 2601.09200](https://arxiv.org/pdf/2601.09200) [S]
- The Llama-3.1 tokenizer has few Korean tokens. Thunder-Tok adds about 92K Korean tokens — [SNU](https://champ.snu.ac.kr/models-snullm) [S]. Extending a Llama-family tokenizer with Korean cut tokens per sentence from about 325 to about 129 — [arXiv 2502.12560](https://arxiv.org/html/2502.12560v1) [S]
- The common rule of thumb of about 4 characters per token for English, with GPT-style tokenizers, comes from OpenAI's tokenizer help page [U, not fetched]

### Inferences / method
- Calibration routine in the probe:
  1. Send 3 to 5 fixed calibration texts (pure Korean, pure English, code/JSON, mixed) of about 2K–8K characters each, with `max_tokens=1`.
  2. Subtract the empty-prompt overhead (a minimal message) to remove chat-template tokens.
  3. Store `chars_per_token` per class.
  4. At runtime, estimate = Σ(len(segment)/cpt[class]) × 1.1, plus the template overhead per message and the tool-schema tokens, measured once.
- After each real call, update a running ratio from the returned `usage.prompt_tokens` using an exponential moving average. This self-corrects drift.
- Use UTF-8 byte length as a fallback proxy. For byte-level BPE, tokens ≈ bytes/2.5–4 for Korean, but calibrate rather than assume [inference].
- Korean doubles or triples the token cost of the same content, so a Korean haystack of N characters fills the window about 3x faster than English. Probe lengths must be set in *measured tokens*, not characters.

### Gaps
- No verified head-to-head chars-per-token table for Qwen3, Llama-3, Gemma 3 and GLM on the same Korean corpus. GLM tokenizer Korean efficiency is unknown [U].
- **Korean long-context benchmarks**: none named "Ko-LongBench" or "KoLongBench" was found. What exists:
  - Ko-LongRAG (EMNLP 2025 Findings), the first Korean long-context RAG benchmark. o1 was the best proprietary model and EXAONE 3.5 the best open model — [ACL Anthology](https://preview.aclanthology.org/dashboard/2025.findings-emnlp.938) [S]
  - Ko-MuSR (arXiv 2510.24150, Oct 2025), multistep soft reasoning over long Korean narratives. Multilingual models beat Korean-specialized ones — [arXiv](https://arxiv.org/abs/2510.24150v1) [S]
  - Neither has length-sweep "effective length" numbers that I could confirm.
