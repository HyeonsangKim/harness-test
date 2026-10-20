# Memory Techniques for LLM Agents: Within-Task and Across-Task, Small/Local-Model Focus (as of Oct 2026)

Tags:
- **[V]** = checked against the primary source (arXiv page, HTML full text, or vendor doc) in this session.
- **[S]** = secondary source, or a vendor self-report without independent replication.
- **[U]** = unverified. This covers things recalled from prior knowledge of the paper and not re-fetched this session, and snippets. Check numbers before quoting.

Pre-2025 items are marked *(older)*.

This file extends `context_verification_recovery.md` (earlier notes, Q1/Q2). It does not repeat that file's masking, compaction and context-rot material.

Harness constraints assumed throughout:
- Python 3.12 stdlib only.
- sqlite3 is available, with FTS5 usually compiled in. FTS5 provides BM25 ranking natively.
- No embeddings and no vector DB.
- Air-gapped network.
- Current model GLM-5.3-Flash; later models of 4B–32B.

---

## Q1. Within-task memory: harness-held structured state, model-written notes, todo lists, JSON vs Markdown, file memory with tools, MemGPT/Letta paging

### Takeaway
Within a single task, the best-supported and lowest-risk memory is **state the harness writes deterministically**:
- a structured task/feature list in JSON whose fields the model may only flip;
- a progress log;
- facts extracted from tool outputs by code;
- the file system or git as restorable state.

**Model-curated free text** (scratchpads, self-summaries, memory-file editing) has vendor support only for strong models. No controlled study shows it helping small models. On short tasks it is predicted to be unmeasurable, consistent with the team's experiment. File-memory-with-tools is cheap to implement in stdlib, but the gains reported for it are self-reported and come from frontier models.

