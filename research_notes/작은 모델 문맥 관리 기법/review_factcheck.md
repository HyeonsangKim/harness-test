# Fact-check of selection_draft.md (primary sources)

Checked 2026-10-20 against arXiv HTML/abs pages, the NVIDIA/RULER GitHub README, the Anthropic docs and engineering posts, the Chroma report, and the CPython source tree. I did not use the research notes as evidence. They were used only to find URLs. The draft was not edited.

## Summary

| Verdict | Count |
|---|---|
| CONFIRMED | 27 claims, plus 2 feasibility facts (FTS5, trigram) |
| PARTLY | 4 (rows 8, 17, 18, 20) |
| WRONG | 1 (row 5) |
| UNVERIFIABLE (secondary only; checked by own measurement) | 1 (row 16) |

Items 5 and 7 in the list below are caveats on confirmed facts (the backbone model; a trigram design gap). They are not counted as PARTLY.

### WRONG / PARTLY, with corrections

1. **WRONG: "Qwen3-4B effective length 64K of 128K" (from the brief; the draft says "25–50% of nominal").** The RULER leaderboard lists Qwen3-4B\* as **>128K**, with scores 95.1/93.6/91.0/87.8/77.8/66.0. Only Qwen3-8B\* is listed at 64K. Both rows are starred (author-reported), and both are **inconsistent with the 85.6% threshold**: by their own scores, Qwen3-4B should be 32K (77.8 at 64K) and Qwen3-8B should also be 32K (82.1 at 64K). Treat the starred effective lengths as unreliable.
2. **PARTLY: A4 "RULER effective length of small models is 25–50% of nominal".** This holds for Llama-3.1-8B (32K/128K = 25%), Phi3-mini (25%), Qwen3-8B (50%, listed) and Mistral-7B (16K/32K = 50%). It fails for **GLM4-9B: 64K/1M ≈ 6%**, the model most relevant to a ~1M-context GLM. It also fails for Qwen3-4B, which is listed at >128K. Suggested wording: "25–50% for 128K models, and about 6% for GLM4-9B (1M)."
3. **PARTLY: B1 "JetBrains: cost about −50%, solve rate maintained".** The abstract says masking "halves cost relative to the raw agent" and matches summarization's solve rate. Per configuration, the cost drop is −50.9/−9.8/−52.7/−56.1/−57.1% (mean about 45%; Qwen3-32B-thinking is only −9.8%). The solve rate is *not* maintained for Gemini 2.5 Flash (thinking): 40.4 raw → 36.4 masking, a significant drop (p≈0.04). Say "usually"; it does not hold in every configuration.
4. **PARTLY: C3 "learned compressor: Qwen3-14B 25.6→33.9 (training required)".** The numbers are correct (§4.4, a 32.4% relative gain). However, **Qwen3-14B is the agent, not the compressor**. The Fig. 5 caption describes "the Qwen3-14B agent distilled from gpt-4.1 trajectories", and the compressor in that setting is a distilled one. ACON's core guideline optimization is gradient-free and does not change agent weights. Reword to: "With a Qwen3-14B agent, ACON-compressed history raised AppWorld from 25.6 to 33.9 (distilled setting)."
5. **PARTLY: C3/B1 "ACON generic prompt compression, hard tasks 39.7→23.8; FIFO 15.9".** The numbers are correct (Table 1, AppWorld test-normal, Hard = 63 tasks). They come from a **gpt-4.1 agent with a gpt-4.1 compressor**, not a small model, and the draft should say so. The "peak tokens −26–54%" figure is the abstract's range across benchmarks (AppWorld ">25%", 8-objective QA about 54%).
6. **PARTLY: C3 "JetBrains Gemini 2.5 Flash 40.4→31.4".** This is correct, but it is the **thinking** variant, raw → LLM-summary. Non-thinking Gemini 2.5 Flash *improved* with summary, 32.8 → 36.0. Add "(thinking)".
7. **PARTLY: D3 "sqlite3 FTS5 BM25 (trigram tokenizer for Korean)".** FTS5 and trigram are available (see the feasibility section). But my local test showed that **trigram MATCH returns nothing for queries shorter than 3 characters**. The 2-syllable Korean word `비용` got 0 hits, while `마스킹` and `"비용을"` hit. Many Korean content words are 2 syllables, so the design needs a fallback, such as `LIKE '%..%'` or a bigram side table. This is a design gap, not a citation error.
8. **UNVERIFIABLE (primary): A3 "Qwen3-8B Korean ≈1.34 chars/token".** The only source is a blog (youngju.dev, 2026-08-12), measured on a single 199-char paragraph. There is no official Qwen or arXiv figure. **Own measurement** with the official Qwen/Qwen3-8B tokenizer.json (HF `tokenizers`):

   | Text | chars/token incl. spaces | excl. spaces |
   |---|---|---|
   | Pure Korean prose | 1.50 | 1.14 |
   | Hangul-dominant lines of the draft | 1.46 | 1.15 |
   | Whole draft (mixed) | 1.59 | 1.27 |
   | English | 5.10 | 4.21 |

   The draft's 1.3–1.5 initial value is reasonable *if spaces are counted*. English is closer to 4–5 chars/token, so "about 4" is conservative, which is fine. Change the citation to "own measurement" and state whether whitespace is counted.

