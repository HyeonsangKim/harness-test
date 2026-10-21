# Runtime tool creation and skill libraries for LLM agents (2023 – Oct 2026)

Research date: 2026-10-21. Every number below was read in the primary source (arXiv abs/HTML, official blog/docs) unless marked otherwise. Numbers are from the authors' own papers. None of them is an independent replication.

## Q1. Tool-making papers: setups and exact numbers (LATM, CREATOR, CRAFT, Voyager, ToolMaker, Alita, ToolLibGen)

### Takeaway
Measured gains are large when four things hold: the task family is narrow and repeats, a strong model (GPT-4 class) writes the tool, the tool is checked by running it against held-out examples, and the tool is then reused many times. On open-ended work (GAIA), self-made tools are bundled with other agent machinery, so their own effect is smaller and harder to separate.

### Cited Findings
**LATM (Cai et al., 2023, arXiv 2305.17126)**
- Pipeline: GPT-4 makes the tools and GPT-3.5 Turbo uses them. Tools are cached and reused. A GPT-3.5 "dispatcher" decides whether a tool already exists or a new one is needed — [arXiv abs](https://arxiv.org/abs/2305.17126)
- Six BIG-Bench-style tasks, each with 3 train, 3 validation and 240 test instances. The tool user is GPT-3.5 Turbo, and the scores compare CoT with LATM:
  - Logical Deduction(5): 66.4 → 79.7
  - Tracking Shuffled Objects(5): 61.6 → 99.6
  - Dyck: 20.4 → 92.2
  - Word Sort: 59.2 → 98.3
  - Chinese Remainder: 0.0 → 100.0
  - Schedule Meeting: 18.9 → 100.0

  GPT-4 with CoT scored 88.8 / 100 / 63.6 / 90.9 / 0.0 / 55.6 on the same tasks — [arXiv HTML](https://arxiv.org/html/2305.17126v2)
- Tool-maker capability decides the outcome. Valid tools out of 5 attempts (Table 3):
  - GPT-3.5 Turbo as maker: 0/5 on LD, TSO and Schedule; 5/5 on Dyck, Word Sort and CRT.
  - GPT-4 as maker: 3/5, 4/5, 5/5, 5/5, 5/5, 3/5.

  The authors attribute the failures mainly to tools that are not general and only fit the training samples. Caveat: the text says "55 trials" but the table shows x/5. The paper itself does not resolve this — [arXiv HTML](https://arxiv.org/html/2305.17126v2)
- Weaker tool users, all given the same GPT-4-made tool (Table 4):
  - text-davinci-002: 58.2 on LD, 35.8 on Dyck.
  - curie: 6.5 on LD, but 93.1 on CRT.
  - ada: 3.0 on LD, 66.0 on CRT.

  Very weak users therefore benefit only when the tool call is trivial. No Llama or ~7B open model was tested — [arXiv HTML](https://arxiv.org/html/2305.17126v2)
- The dispatcher picked the right existing tool 95% ± 2% of the time and decided correctly when to request a new tool 96% ± 3% of the time, over 100 mixed samples — [arXiv HTML](https://arxiv.org/html/2305.17126v2)
- Verification:
  - Tools are checked on held-out validation samples, with at most 3 retries.
  - Only 2 of 60 trials fixed a mistake from the error message.

  Stated limits: overfitting to the training samples, the 8k context, and "did not address control and safety issues in depth" (Appendix B) — [arXiv HTML](https://arxiv.org/html/2305.17126v2)

**CREATOR (Qian et al., 2023, arXiv 2305.14318)**
- Four stages: creation, decision, execution, rectification. Every experiment uses ChatGPT (gpt-3.5-turbo) and only ChatGPT — [arXiv HTML](https://arxiv.org/html/2305.14318)
- MATH, without CoT: CREATOR 59.7% vs. PoT 49.8%, PoT+rectification 53.9%, WolframAlpha tool use 39.0%, vanilla 25.3% — [arXiv HTML](https://arxiv.org/html/2305.14318)
- TabMWP, with CoT: CREATOR 94.7% vs. PoT+rectification 87.3% and vanilla 75.2% — [arXiv HTML](https://arxiv.org/html/2305.14318)
- Creation Challenge (2K questions): 63.8% with no hint, 75.7% with all hints. Vanilla scores 27.9% — [arXiv HTML](https://arxiv.org/html/2305.14318)
- Reusing tools across scenarios on a 300-question transfer set: 63.0% → 78.3% — [arXiv HTML](https://arxiv.org/html/2305.14318)
- The authors' own limitation: correctness of created tools on larger tasks "remain[s] questionable" — [arXiv HTML](https://arxiv.org/html/2305.14318)

**CRAFT (Yuan et al., ICLR 2024, arXiv 2309.17428)**
- Toolset construction is offline:
  1. GPT-4 writes Python solutions on training problems. Only bug-free solutions with correct answers are kept.
  2. GPT-4 abstracts each solution into a function with a name and docstring.
  3. Validation: the abstracted tool must reproduce the original answer.
  4. Deduplication: tools are grouped by name and argument count, and GPT-4 keeps the most general one.

  Construction cost about $2,500 — [arXiv HTML](https://arxiv.org/html/2309.17428v2)
- Toolset sizes: 525 tools for VQA, 181 for tabular, 282 for math — [arXiv HTML](https://arxiv.org/html/2309.17428v2)
- Gains with GPT-3.5-Turbo:
  - GQA: 35.0 → 45.4
  - OK-VQA: 15.4 → 33.4
  - A-OKVQA: 15.6 → 30.8
  - TabMWP: 80.6 → 88.4 (a plain BM25 retrieval variant scored 89.2)
  - MATH algebra: 58.2 → 68.1

  With GPT-4 the gains shrink (GQA 51.4 → 55.6) — [arXiv HTML](https://arxiv.org/html/2309.17428v2)
- Open models: CodeLlama showed "near-random performance". No numbers are given — [arXiv HTML](https://arxiv.org/html/2309.17428v2)

**Voyager (Wang et al., 2023, arXiv 2305.16291)**
- Setup: a GPT-4 agent in Minecraft with three parts: an automatic curriculum, a skill library of JavaScript functions, and iterative prompting (environment feedback, execution errors, self-verification) — [arXiv abs](https://arxiv.org/abs/2305.16291)
- Results:
  - 63 unique items in 160 iterations, 3.3× more than baselines.
  - Wooden, stone and iron tools unlocked 15.3×, 8.5× and 6.4× faster.
  - Only Voyager reached the diamond tool, in 1 of 3 runs.

  — [arXiv HTML](https://arxiv.org/html/2305.16291)
- Ablations:
  - Without self-verification: 73% fewer items.
  - GPT-3.5 instead of GPT-4 for code: 5.7× fewer items.
  - Without the skill library: no diamond tool. In the new-world tests it was slower (diamond pickaxe 36 iterations, 2/3 runs, vs. 19 ± 3, 3/3).
  - AutoGPT given Voyager's skill library: partial success (1–2 of 3 runs on 3 of 4 tasks).

  — [arXiv HTML](https://arxiv.org/html/2305.16291)

**ToolMaker (Wölflein et al., ACL 2025, arXiv 2502.11705)**
- Turns a GitHub repo plus a task description into a tool. It installs the environment and writes the wrapper code in a closed-loop self-correction cycle, using gpt-4o-2024-08-06 — [arXiv HTML](https://arxiv.org/html/2502.11705v2)
- TM-Bench has 15 tasks, 42 invocations and 124 unit tests. A tool counts as correct only if every unit test passes.

  | Agent | Tools correct | Unit tests passed | Avg. cost per tool | Avg. actions |
  |---|---|---|---|---|
  | ToolMaker | 12/15 (80%) | 116/124 | $0.94 | 21.8 |
  | OpenHands | 3/15 | 31/124 | $0.15 | 7.5 |

  With o3-mini, ToolMaker got 9/15 — [arXiv HTML](https://arxiv.org/html/2502.11705v2)
- Execution runs in a Docker container sandboxed from the host, and Docker checkpointing restores the state between attempts.
- Stated limits: passing the unit tests does not guarantee real-world correctness, and high-stakes uses need expert validation. The authors also discuss misuse risk — [arXiv HTML](https://arxiv.org/html/2502.11705v2)

**Alita (Qiu et al., 2025, arXiv 2505.20286)**
- Design: minimal predefined tools. The agent generates MCP servers from open-source resources at runtime.
- How a tool is accepted: each candidate tool gets its own Conda environment. The tool is registered as an MCP if a run produces the expected output. If setup fails, the tool is discarded and the failure logged.
- There is no formal test suite and no security analysis — [arXiv HTML](https://arxiv.org/html/2505.20286)
- GAIA **validation** set:
  - Claude-Sonnet-4 + GPT-4o: 75.15% pass@1, 87.27% pass@3.
  - Claude-3.7-Sonnet + GPT-4o: 72.73% pass@1, 86.06% pass@3.
  - GPT-4o-mini only: 43.64% pass@1.

  The authors' baseline table: OpenAI Deep Research 67.36, OWL 69.09, A-World 69.70, ODR-smolagents 55.15 — [arXiv HTML](https://arxiv.org/html/2505.20286)
- MCP reuse, using MCPs that strong models had made:
  - ODR-smolagents + GPT-4o: 27.88 → 33.94.
  - GPT-4o-mini base framework: 21.82 → 29.09; Level 3 went from 3.85 to 11.54.

  — [arXiv HTML](https://arxiv.org/html/2505.20286)
- The authors' own limitation: Alita "highly relies on the coding capability of LLM", and with weak coders it does worse than traditional agents — [arXiv HTML](https://arxiv.org/html/2505.20286)

**ToolLibGen (arXiv 2510.07768, Oct 2025)**
- Problem it addresses: question-specific tools pile up (48k–175k per domain) and retrieval degrades. It clusters and merges them into a library of 3.1k–8.9k tools. GPT-5 builds the library and GPT-4.1 validates it — [arXiv HTML](https://arxiv.org/html/2510.07768)
- Accuracy for each solver, seen / unseen (SuperGPQA):

  | Solver | CoT | Fragmented toolset | ToolLibGen |
  |---|---|---|---|
  | Qwen3-8B | 45.5 / 52.8 | 50.9 / 54.2 | 61.4 / 56.3 |
  | GPT-oss-20B | 46.6 / 54.0 | — | 62.1 / 60.5 |

  "Seen" questions are the ones the library was built from. Gains on unseen questions are about 2–4 points — [arXiv HTML](https://arxiv.org/html/2510.07768)

### Inferences
- In every paper the tools were made by GPT-4, GPT-4o, GPT-5 or Claude Sonnet. Every gain comes with an acceptance check by execution (validation samples, unit tests, or an expected-output run).
- Gains concentrate on repeated, algorithmic task families where one tool covers many instances: LATM's CRT and Schedule tasks went from 0–19% to 100%. Gains are small on unseen open questions (ToolLibGen unseen +2–4 points) and on open-ended agent work (Alita's MCP reuse +6–7 points).
- None of these setups matches an air-gapped Windows box running only the standard library: Alita needs pip/conda, and ToolMaker needs Docker and GitHub.

### Gaps
- Alita GAIA **test**-set or leaderboard entries with dates were not verified. The paper reports validation only.
- No 2026 follow-up to LATM, CREATOR or Alita that reports numbers was read. MUSE-Autoskill (arXiv 2605.27366) appeared in search but was not opened.

## Q2. "Skills as files" (Anthropic Agent Skills, SKILL.md, progressive disclosure), OpenAI equivalents, MCP: claimed vs measured

### Takeaway
SKILL.md has become a cross-vendor open format. Anthropic's announcement reported no measurements. The main independent benchmark (SkillsBench, 2026) found:
- Curated, human-written skills help: +16.6 pp on average.
- Skills that a model writes for itself do not help and often hurt: −8 to −12 pp in v4.
- Small, focused skills beat large bundles.

### Cited Findings
- **Anthropic announcement (2025-10-16).** Agent Skills became an open standard on 2025-12-18.
  - A skill is a folder with a SKILL.md: YAML frontmatter with `name` and `description`, then instructions, plus optional scripts and resource files.
  - Progressive disclosure works in three levels: (1) the name and description of every skill sit in the system prompt; (2) the full SKILL.md is read when a skill seems relevant; (3) bundled files are read only when needed.
  - Bundled scripts can run without being loaded into context.
  - No quantitative results are given. "Agents create, edit, and evaluate their own skills" is stated as a future goal.

  — [Anthropic engineering](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- **Anthropic's security advice:** install skills only from trusted sources, audit less-trusted ones (read the bundled files and dependencies), and watch for instructions that connect to untrusted networks — [Anthropic engineering](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- **OpenAI Codex** builds on the open agent skills standard (agentskills.io). Codex loads only each skill's name, description and path, and reads the full SKILL.md when it picks that skill. Plugins are the distribution unit — [OpenAI Codex docs](https://developers.openai.com/codex/skills)
- **Unverified adoption claim:** "30+ tools" by April 2026, from a secondary blog only — [noqta.tn](https://noqta.tn/en/news/skill-md-open-standard-30-ai-coding-tools-adoption-2026)
- **SkillsBench (arXiv 2602.12670, v1 Feb 2026, v4 Jun 2026)**, abstract of the latest version:
  - 87 tasks across 8 domains, 18 model-harness setups.
  - Curated skills raise the average pass rate from 33.9% to 50.5% (+16.6 pp; range +4.1 to +25.7).
  - Focused skills with at most 3 modules beat exhaustive bundles.

  An earlier version, as quoted in search snippets, reported 86 tasks / 11 domains, +16.2 pp, and −1.3 pp for self-generated skills, so the numbers changed between versions — [arXiv abs](https://arxiv.org/abs/2602.12670)
- **SkillsBench v4 details:**
  - Self-generated skills vs. no skills: Claude Code + Opus 4.7 −8.1 pp, Codex + GPT-5.5 −11.3 pp, Gemini CLI + Gemini 3.1 Pro −11.5 pp. On the same setups, curated skills gave +18.2 to +24.8 pp.
  - Skill count: 1 skill +18.0 pp, 2–3 skills +19.0 pp, 4 or more +10.1 pp.
  - Skill length: compact +19.0 pp and standard +21.5 pp vs. comprehensive documentation +0.7 pp.
  - 13 of 87 tasks got worse with skills.
  - A smaller model with skills (MiniMax M2.7: 34.9%) beat larger models without them (GLM 5.1: 32.7%, both on OpenHands).
  - All verification is deterministic pytest. There is no LLM judge.

  — [arXiv HTML](https://arxiv.org/html/2602.12670)
- **SkillsBench's stated caveats:**
  - Gains may partly come from added context length rather than procedure, so length-matched controls are needed.
  - Benchmark skills score 10.1/12 on the quality rubric vs. 6.2/12 across the ecosystem, so the results may be optimistic for typical public skills.
  - The self-generated deficit mixes content quality with discovery effects.

  — [arXiv HTML](https://arxiv.org/html/2602.12670)
- **Conflicting result:** MUSE-Autoskill reports that self-created skills helped on a 75-task SkillsBench subset (Codex 44.80 → 47.52). This comes from search-result text only and was not verified in the source — [arXiv PDF](https://arxiv.org/pdf/2605.27366)

### Inferences
- The thing shown to help is the pattern: a short, curated, human-reviewed SKILL.md loaded on demand. That pattern needs only files and the standard library, so it fits the air-gapped harness.
- Live self-authored skills are not supported by the 2026 evidence, even with frontier models.

### Gaps
- No measured comparison of SKILL.md vs. MCP as a distribution mechanism was found.
- No SkillsBench result for Qwen-class ≤10B models (Qwen is not in the table) and no GLM-5.3-Flash result.

## Q3. Does tool-making work for small models? (big maker / small user)

### Takeaway
The evidence supports small models as tool *users* of tools made by strong models (LATM, Alita MCP reuse, ToolLibGen with Qwen3-8B). It does not support small models as tool *makers*: GPT-3.5 already failed half of LATM's tasks, and Voyager and Alita degrade sharply with weaker coders.

### Cited Findings
- **GPT-3.5 as maker in LATM:** 0/5 valid tools on 3 of 6 tasks. GPT-3.5 as user of GPT-4-made tools matches or beats GPT-4 with CoT — [LATM HTML](https://arxiv.org/html/2305.17126v2)
- **Voyager:** GPT-3.5 instead of GPT-4 for code produced 5.7× fewer items — [Voyager HTML](https://arxiv.org/html/2305.16291)
- **Alita with GPT-4o-mini only:** 43.64% on GAIA validation vs. 75.15% with Claude-Sonnet-4. GPT-4o-mini given strong-model MCPs: 21.82 → 29.09 — [Alita HTML](https://arxiv.org/html/2505.20286)
- **CRAFT:** CodeLlama "near-random" — [CRAFT HTML](https://arxiv.org/html/2309.17428v2)
- **Qwen3-8B as user of a GPT-5-built library:** 45.5 → 61.4 on seen questions, 52.8 → 56.3 on unseen — [ToolLibGen HTML](https://arxiv.org/html/2510.07768)
- **SkillsBench:** MiniMax M2.7 with curated skills outperformed larger models without skills — [SkillsBench HTML](https://arxiv.org/html/2602.12670)

### Inferences
- For Qwen3.5-9B and GLM-5.3-Flash, the practical split is: humans (or a strong external model, offline) make and verify the tools and skills, and the small in-house model only selects and calls them. That is the LATM split with a human in the maker seat.
- Whether GLM-5.3-Flash can make tools is unknown. The literature gives no basis to assume it can.

### Gaps
- No paper found that tests a ≤10B model as tool *maker* with numbers. CRAFT gives only a qualitative "near-random" note.
- Nothing published on GLM-5.3-Flash or Qwen3.5-9B in tool-making setups.

## Q4. Risks (wrong, overfit or insecure tools; injection) and recommended verification patterns

### Takeaway
The reported failures fall into four groups:
- Overfitting: tools that only fit their examples (LATM).
- Silent incorrectness: unit tests pass but real-world behavior is still unverified (ToolMaker).
- Library sprawl and retrieval decay (ToolLibGen).
- Supply-chain and prompt-injection risk in shared skills: about 26% of marketplace skills are flagged, and skills that bundle scripts are flagged more often.

Every successful system gates reuse behind execution-based checks. Security work adds permissions and human vetting.

### Cited Findings
- **Overfitting:** LATM attributes failed tools to "not general, only fit training samples" and leaves safety unaddressed — [LATM HTML](https://arxiv.org/html/2305.17126v2)
- **Silent incorrectness:** ToolMaker says that passing unit tests does not guarantee real-world correctness and that high-stakes use needs expert validation. It also discusses misuse risk — [ToolMaker HTML](https://arxiv.org/html/2502.11705v2)
- **Library sprawl:** retrieval over a fragmented toolset "declines sharply" as tools grow, and merging into a curated library fixes it. The largest failure mode is the model ignoring the tool's output — [ToolLibGen HTML](https://arxiv.org/html/2510.07768)
- **Marketplace skills (arXiv 2601.10338):**
  - 42,447 skills collected and 31,132 scanned; 26.1% have at least one vulnerability.
  - Data exfiltration 13.3%, privilege escalation 11.8%, high-severity or likely malicious 5.2%.
  - Skills that bundle scripts are 2.12× more likely to be vulnerable (OR, p<0.001).
  - The authors recommend capability-based permissions and mandatory security vetting.

  — [arXiv abs](https://arxiv.org/abs/2601.10338)
- **Other 2026 skill-security papers, seen in search results and not opened (titles/snippets only):**
  - Prompt-injection detectors flagged almost nothing on top marketplace skills (0% on skills.sh top 100, 2.6% on ClawHub) while flagging 91% of confirmed-malicious ones — [arXiv 2605.28588](https://arxiv.org/pdf/2605.28588)
  - Natural-language-only edits to SKILL.md can manipulate which skill gets selected and can pass registry scans — [arXiv 2605.11418](https://arxiv.org/html/2605.11418v1)
  - Permission-centric defense — [SkillGuard 2606.03024](https://arxiv.org/pdf/2606.03024)
  - Threat-model survey — [arXiv 2607.13987](https://arxiv.org/pdf/2607.13987)
- **Verification patterns in successful systems:**

  | System | Check before reuse | Isolation |
  |---|---|---|
  | LATM | Held-out validation samples, 3 retries | — |
  | CRAFT | Abstracted tool must reproduce the correct answer, then dedup | — |
  | ToolMaker | Unit tests | Docker sandbox with checkpoint/restore |
  | Alita | Expected-output run | Isolated Conda env per tool |
  | Voyager | Self-verification (its removal cost 73% of items) | — |

  Sources: [LATM](https://arxiv.org/html/2305.17126v2), [CRAFT](https://arxiv.org/html/2309.17428v2), [ToolMaker](https://arxiv.org/html/2502.11705v2), [Alita](https://arxiv.org/html/2505.20286), [Voyager](https://arxiv.org/html/2305.16291)

### Inferences
**Usable in the air-gapped, stdlib-only harness:**
1. Log requests the harness could not satisfy (no tool, tool failed).
2. A human or strong external model writes the tool or SKILL.md outside the air-gapped network.
3. Attach deterministic unit tests and held-out cases (the LATM/CRAFT/ToolMaker gate).
4. A/B the tool against the baseline on the pre-registered bench before promoting it to the curated library, which arrives via `git clone`.
5. Keep skills few and short (SkillsBench: ≤3 per task, compact). Prefer instruction-only skills over script-bundled ones (OR 2.12 for vulnerability). Make any script a stdlib function that is reviewed in code review.

**Not recommended:** letting GLM-5.3-Flash or Qwen3.5-9B write and register tools live. Small makers failed in the literature, self-generated skills hurt even frontier models, and the sandboxes the literature relies on (Docker, conda) are unavailable here.

**If live drafting is allowed at all:** keep it in a quarantine area. Run it through a subprocess with a timeout and no network, and only as a suggestion for human promotion. Never let it be loaded automatically.

### Gaps
- No controlled study found comparing human-approval gates with automatic test gates for tool promotion.
- Numbers from the four unopened 2026 security papers above are from search snippets and must be checked before citing.
