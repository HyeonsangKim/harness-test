# Context management within a task, for small and local models (as of 20 Oct 2026)

**Tags.** [V] means I checked the claim against the primary source (fetched in this session). [P] means it was verified in the earlier note `context_verification_recovery.md` and not re-fetched now. [S] means a secondary source, or from memory of the primary source without re-fetching. [U] means unverified, or a snippet only. Material from before 2025 is marked *(older)*.

**Scope.** This note extends the earlier note and does not repeat it. JetBrains masking-vs-summary per-model numbers, Chroma context rot, Manus's blog post and Anthropic's context-engineering post are cited here only briefly, as [P].

---

## Q1. Observation masking and tool-result clearing: mechanism, policies and evidence

### Takeaway
Replacing old tool *results* with a short placeholder, while keeping the tool *calls* and the model's reasoning, is the best-evidenced, cheapest and deterministic technique.

- **Evidence.** It matches LLM summarization at about half the cost on SWE-bench for 32B to 480B models. Anthropic made it a first-class API feature.
- **Keep-last-N defaults in practice:** N=3 for Anthropic's API, N=10 in JetBrains' study, N=5 in *(older)* SWE-agent.
- **Cache cost.** Clearing breaks the prompt cache at the point of the edit, so clear in batches: a large chunk, rarely.