## Detailed results

| # | Claim (draft location) | Verdict | Primary value | URL |
|---|---|---|---|---|
| 1 | RULER threshold = Llama-2-7B at 4K, 85.6% | CONFIRMED | "Llama-2-7b performance at 4K (85.6%)" used as the threshold. The README does not formally state "effective length = longest length above it", but the non-starred rows follow it. | https://github.com/NVIDIA/RULER |
| 2 | Llama-3.1-8B 128K → 32K | CONFIRMED | 95.5/93.8/91.6/87.4/84.7/77.0 | same |
| 3 | GLM4-9B 1M → 64K | CONFIRMED | 94.7/92.8/92.1/89.9/86.7/83.1 | same |
| 4 | Qwen3-8B 128K → 64K | CONFIRMED as listed (author-reported \*). By the threshold it should be 32K. | 96.3/96.0/91.8/91.2/82.1/77.4 | same |
| 5 | Qwen3-4B 128K → 64K | **WRONG** | Listed as >128K (\*), scores 95.1/93.6/91.0/87.8/77.8/66.0 | same |
| 6 | Phi3-mini 128K → 32K | CONFIRMED | 92.2/91.5/90.7/87.5/80.6/66.7 | same |
| 7 | Mistral-7B 32K → 16K | CONFIRMED | 93.6/91.2/87.2/75.4/49.0/13.8 | same |
| 8 | "25–50% of nominal" (A4) | PARTLY | GLM4-9B ≈6%; Qwen3-4B listed >100% | same |
| 9 | NoLiMa: Llama-3.1-8B effective ≈1K | CONFIRMED | 1K (base 76.7, threshold 65.2) | https://arxiv.org/html/2502.05167 |
| 10 | NoLiMa: GPT-4o 8K | CONFIRMED | 8K (base 99.3) | same |
| 11 | NoLiMa: 11 of 13 models ≤ half base at 32K | CONFIRMED | "Out of the 13 models, 11 exhibit performance at 32K lengths that is half or less of their base scores." Threshold = 85% of base (250/500/1K). | same |
| 12 | Chroma Context Rot, Jul 2025, 18 models; LongMemEval focused (~300 tok) ≫ full (~113k) | CONFIRMED | 14 Jul 2025; 18 LLMs; "significantly higher performance on focused prompts". Qwen3-8B random outputs from ~5,000 words. | https://www.trychroma.com/research/context-rot |
| 13 | HELMET: NIAH doesn't predict downstream (C1) | CONFIRMED | "synthetic tasks like NIAH do not reliably predict downstream performance"; RAG tasks recommended as the proxy | https://arxiv.org/abs/2410.02694 |
| 14 | LongFuncEval: 7–85% (tools), 7–91% (response length), 13–40% (turns) (A2, C2) | CONFIRMED | Exact abstract wording | https://arxiv.org/abs/2505.10570 |
| 15 | Tool-DC: <10 → 20 tools hurts small models most (C2) | CONFIRMED | "all LLMs suffer from performance degradation, especially for the smaller models". E.g. All_Funs Qwen2.5-1.5B 55.2→29.5, 3B 59.0→45.0, 7B 68.4→63.9 (Standard→Extended, 20 functions). | https://arxiv.org/html/2603.11495v1 |
| 16 | Qwen3-8B Korean 1.34 chars/token (A3) | UNVERIFIABLE (secondary) | Blog only. Own measurement: 1.46–1.50 incl. spaces | blog: https://www.youngju.dev/blog/ai-papers/2026-08-12-model-internals-tokenizer-internals.en ; tokenizer: https://huggingface.co/Qwen/Qwen3-8B |
| 17 | JetBrains 2508.21433: ~50% cost, solve rate kept (B1) | PARTLY | See WRONG/PARTLY #3 | https://arxiv.org/html/2508.21433v3 |
| 18 | JetBrains Gemini 2.5 Flash 40.4→31.4 (C3) | PARTLY (needs "thinking") | Thinking variant: raw 40.4, masking 36.4, summary 31.4 | same |
| 19 | Anthropic context editing: trigger 100k, keep 3, cache invalidated on clear (A1, B1) | CONFIRMED | `clear_tool_uses_20250919` defaults: 100,000 input tokens, keep 3 tool uses; "Invalidates cached prompt prefixes when content is cleared"; `clear_at_least` exists for this. Beta `context-management-2025-06-27`. | https://platform.claude.com/docs/en/build-with-claude/context-editing |
| 20 | ACON Qwen3-14B 25.6→33.9 (C3) | PARTLY | Numbers correct; Qwen3-14B is the agent, and the compressor is distilled | https://arxiv.org/html/2510.00615v3 |
| 21 | ACON prompting baseline hard 39.7→23.8; FIFO 15.9 (B1, C3) | CONFIRMED (numbers); caveat gpt-4.1 | Table 1, Hard split, gpt-4.1 agent and compressor | same |
| 22 | ACON peak tokens −26–54% | CONFIRMED | Abstract "26–54%" | same |
| 23 | Anthropic multi-agent +90.2%, ~15× tokens, poor fit for shared context (B2) | CONFIRMED | Opus 4 lead + Sonnet 4 subagents vs single Opus 4; agents ~4×, multi-agent ~15× chat tokens; domains that "require all agents to share the same context" are not a good fit | https://www.anthropic.com/engineering/multi-agent-research-system |
| 24 | ACE context collapse 18,282→122 tokens, 66.7→57.1, baseline 63.7 (B3) | CONFIRMED | §2.2, AppWorld, step 60; attributed to Dynamic Cheatsheet's monolithic rewriting | https://arxiv.org/html/2510.04618 |
| 25 | AMD 2608.07169: Qwen3-4B AppWorld 14.88→16.07 (self), →49.40 (teacher) (D1) | CONFIRMED | Tables 1–2 (Kim, Kim, Hwang; KAIST/DeepAuto) | https://arxiv.org/html/2608.07169 |
| 26 | AMD: ReasoningBank transplant →10.71 | CONFIRMED | Table 1 | same |
| 27 | AMD function memory: indexed by function name, injected on tool error (D2) | CONFIRMED, with nuance | Retrieved reactively on tool error and added to the error message. When several records exist for a function, they are **ranked by embedding cosine similarity** (text-embedding-3-small) to the task. Lookup by name alone is the draft's own simplification, so "임베딩 불필요" (no embedding needed) is a design choice, not the paper's method. | same |
| 28 | Dynamic Cheatsheet gains tied to scale; GPT-4o-mini GPQA 34.3→33.8/32.3, AIME 16.7→13.3 (D1) | CONFIRMED | "strongly tied to the model's scale and underlying generative capacity"; Haiku AIME 10.0→36.7 (Cu)/30.0 (RS) | https://arxiv.org/html/2504.07952 |
| 29 | 2505.16067: add-all worst; strict add + deletion best; EHRAgent 16.75→38.50→42.06 (D3) | CONFIRMED | Add-all lowest for all 4 agents (EHRAgent 13.05). 42.06 is from Table 2. (Side note: the notes give coarse-filter EHRAgent as 34.66; the paper says 26.19 in Table 1 and 25.91 in Table 2. The draft does not use this number.) | https://arxiv.org/html/2505.16067 |
| 30 | MINJA injection 98.2%, attack 76.8% (D3) | CONFIRMED | Stated in the Introduction contributions, not the abstract | https://arxiv.org/html/2503.03704 |
| 31 | SkillsBench 33.9→50.5%, focused ≤3 modules best (D4) | CONFIRMED | "Curated Skills raise the average pass rate from 33.9% to 50.5%"; "Focused Skills with at most three modules outperform larger or exhaustive bundles" | https://arxiv.org/abs/2602.12670 |
| 32 | 2609.29875 exists; drops old reasoning blocks (E) | CONFIRMED | "When Can Agents Forget Their Reasoning? ICLR for Long-Horizon Agent Context Compression" (Wang et al., 24 Sep 2026). Keeps actions, tool calls and observations and drops ranked reasoning. On 260 WorkBuddyBench tasks: reward 0.699→0.718, input −25.5%, output −14.4%, cache-read −33.3%. | https://arxiv.org/abs/2609.29875 |
| 33 | Anthropic long-running: JSON less likely overwritten than Markdown (A5) | CONFIRMED (qualitative) | "the model is less likely to inappropriately change or overwrite JSON files compared to Markdown files" | https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents |

## Feasibility: SQLite in CPython 3.12 on Windows (python.org builds)

- **FTS5: CONFIRMED.** `PCbuild/sqlite3.vcxproj` defines `SQLITE_ENABLE_FTS4;SQLITE_ENABLE_FTS5;SQLITE_ENABLE_RTREE;SQLITE_ENABLE_MATH_FUNCTIONS` at tags v3.12.0, v3.12.4, v3.12.8 and v3.12.10.
- **Bundled SQLite version** (from `PCbuild/get_externals.bat`):

  | CPython tag | Bundled SQLite |
  |---|---|
  | v3.12.0 | 3.42.0 |
  | v3.12.4, v3.12.8 | 3.45.3 |
  | v3.12.10 (last 3.12 release with Windows installers; later 3.12.x are source-only security releases) | 3.49.1 |
  | 3.12 branch head | 3.49.1 |

  Sources: https://github.com/python/cpython/blob/v3.12.0/PCbuild/get_externals.bat and https://github.com/python/cpython/blob/3.12/PCbuild/sqlite3.vcxproj
- **Trigram tokenizer: CONFIRMED available.** It was added in SQLite 3.34.0, and every 3.12 Windows build ships ≥3.42. **Caveat** (local test, SQLite 3.50.4): MATCH with fewer than 3 characters returns no rows. `LIKE '%비용%'` worked, and SQLite can use the trigram index for LIKE/GLOB patterns of 3 or more characters. `bm25()` works on trigram tables.
