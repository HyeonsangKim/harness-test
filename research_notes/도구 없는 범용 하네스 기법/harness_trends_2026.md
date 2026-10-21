# Harness / Context Engineering for General-Purpose Agents — 2026 Trend Analysis (verified vs. hype)

Research date: 2026-10-21. All numbers below were read in the cited page unless marked **[unverified]** or **[secondary]**. "Vendor" = the party reporting the number also sells the harness or model.

## Q1. Which task-agnostic harness components are converging as standard?

### Takeaway
Across the major harnesses, the shared core is now: (a) a project instruction file (AGENTS.md / CLAUDE.md) loaded at startup, (b) a todo/plan tool, (c) file-system tools used as external memory/context offload, (d) sub-agents with isolated context that return only a summary, (e) automatic context compaction/condensation, (f) lifecycle hooks/middleware around model and tool calls, and (g) loop/stall detection plus a forced pre-completion verification step. Verification-before-exit and loop guards are the newest additions to the "standard" list and are where measured gains are claimed.

### Cited Findings
- **Codex CLI**: reads AGENTS.md before doing any work; discovery is layered — global `AGENTS.override.md` or `AGENTS.md`, then project files from repo root down to the working directory — [OpenAI Codex docs: Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md). A 32 KiB default cap (`project_doc_max_bytes`) is reported only by a secondary guide **[secondary]** — [Duke Codex best practices](https://codex-best-practices-d67bea.pages.oit.duke.edu/best-practices/agents.html).
- **Claude Code**: sub-agents run in their own context window, support their own automatic compaction (per-subagent `autoCompactWindow` frontmatter), and only the final message (summary + metadata) returns to the main session; hook events include `PreCompact`/`PostCompact` (PreCompact can block compaction with exit code 2) — [Claude Code docs: sub-agents](https://code.claude.com/docs/en/sub-agents); [Claude Code docs: hooks](https://code.claude.com/docs/en/hooks). Anthropic's own guidance article on when to use CLAUDE.md vs skills vs hooks vs subagents — [claude.com steering article](https://claude.com/resources/articles/steering-claude-code-skills-hooks-rules-subagents-and-more). The exact auto-compaction threshold (blogs say low-to-mid 80% of window) is **[unverified]** in official docs.
- **OpenHands SDK**: "condenser" component; LLM-summarizing condenser keeps the first few events (system prompt) and the most recent events, replaces the middle with an LLM summary once event count exceeds `max_size`; triggered automatically by threshold or manually by a condensation request — [OpenHands docs: Context Condenser](https://docs.openhands.dev/sdk/guides/context-condenser); [OpenHands docs: Condenser architecture](https://docs.openhands.dev/sdk/arch/condenser). OpenHands also has a "stuck detector" that terminates runs (see Q2, arXiv 2610.00917).
- **LangChain Deep Agents**: the pattern is planning tool (`write_todos`), virtual file system (ls/read_file/write_file/edit_file/glob/grep, pluggable backend) for context offload, a built-in `task` tool spawning ephemeral isolated sub-agents, and long-term memory — [deepagentsjs GitHub](https://github.com/langchain-ai/deepagentsjs) (secondary summaries: [eastondev](https://eastondev.com/blog/en/posts/ai/deepagents-architecture/)).
- **Deep Agents harness-engineering additions (Feb 17 2026)**: `PreCompletionChecklistMiddleware` (intercepts the agent before exit and forces a verification pass against the spec), `LocalContextMiddleware` (maps working dir/parents/children and locates tools like Python at start), `LoopDetectionMiddleware` (counts per-file edits via tool-call hooks; after N edits injects "reconsider your approach"), time-budget warnings, build→verify system prompt, "reasoning sandwich" — [LangChain blog, Vivek Trivedy](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering).
- **Kimchi (vendor harness, Sep 7 2026)** credits: runtime sanitation of message stream (removing phantom tool calls / dangling tool results), behavioral guardrails for exploration/bash/review-write phase, a loop guard detecting repeated edit-run-fail cycles and ending the turn, a process-wide circuit breaker when the provider is degraded, early compaction + pruning, and a fix for "unbound thinking" with GLM-5.2 — [Kimchi blog](https://kimchi.dev/blog/same-model-different-harness-terminal-bench).
- Harness taxonomy used in 2026 commentary: loop, tools, context, policy, persistence; outer harness split into **guides** (instructions, skills), **sensors** (tests, linters), **caps** (permissions/infra the model cannot override); inner/outer split attributed to Birgitta Böckeler — [Sukhareva, AI Realist, Aug 4 2026](https://msukhareva.substack.com/p/how-a-small-open-model-beat-a-frontier) (opinion piece).
- A formal disclosure taxonomy of harness layers (ETCSOVG: Execution, Tool, Context, Scheduling, Observability, Verification, Governance) — [arXiv 2605.23950](https://arxiv.org/html/2605.23950v1).

### Inferences
- The convergent set is model-agnostic and mostly deterministic code (file loading, counters, truncation, hooks) — exactly what a stdlib-only harness can implement. The parts that need an extra LLM call (LLM summarization, sub-agents) are the parts with the weakest measured evidence for small models.
- "Convention style" files are universal in product design but not supported by evidence of correctness gains (see Q2) — their adoption is driven by product ergonomics, not benchmarks.

### Gaps
- Did not fetch official Cursor, OpenCode, Kimi Code or Z.ai coding-agent docs; component claims for those are not verified here.
- No official doc found for OpenHands' observation-masking condenser parameters.

## Q2. Measured evidence of harness effects with the model held fixed

### Takeaway
Same-model harness swings of 5–15 pp on Terminal-Bench / SWE-bench are now well documented, including in independent academic work. But almost every single number comes from 1 run (or undisclosed run counts), and most component-level gains are not ablated individually. The best-controlled evidence is for (1) cheap observation masking matching LLM summarization at ~half the cost, (2) AGENTS.md files NOT improving correctness while raising cost ~20%, and (3) truncating old tool output + stall handling helping a lot under tight context windows.

### Cited Findings
**LangChain Deep Agents (vendor, Feb 17 2026)**
- deepagents-cli on Terminal-Bench 2.0 (89 tasks, Harbor + Daytona), model fixed at gpt-5.2-codex: **52.8% → 66.5%** (+13.7), "Top 30 → Top 5" — [LangChain blog](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering).
- Only the reasoning-budget split has comparative numbers: all-xhigh 53.9% (timeouts), all-high 63.6%, xhigh-high-xhigh sandwich 66.5%. Author: "There weren't large differences in trial runs across reasoning budget splits." No per-component ablations, no trial counts, no CIs. Claude Opus 4.6 got 59.6% on an earlier harness version (not re-tuned). Author warns trace-driven changes can overfit and expects loop detection to become unnecessary as models improve — [same](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering).

**Kimchi — GLM-5.2 across 4 harnesses (vendor, Sep 7 2026)**
- Terminal-Bench 2.1, 89 tasks, 5 runs per task, averaged: **Kimchi 72.6%, Cursor 69.0%, Claude Code 65.4%, OpenCode 59.8%** (13.0 pp spread). No variance/SD reported; harness versions not disclosed; OpenCode numbers came from different runs/time periods so author calls them "directional". Post says inference was via Moonshot's API (odd for a Zhipu model — as reported). Published on Kimchi's own blog promoting Kimchi — [Kimchi blog](https://kimchi.dev/blog/same-model-different-harness-terminal-bench).
- A separate Kimchi post reportedly shows Kimchi 69.4% vs a DeepSeek harness 47.1% on the same model **[secondary, not fetched]** — [Kimchi blog index](https://kimchi.dev/blog).
- Z.ai's own reported GLM-5.2 Terminal-Bench 2.1 number (81.0) is far above Kimchi's best 72.6 **[secondary]** — [morphllm](https://www.morphllm.com/glm-5-2); setups unexplained.

**"Same Model, Different Harness" (arXiv 2608.26218, Sydney Lewis, Aug 26 2026)**
- Control = full conversation in order; treatment = same record but older tool results mechanically shortened as context fills + reacting to repeated or stalled work; treatment frozen (no per-model retuning). Tight window (20,480 tokens, 480 s per attempt), SWE-bench Verified 169-task cohort: mean per-task fail-to-pass fraction **28% → 49%**, complete solutions **43 → 72**. Frozen treatment also helped three other models. With a wide window (Qwen3.6), arms were close on Verified and Pro; FeatureBench still favored treatment; treatment used fewer prompt tokens per turn. Abstract does not mention repeated runs/CIs — [arXiv 2608.26218](https://arxiv.org/abs/2608.26218).

**"The Complexity Trap" (JetBrains, arXiv 2508.21433, Aug–Oct 2025)**
- SWE-agent, SWE-bench Verified (n=500), ± values reported. Observation masking (keep last M=10 turns' observations, mask older) vs LLM summary (summarize N=21 turns, keep last 10) vs raw:
  - Qwen3-32B: raw 17.0±3.3 / mask 15.0 / summary 16.0; cost $1.12 → $0.55 / $0.50.
  - Qwen3-32B thinking: 23.0 / 24.6 / 24.8; cost 0.51 / 0.46 / 0.51.
  - Qwen3-Coder 480B: 53.4 / 54.8 / 53.8; cost 1.29 / 0.61 / 0.64.
  - Gemini 2.5 Flash: 32.8 / 35.6 / 36.0; cost 0.41 / 0.18 / 0.24.
  - Gemini 2.5 Flash thinking: 40.4 / 36.4 / 31.4 (summary −22% relative).
- Hybrid (masking + occasional summary) tested only on Qwen3-Coder 480B on a 50-task subset: −7% cost vs masking, −11% vs summary. In OpenHands, M=10 degraded sharply; M had to be retuned (M=58) to match — i.e. the window is scaffold-specific. Qwen3-32B solve-rate changes "not statistically significant" — [arXiv 2508.21433 HTML](https://arxiv.org/html/2508.21433v3).

**AGENTS.md / context-file studies**
- Gloaguen et al. (ETH/LogicStar), arXiv 2602.11988 (v1 Feb 12 2026, v3 Sep 29 2026; ICLR 2026): Claude Code+Sonnet-4.5, Codex+GPT-5.2 / GPT-5.1 mini, Qwen Code+Qwen3-30B-coder (local vLLM). SWE-bench Lite (300, LLM-generated files) and CTXbench (138 issues, 12 repos with developer-committed files). Resolution None/LLM/Dev on CTXbench: Sonnet-4.5 73.2/65.2/70.3; GPT-5.2 65.2/68.1/68.1; GPT-5.1 mini 54.3/50.7/55.8; **Qwen3-30B 45.7/47.1/53.6**. SWE-bench Lite None/LLM: Qwen3-30B 31.1/32.4. CMH tests: None vs LLM p=0.87 (SWE) and 0.37 (CTX); None vs Dev p=0.21; only LLM vs Dev p=0.038. Steps and cost rose significantly (~20–23% with LLM files, up to 19% with dev files). Recommendation: omit LLM-generated files; human files only for non-standard conventions not in README; repository overviews don't help — [arXiv 2602.11988 HTML](https://arxiv.org/html/2602.11988v3).
- Khatri, arXiv 2607.27250 (Jul 28 2026): Claude Code and Codex, 17 tasks / 3 repos, 288 runs; no-context vs always-on full file vs on-demand wiki: "context strategy does not measurably move correctness on either agent"; equivalence bound ~10–15 pp; real AGENTS.md never turned a near-miss into a pass; failures are implementation skill, not missing repo knowledge — [arXiv 2607.27250](https://arxiv.org/abs/2607.27250).

**Same model, multiple harnesses (compiled evidence)**
- Table in arXiv 2605.23950: Claude Opus 4.5 SWE-bench Pro SEAL → Claude Code 45.9 → 55.4; Grok 4 SWE-bench Verified SWE-agent → xAI scaffold 58.6 → 72–75; GPT-5.4 (high) Terminal-Bench 2 via automated harness evolution (AHE) 69.7 → 77.0; HAL: Claude Sonnet 4.5 on SWE-bench Verified Mini ranges 68% → 34% across scaffolds; Epoch AI: scaffold-only variation up to 11 pp (GPT-5) and 15 pp (Kimi K2 Thinking); Vercel 15 tools → 2 tools 80% → 100% — [arXiv 2605.23950 HTML](https://arxiv.org/html/2605.23950v1) (these are the paper's citations of others; underlying sources not re-checked).
- Same paper's own factorial: 3 models (GPT-5.4, Kimi K2.6, GLM-5.1) × 3 harnesses (Minimal/Improved/Full), 100-task SWE-bench Verified subset, 2 runs: GLM-5.1 52.5 → 65.5; GPT-5.4 55.0 → 63.5; Kimi K2.6 52.0 → 60.5; model effect within a harness only 2.5–5.0 pp; harness variance / model variance = **7.80×**; 6/9 ranking reversals. Authors say 7.80× is not universal — [same](https://arxiv.org/html/2605.23950v1).
- NTU, arXiv 2610.00917 (Oct 1 2026): 5 frontier models × OpenHands / DeepSeek Harness / PI / openJiuwen (+ native Codex, Claude Code), 66 configs, TUA-Bench (120), ALE-CLI (99), Terminal-Bench 4 subset (63). Rankings reverse (Claude leads GPT by 7.94 in OpenHands, trails by 30.16 in PI); vendor harness not reliably best (Codex never best for GPT); GPT-6 Astra 60.32% under PI at $4.66/task vs 52.38% under DSH at $19.94/task. Much variation explained by how harnesses return failures: OpenHands' stuck detector killed recoverable Kimi runs; PI's shell had no default timeout. **Single run per task; run-to-run variance not measured** — [arXiv 2610.00917](https://arxiv.org/html/2610.00917v1).
- GPT-5.5 on Terminal-Bench 2.1: 83.1 (Codex) vs 78.0 (Terminus 2), both xhigh; Opus 4.7: 68.9 (Claude Code) vs 66.1 (Terminus 2) **[secondary — from Sukhareva citing the leaderboard]** — [AI Realist](https://msukhareva.substack.com/p/how-a-small-open-model-beat-a-frontier).
- OpenSWE-32B: 59.8 under OpenHands vs 62.4 under SWE-Agent **[secondary, search snippet]** — [arXiv 2603.13023](https://arxiv.org/pdf/2603.13023).

### Inferences
- The robust, replicated pattern is "deterministic context hygiene" (truncate/mask old tool output, bound commands with timeouts, return errors structurally, detect stalls) — cheap and positive or neutral. LLM summarization is not better than masking and can hurt (Gemini Flash thinking −22% rel.).
- Under small context windows (relevant for local 9B models), the 2608.26218 result suggests the gain from tool-output truncation + stall handling is much larger than under wide windows.
- Loop/stall detection can also hurt: OpenHands' stuck detector terminated recoverable runs (2610.00917). Treat its threshold as a parameter to A/B, not a free win.
- AGENTS.md-style files are a cost item with no measured correctness benefit; the one positive signal (dev-written files, Qwen3-30B 45.7 → 53.6 on CTXbench) is not statistically significant overall.

### Gaps
- No per-component ablation exists for LangChain's middleware stack; Kimchi gives none either.
- 2608.26218: names of the "three additional models" and Pro/FeatureBench sample sizes not in the abstract; full text not read.
- Did not directly read tbench.ai / swebench.com leaderboards to tabulate same-model-multiple-harness rows.

## Q3. Small models (≤35B) + harness, and viral claims

### Takeaway
Headline ≤35B numbers in 2026 (Qwen3.6-27B, Qwen3.6-35B-A3B, Ornith-9B, Devstral-Small-2-24B) are vendor-reported on vendor-chosen harnesses; no independent same-harness reproduction found. Where reproductions exist, they show the score depends heavily on the harness — even a single edit tool can double it. Viral "small model beats frontier" claims compare a small model's best-harness run against a frontier model's standard-harness number.

### Cited Findings
- Qwen3.6-27B (dense): Terminal-Bench 2.0 **59.3** under Harbor/Terminus-2 (vendor) vs Sonnet 4.6 59.1 — [Qwen blog](https://qwen.ai/blog?id=qwen3.6-27b); [AI Realist](https://msukhareva.substack.com/p/how-a-small-open-model-beat-a-frontier).
- Qwen3.6-27B SWE-bench Verified **90.0** in Claude Code CLI by an independent researcher vs Sonnet 4.6's published 79.6 — unofficial, engineered run, not verified by the article author **[unverified]** — [AI Realist](https://msukhareva.substack.com/p/how-a-small-open-model-beat-a-frontier).
- Qwen3.6-27B SWE-bench Pro: model card 53.5; bash-only reproduction ≈28; with a `str_replace` edit tool 50.7 (from a Qwen GitHub issue) — [AI Realist](https://msukhareva.substack.com/p/how-a-small-open-model-beat-a-frontier) **[secondary; GitHub issue not opened]**.
- Qwen3.6-35B-A3B SWE-bench Verified 73.4 **[secondary, Medium]** — [Medium](https://medium.com/data-science-in-your-pocket/qwen3-6-35b-a3b-the-tiny-active-open-model-that-thinks-codes-and-agents-like-a-much-bigger-one-486d535e372e).
- Ornith-1.0-9B: SWE-bench Verified 69.4% (OpenHands, 256K context, specified sampling) and Terminal-Bench 2.1 43.1% vs **Qwen3.5-9B 21.3%** and Qwen3.5-35B 41.4 — all vendor/unsourced; page notes the score reflects model+agent system — [Modal, Jul 2026](https://modal.com/resources/best-small-open-source-code-llms-ai-agents); [modelfit.io](https://modelfit.io/blog/ornith-9b-coding-model-16gb-mac/).
- Devstral-Small-2-24B SWE-bench Verified 68.0% (Mistral's own eval) — [Modal](https://modal.com/resources/best-small-open-source-code-llms-ai-agents).
- Older independent small-model baselines (with ±): Qwen3-32B SWE-agent 17.0±3.3 (non-thinking), 23.0±3.7 (thinking) — [arXiv 2508.21433](https://arxiv.org/html/2508.21433v3); Qwen3-30B-coder in Qwen Code 31.1% SWE-bench Lite — [arXiv 2602.11988](https://arxiv.org/html/2602.11988v3).
- Viral claim #1 "small open model beat a frontier LLM" (Sukhareva, Aug 4 2026) — itself a debunk framing: the gap is harness + effort ("harness-maxxing"); Moonshot's footnote says competitor columns show best score across harnesses; Kimi K3 88.3 on TB 2.1 in Kimi Code at max effort vs 85.0 in Artificial Analysis' own harness; MiniMax-M3 80.5% SWE-bench Verified uses Claude Code scaffold + internal infra, avg of 4 runs — [AI Realist](https://msukhareva.substack.com/p/how-a-small-open-model-beat-a-frontier).
- Viral claim #2 "LangChain jumps 25 spots without changing the model" — true as reported (52.8 → 66.5) but single-vendor, single-model, no CIs — [blockchain.news](https://blockchain.news/news/langchain-terminal-bench-harness-engineering-breakthrough); primary [LangChain](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering).
- Viral claim #3 "Cursor 46% vs 80% same model" and "Salesforce harness evolution 29.2% → 78.0% (arXiv 2609.09134)" — circulated in MindStudio / Medium posts; **not verified** against primary sources — [MindStudio](https://www.mindstudio.ai/blog/better-model-vs-better-harness-agent-benchmark-score).
- Independent locked-harness leaderboard: Vals.ai Terminal-Bench 4.0 runs all models through mini-swe-agent (bash-only) — [Vals.ai](https://www.vals.ai/benchmarks/terminal-bench-4).

### Inferences
- For Qwen3.5-9B, the realistic independent reference point is low (TB 2.1 ≈21% as cited, source unclear); "small + harness ≈ frontier" is not established for 9B-class models on any benchmark by independent reproduction.
- The Qwen3.6-27B bash-only ≈28 → str_replace 50.7 anecdote suggests the single largest lever for small models is the edit/action interface, not elaborate orchestration. Worth pre-registering as a test.

### Gaps
- Found no 2026 BFCL or τ²-bench results that compare harness variants for ≤35B models.
- Could not locate Qwen3.5-9B's primary benchmark source; GLM-5.3-Flash harness-effect data not found.
- LinkedIn/Threads posts not searchable with available tools; the X/Substack claims above are the best proxies.

## Q4. Critiques: contamination, harness overfitting, variance reporting

### Takeaway
The field now has an explicit position paper (ICML 2026) arguing harness variance can exceed model variance by ~8× in one grid and proposing a "Harness Card" disclosure standard. Recurring weaknesses in the evidence: single runs, undisclosed harness versions, vendor-tuned harnesses, trace-driven tuning on the test set, and mismatched effort/budget settings.

### Cited Findings
- "Stop Comparing LLM Agents Without Disclosing the Harness" (Zhang, Wang, Ge, Xu, Hamm, Reddy; arXiv 2605.23950, May 7 2026; ICML 2026): Binding Constraint Thesis; proposes Harness Card (Execution, Tool, Context, Scheduling, Observability, Verification, Governance), variance decomposition reporting (HV per model, MV per harness, HV/MV ratio, ranking-reversal counts, partial η² with ω² or bootstrap interval), and either a locked-harness or factorial protocol; trajectory metrics recovery rate, context retention, control lag — [arXiv 2605.23950 HTML](https://arxiv.org/html/2605.23950v1); [ICML page](https://icml.cc/virtual/2026/67845).
- Harness overfitting: LangChain's author explicitly warns trace-driven changes can overfit to specific tasks — [LangChain](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering). JetBrains' masking window M=10 had to be retuned to M=58 in OpenHands — [arXiv 2508.21433](https://arxiv.org/html/2508.21433v3).
- No variance measured: arXiv 2610.00917 runs each task once and states run-to-run variance was not measured; model settings/budgets not uniformly matched — [arXiv 2610.00917](https://arxiv.org/html/2610.00917v1). Kimchi averages 5 runs but reports no spread — [Kimchi](https://kimchi.dev/blog/same-model-different-harness-terminal-bench).
- Task selection bias: borderline difficulty is agent-specific (Spearman ρ=0.75), offered as an explanation for contradictory prior context-file results — [arXiv 2607.27250](https://arxiv.org/abs/2607.27250).
- Vendor tables mix harnesses/effort; "LLM Y scores X" is incomplete without harness + effort — [AI Realist](https://msukhareva.substack.com/p/how-a-small-open-model-beat-a-frontier).
- Benchmark misalignment / reliability position papers exist (e.g. arXiv 2606.17799 "Coding Benchmarks Are Misaligned with Agentic Software Engineering"; arXiv 2609.08149 "SWE-Bench Pro Verified") — **[titles only, not read]** — [2606.17799](https://arxiv.org/pdf/2606.17799); [2609.08149](https://arxiv.org/pdf/2609.08149).

### Inferences
- The team's pre-registered A/B with fixed model and repeated runs is already stricter than most public evidence; the Harness Card is a ready-made template for documenting each arm.

### Gaps
- Did not read a 2026 primary source specifically quantifying SWE-bench Verified contamination; contamination critique is therefore asserted, not sourced, here.

## Q5. What the team (stdlib-only, task-agnostic, GLM-5.3-Flash + Qwen3.5-9B, pre-registered A/B) should adopt next and how to test

### Takeaway
Prioritize cheap deterministic components with replicated evidence (old-tool-output masking/truncation, command timeouts + structured error return, stall/loop guard, pre-exit verification prompt); treat convention files and LLM summarization as cost items that must prove themselves; test each as a single-factor arm with a frozen config, multiple reps, and report HV/MV-style spreads.

### Cited Findings
- Masking ≈ summary at ~half the cost; window size is scaffold-specific — [arXiv 2508.21433](https://arxiv.org/html/2508.21433v3).
- Truncating older tool results + reacting to repeated/stalled work: 28% → 49% F2PF under a 20K window; small effect under wide windows — [arXiv 2608.26218](https://arxiv.org/abs/2608.26218).
- Pre-completion verification middleware, loop detection (N edits per file), time-budget warnings, local-environment mapping at start — [LangChain](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering).
- Return tool/argument errors as structured feedback; bound commands with timeouts; provide checkable acceptance criteria; stuck detectors can kill recoverable runs — [arXiv 2610.00917](https://arxiv.org/html/2610.00917v1).
- Message-stream sanitation (phantom tool calls, dangling results), circuit breaker, unbound-thinking handling for GLM — [Kimchi](https://kimchi.dev/blog/same-model-different-harness-terminal-bench) (vendor).
- Context files: no correctness gain, +~20% cost; keep only non-standard conventions — [arXiv 2602.11988](https://arxiv.org/html/2602.11988v3).

### Inferences
- Suggested A/B queue (each vs current baseline, model fixed, ≥3 reps, pre-registered metric = task success + tokens):
  1. Observation masking of tool outputs older than M turns (test M ∈ {5,10,20}) — expect cost ↓, success ≈/↑; especially for Qwen3.5-9B with small windows.
  2. Pre-exit verification hook ("re-check against the task spec before final answer") — expect success ↑, tokens ↑.
  3. Loop/stall guard (repeat-action or N-edits-same-target counter → injected reconsider message; compare inject-only vs terminate) — watch for false kills.
  4. Hard command timeouts + structured error messages to the model.
  5. Message sanitation for malformed/phantom tool calls and thinking-length cap (GLM-specific failure modes).
  6. Convention file (AGENTS.md style) on vs off — expect cost ↑, success ≈; keep only if it beats off.
  7. Todo/plan file and sub-agent delegation last — least evidence for small models, and sub-agents cost extra calls.
- Report per arm: mean, spread across reps, and whether model ranking (GLM vs Qwen) flips across arms — mirrors the 2605.23950 protocol.
- Because the harness must be task-agnostic, avoid trace-driven tuning on the evaluation set (LangChain's own overfitting warning); freeze the config as 2608.26218 did and test on held-out tasks.

### Gaps
- No public measurement found for any of these components on GLM-5.3-Flash or Qwen3.5-9B specifically; all transfer to these models is inference.