### Cited Findings
**Mechanism and numbers**
- [V] Anthropic `clear_tool_uses_20250919`. Requires beta header `context-management-2025-06-27`. Parameters and defaults:
  - `trigger`: default 100,000 input tokens. Can be set in `input_tokens` or `tool_uses`.
  - `keep`: default 3 most recent tool use/result pairs; the oldest are cleared first.
  - `clear_at_least`: minimum tokens to clear per edit. If that minimum can't be reached, the strategy is not applied.
  - `exclude_tools`: tools whose results are never cleared.
  - `clear_tool_inputs`: default `false`, so only results are cleared and call arguments stay.
  - Cleared results are replaced by placeholder text telling the model the content was removed. The exact wording is not given on the page.
  - The docs example uses trigger 30k, keep 3, clear_at_least 5k, `exclude_tools=["web_search"]`.
  - Source: [Claude docs: context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [V] Anthropic, the same page, on caching. Clearing invalidates the cached prefix from the edit point onward. `clear_at_least` exists so that each invalidation is "worth it". Each clear costs one cache write, after which later requests reuse the new prefix. A separate `clear_thinking_20251015` strategy keeps the last N turns of thinking blocks (`thinking_turns`). Clearing thinking blocks also breaks the cache. — [Claude docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [P] Anthropic self-reported results: context editing alone gave +29% on agentic search, and +39% combined with the memory tool. In a 100-turn web-search evaluation, it cut tokens by 84%. — [Anthropic news](https://www.anthropic.com/news/context-management)
- [P] JetBrains "The Complexity Trap" ([arXiv 2508.21433](https://arxiv.org/abs/2508.21433)), SWE-agent on SWE-bench Verified:
  - Masking all but the last M=10 observations cut cost by about 50% and matched summarization on solve rate. The smallest model tested was Qwen3-32B: 17.0 raw, 15.0 masked, 16.0 summarized.
  - Short trajectories (median about 15 turns) got only about 10% savings.
  - Both strategies hurt Gemini-2.5-Flash-thinking (40.4 raw, 36.4 masked, 31.4 summarized), so the sign of the effect depends on the model.
- [V] ICLR (Wang et al., 24 Sep 2026; [arXiv 2609.29875](https://arxiv.org/abs/2609.29875)) addresses the opposite question: which old **reasoning** blocks can be dropped while actions, tool calls and observations are kept.
  - On WorkBuddyBench (260 tasks), reward went from 0.699 to 0.718, with 25.5% fewer input tokens, 14.4% fewer output tokens and 33.3% fewer cache-read tokens.
  - Reasoning becomes more replaceable once task state has been externalized into files, code or tool outputs.
  - The authors warn of "trajectory amplification": deleting reasoning changes later behaviour non-linearly.
  - Model sizes are not given in the abstract.
- [V] Self-GC (Hao et al., 1 Jul 2026; [arXiv 2607.00692](https://arxiv.org/abs/2607.00692)) has a side-channel planner propose fold, mask and prune actions over indexed context objects. The harness enforces "recoverable sidecars", safe commit boundaries and cache-aware commits.
  - On a 33-session hard set: 43.95% of prefix tokens pruned, with 84.85% of future continuations unaffected. Heuristic baselines reached 54.55–69.70%.
  - On 332 sessions: 91.27–94.58% no-impact, versus 77.71–87.46% for baselines.
  - In production: 10–15% fewer input tokens.
  - Implication: simple heuristics are measurably worse at deciding *what* to prune than a planned pruner, but they are still mostly safe.
- [V] ACON ([arXiv 2510.00615](https://arxiv.org/html/2510.00615v3)) found naive deletion strategies weak on hard AppWorld tasks with gpt-4.1: FIFO fell to 15.9% and retrieval-based selection to 7.9%, against 39.7% with no compression.
  - Caveat: these are history-truncation baselines that drop whole turns, not placeholder masking that keeps the calls.
- [S] *(older, 2024)* SWE-agent collapsed all but the last 5 observations into one-line placeholders. — [arXiv 2405.15793](https://arxiv.org/abs/2405.15793)

**Placeholder design**
- [V] Manus (Lance Martin's write-up of the Manus webinar, 15 Oct 2025) keeps two forms of every tool result:
  - a "full" form, written to the sandbox file system;
  - a "compact" form, a reference such as a file path.

  Stale results are swapped to the compact form, which can be reversed by re-reading the file. Newer results stay in full. — [rlancemartin.github.io](https://rlancemartin.github.io/2025/10/15/manus/)

### Inferences
- **Recommended v1.1 policy for the stdlib harness**, applied inside the single context-assembly function:
  - Keep the system prompt, the task and all assistant tool *calls*.
  - For tool *results* older than the last N (start with N=3–5 for small windows and N=10 for GLM-5.3-Flash), substitute a placeholder.
  - Make the placeholder self-describing and recoverable, for example `[result of read_file(path=a.txt) at step 7 cleared: 4,812 chars, saved to .runs/<id>/obs_007.txt; call read_obs(7) to view]`.
  - Use `exclude_tools` for small, high-value outputs, such as a final `verify` result or a credentials or login response. The Qwen3-8B AppWorld failure analysis (Q6) shows auth and credential loss as the top failure class.
- **Trigger on a budget, not on every turn.** Mask only once the estimated prompt exceeds about 60–70% of `context_tokens`, and then clear enough to drop below about 40%. This mimics `clear_at_least` and limits cache invalidations to a handful per task.
- **For small models, add (in v2) a cheap deterministic "fact pin".** Before masking a result, regex-extract IDs, paths, tokens and numeric answers into a harness-held facts block. This answers ACON's and the AppWorld paper's point that compression drops exactly these details, without depending on a model-written summary.
- Masking matters only once the trajectory exceeds about 15–20 turns or the tool outputs are large; see the threshold table in Q8.

### Gaps
- No study found of masking with 4B–14B agent models on long tasks; JetBrains' smallest was 32B.
- Anthropic's exact placeholder string was not shown on the docs page I fetched.

---

## Q2. LLM summarization and compaction: numbers, hybrids, and when it hurts

### Takeaway
LLM summarization helps when trajectories exceed the window. Generic prompts are risky: they paraphrase away identifiers, hide failure signals and lengthen runs. They hurt on hard tasks unless the summary prompt is task-tuned and the summary is structured. The evidence-backed pattern is a hybrid:

- compaction (deterministic, reversible) first;
- summarization with a fixed schema only when compaction stops yielding savings;
- recent turns kept verbatim.

On small models, a *task-tuned* compressor gave large gains: +32% relative on AppWorld for Qwen3-14B with ACON.

### Cited Findings
- [V] OpenHands condenser blog (9 Apr 2025): "up to 2x" lower per-turn API cost. Per-turn cost levels off below half the baseline once condensation starts. Solve rate was 54% with the condenser versus 53% baseline on a SWE-bench Verified subset. The post does not state the subset size, the model or the trigger threshold. — [OpenHands blog](https://openhands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents)
- [U] OpenHands condenser config parameters (e.g., `max_size`, `keep_first`) were not on the blog page and remain unverified.
- [V] ACON (Kang et al.; v1 Oct 2025, v3 1 Jun 2026) optimizes the compression *guidelines* using contrastive failure analysis: cases where the full context succeeded but the compressed one failed. — [arXiv 2510.00615](https://arxiv.org/html/2510.00615v3)
  - Triggers: history compression above 4,096 tokens; observation compression above 1,024 tokens.
  - gpt-4.1 on AppWorld: 56.0 with no compression (peak 9.93k tokens); 56.5 with ACON history compression (peak 7.33k); 43.5 with a **prompting** baseline (6.93k); 32.1 with LLMLingua observation compression.
  - Hard AppWorld: generic prompting-based history compression gave 23.8, versus 39.7 with no compression. Generic observation compression dropped OfficeBench from 76.84 to 55.79.
  - Small agent Qwen3-14B: AppWorld 25.6 → 33.9; 8-objective QA EM 0.158 → 0.23. The authors attribute this to removing distracting context.
  - Distilled compressors (Qwen3-14B, Qwen3-8B, Phi-4) keep more than 95% of the teacher's performance. Compressor cost: Qwen3-14B $0.0004 versus $0.045 for gpt-4.1.
  - Latency for the Qwen3-14B agent rises: 73 s per task without compression, 88 s with history compression, 102 s with observation compression.
- [P] JetBrains: summarization lengthened trajectories (Gemini 2.5 Flash: 52 turns versus 44 with masking). The authors believe summaries hide failure signals. A hybrid (mask first, summarize rarely) gave +2.6 pp and was 7% cheaper than masking, but only on n=50. — [arXiv 2508.21433](https://arxiv.org/html/2508.21433v3)
- [V] Manus policy: compaction (full → compact reference) first; summarization only "after compaction reaches diminishing returns". The summary uses a predefined schema of fields so each one is a consistent object. No numeric thresholds are given. — [Lance Martin on Manus](https://rlancemartin.github.io/2025/10/15/manus/)
- [V] Anthropic API compaction options:
  - client-side SDK `compaction_control`: default `context_token_threshold` 100,000, summary in `<summary>` tags; deprecated in favour of server-side;
  - server-side compaction: edit type `compact_20260112`. Its parameters were on a separate page I did not fetch.

  Source: [Claude docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [P] OpenAI GPT-5.1-Codex-Max was *trained* for compaction across windows, and `/responses/compact` returns an opaque compaction item. This is a model-trained capability, which local models lack. — see the earlier note
- [P] Anthropic's guidance: tune the compaction prompt for recall first, then precision. Claude Code keeps the summary plus the 5 most recently accessed files. — [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [S] A practitioner guide notes that summaries often paraphrase file paths and error messages, while deletion-based compaction keeps surviving text byte-identical. This is vendor marketing (Morph), so the claim is plausible but carries low evidential weight. — [Morph](https://www.morphllm.com/compaction-vs-summarization)

### Inferences
- **For this team:** do not put LLM summarization into v1. If added later (v3, for 8k–32k windows), make it:
  - (a) schema-based, with fields such as `goal`, `done_steps[]`, `facts{key: value, source_step}`, `open_errors[]` and `next_step`;
  - (b) built by merging over a harness-extracted facts dict, so the model fills only the free-text fields;
  - (c) triggered only when masking cannot get under budget;
  - (d) kept alongside the verbatim last K turns, as in the AppWorld paper (first 26 and last 6 messages) and Claude Code (last 5 files);
  - (e) logged as before/after with an A/B switch, because JetBrains shows sign flips per model.
- ACON's 4,096/1,024-token triggers are a useful calibration point for 8k–32k-window models.

### Gaps
- The OpenHands condenser's model, subset size and default parameters were not verified.
- The parameters of Anthropic's server-side `compact_20260112` were not fetched.
- The Claude Code auto-compact trigger percentage was not verified.

---

## Q3. Shaping tool output: truncation, head/tail, pagination, search over dump, offloading to files

### Takeaway
The cheapest large win is to **never let a big output in**:

- cap it;
- keep head and tail;
- write the full text to a file and return a handle;
- expose `grep` or `read_range` tools for just-in-time retrieval.

Manus, Anthropic and *(older)* SWE-agent all converged on this. There are few controlled numbers, except the *(older)* SWE-agent interface ablations and ACON's finding that observation compression is the riskier half.

### Cited Findings
- [V] Manus offloads full tool results to the sandbox file system and lets the agent search them with `glob`/`grep`, not a vector index. It uses fewer than 20 atomic tools, pushes most actions into the sandbox shell, and exposes MCP tools through a CLI. — [Lance Martin on Manus](https://rlancemartin.github.io/2025/10/15/manus/)
- [P] Manus: "file system as context". Drop the content but keep a restorable pointer (URL or path), so compression stays reversible. — [Manus blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [P] Anthropic: just-in-time retrieval. Keep lightweight identifiers (paths, queries, links) and load data at runtime through tools, instead of pre-loading. — [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [V] ACON: observation compression was consistently somewhat worse than history compression (gpt-4.1 AppWorld: 53.6 versus 56.5). A generic token-dropping compressor (LLMLingua) collapsed to 32.1. Compressing *inside* an observation loses details the agent needs. — [arXiv 2510.00615](https://arxiv.org/html/2510.00615v3)
- [S] *(older, 2024)* SWE-agent's agent-computer interface (ACI) ablations:
  - a windowed file viewer (100 lines) and concise search summaries beat full-file cat and verbose grep;
  - an edit linter guard added several points.
  - [arXiv 2405.15793](https://arxiv.org/abs/2405.15793)
- [U] LineRetriever (planning-aware, embedding-based retrieval of observation lines) and "Signal-Driven Observation for Long-Horizon Web Agents" (arXiv 2606.06708) were seen only as search snippets.

### Inferences
- The v1 "tool-output length cap" should become a **standard envelope**, roughly 30 lines of stdlib:
  - If `len(out) > cap`, return the head (e.g., 60%) and tail (e.g., 20%) of the capped budget.
  - Add a line `[... 12,345 chars / 410 lines omitted; full output: obs/007.txt; use grep_obs(7, pattern) or read_obs(7, start, n)]`.
  - Always write the full text to disk first.
  - Tail matters for logs, stack traces and test results; head matters for files and listings.
  - Make the cap per tool and set it in tokens derived from `context_tokens`, e.g., `min(4k, 0.1 × window)`.
- Prefer **search tools over dump tools**: `grep(path, pattern, max_hits)`, `read_range(path, start, n)` and `list(dir, max)` with explicit limits. Return structured, count-first summaries ("37 matches in 5 files; first 10 shown"). For tabular data, return the row count, schema and the first rows.
- **Structured extraction** (a model call to extract fields from a large output) is a model-dependent step. Do it deterministically where formats are known (JSON path, CSV columns) and keep the raw file as the source of truth.

### Gaps
- No 2025–26 controlled ablation found of head/tail versus head-only truncation, or of cap sizes, for small models.

---

## Q4. Recitation, todo blocks, pinned instructions, and position effects

### Takeaway
Put the critical, changing state at the **end** of the context, in a harness-rendered block: goal, plan or todo with checkmarks, key facts, remaining budget. Keep stable instructions at the **start**. This uses the U-shaped position effect and keeps the prefix cacheable. The evidence is mostly practitioner reports plus the *(older)* "lost in the middle" result. Chroma's 2025 work confirms that degradation sets in well below the window.

### Cited Findings
- [P] Manus "recitation": the agent rewrites `todo.md` at the end of the context to keep the goal in recent attention over about 50-tool-call tasks. No controlled numbers. — [Manus blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [S] *(older, 2023)* "Lost in the Middle": accuracy is U-shaped over the position of relevant information; best at the start and end. — [arXiv 2307.03172](https://arxiv.org/abs/2307.03172)
- [P] Chroma "Context Rot" (Jul 2025, 18 models): degradation grows with input length even on trivial tasks. Qwen3-8B broke down at about 5,000 words in repeated-word tasks. Focused prompts of about 300 tokens beat full prompts of about 113k on LongMemEval. — [Chroma](https://www.trychroma.com/research/context-rot)
- [P] Laban et al. (May 2025): an average 39% drop when instructions are spread across turns. Restating the full spec helps. — [arXiv 2505.06120](https://arxiv.org/abs/2505.06120)
- [V] On AppWorld with Qwen3-8B, the paper's summarizer preserves auth tokens, endpoint names, schemas, error patterns, pagination state and completion status *verbatim*. After scaffolding, the "context length" failure class disappeared. — [arXiv 2604.11465 v2](https://arxiv.org/html/2604.11465v2)

### Inferences
- **Layout**, assembled every call by the single context function:
  1. A stable system prompt, the tool schemas and the task statement, pinned and never edited.
  2. The append-only history, with placeholders for masked results.
  3. A final harness-rendered `<state>` block, rendered from harness data and not model-written. It contains:
     - the goal restated in one line;
     - the plan steps with status;
     - a facts table (key, value, step);
     - the last error;
     - steps and tokens left.
- The state block is regenerated each turn. Put it in the **last user/tool message**, not in the system prompt, so the prefix cache survives (Q5).
- For small models, restating the goal and constraints in the tail block addresses both Laban's multi-turn drift and lost-in-the-middle. It costs a few hundred tokens per call.

### Gaps
- No 2025–26 controlled study found that quantifies recitation or todo-block gains for agents, at any model size.
- No position-effect measurements found for GLM-5.3-Flash or for 4B–32B models.

---

## Q5. Prefix-cache-friendly layout and its interaction with masking

### Takeaway
A stable prefix with append-only history maximises KV and prefix-cache reuse. This matters for latency on local serving too, through automatic prefix caching in vLLM and SGLang. Each mask, edit or summary invalidates the cache from the edit point onward. So:

- batch masking into rare, large edits;
- never mutate the system prompt;
- put changing state at the tail.

### Cited Findings
- [P] Manus: the KV-cache hit rate is the key production metric. The input:output token ratio is about 100:1, and cached input is about 10x cheaper. Keep the prefix stable, the context append-only and the serialization deterministic; a timestamp in the system prompt kills the cache. — [Manus blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [V] Anthropic: clearing invalidates the cache, so use `clear_at_least` to make each invalidation worth it. Each clear means one cache write; afterwards the new prefix is reused. — [Claude docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [V] ICLR: removing reasoning blocks reduced cache-read tokens by 33.3%. Removal changes what is cached, not only how much. — [arXiv 2609.29875](https://arxiv.org/abs/2609.29875)
- [V] Self-GC enforces "cache-aware commits" and "safe commit boundaries" for its edits. — [arXiv 2607.00692](https://arxiv.org/abs/2607.00692)
- [S] vLLM and SGLang implement automatic prefix caching (block-hash and radix-tree), so local serving gains from identical prefixes. This is from general knowledge of their docs; I did not fetch them this session.

### Inferences
- **Hysteresis masking:** mask at most once every K turns, or when the estimate crosses a high watermark, and clear down to a low watermark. Masking every turn in a sliding window shifts the edit point each turn and gives near-zero cache reuse.
- Serialize tool results deterministically (sorted JSON keys, no timestamps in the prefix). This also keeps the placeholder for a given step identical across turns.
- If the local server lacks prefix caching, or the model is small and fast, cache considerations matter less than the window budget.

### Gaps
- No measurement found of masking × prefix-cache trade-offs on local inference servers.

---

## Q6. Small-model-specific studies, 2025–2026

### Takeaway
The few small-model studies agree on three points:

- small agents are hurt *more* by distracting long context;
- compression that is **task-aware** and preserves identifiers verbatim helps them substantially;
- absolute scores stay low, and the cleanest results come from deterministic preservation rules plus history-free correction.

### Cited Findings
- [V] "Three Roles, One Model" (McClendon et al., 13 Apr 2026; v2 15 Apr). — [arXiv 2604.11465](https://arxiv.org/abs/2604.11465), [HTML v2](https://arxiv.org/html/2604.11465v2)
  - **Setup.** Qwen3-8B on one 24 GB GPU; AppWorld test_normal, 168 tasks, pass@1.
  - **Task goal completion.** FP16: 5.4 → 8.9%. AWQ 4-bit: 3.0 → 5.9%. Difficulty-1 tasks: FP16 15.8 → 26.3%, AWQ 5.3 → 14.0%. For comparison, DeepSeek-Coder-33B scored 7.1%.
  - **Context.** Window 12k tokens for FP16 (truncated) and 32,768 for AWQ.
  - **Summarizer rules.** It triggers when history exceeds 24,000 chars or 6,000 tokens. It keeps the first 26 and last 6 messages verbatim. It preserves auth tokens, credentials, endpoint names, schemas, errors, pagination state and completion status verbatim.
  - **Ablation (AWQ):**

    | Configuration | Aggregate | Difficulty 1 | Difficulty 2 | Difficulty 3 |
    |---|---|---|---|---|
    | Baseline | 3.0 | 5.3 | 2.1 | 1.6 |
    | Corrector only | 4.8 | 12.3 | 2.1 | 0.0 |
    | Full scaffold | 5.9 | 14.0 | 4.2 | 0.0 |

    No summarizer-only run was reported. So the summarizer's own contribution is at most about +1.1 pp aggregate, and is not isolated.
  - **Failure classes (baseline).** Auth/credentials 28.2%, reasoning/planning 26.4%, schema mismatch 17.8%, context-length only 1 case.
  - **Internal inconsistencies.** 5.4% of 168 implies about 9 successes, yet the paper reports 163 failures; there is train/test split ambiguity; and one table is mislabeled. Treat the magnitudes as approximate.
  - Scenario goal completion was not reported (near zero).
- [V] ACON with a Qwen3-14B agent: AppWorld 25.6 → 33.9 (+32% relative); 8-objective QA EM 0.158 → 0.23 (+46%). The authors also report +20% on OfficeBench in the introduction; I did not see that number in the tables I read. — [arXiv 2510.00615](https://arxiv.org/html/2510.00615v3)
  - Without compression, Qwen3-14B often failed medium and hard tasks because of distracting context.
  - Compressors distilled to 8B–14B keep more than 95% of the teacher's performance.
  - Caveat: the guidelines were optimized with o3/gpt-4.1. An air-gapped team can't easily replicate that optimization, but they *could* adopt the published guideline style.
- [P] JetBrains: Qwen3-32B masking 15.0 versus summarization 16.0 versus raw 17.0. At 32B, neither helped accuracy; only cost went down. — [arXiv 2508.21433](https://arxiv.org/html/2508.21433v3)
- [P] Chroma: Qwen3-8B degraded at about 5k words even on trivial repetition. — [Chroma](https://www.trychroma.com/research/context-rot)
- [U] Other 2026 papers seen only in search: Scroll (arXiv 2608.21690, "context as an environment"), ACM (arXiv 2607.23809) and Context Language Models (arXiv 2609.37725). Their contents were not verified.

### Inferences
- **Preservation lists are the transferable part.** The categories that small agents lose (credentials, IDs, schemas, pagination cursors, completion status) can be captured *deterministically* by the harness: regex and JSON-key extraction into the pinned facts block. This needs no small-model summarizer, which fits the team's principle.
- **A history-free corrector** (a second call that sees only the task, the last action and the error) had the larger measured effect in the AppWorld ablation, and it is cheap to implement. It overlaps with the verification and recovery topic of the earlier note.

### Gaps
- No GLM-family results.
- No ≤4B agent context-management results.
- No summarizer-only ablation in the AppWorld paper.

---

## Q7. Token budgeting without a tokenizer (Korean vs English)

### Takeaway
No reliable 2025–26 per-character constants exist for current tokenizers on Korean. Rates vary roughly 2–3x by tokenizer. So:

- start with a conservative heuristic;
- **calibrate online** from `usage.prompt_tokens`, which the server already returns and which v1 already logs;
- keep a safety margin.

### Cited Findings
- [S] Korea University (ICICPE 2024) *(older)*: among four LLMs including GPT-4, Korean needed up to about 3x more tokens than English for equivalent text. — [paper PDF](https://hiai.korea.ac.kr/wp-content/uploads/2024/12/Korean-Penalty-of-Large-Language-Models-Derived-by-the-Tokenizer_ICICPE_2024.pdf)
- [S] *(older, 2024)* Korean-specific tokenizers or vocabulary expansion roughly halve token counts (EEVE: 1.6B versus 5.6B tokens for Phi-2 on the same data). HyperCLOVA X's tokenizer was most efficient on Korean. — [arXiv 2402.14714](https://arxiv.org/pdf/2402.14714); [arXiv 2404.01954](https://arxiv.org/pdf/2404.01954)
- [U] OpenAI forum anecdote: the GPT-3.5/4 tokenizer uses about 1 token per Hangul syllable, while others claimed 3–5x English. — [OpenAI community](https://community.openai.com/t/need-more-efficient-tokenizer-for-korean/286682)
- [S] Thunder-Tok (2025) targets Korean fertility, i.e., tokens per word. — [arXiv 2506.15138](https://arxiv.org/html/2506.15138v1)

### Inferences
- **Initial estimate.** Count characters per script class with stdlib (`unicodedata` or range checks):
  - Hangul syllables (U+AC00–D7A3) at about 1.0 token per char. This is conservative; modern multilingual vocabularies such as Qwen or GLM are likely 0.5–0.8.
  - ASCII and English text at about 0.25–0.3 token per char (≈ 3.5–4 chars per token).
  - Code and JSON at about 0.35–0.4 token per char, since punctuation is dense.
  - Other characters at 1.0.

  Add per-message overhead (about 4–10 tokens) and the tool-schema size measured once.
- **Calibration loop.** After each call, compute `ratio = usage.prompt_tokens / estimate(prompt)`. Keep an exponential moving average per model profile, and persist it to the profile's `chars_per_token_ko` and `_en` fields, or to a single multiplier.
  - A simple two-variable least squares over the logged (hangul_chars, other_chars, prompt_tokens) triples gives per-script rates after about 20 calls. This is pure stdlib arithmetic.
- **Budget.** Usable input = `context_tokens − max_output_tokens − safety` (safety about 10%, or 15% before calibration). Trigger masking at a high watermark of about 70% of usable input.
- These numbers are my heuristics, not sourced constants. Validate them by logging.

### Gaps
- No primary 2025–26 measurement of Korean tokens per char for GLM-5.x or Qwen3 tokenizers. Measure it locally: the team's own `prompt_tokens` logs are the best source.

---

## Q8. Task decomposition, sub-agents with fresh context, and map-reduce

### Takeaway
Fresh-context sub-agents are the strongest way to keep a small window clean on *parallelizable* work, such as per-document extraction or per-file checks. Each worker sees only its slice and returns a short, schema-constrained result. Evidence for large models is strong but costly (Anthropic: +90.2%, about 15x chat tokens). For small models, the evidence is indirect: 2025–26 scaffolds with role splits roughly doubled weak-model scores. Sub-agents are a poor fit for tightly coupled tasks.

### Cited Findings
- [V] Anthropic multi-agent research system (13 Jun 2025): an Opus 4 lead with Sonnet 4 sub-agents beat a single Opus 4 by 90.2% on an internal research eval. — [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)
  - Token usage alone explained 80% of BrowseComp variance (95% with 3 factors).
  - Agents use about 4x chat tokens, and multi-agent systems about 15x.
  - Not a good fit: tasks where agents must share context or have many interdependencies, most coding, and low-value tasks.
- [V] Manus uses sub-agents mainly for **context isolation**. The planner defines each sub-agent's output schema, enforced by constrained decoding. Simple sub-tasks get only instructions; complex ones share the planner's context. — [Lance Martin on Manus](https://rlancemartin.github.io/2025/10/15/manus/)
- [P] Anthropic: sub-agents may use tens of thousands of tokens internally and should return condensed results of about 1–2k tokens. — [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [P] Small-model role splits: Qwen3-8B with three roles (summarizer, agent, history-free corrector) roughly doubled AppWorld scores. *(older)* α-UMi's split into planner, caller and summarizer beat a single small model. — [arXiv 2604.11465](https://arxiv.org/abs/2604.11465); [arXiv 2401.07324](https://arxiv.org/abs/2401.07324)
- [U] Hardware-design SLM study: 30–140% relative gains from task decomposition (snippet only). — [arXiv 2512.05073](https://arxiv.org/html/2512.05073v1)

### Inferences
- **Harness pattern:** `map_docs(task_template, items, schema)`.
  - The harness, not the model, loops over items.
  - Each worker gets a fresh context with the system prompt, one item and the schema.
  - The harness validates the JSON returned against the schema and retries once on failure.
  - The reduce step runs over the validated rows, deterministically where possible.

  This is the small-window equivalent of sub-agents, with no model-driven delegation. It suits the team's earlier 12-row style tasks, and gets more useful as windows shrink to 8k–32k.
- Delegation chosen by the model ("spawn a sub-agent when needed") depends on planning skill that small models lack. Prefer harness-declared decomposition: a fixed plan template, or a plan produced once and validated.
- **Cost.** About N× calls, but each is short. On local hardware, throughput rather than the token price is the cost.

### Gaps
- No controlled 2025–26 study found of fresh-context workers versus a single long context for ≤14B models on document tasks.

---

## Summary: when each technique starts to matter (synthesis; the thresholds are my inferences from the cited numbers)

| Technique | Implement cost (stdlib) | Starts to matter | Main failure mode |
|---|---|---|---|
| Tool-output cap + head/tail + full text saved to file with a handle (Q3) | Low (~30–60 LOC) | Immediately; any tool can return more than ~10% of the window | The cut hides the needed line → provide `grep_obs` / `read_obs` |
| Token estimate + calibration from `prompt_tokens` (Q7) | Low | Immediately; needed by every budgeted mechanism | Korean underestimate → overflow; keep 10–15% margin |
| Tail `<state>` block (goal, plan status, facts, budget), harness-rendered (Q4) | Low–Med | More than ~10 turns, or multi-step plans | Stale or wrong facts if extraction is buggy; tag the source step |
| Observation masking, keep last N, with recoverable placeholder and hysteresis (Q1, Q5) | Low–Med | Above ~15–20 turns, or the prompt above ~50–70% of the window (8k–32k models: early) | Drops needed IDs → pin facts first; per-model sign flips (JetBrains) |
| Deterministic fact pinning (IDs, paths, tokens) before masking (Q1, Q6) | Med (regexes per tool) | Together with masking on small models | Missed patterns |
| Fresh-context map workers with schema validation (Q8) | Med | Many independent items, or the window below ~32k | Coupled tasks; the reduce step loses cross-item context |
| History-free corrector call (Q6) | Low–Med | Repeated failures or loops | Extra calls; the corrector "fixes" correct work |
| Reasoning-block dropping (Q1) | Low | Thinking models with long traces | Trajectory amplification (ICLR) |
| Schema-based LLM summary as a last resort (Q2) | Med–High | Masking can't get under budget (long tasks on 8k–32k windows) | Paraphrased identifiers, hidden failure signals, longer runs, extra latency (ACON: +20–40% time) |
