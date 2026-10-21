# Universal action spaces for LLM agents (code-as-action, bash-only, file system) — small/open model focus

Retrieval date: 2026-10-21. All numbers below were read in the linked primary source unless marked otherwise. "Self-report" = the authors/vendor of the harness or model report it; "independent" = a third party ran it.

## Q1. CodeAct (Wang et al., ICML 2024): exact gains vs JSON/text, which models, small open models

### Takeaway
CodeAct's large gains (e.g. GPT-4-1106 74.4% vs 52.4% JSON on M3ToolEval) are a frontier-closed-model result from early 2024. For the 7B–70B open models of that time, M3ToolEval success was near zero in every format (0–15.9%), and code sometimes did *worse* than JSON (Mistral-7B 0.0 vs 3.7). The atomic-call benefit (API-Bank) was real for Llama-2 chat models, though: code roughly equals text and beats JSON.

### Cited Findings
- Paper: arXiv 2402.01030, v1 1 Feb 2024, v4 7 Jun 2024, ICML 2024. It evaluates 17 LLMs and claims "up to 20% higher success rate" vs alternatives. CodeActAgent is fine-tuned from Llama-2 and Mistral on CodeActInstruct (7k multi-turn interactions). — [arXiv abs](https://arxiv.org/abs/2402.01030)
- M3ToolEval success rate, CodeAct / JSON / Text (Table 3). Closed models: gpt-4-1106-preview 74.4 / 52.4 / 53.7 (avg turns 5.5 / 7.6 / 7.7); gpt-4-0613 67.1 / 56.1 / 45.1; claude-2 54.9 / 39.0 / 29.3; gpt-3.5-turbo-0613 51.2 / 26.8 / 20.7; gemini-pro 22.0 / 19.5 / 11.0. Counterexamples where code lost: claude-instant-1 20.7 / 31.7 / 24.4; text-davinci-002 4.9 / 4.9 / 8.5. — [arXiv HTML v4](https://arxiv.org/html/2402.01030v4)
- M3ToolEval, open models, CodeAct / JSON / Text: CodeLlama-7B 4.9 / 2.4 / 2.4; CodeLlama-13B 4.9 / 4.9 / 4.9; CodeLlama-34B 2.4 / 0.0 / 0.0; Llama-2-7B-chat 0.0 / 1.2 / 2.4; Llama-2-13B-chat 0.0 / 0.0 / 0.0; Llama-2-70B-chat 11.0 / 3.7 / 3.7; Mistral-7B-Instruct-v0.1 0.0 / 3.7 / 1.2; lemur-70b-chat 13.4 / 15.9 / 12.2. Average turns are about 9–10 of a 10-turn cap for all of them, so most runs hit the cap. — [arXiv HTML v4](https://arxiv.org/html/2402.01030v4)
- API-Bank level-1 atomic-call correctness (%), open models, CodeAct / JSON / Text: Llama-2-7B 28.8 / 11.3 / 25.8; Llama-2-13B 38.1 / 8.5 / 37.3; Llama-2-70B 35.6 / 14.3 / 37.6; CodeLlama-7B 12.5 / 12.0 / 17.0; CodeLlama-34B 17.3 / 12.0 / 16.8; Mistral-7B 2.5 / 2.3 / 3.0; lemur-70b 58.6 / 46.6 / 56.1. — [arXiv HTML v4](https://arxiv.org/html/2402.01030v4)
- The paper says "CodeAct's improvements are more prominent in open-source models". It attributes open models' low M3ToolEval scores to "weak task-solving capability". — [arXiv HTML v4](https://arxiv.org/html/2402.01030v4)
- CodeActAgent results (MINT in-domain / MINT out-of-domain / M3ToolEval): Llama-2-7B variant 51.3 / 20.4 / 0.0; Mistral-7B variant 57.4 / 32.4 / 12.2. The Mistral-7B-Instruct baseline is 18.8 / 9.7 / 0.0. The paper notes "no improvement is observed for the Llama-2 variant" on M3ToolEval. — [arXiv HTML v4](https://arxiv.org/html/2402.01030v4)

### Inferences
- The "code beats JSON" result holds mainly when the model is already strong at code and the task needs composition (loops, multiple tools, data passing). For weak small models it is not reliable. On the 2024 7B models, much of the gap came from JSON being bad (API-Bank), not from code being good.
- The 2024 open models (Llama-2, Mistral-0.1) are far weaker than Qwen3.5-9B or GLM-x Flash, so these numbers should not be read as a prediction for current small models.

### Gaps
- CodeAct has no results for Qwen, GLM, Gemma or Llama-3. I found no independent replication of M3ToolEval on 2025–26 small models.

## Q2. smolagents CodeAgent vs ToolCallingAgent; Vercel d0; Terminus / Terminal-Bench; mini-SWE-agent vs full harnesses

### Takeaway
Bash-only and code-only harnesses are competitive with, or beat, bespoke-tool harnesses for frontier models (Terminal-Bench Table 2: Terminus 2 is the best scaffold for most Anthropic and Gemini models). For open models, a bash-only harness is usable but often scores below a tuned tool harness: on SWE-bench Verified, Kimi K2 gets 43.8 with mini-SWE-agent vs 65.4 with OpenHands, and Qwen3-Coder-480B gets 55.4 vs 69.6. Those pairs differ in date and config, though, so they are not controlled. Vendor posts (smolagents, Vercel) are directional and have tiny or undisclosed evals.

### Cited Findings
**smolagents (Hugging Face)**
- The launch blog (31 Dec 2024) claims code agents work better ("spoilers: code works better"). The comparison is only a chart image plus a linked notebook. The text gives no numbers and no named models. A reader comment reports Qwen 32B with CodeAgent sometimes calling `final_answer` several times. — [HF blog](https://huggingface.co/blog/smolagents) (self-report, numbers not verifiable from the text)
- smolagents docs justify code actions by citing CodeAct (2402.01030) and two other papers (2411.01747, 2401.00812). The arguments are composability, object management, generality, and code's presence in training data. — [smolagents secure execution docs](https://huggingface.co/docs/smolagents/tutorials/secure_code_execution)

**Vercel d0 (text-to-SQL internal agent)**
- Post by Andrew Qu, 22 Dec 2025. The model was Claude Opus 4.5 running in Vercel Sandbox. The code snippets show the toolset going from 17 tools to 2 (`ExecuteCommand`, `ExecuteSQL`); the title says "80%" and the prose says "a single tool". Results on **5 queries**: success 80% (4/5) → 100% (5/5). Average time 274.8s → 77.4s (3.5x). Average tokens about 102k → 61k (−37%). Average steps about 12 → 7 (−42%). On the worst-case query, the old setup failed after 724s, 100 steps and 145,463 tokens; the new setup took 141s, 19 steps and 67,483 tokens. — [Vercel blog](https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools)
- The author's own caveat: it worked because the semantic-layer files were already good documentation. Without that, raw file access gives "faster bad queries". The post does not caveat its n=5 sample. Secondary write-ups give different figures (e.g. "18 tools", "40% fewer"), so treat only the blog's figures as authoritative. — [Vercel blog](https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools); [ZenML summary](https://www.zenml.io/llmops-database/simplifying-text-to-sql-agents-by-removing-80-of-tools)

**Terminal-Bench / Terminus 2 (independent benchmark paper, arXiv 2601.11868, 17 Jan 2026)**
- Terminus 2 is a "minimal, unopinionated agent". The model emits keystrokes into a tmux shell inside a Docker container and gets the terminal output back. It has no dedicated file-edit or download tools. It can scroll, use arrow keys and launch extra shells. When context nears the limit, a separate model call summarizes it. Trace examples show JSON responses with `analysis`, `plan`, `commands[{keystrokes, duration}]` and `task_complete`. — [arXiv 2601.11868](https://arxiv.org/html/2601.11868)
- TB2 (89 tasks), same model under different harnesses (Table 2):
  - Claude Opus 4.5: Terminus 2 57.8, Claude Code 52.1, OpenHands 51.9
  - Claude Sonnet 4.5: Terminus 2 42.8, mini-SWE-agent 42.5, OpenHands 40.3, Claude Code 40.1
  - Gemini 2.5 Pro: Terminus 2 32.6, mini-SWE-agent 26.1, Gemini CLI 19.6, OpenHands 15.7
  - Claude Haiku 4.5: mini-SWE-agent 29.8, Terminus 2 28.3, Claude Code 27.5, OpenHands 13.3
  - GPT-5.2: Codex CLI 62.9, Terminus 2 54.0
  - GPT-5: Codex CLI 49.6, OpenHands 41.5, Terminus 2 35.2, mini-SWE-agent 33.9
  - GPT-5-Mini: Codex CLI 31.9, OpenHands 27.7, Terminus 2 24.0, mini 22.2
  - GPT-5-Nano: Codex CLI 11.5, OpenHands 9.5, Terminus 2 7.9, mini 7.0

  The paper concludes that model choice usually matters more than the scaffold. — [arXiv 2601.11868](https://arxiv.org/html/2601.11868)
- Open-weight models on TB2: Kimi K2 Thinking 35.7 (Terminus 2); MiniMax M2 30.0; Kimi K2 Instruct 27.8 (Terminus 2) vs 25.6 (OpenHands); GLM 4.6 24.5; Qwen3-Coder-480B 23.9 (Terminus 2) vs 24.3 (OpenHands); gpt-oss-120b 18.7 (Terminus 2) vs 14.2 (mini); **gpt-oss-20b 3.4 (mini) / 3.1 (Terminus 2)**. — [arXiv 2601.11868](https://arxiv.org/html/2601.11868)
- Command error rates under Terminus 2 range from 9.2% (Grok 4) to 26.7% (gpt-oss-120b). The most frequent failure class is invoking executables that are not installed or not on PATH (24.1% of failures), followed by executable runtime failures (9.6%). — [arXiv 2601.11868](https://arxiv.org/html/2601.11868)
- A third-party aggregator lists Qwen3.6-27B at 44.9% on TB2 without naming the harness. Unverified. — [benchmarklist](https://benchmarklist.com/benchmarks/vals_terminal_bench_2/)

**mini-SWE-agent (bash only)**
- The README says "100 line AI agent", "does not have any tools other than bash", and that it does not use the LM tool-calling interface, so it runs "with literally any model". Each action is an independent `subprocess.run` (no persistent shell), which makes swapping in `docker exec` easy. History is linear. Supported environments: local, docker/podman, singularity/apptainer, bubblewrap. It claims ">74%" on SWE-bench Verified (self-report). — [GitHub README](https://github.com/SWE-agent/mini-swe-agent); [docs](https://mini-swe-agent.com/latest/)
- SWE-bench Verified, mini-SWE-agent ("bash only") entries from the official leaderboard data file. The latest entry in the file is dated 2026-02-26, so it may lag the live site. Results run by the SWE-bench/mini-SWE-agent team, so this is a common harness across models.
  - Closed models: Claude 4.5 Opus (high) 76.8; Gemini 3 Flash (high) 75.8; GPT-5.2 (high) 72.8; Claude 4.5 Haiku (high) 66.6; GPT-5 mini 59.8 (2025-08) / 56.2 (2026-02); GPT-5 nano 34.8; GPT-4.1 mini 23.94; Gemini 2.0 Flash 13.52.
  - Open-weight models:
    - MiniMax M2.5 (high) 75.8
    - **GLM 5 (high) 72.8**
    - Kimi K2.5 70.8
    - DeepSeek V3.2 (high) 70.0
    - MiniMax M2 61.0
    - **Devstral Small 2512 56.4** (24B)
    - Qwen3-Coder-480B-A35B 55.4
    - **GLM 4.6 55.4; GLM 4.5 54.2**
    - Kimi K2 Instruct 43.8
    - gpt-oss-120b 26.0
    - Llama 4 Maverick 21.04; Llama 4 Scout 9.06
    - **Qwen2.5-Coder-32B 9.0**

  — [SWE-bench leaderboard data (leaderboards.json)](https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/master/data/leaderboards.json); [swebench.com](https://www.swebench.com/)
- The same file has non-mini entries for some of the same open models. These are not controlled pairs: dates, versions and test-time settings differ.
  - Qwen3-Coder-480B: OpenHands 69.6 vs mini 55.4
  - Kimi K2: OpenHands 65.4 vs mini 43.8
  - GLM-4.5: 64.2 with an undisclosed Z.ai harness (vendor self-report) vs mini 54.2
  - GLM-4.6: 68.2 undisclosed vs mini 55.4
  - Qwen3-Coder-30B-A3B: OpenHands 51.6
  - Devstral Small: 2505 OpenHands 46.8; 2507 SWE-agent 38.0; 2512 mini 56.4 (different checkpoints)
  - Claude 4 Sonnet: OpenHands 70.4 vs mini 64.93
  - GPT-5: OpenHands 71.8 vs mini 65.0

  — [leaderboards.json](https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/master/data/leaderboards.json)

### Inferences
- Across SWE-bench and Terminal-Bench, bash-only scaffolds give up roughly 5–20 points against tuned tool scaffolds on coding tasks. The gap looks larger for open and older models (Kimi K2 −21.6, Qwen3-Coder −14.2) than for frontier Claude (−5.5). On Terminal-Bench, Terminus 2 is at or near the top for most models, so the "generic shell vs bespoke" gap depends on the task family. These are inferences from uncontrolled pairs.
- Results at the small end are weak. Qwen2.5-Coder-32B (9.0) and gpt-oss-20b (3%) barely function in a pure bash loop. A 24B model trained for agentic coding (Devstral Small 2512, 56.4) works well. Agentic post-training matters more than parameter count.
- GLM 5 at 72.8 with bash-only suggests the GLM family follows bash-only protocols well. GLM-5.3-Flash is a different, smaller model, so this does not transfer directly.

### Gaps
- No primary source found for "Vercel d0 18 tools" (the blog shows 17). I found no larger-n d0 evaluation.
- I could not retrieve the smolagents benchmark numbers (chart or notebook only).
- I found no tbench.ai leaderboard rows (page rendered empty). There are no Terminal-Bench results for ≤35B Qwen3/3.5/3.6, GLM Flash or Gemma from a primary source.
- The full SWE-agent (bespoke ACI tools) vs mini-SWE-agent comparison on the same model and date was not found in a primary source.

## Q3. Do small models do worse or better with code actions? Failure modes; sandboxing for an air-gapped, stdlib-only setting

### Takeaway
The most directly relevant evidence is a single small practitioner test on Qwen3.5-9B: code mode scored 28/30 vs 19/30 for tool calling (p=0.012) and used about 45% of the tokens. The gain came from join/aggregate tasks, where the tool-calling model ran out of output tokens counting by hand. Known code-action failure modes include escape/newline errors, misreading return types, and missing executables. For sandboxing, the smolagents maintainers say plainly that no local Python sandbox is fully secure. Process isolation plus resource limits is the baseline.

### Cited Findings
- SOTAAZ Lab blog, 10 Oct 2026 (independent practitioner, not peer-reviewed). Setup: llama.cpp at commit 4da6337, Q4_K_M GGUF, temperature 0, reasoning off, 32K context, 2,048 output tokens per reply. 30 exact-answer tasks over a mock issue tracker (240 issues, 30 users) with 5 tools. Tool-calling mode: up to 40 calls. Code mode: one `run_python` tool, with the 5 tools exposed as Python functions in a separate process, no network, no file writes, a 10s limit, output truncated to 4,000 chars, up to 10 calls.
  - Results, tool calling vs code mode: Qwen3.5-4B 18 vs 22 (p=0.388); **Qwen3.5-9B 19 vs 28 (p=0.012)**; "Qwen3.8-27B" (name as written in the source) 26 vs 30 (p=0.125).
  - Join tasks drive the gap (9B: 2/10 vs 10/10). Single lookups favored tool calling at 4B (10 vs 7).
  - Median tokens on tasks both modes solved: 9B 4,003 vs 1,787.

  — [SOTAAZ](https://sotaaz.com/post/codemode-small-models-en)
- Failure modes in that test: 8 tool-calling failures at 4B and 8 at 9B hit the 2,048-token limit while hand-counting. 3 code-mode answers at 4B were correct but missing the `ANSWER:` line. The 9B in code mode misread a return type (treated `comments` count as a list) until return structures were added to tool docs. The authors' caveats: n=30, one run each; the code prompt explicitly told the model to compute in code; grading leniency was added post hoc (4B code mode 22→25 under the lenient rule); the result is sensitive to the token limit. Syntax-error counts were not reported. — [SOTAAZ](https://sotaaz.com/post/codemode-small-models-en)
- "The Bitter Lesson of Tool Calling" (PwC authors, arXiv 2608.06370, 6 Aug 2026). Programmatic tool calling (the model writes a Python script calling typed stubs, run in a native shell subprocess) vs JSON on a 309-entry BFCL v4 subset, 14 **closed** models, temperature 0. 11/14 models were ≥ the JSON baseline. Gains included GPT-5.6-Sol/Terra +10.6 and Claude Sonnet 4.6 +6.5. Losses: GPT-4o −26.9, GPT-5.4-mini −24.3, GPT-4.1 −19.8. All three losses came from writing literal `\n` escapes instead of newlines, which caused syntax errors. GPT-5-nano, the smallest, did not show this failure (+1.6). Runtime errors scored zero. The paper evaluates no open-weight or small open models. — [arXiv 2608.06370](https://arxiv.org/html/2608.06370v1)
- On TB2, command failures (missing executables, PATH) dominate. gpt-oss-120b has the highest command error rate (26.7%). — [arXiv 2601.11868](https://arxiv.org/html/2601.11868)
- In CodeAct 2024, Mistral-7B and Llama-2-7B got 0.0 with code on M3ToolEval, at or below their JSON/Text scores. — [arXiv HTML v4](https://arxiv.org/html/2402.01030v4)
- smolagents `LocalPythonExecutor` walks the AST and executes operation by operation:
  - imports are blocked unless allow-listed, and submodules need explicit allow-listing (e.g. `random._os` is blocked)
  - elementary operations are capped, e.g. "Maximum number of 1000000 iterations in While loop exceeded"
  - undefined operations raise errors

  Its warning: "no local python sandbox can ever be completely secure"; allowed packages can still fill the disk. The recommended Docker settings are `mem_limit="512m"`, `cpu_quota=50000`, `pids_limit=100`, `no-new-privileges`, `cap_drop=["ALL"]`, `user nobody`. The best-practice list is: memory and CPU limits, execution timeouts, minimal privileges, disable unnecessary network, secrets via environment variables, minimal dependencies, cleanup. — [smolagents docs](https://huggingface.co/docs/smolagents/tutorials/secure_code_execution)
- mini-SWE-agent's stateless `subprocess.run` per action is explicitly motivated by easier sandboxing: the executor can be swapped for docker exec, bubblewrap, and so on. — [GitHub README](https://github.com/SWE-agent/mini-swe-agent)
- Vercel ran d0's bash agent inside Vercel Sandbox (Firecracker microVMs, per Vercel docs). It gave the agent read access to semantic-layer files, not arbitrary systems. — [Vercel blog](https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools)

### Inferences (for a stdlib-only harness: GLM-5.3-Flash via gateway + Qwen3.5-9B local, Windows, Python 3.12)
- Implementing a single `run_python` action with stdlib only is feasible:
  - `subprocess.run([sys.executable, "-I", "-c", code], timeout=..., capture_output=True, cwd=<scratch dir>)`
  - truncate output to a fixed cap (about 4k chars, as in the SOTAAZ setup)
  - pass a minimal `env` with no API key
  - expose task functions as an injected stub module

  On Windows there is no stdlib `resource` (rlimit) module. CPU and memory limits need a timeout plus a Job Object, which takes ctypes. A Python `-I` subprocess is not a security boundary, so treat it as accident-prevention, not containment. This follows from the smolagents warning.
- An AST allow-list pre-check (stdlib `ast`) can cheaply reject `os`/`subprocess`/`socket` imports and dunder access before execution, in the spirit of `LocalPythonExecutor`. It is not airtight.
- Small-model guardrails suggested by the failure modes:
  - normalize literal `\n` in code payloads, or request code in a fenced block rather than a JSON string. JSON-string escaping is exactly what broke GPT-4o/4.1 in 2608.06370.
  - document function return types in the prompt (SOTAAZ fix)
  - enforce an explicit final-answer marker, with lenient parsing
  - list which executables or modules exist, since "not installed or not on PATH" is the top TB2 failure class
- Expect code actions to help most on aggregate/join/multi-step data tasks, and to be neutral or harmful on single lookups for ≤4B models. Plan an A/B in the existing bench rather than assuming.

### Gaps
- I found no primary data on code-action syntax-error rates for Qwen3/3.5 or GLM Flash, and nothing on GLM-5.3-Flash at all.
- I found no study of Windows-specific sandboxing for agent code execution.

## Q4. 2025–2026 papers comparing tool-call formats vs code actions specifically for small models

### Takeaway
I found no peer-reviewed 2025–2026 paper that isolates code actions vs JSON tool calls on ≤35B open models. The closest evidence:
- arXiv 2608.06370 (Aug 2026): closed models only, mostly positive, with large losses from escape errors.
- The SOTAAZ blog test (Oct 2026): Qwen3.5 4B/9B/27B, n=30, positive at 9B.
- Terminal-Bench (Jan 2026) and SWE-bench bash-only (through Feb 2026): show which open models function in pure shell loops.

### Cited Findings
- arXiv 2608.06370: 14 closed models (5 Anthropic, 9 OpenAI), no open models; the BFCL v4 categories and per-model deltas are listed under Q3. — [arXiv 2608.06370](https://arxiv.org/html/2608.06370v1)
- arXiv 2609.07370 benchmarks JSON (MCP-style) tool calling in sub-2B open models on CPU. Qwen2.5-1.5B reached 75–79% end-to-end; Phi-1.5 and Pythia-1.4B were near 0% under greedy decoding. It does not test code actions. Figures come from the search snippet; I did not open the paper. — [arXiv 2609.07370](https://arxiv.org/html/2609.07370v1) (unverified beyond snippet)
- Quasar (arXiv 2506.12202, 2025) proposes a dedicated language for LLM code actions. It cites prior work that code actions improve performance, latency and token use. I did not verify its own small-model results. — [arXiv 2506.12202](https://arxiv.org/pdf/2506.12202) (not read in full)
- SOTAAZ Qwen3.5 test: see Q3. — [SOTAAZ](https://sotaaz.com/post/codemode-small-models-en)

### Inferences
- The evidence base for "code beats JSON for small models" is thin and mostly informal. The team's own pre-registered A/B (the BFCL multi-turn adapter already in `bench/`) would be among the more rigorous data points available for GLM-Flash/Qwen3.5-9B.
- Positive results for code depend on three things: (a) tasks with real composition, (b) a capped and truncated execution output, and (c) prompts that tell the model to compute in code. All three should be held constant or manipulated deliberately in any A/B.

### Gaps
- No primary source found for GLM-4.x Flash, Gemma 3/4, or Llama 3.x 8B under code vs JSON action formats in 2025–26.
- I did not open the full papers for arXiv 2609.07370 or Quasar.