### Cited Findings
**JSON vs Markdown; harness-defined state (Anthropic long-running agents)**
- [V] Anthropic, "Effective harnesses for long-running agents" (26 Nov 2025), describes an **initializer session** that writes four things:
  - a feature list;
  - `claude-progress.txt` ("keeps a log of what agents have done");
  - an `init.sh` that starts the dev server;
  - an initial git commit.

  Each later coding session reads these to "quickly understand the state of work when starting with a fresh context window." — [Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [V] On the feature list format: "the model is less likely to inappropriately change or overwrite JSON files compared to Markdown files." This is stated as a result of their experimentation, with no numbers given. Agents are prompted to "edit this file only by changing the status of a `passes` field", and the post says "It is unacceptable to remove or edit tests." Git commits with descriptive messages let the model "revert bad code changes and recover working states." — [Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [V] The Claude memory-tool docs restate this as a "multisession software development pattern":
  - an initializer creates the progress log, the feature checklist and a reference to the init script;
  - each session reads them first and updates the progress log at the end;
  - "Mark a feature complete only after end-to-end verification confirms it works, not when the code is written." — [Claude docs, Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)

**File memory with read/write tools (Anthropic memory tool)**
- [V] The tool is `memory_20250818` and runs **client-side**: the model requests file operations under `/memories`, and the application executes them. Commands: `view` (directory listing two levels deep, or a file with 6-wide line numbers and an optional `view_range`), `create`, `str_replace` (which must match exactly one occurrence), `insert`, `delete` and `rename`.
- [V] The API auto-injects this instruction into the system prompt: "ALWAYS VIEW YOUR MEMORY DIRECTORY BEFORE DOING ANYTHING ELSE … ASSUME INTERRUPTION: Your context window might be reset at any moment."
- [V] Security guidance in the docs:
  - validate every path against traversal (`../`, URL-encoded `%2e%2e%2f`), using `pathlib.Path.resolve()` and `relative_to()`;
  - cap file sizes and cap `view` output;
  - expire files that have not been accessed;
  - strip sensitive data before writing.

  The docs pair the memory tool with context editing and compaction: "memory preserves the information that must survive summarization." — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- [S] Anthropic reports, from internal evaluations, memory tool plus context editing at +39% over baseline on agentic search, and context editing alone at +29%. This is vendor self-reported and was already noted in the earlier notes. — [Anthropic news](https://www.anthropic.com/news/context-management)
- [S] Letta, "Benchmarking AI agent memory: is a filesystem all you need?" (12 Aug 2025):
  - An agent on **gpt-4o-mini** with only file tools (conversation histories stored in files, plus grep/search-style tools) scored **74.0%** on LoCoMo.
  - Mem0's reported best (graph) variant scored **68.5%**.
  - The claim is that "an agent's ability to use retrieval tools matters more than the retrieval mechanism."
  - Caveats: vendor-authored; Mem0's numbers could not be reproduced; tool rules forced the weak model to start with search and end with an answer call; LoCoMo is retrieval QA, not agentic memory.

  — [Letta blog](https://www.letta.com/blog/benchmarking-ai-agent-memory)

**MemGPT / Letta paging**
- [U] *(older, Oct 2023)* MemGPT (Packer et al.) uses an OS-style hierarchy: a "main context" of system prompt, working context and FIFO queue, plus "external context" made of recall storage and archival storage. The model pages data in and out with function calls, and memory-pressure warnings trigger summarization or eviction. It was evaluated on GPT-4 versus GPT-3.5; my recollection is that weaker models misused the paging functions. — [arXiv 2310.08560](https://arxiv.org/abs/2310.08560)
- [U] Letta's current product exposes "memory blocks" that the agent edits through tools, plus archival search. The Letta filesystem result above suggests simple file tools are competitive with this.

**Todo / recitation (Manus) and scratchpad**
- [V] (Earlier notes.) Manus rewrites `todo.md` at the end of the context to fight goal drift over tasks of about 50 tool calls. This is practitioner advice with no numbers. — [Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [V] (Earlier notes.) JetBrains: LLM summarization did not beat observation masking and made trajectories longer. On short trajectories of about 15 turns it gave no savings. — [arXiv 2508.21433](https://arxiv.org/abs/2508.21433)
- [V] (Earlier notes.) ACE's "context collapse" is the failure mode of monolithic LLM rewrites. A context of **18,282 tokens at 66.7% accuracy** was rewritten by the model to **122 tokens at 57.1%**, below the no-adaptation baseline of 63.7 (AppWorld, DeepSeek-V3.1). This is the strongest quantitative argument against "rewrite the whole note each call." — [arXiv 2510.04618 HTML](https://arxiv.org/html/2510.04618)

### Inferences
- The team's "≤1500-char model-written note re-injected each call" is effectively a full-rewrite scratchpad, the design ACE shows can collapse. If they keep a note, prefer these changes:
  - **append/delta edits** (entries with IDs, plus `str_replace`-style edits only) over full rewrites;
  - **harness-owned schema fields** (JSON) in which the model can only set a status or value;
  - **provenance tags** (`observed:tool_X@step_n` vs `inferred`).
- Recommended within-task stack, cheapest and most reliable first:
  1. A JSON task-state file written by the harness: goal, constraints, a checklist with `status` fields, and facts extracted from tool outputs by regex or parsers. Re-inject it near the **end** of the context (recitation) to keep prefix caching intact.
  2. An append-only progress log the harness writes per step: tool, arguments hash, ok/error, one-line result.
  3. Optional `memory_*` file tools (view, create, str_replace) over a sandboxed directory, using the Anthropic command semantics and its path-traversal checks. This is roughly 100–200 lines of stdlib code.
  4. A model-written note, only for long tasks where history is masked.
- To measure any of this, the task family must force information loss. The earlier notes propose a 2×2 design {full, masked history} × {state on, off}. Short full-history tasks will keep showing null effects.

### Gaps
- No controlled ablation of JSON vs Markdown state was found. Anthropic's claim is qualitative.
- No primary study was found of MemGPT-style self-paging with models of 32B or smaller from 2025–26.
- No data was found on how often small models corrupt or overwrite structured state files.

---

## Q2. Across-task memory: AWM, ReasoningBank, ACE, Dynamic Cheatsheet, Mem0, A-MEM, Zep/Graphiti, skills, trajectory replay

### Takeaway
Cross-task memory gives the largest gains when four conditions hold:
- tasks recur;
- a correctness signal exists (ground truth, execution success, or a decent judge);
- the memory is stored as small, structured, retrievable units, not a monolithic blob;
- the backbone is strong enough to write good entries.

The **admission policy** (what gets stored) matters more than the retrieval algorithm. "Add everything" is consistently worse than a fixed memory. Curated human or teacher-written skills give the most reliable boost.

### Cited Findings
**Experience/strategy memory**
- [V] ReasoningBank (Ouyang et al., Google, Sep 2025, ICLR 2026) is tested on WebArena, Mind2Web and SWE-Bench-Verified with Gemini-2.5-flash/pro and Claude-3.7-Sonnet.
  - Memory items are a title, a one-sentence description and content. Up to 3 items are extracted per trajectory: strategies from successes, pitfalls from failures.
  - Retrieval embeds the query (gemini-embedding-001) and takes the **top-1** by cosine similarity into the system prompt.
  - Success labels come from **LLM-as-judge with no ground truth**, using the same backbone at temperature 0. Judge agreement with ground truth was 72.7% on WebArena-Shopping. Simulated judge accuracy of 70–90% had little effect, and 100% was best.
  - WebArena success rate, no memory → ReasoningBank → +MaTTS: Flash 40.5→48.8→51.8; Pro 46.7→53.9→56.3; Claude-3.7 41.7→46.3→48.8.
  - SWE-bench-Verified: Flash 34.2→38.8; Pro 54.0→57.4.
  - Synapse and AWM gave smaller gains. AWM fell below no-memory on the Flash Multi subset.

  — [arXiv 2509.25140 HTML](https://arxiv.org/html/2509.25140)
  - Appendix C.4 (smaller open-source LLMs) was not read because of page truncation. **Flag:** check it before relying on small-model claims.
- [V] ACE (Zhang et al., Oct 2025, ICLR 2026) has generator, reflector and curator roles that apply **delta updates** to a playbook of bullets.
  - Each bullet has a unique ID, helpful/harmful counters and content. Bullets are deduplicated by semantic embeddings.
  - AppWorld with DeepSeek-V3.1 (ReAct baseline 42.4): offline with ground-truth labels 59.4 (+17.0); offline without labels 57.2 (+14.8); online without labels 59.5 (+17.1).
  - GPT-OSS-120B: base 34.6 → 40.5 / 39.4 / 42.2.
  - Llama-3.3-70B showed smaller gains, which the authors attribute to noisier reflections from weaker models.
  - Without reliable feedback, "ACE and Dynamic Cheatsheet can degrade because the context gets polluted": online finance FiNER went −3.4.

  — [arXiv 2510.04618 HTML](https://arxiv.org/html/2510.04618)
- [V] Dynamic Cheatsheet (Suzgun et al., Apr 2025) comes in two variants:
  - DC-Cu: curated cheatsheet, no retrieval.
  - DC-RS: retrieves the top-3 similar past input/output pairs with text-embedding-3-small, then curates.

  Strong models gained greatly (earlier notes: AIME more than doubled for Claude 3.5 Sonnet; Game of 24 10→99% for GPT-4o). See Q3 for small models. — [arXiv 2504.07952 HTML](https://arxiv.org/html/2504.07952)
- [U] *(older, Sep 2024)* Agent Workflow Memory (Wang et al.) induces reusable sub-routine "workflows" from successful trajectories. It reported +24.6% (Mind2Web) and +51.1% (WebArena) relative success with GPT-4. — [arXiv 2409.07429](https://arxiv.org/abs/2409.07429)
- [V] "How Memory Management Impacts LLM Agents" (Xiong et al., arXiv 2505.16067, May 2025, revised Oct 2025) uses GPT-4o-mini as the main backbone, with GPT-4o and DeepSeek-V3 as checks. Agents: RegAgent, EHRAgent, AgentDriver, CIC-IoT. Final performance:

  | Agent | Fixed memory | Add-all | Coarse-filter add | Strict-eval add |
  |---|---|---|---|---|
  | EHRAgent (ACC) | 16.75 | 13.05 | 34.66 | 38.50 |
  | AgentDriver (SR) | 40.11 | 32.32 | 47.37 | 51.00 |
  | CIC-IoT (ACC) | 71.50 | 59.90 | 79.50 | 85.40 |
  | RegAgent (SR) | 67.53 | 55.48 | 67.35 | 70.95 |

  **Add-all was worst for every agent.**
  - History-based deletion (dropping records that repeatedly lead to bad outcomes) further improved EHRAgent 38.67→42.06 and CIC-IoT 85.40→89.60.
  - Periodic deletion cut EHRAgent memory from 1,012 to 302 records with no loss.
  - The paper defines **experience-following** (output similarity tracks input similarity; r≈1 for RegAgent), **error propagation** and **misaligned experience replay**.

  **The phrase "memory copying errors" does not appear in the paper.** The closest concepts are experience-following and error propagation: the agent copies a retrieved record's output, including its errors. — [arXiv 2505.16067 HTML](https://arxiv.org/html/2505.16067)
- [V] MemHarness (Wu et al., Shanghai AI Lab and others, Jul 2026), Qwen2.5-7B with GRPO:
  - Inserting retrieved trajectories **verbatim** causes negative transfer. On ALFWorld, RL plus raw memory scored 70.1% versus 76.4% for RL alone.
  - Naive Mem0+GRPO and SimpleMem+GRPO degraded WebShop.
  - Their fix is retrieve → critique → **reconstruct** state-specific guidance, or fall back to self-reasoning: 85.2% ALFWorld, 75.6% WebShop. Removing reconstruction gave 79.6% and 74.6%.
  - The fix requires RL training.

  — [arXiv 2607.28272](https://arxiv.org/html/2607.28272v1)
- [V] "Retrieval-Augmented LLM Agents: Learning to Learn from Experience" (Ferraz et al., Naver Labs Europe, EMNLP 2026) argues that simple episodic retrieval of past trajectories is a strong baseline. It studies storage, query and selection choices. Gains persist with imperfect experience and when the agent reuses its own failed attempts. The best results integrate retrieval into LoRA fine-tuning. Models and numbers were not visible in the abstract. — [arXiv 2603.18272](https://arxiv.org/abs/2603.18272)

**Conversational/user memory systems** (mostly for chat personalization, less relevant to task agents)
- [V] Mem0 (Apr 2025) dynamically extracts, consolidates and retrieves salient facts. On LoCoMo it reports a +26% relative LLM-judge score over OpenAI memory, 91% lower p95 latency and more than 90% token savings versus full context. The graph variant adds about 2%. These are vendor self-reported numbers, and Letta disputes the comparison. — [arXiv 2504.19413](https://arxiv.org/abs/2504.19413); [Letta](https://www.letta.com/blog/benchmarking-ai-agent-memory)
- [U] The Mem0 paper body describes an LLM choosing ADD, UPDATE, DELETE or NOOP per extracted fact against similar existing memories. This was not seen in the abstract this session.
- [U] A-MEM (Xu et al., Feb 2025, NeurIPS 2025) gives Zettelkasten-style notes with keywords, tags and context descriptions, LLM-generated links and "memory evolution" that updates linked notes. My recollection is that it was evaluated on LoCoMo including smaller backbones (Qwen2.5-1.5B/3B, Llama-3.2 1B/3B), but I did not verify this. — [arXiv 2502.12110](https://arxiv.org/abs/2502.12110)
- [U] Zep/Graphiti (Jan 2025) is a bi-temporal knowledge graph that tracks the valid-from/valid-to time of facts. It reported DMR 94.8% vs MemGPT 93.4%, and LongMemEval gains of up to about 18.5% with about 90% lower latency. Not verified. It requires a graph DB (Neo4j) and embeddings, so it does not fit an air-gapped stdlib harness. — [arXiv 2501.13956](https://arxiv.org/abs/2501.13956)

**Skills / skill libraries**
- [V] SkillsBench (Li et al., 79 authors, Feb 2026, v4 Jun 2026) covers 87 tasks in 8 domains across 18 model-harness configurations.
  - **Curated** skills raised the average pass rate from 33.9% to 50.5% (+16.6 pp; range +4.1 to +25.7).
  - Focused skills with at most 3 modules beat large or exhaustive bundles.
  - "Smaller models equipped with skills can match larger models that lack them," with no figures in the abstract.
  - I did not see the self-generated vs curated comparison. [U] My recollection from snippets is that self-generated skills gave little or no benefit; check the full paper.

  — [arXiv 2602.12670](https://arxiv.org/abs/2602.12670)
- [U] *(older, 2023)* Voyager admitted code skills to its library only after self-verification passed. — [arXiv 2305.16291](https://arxiv.org/abs/2305.16291)

### Inferences
- What carries over to this harness:
  - (a) **strict admission**: store only verifier-passed or human-approved cases;
  - (b) **small itemized entries** with IDs and helpful/harmful counters (ACE), plus deletion of entries tied to repeated failures (Xiong);
  - (c) **top-1 retrieval** (ReasoningBank and AMD defaults);
  - (d) **curated skills** written by humans or a strong model, which avoid relying on the small model's curation ability.
- Graph and temporal memory (Zep, A-MEM linking) and Mem0-style LLM consolidation suit user and chat memory. For a task harness they add LLM-curation steps that small models do poorly.
- Ranked by evidence quality per unit of implementation cost in stdlib:
  1. Curated skill or playbook files, selected by keyword.
  2. Verified trajectory or workflow exemplars, retrieved top-1 by BM25.
  3. ReasoningBank-style lessons distilled by a strong model offline.
  4. Online self-curated memory by the small model, last or not at all.

### Gaps
- ReasoningBank Appendix C.4 (smaller open models) and the self-generated skills result in SkillsBench were not read.
- The A-MEM and Zep numbers were not verified this session.

---

## Q3. Small-model evidence (≤10B, up to ~32B): does memory help or distract?

### Takeaway
2025–26 evidence is fairly consistent:
- **Small models' own memories help little.** They produce mostly failures and curate poorly.
- **Memory written by a stronger teacher or by humans helps a lot**, even 4B models.
- **Verbatim or too many retrieved items can hurt.** Top-1 is safest, and larger k hurt small models.
- Frameworks tuned on frontier models, such as ReasoningBank, can *reduce* small-model accuracy when transplanted.

### Cited Findings
- [V] Agent Memory Distillation (AMD; Kim, Kim, Hwang; KAIST/DeepAuto; 7 Aug 2026). Teacher GPT-5-mini; students Qwen3-4B, Gemma4-E4B, Qwen3-8B and Llama3.1-8B, with a Qwen3 1.7B–14B sweep on AppWorld.
  - Average gains over zero-shot: **+27.2 pp AppWorld, +11.2 BFCL-v3, +3.4 ToolSandbox**.
  - Qwen3-4B on AppWorld went 14.88→49.40%. Gemma4-E4B reached 54.17%, above the teacher's 50.00%. Qwen3-4B on BFCL went 15.5→38.5%.
  - The student's **own** memory gave almost nothing (Qwen3-4B AppWorld 14.88→16.07), because small students' repositories are mostly failed trajectories.
  - **ReasoningBank adapted to teacher-to-student use *lowered* Qwen3-4B on AppWorld, 14.88→10.71.** MemP and SASM gains were inconsistent.
  - Memory has three levels:
    - workflow: top-1 by task instruction, injected proactively;
    - subtask: up to 6 subtask queries, deduplicated;
    - **function**: indexed by function name and injected *reactively only when a tool call errors*.
  - k=1 for all levels. **Larger k generally hurt**, especially subtask memory.
  - Retrieval used text-embedding-3-small with a similarity threshold.

  — [arXiv 2608.07169 HTML](https://arxiv.org/html/2608.07169)
- [V] Dynamic Cheatsheet §4.5: "the effectiveness of DC is strongly tied to the model's scale and underlying generative capacity." Claude 3.5 Haiku and GPT-4o-mini "showed more limited and inconsistent gains."
  - GPT-4o-mini: GPQA-Diamond went 34.3 baseline → 33.8 (DC-Cu) and 32.3 (DC-RS), i.e. slightly worse. AIME-2024 went 16.7 → 13.3 with DC-Cu and DC-RS.
  - Haiku did gain on AIME-2024 (10.0→36.7, DC-Cu).
  - Reasons given: small models "generate correct solutions less reliably, leading to a sparse or low-quality memory repository" and "often fail to retrieve the most relevant past solutions or misapply retrieved knowledge."

  This confirms the earlier [U] item. — [arXiv 2504.07952 HTML](https://arxiv.org/html/2504.07952)
- [V] ACE: Llama-3.3-70B gained less, attributed to noisier reflections from weaker models. The paper says ACE stays effective with a much weaker *Reflector*, but the generator and backbone were large. — [arXiv 2510.04618 HTML](https://arxiv.org/html/2510.04618)
- [V] MemHarness with Qwen2.5-7B: raw verbatim memory hurt (70.1 vs 76.4 on ALFWorld) unless the model is trained to reconstruct. — [arXiv 2607.28272](https://arxiv.org/html/2607.28272v1)
- [V] Xiong et al. ran most experiments on GPT-4o-mini, a small or cheap class model of unstated size. Add-all memory degraded every agent below fixed memory. — [arXiv 2505.16067 HTML](https://arxiv.org/html/2505.16067)
- [S] LightMem (arXiv 2604.07798, ACL 2026) runs memory retrieval, writing and consolidation *with* small LMs, separating online processing from offline consolidation. Seen only in an abstract or snippet, with no numbers. — [arXiv 2604.07798](https://arxiv.org/abs/2604.07798)
- [S] Letta: gpt-4o-mini with plain file tools scored 74% on LoCoMo, which suggests a small model can use simple retrieval tools when tool rules constrain the flow. — [Letta](https://www.letta.com/blog/benchmarking-ai-agent-memory)

### Inferences
- This strongly supports the team's principle that "the harness, not the model, holds memory." For 4B–32B models, the memory **content** should come from:
  - (a) harness-extracted facts;
  - (b) human-curated skills;
  - (c) a stronger model (GLM-5.3-Flash now, offline distillation later). This is the AMD pattern: the current larger model acts as "teacher" and writes the playbook that later small models consume.
- Copy AMD's **reactive function-level memory**: when a tool call errors, the harness looks up notes by function name ("known pitfalls for `tool_X`") and injects them. This is deterministic, keyed by an exact string (no embeddings needed), and fires only when useful, which limits distraction.
- Defaults: k=1, a similarity or score threshold so that sometimes nothing is injected, and short entries.

### Gaps
- No 2025–26 study was found that is specific to GLM-family models.
- No study was found isolating keyword (BM25) retrieval versus embeddings for small-agent experience memory.
- AMD's full Qwen3 1.7B–14B scaling curve was not extracted.

---

## Q4. Retrieval without embeddings: BM25/keyword feasibility

### Takeaway
Every major experience-memory paper reviewed uses dense embeddings (ReasoningBank: gemini-embedding-001; DC-RS, AMD: text-embedding-3-small; ACE dedup: embeddings). None tested BM25 head-to-head in an agent-memory setting that I could verify. Offline, the practical route is **exact-key lookup** (tool name, task type, error code) plus **sqlite FTS5 BM25** over entry titles and keywords. This is plausible because retrieval sets are small and k=1, but it is unproven.

### Cited Findings
- [V] Retrieval methods per paper:
  - ReasoningBank: cosine similarity, top-1 — [2509.25140](https://arxiv.org/html/2509.25140)
  - DC-RS: text-embedding-3-small, top-3 — [2504.07952](https://arxiv.org/html/2504.07952)
  - AMD: text-embedding-3-small with a threshold; function memory is *indexed by function name* — [2608.07169](https://arxiv.org/html/2608.07169)
  - ACE: embedding deduplication — [2510.04618](https://arxiv.org/html/2510.04618)
- [V] LongMemEval (Wu et al., Oct 2024, ICLR 2025) found that commercial assistants and long-context LLMs show about a 30% accuracy drop over sustained interactions. Three memory-design optimizations "greatly improve" recall and QA:
  - session decomposition (finer-grained values);
  - **fact-augmented key expansion** (index entries under extracted facts);
  - **time-aware query expansion**.

  No numbers were visible in the abstract. — [arXiv 2410.10813](https://arxiv.org/abs/2410.10813)
- [S] Letta's filesystem agent used file search tools (grep-like) and beat a vector or graph memory system on LoCoMo. — [Letta](https://www.letta.com/blog/benchmarking-ai-agent-memory)

### Inferences
- Implementation in stdlib:
  - `sqlite3` with an FTS5 virtual table over entries (title, keywords, body, tool_names, task_type, status, helpful, harmful, created, source).
  - Query with `bm25()` plus exact filters, and apply a minimum-score cutoff.
  - Check FTS5 availability with `sqlite3.connect(':memory:').execute("create virtual table t using fts5(x)")`.
  - Fallback if FTS5 is missing: a hand-rolled BM25 over tokenized text in about 50 lines.
- Korean text: FTS5's `unicode61` tokenizer splits on whitespace, so it does not segment Korean morphemes. Use the `trigram` tokenizer (SQLite 3.34+) or character n-grams for Korean. This follows from SQLite tokenizer behavior and was not verified for this deployment.
- Apply LongMemEval's key expansion without embeddings: at write time, the harness adds extracted keys (tool names, entity IDs, error codes) to each entry's keyword field.

### Gaps
- No verified head-to-head of BM25 vs dense retrieval for agent experience memory was found.
- Whether the target SQLite build includes FTS5 or trigram is unknown.

---

## Q5. Safety: memory poisoning and governance

### Takeaway
Persistent memory is an attack and error surface:
- **Query-only** injection (MINJA) reaches about 98% injection success, with no write access to the store.
- Backdoor poisoning (AgentPoison) works at a poison rate below 0.1%.
- Prompt-level detection either misses records or produces false positives.

The workable defenses are **governance**: provenance, verified-only admission, human review, isolation per user or task, expiry, and deletion driven by outcomes. Do not rely on LLM screening.

### Cited Findings
- [V] MINJA, "Memory Injection Attacks on LLM Agents via Query-Only Interaction" (Dong et al., Mar 2025, v5 Feb 2026). The attacker only sends queries and observes outputs. Tested on EHRAgent (GPT-4), RAP/Webshop (GPT-4, GPT-4o) and a QA agent (MMLU).
  - Injection success rate (ISR) 95.6–100%; attack success rate (ASR) 57–98.9%. Overall averages were about 98.2% ISR and 76.8% ASR.
  - Defenses:
    - embedding-level sanitization fails, because malicious and benign records are "highly entangled";
    - a GPT-4o detector with a targeted prompt caught 131/135 EHRAgent records but 0/135 RAP records;
    - a general prompt caught some, with false positives as high as 34/50 on MIMIC-III.

  — [arXiv 2503.03704 HTML](https://arxiv.org/html/2503.03704)
- [V] *(older, Jul 2024; NeurIPS 2024 [U])* AgentPoison poisons memory or a RAG knowledge base with optimized triggers. Tested on an autonomous-driving agent, a knowledge QA agent and EHRAgent: average ASR ≥80%, poison rate <0.1%, benign performance change <1%. — [arXiv 2407.12784](https://arxiv.org/abs/2407.12784)
- [V] Non-adversarial "self-poisoning": add-all memory degrades performance through error propagation and misaligned replay, and strict evaluation plus history-based deletion fixes it. — [arXiv 2505.16067](https://arxiv.org/html/2505.16067)
- [V] ReasoningBank uses an unverified self-judge (72.7% agreement), and ACE notes pollution without reliable feedback. Self-labelled admission therefore lets wrong memories in. — [2509.25140](https://arxiv.org/html/2509.25140); [2510.04618](https://arxiv.org/html/2510.04618)
- [V] Anthropic's memory-tool guidance covers path-traversal validation, size caps, expiry and stripping sensitive data. — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)

### Inferences
Governance checklist for a team asset on an air-gapped network:
1. **Admission:** store only cases where a deterministic verifier passed, or a human approved. Never admit on model self-judgment alone. For failure "lessons", require human or strong-model review.
2. **Provenance per entry:** source task ID, model, verifier result, author (human, teacher model or agent), date, and the version of harness and tools.
3. **Status lifecycle:** `candidate → approved → deprecated`. Only `approved` entries are retrievable in production, and human review happens via the sqlite table or a CSV export.
4. **Outcome tracking:** increment helpful/harmful counters when a retrieved entry precedes a verifier pass or fail. Auto-deprecate entries above a harmful threshold (Xiong's history-based deletion, ACE's counters).
5. **Isolation:** keep namespaces per project or user. Content arriving through user queries or tool outputs (documents, web, email) is untrusted and must not be auto-promoted to memory. MINJA shows that ordinary queries suffice to inject.
6. **Format:** inject memories as clearly delimited, data-labelled reference blocks ("reference notes; may be outdated"), never as instructions in the system role.
7. **Expiry and caps:** apply a TTL and a maximum entry length, and invalidate entries when the tool schema changes.

### Gaps
- No 2025–26 defense paper with strong results against query-only injection was verified.
- No poisoning study was found that targets small local models specifically.

---

## Q6. Benchmarks for agent memory (for later evaluation)

### Takeaway
Existing memory benchmarks mostly test conversational recall (LoCoMo, LongMemEval) or incremental multi-turn competencies (MemoryAgentBench). Task-agent memory is better evaluated by running the team's own recurring task suite, with a held-out split, before and after memory accumulates (the AppWorld, WebArena and BFCL style).

### Cited Findings
- [V] LongMemEval (ICLR 2025, *older* v1 Oct 2024) has 500 questions testing five abilities: information extraction, multi-session reasoning, temporal reasoning, knowledge updates and **abstention**. — [arXiv 2410.10813](https://arxiv.org/abs/2410.10813)
- [V] MemoryAgentBench (Hu, Wang, McAuley; Jul 2025, v4 Jun 2026) tests four competencies: accurate retrieval, test-time learning, long-range understanding and **selective forgetting**. "Current methods fall short of mastering all four competencies." — [arXiv 2507.05257](https://arxiv.org/abs/2507.05257)
- [S] LoCoMo is long-conversation QA. Letta argues it measures retrieval rather than agentic memory. — [Letta](https://www.letta.com/blog/benchmarking-ai-agent-memory)
- [V] Agentic evaluations used in the memory papers above:
  - AppWorld, BFCL-v3 and ToolSandbox (AMD);
  - WebArena, Mind2Web and SWE-bench-Verified (ReasoningBank);
  - ALFWorld and WebShop (MemHarness);
  - AppWorld and finance (ACE).

### Inferences
Minimal in-house protocol:
1. Build a recurring task suite with a deterministic checker. Split it into a "warm-up" (memory-building) stream and a held-out test set.
2. Arms:
   - no memory;
   - curated skills only;
   - verified-exemplar retrieval (BM25, top-1);
   - plus failure-time function memory;
   - add-all memory, as a negative control.
3. Metrics:
   - success rate;
   - number of steps;
   - tokens;
   - the share of retrievals that were relevant;
   - the share of errors traceable to an injected memory.
4. Run per model: GLM-5.3-Flash, then each small model.

### Gaps
- No benchmark was found that targets memory for ≤10B tool agents in offline enterprise settings.
