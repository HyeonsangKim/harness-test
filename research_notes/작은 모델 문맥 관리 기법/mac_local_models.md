# Open-weight LLMs for local agent-harness testing on Apple Silicon (as of 2026-10-20)

Tags: [V] = checked against a primary source (vendor HF card / official repo / GitHub issue) this session; [S] = secondary source (guide, aggregator, community benchmark); [U] = unverified this session (from prior knowledge or inference). Memory figures marked "≈" are my own estimates (4-bit ≈ 0.55–0.6 GB per billion params + KV cache), not measured, unless a source is given.

Research budget note: ~15 tool calls. Primary-source checks covered Qwen (3.5/3.6/3.8), GLM (4.7-Flash, 5.3-Flash, zai-org org page), Gemma 4 (Google docs via search), EXAONE 4.5, Kanana-2, llama.cpp issues, and Mac throughput. Gaps remain for gpt-oss, Mistral/Devstral, Llama, Phi, Granite, SmolLM, HyperCLOVA X SEED, A.X, Solar, plus the current serving-stack docs for Ollama, LM Studio and mlx-lm. All of these are listed under Gaps.

## Q1. Which model families are current and capable as of Oct 2026, and which have good native tool calling?

### Takeaway
The current "worth testing" core is **Qwen3.6-35B-A3B / Qwen3.6-27B / Qwen3.8-27B** (Apache-2.0, strong agentic scores), **GLM-4.7-Flash 30B-A3B** (MIT, τ²-Bench 79.5, the only small GLM-family model), **Gemma 4** (E2B/E4B/12B/26B-A4B/31B, native tool use), and the **Qwen3.5 small dense models (0.8B–9B)** for weak-model stress tests. Z.ai has **not** released a small GLM-5.x model. The production model GLM-5.3-Flash (≈321B) is the smallest GLM-5 variant and only fits on the largest Macs with aggressive quantization. For Korean, **Kanana-2-30B-A3B** (Kakao) and **EXAONE 4.5 33B** (LG) are the notable open models. EXAONE 4.5 carries a **non-commercial (NC)** license, and its Korean scores are actually *below* Qwen3.5-27B's on LG's own table.

### Cited Findings

**Qwen family (Alibaba)**
- Official release timeline [V]: Qwen3.5-397B-A17B (2026-02-16); Qwen3.5-122B-A10B, 35B-A3B and 27B (2026-02-24); Qwen3.5-9B/4B/2B/0.8B (2026-03-02); Qwen3.6-35B-A3B (2026-04-16); Qwen3.6-27B (2026-04-22); Qwen3.8-2.4T-A95B (2026-08-12); Qwen3.8-27B (2026-08-14). No small Qwen3.8 below 27B is listed. A "Qwen3.7-Plus" appears only as a comparison model, apparently API-only. — [QwenLM GitHub](https://github.com/QwenLM/Qwen3.8)
- Qwen3.5 is supported by mlx-lm (text) and mlx-vlm, and by llama.cpp (text + vision) [V]. — [QwenLM GitHub](https://github.com/QwenLM/Qwen3.8)
- Qwen3.5 family is Apache-2.0. 35B-A3B is a MoE + Gated DeltaNet hybrid; 9B and 27B are dense. The 9B is described as the top sub-10B model on the Artificial Analysis Intelligence Index [S]. — [Artificial Analysis](https://artificialanalysis.ai/articles/qwen3-5-small-models); [Unsloth Qwen3.5 docs](https://unsloth.ai/docs/models/qwen3.5)
- **Qwen3.6-35B-A3B** [V]: 35B total / 3B active (256 experts, 8 routed + 1 shared), 262,144 native context (YaRN to ~1M), Apache-2.0. Thinking is ON by default; disable with `chat_template_kwargs: {"enable_thinking": false}`. Supports "preserve thinking" across turns. Recommended tool parser: `qwen3_coder` (vLLM ≥0.19 / SGLang ≥0.5.10). Agentic scores: TAU3-Bench 67.2, MCP-Atlas 62.8, Terminal-Bench 2.0 51.5, SWE-bench Verified 73.4, MCPMark 37.0. BFCL/tau2 are not reported. No Korean claim. — [HF card Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
- Same card's comparisons [V]: Qwen3.5-27B scores TAU3 68.4, MCP-Atlas 68.4, Terminal-Bench 2.0 41.6, SWE-V 75.0. Gemma 4 31B scores TAU3 67.5, MCP-Atlas 57.2, TB2 42.9, SWE-V 52.0. — [HF card Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
- **Qwen3.8-27B** [V]: 27B dense (28B with vision encoder, includes MTP), 262,144 context, Apache-2.0. Controls: `enable_thinking` toggle, `reasoning_effort` (xhigh default / medium / low), `preserve_thinking` (default on). Terminal-Bench 2.1 73.0 (vs Qwen3.6-27B 63.4), SWE-bench Pro 61.7 (vs 53.5). No BFCL/tau, no multilingual claims on the card. — [HF card Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B). The serve examples use `--tool-call-parser qwen3_coder --reasoning-parser qwen3` [V]. — [QwenLM GitHub](https://github.com/QwenLM/Qwen3.8)

**GLM family (Z.ai / Zhipu), same family as production**
- **GLM-4.7-Flash** [V]: 30B total / ~3B active MoE (31B in safetensors metadata), MIT license, tagged English/Chinese only. Vendor benchmarks vs Qwen3-30B-A3B-Thinking-2507 / gpt-oss-20b: τ²-Bench **79.5** / 49.0 / 47.7; SWE-bench Verified 59.2 / 22.0 / 34.0; BrowseComp 42.8 / 2.29 / 28.3. No BFCL. vLLM: `--tool-call-parser glm47 --enable-auto-tool-choice --reasoning-parser glm45`. Recommends "Preserved Thinking" for multi-turn agentic tasks. Context is not stated on the card; default max_new_tokens is 131,072. — [HF card GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash); [SGLang cookbook](https://docs.sglang.io/cookbook/autoregressive/GLM/GLM-4.7-Flash)
- GLM-4.7-Flash's tool-call format is XML-ish: `<tool_call>` with `<arg_key>`/`<arg_value>`. This differs from Qwen/Hermes JSON, and it is the same style as the GLM-5 line [S]. — [vllm-mlx tool-calling guide](https://vllm-mlx.is-a.dev/guides/tool-calling/)
- Unsloth recommends `--temp 0.7 --top-p 1.0` for tool calling and `--min-p 0.01` on llama.cpp [S]. — [Unsloth GLM-4.7-Flash](https://unsloth.ai/docs/models/tutorials/glm-4.7-flash)
- zai-org HF org (visible list): GLM-5.3-Flash (321B, image-text-to-text, updated ~4 days ago, i.e. mid-Oct 2026), GLM-5.3 (753B), GLM-5.2 (753B, Sep 1), GLM-5 (754B, Aug 11), GLM-4.1V-9B-Thinking (10B). **No GLM-5.x Air or sub-100B text model is visible** [V, partial: only 10 of 154 models were shown]. — [zai-org on HF](https://huggingface.co/zai-org)
- GLM-5.3-Flash: 320B total / 18B active, MIT, natively multimodal. An aggregator lists 1M context [S]. A third-party GGUF exists (AtomicChat/GLM-5.3-Flash-GGUF) [S]. — [AtomicChat GGUF](https://huggingface.co/AtomicChat/GLM-5.3-Flash-GGUF); [Benchgen](https://benchgen.com/models/zhipu-ai/glm-5-3-flash); [models.dev](https://models.dev/models/zhipuai/glm-5.3-flash/)

**Gemma 4 (Google)**
- Five sizes: E2B (2.3B effective / 5.1B with embeddings), E4B (4.5B eff / 8B), 12B (11.95B, added ~June 2026), 31B dense (30.7B), 26B-A4B MoE (25.2B total / 3.8B active). Context is 128K for E2B/E4B and 256K for the rest. Every size ships a draft model for speculative decoding. Native structured tool use; thinking mode at all sizes [V via Google docs as surfaced in search; the thinking-at-all-sizes claim is S]. — [Gemma 4 model overview](https://ai.google.dev/gemma/docs/core); [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4); [HF blog](https://huggingface.co/blog/gemma4)
- License: described as Apache-2.0 by secondary sources [S]. Needs confirmation on Google's terms page. — [MindStudio](https://www.mindstudio.ai/blog/what-is-gemma-4-google-apache-open-weight-model) (note: this same article gets the sizes wrong, so treat it as low quality)

**Korean models**
- **EXAONE 4.5 33B** (LG, 2026-04-09) [V]: 31.7B LM + 1.29B vision encoder, 262,144 context, license **"EXAONE AI Model License 1.2 – NC"** (non-commercial). Thinking is on by default (`enable_thinking=False` to disable). vLLM `--tool-call-parser hermes --reasoning-parser qwen3`. Official GGUF builds exist for llama.cpp, Ollama and LM Studio; MLX is not mentioned. Korean scores (EXAONE 4.5 / Qwen3.5-27B): KMMLU-Pro 67.6 / **73.0**; KoBALT 52.1 / **54.9**; KMMMU 42.7 / **51.7**; KRETA 91.9 / **96.5**. τ²: Retail 77.9 / 84.7, Airline 56.5 / 67.5, Telecom 73.0 / 99.3. **On LG's own table, Qwen3.5-27B beats EXAONE 4.5 on every Korean and agentic metric shown.** — [HF card EXAONE-4.5-33B](https://huggingface.co/LGAI-EXAONE/EXAONE-4.5-33B); [EXAONE 4.5 tech report](https://arxiv.org/html/2604.08644v1)
- K-EXAONE (236B total / 23B active) also exists. It is too large for this purpose [S]. — [llmdb](https://llmdb.com/models/exaone-4-5)
- **Kanana-2-30B-A3B** (Kakao), Instruct and Thinking variants [V]: 30B / 3B active, MLA + MoE, **32,768 native context** (YaRN to 128K), "Kanana License" (terms not summarized on the card). The card positions it explicitly for agentic AI and tool calling. Instruct-variant numbers (Kanana-2 / Qwen3-30B-A3B-2507): KMMLU 67.32 / 67.56; HAERAE-Bench 75.57 / 53.41; KoMT-Bench 8.24 / 8.49. BFCL-v3 Live 74.30 / 73.93; BFCL-v3 Multi-Turn 35.38 / 38.77. Thinking variant: BFCL Live 75.6 vs 82.9 for Qwen3-30B-A3B-Thinking-2507; Multi-Turn 34.3 vs 53.6. Parser: vLLM `hermes` + `deepseek_r1` reasoning parser; SGLang `qwen`. **No GGUF/MLX/Ollama mentioned on the card.** — [HF card kanana-2-30b-a3b-thinking](https://huggingface.co/kakaocorp/kanana-2-30b-a3b-thinking)
- Kanana-2 small sizes also exist: kanana-2-3b-instruct and kanana-2-1.3b-instruct [V, existence only]. — [HF kanana-2-3b-instruct](https://huggingface.co/kakaocorp/kanana-2-3b-instruct); [HF kanana-2-1.3b-instruct](https://huggingface.co/kakaocorp/kanana-2-1.3b-instruct)

**Apple Silicon throughput**
- Qwen3.6-35B-A3B on M4 Max under oMLX (4-bit, community runs): about 109 tok/s generation at 1k context on 36GB/48GB machines, with a peak memory of 19.2 GB. About 95 tok/s on a 128GB 40-core machine, dropping to 64 tok/s at 64k context. Batch 4 reaches 271 tok/s aggregate [S, community-measured]. — [oMLX benchmark](https://omlx.ai/benchmarks/fqabp6rx); [oMLX benchmarks list](https://omlx.ai/benchmarks/8r66ysnf)
- A lower estimate of ~42 tok/s (Q4_K_M, M4 Max 48GB) is a bandwidth-model estimate, not a measurement [S]. — [LLMCheck](https://llmcheck.net/models/qwen-36-35b-a3b-on-m4-max/)
- Qwen3.5 reports 70–92 tok/s on M3/M4 [S]. — [Techplained](https://www.techplained.com/qwen-3-5-apple-silicon)

### Inferences

**Shortlist by Mac RAM tier.** Memory figures are ≈4-bit weight sizes. macOS caps GPU-wired memory at roughly 65–75% of RAM by default, adjustable with `sysctl iogpu.wired_limit_mb` [U].

| RAM | Candidates (4-bit) | ≈ weights | Notes |
|---|---|---|---|
| **16GB** | Qwen3.5-9B (≈5.5GB), Qwen3.5-4B (≈2.5GB), Gemma 4 E4B (≈5GB with embeddings), Gemma 4 12B (≈7GB), Kanana-2-3B (≈2GB) | 2–7GB | The 35B-A3B MoE models do not fit. A 9B dense model is the practical ceiling with room left for KV cache. |
| **24GB** | Qwen3.6-27B / Qwen3.8-27B dense (≈15–16GB), Gemma 4 26B-A4B (≈15GB), Gemma 4 12B | 15–16GB | Tight. Keep context ≤32K. Dense 27B runs maybe ~15–25 tok/s on Pro-class chips [U]. |
| **32–36GB** | **Qwen3.6-35B-A3B** (19.2GB peak measured), **GLM-4.7-Flash** (≈17–18GB), Kanana-2-30B-A3B (≈17GB, needs your own MLX/GGUF conversion or a community one), EXAONE 4.5 33B (≈19GB, NC license), Gemma 4 31B (≈18GB) | 17–20GB | The sweet spot. A3B MoE models run ~100 tok/s on M4 Max [S]. |
| **48GB** | Same as above, at Q6/Q8 (35B at 8-bit ≈ 37–40GB) or with long context (64–128K) | — | Higher quantization means fewer tool-call format errors [U]. |
| **64GB** | Q8 of all 30–35B models; Qwen3.5-122B-A10B at 3-bit (≈50GB) [U on fit] | — | |
| **96–128GB** | Qwen3.5-122B-A10B 4-bit (≈65–70GB); **GLM-5.3-Flash** only at ~2–3-bit (320B × ~2.5–3 bits ≈ 100–120GB) [U: fit and quality unverified] | — | The only way to run the *actual* production model locally. A 4-bit build (≈180GB) does not fit. |

**Recommendations**
- **Harness-dev model:** Qwen3.6-35B-A3B at 4-bit on 32GB+ machines (fast, Apache-2.0, strong MCP and terminal agent scores, `enable_thinking:false` toggle). On 16–24GB machines, use Qwen3.5-9B instead.
- **Same-family-as-GLM transfer model:** GLM-4.7-Flash 30B-A3B. It is the only small GLM-family text model, and it shares the GLM-style XML tool-call format, the `glm45` reasoning parser lineage and the "preserved thinking" convention with GLM-5.x. It also has the best vendor τ²-Bench score of the ~30B class (79.5).
- **Weak small model for stress-testing recovery:** Qwen3.5-4B (or 2B/0.8B for extreme cases), or Gemma 4 E4B as a second family with a different template.
- **Korean specialist:** Kanana-2-30B-A3B-Instruct. It beats Qwen3-30B on HAERAE (75.6 vs 53.4), has a commercially usable (custom) license, and has BFCL Live parity. EXAONE 4.5 is usable only for internal non-commercial testing, and Qwen3.5-27B outscores it on Korean in LG's own table. Note that for Korean *plus* tool calling, Qwen3.5/3.6-27B may simply be the better all-rounder.

### Gaps
- **gpt-oss-20b/120b, Mistral Small 3.x/4 / Devstral / Ministral, Llama 4 / 3.x, Phi-4, Granite 4, SmolLM3, DeepSeek distills:** not researched this session. From prior knowledge [U]: gpt-oss-20b (21B / 3.6B active, Apache-2.0, harmony format, ~13GB MXFP4, fits 16–24GB) is widely used with good tool calling, but its harmony-format parsing has historically been fragile in llama.cpp and Ollama. GLM-4.7-Flash's card shows it far behind on τ²-Bench (47.7). Llama 4 Scout (109B total) is too big for most tiers and weak at tool calling. Verify all of these before including them.
- **HyperCLOVA X SEED (Naver), A.X 4.x (SKT), Solar Pro (Upstage):** not checked. Current versions, licenses and tool support are unknown.
- **Kanana-2 release date, Kanana License terms, and GGUF/MLX availability:** not confirmed.
- **Gemma 4 license and Korean ability:** not confirmed from a primary source. No Korean benchmark was found for Gemma 4, GLM-4.7-Flash, or Qwen3.6/3.8 (the Qwen3.5-27B Korean numbers come only from LG's EXAONE card).
- **Horangi/Nejumi and Open Ko-LLM leaderboards:** not consulted.
- **BFCL leaderboard numbers** for the 2026 models: not found on the vendor cards checked.
- **GLM-5.3-Flash low-bit quant sizes and quality, and whether llama.cpp/MLX support its architecture:** unverified.

## Q2. Which Mac serving stacks give an OpenAI-compatible endpoint with reliable tool calling, tool_choice=required and reasoning fields?

### Takeaway
llama.cpp `llama-server --jinja` is the most transparent option, but it has a history of model-specific parser bugs. Gemma 4 and GLM-4.7-Flash have had several. Ollama's `tool_choice` support is murky. Official mlx-lm tool-call support was not confirmed. vllm-mlx explicitly ships `qwen` and `glm47` parsers. Expect per-model breakage, so the harness should tolerate tool calls that arrive as content text.

### Cited Findings
- llama.cpp + Gemma 4: several reported bugs. One is a 500 error, "output does not match expected peg-gemma4 format", when used with a draft model (#25072, closed not-planned). In another, a valid tool call was returned as plain `content` (#22786, closed). A third left stray special tokens in tool-call arguments (#21316, fixed via PR #21327) [V]. — [#25072](https://github.com/ggml-org/llama.cpp/issues/25072); [#22786](https://github.com/ggml-org/llama.cpp/issues/22786); [#21316](https://github.com/ggml-org/llama.cpp/issues/21316)
- llama.cpp + GLM-4.7-Flash: a grammar-trigger loop caused memory growth and gibberish (#19068, closed not-planned) [V]. Unsloth re-uploaded all GLM-4.7-Flash quants on Jan 21 after a llama.cpp looping fix, and users reported better tool calls after updating [S]. — [#19068](https://github.com/ggml-org/llama.cpp/issues/19068); [Unsloth discussion](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/10)
- Qwen3.6 on llama.cpp needs `--jinja`, or raw `<tool_call>` tags leak into the output. One guide suggests disabling speculative decoding if problems persist, and MTP support is tracked in PR #22673 [S]. — [netclaw troubleshooting](https://netclaw.dev/troubleshooting/llama-cpp/)
- A community gist documents fixes for Gemma 4 26B tool calling on macOS llama.cpp [S]. — [gist](https://gist.github.com/daniel-farina/87dc1c394b94e45bb700d27e9ea03193)
- Ollama `tool_choice`: a Feb 2026 issue says `/v1/chat/completions` accepts `"required"` and `"auto"` [S]. A 2026 comparison article claims there is no support, but that claim is dated "as of 2024" [S, stale]. llama-stack found that `tool_choice="none"` was ignored (Apr 2025) and worked around it by stripping `tools` from the request [S]. — [claudeissues](https://claudeissues.com/issue/22879-feature-request-add-tool-choice-config-per-model-provider-for-ollama-tool-callin); [glukhov.org](https://www.glukhov.org/llm-hosting/comparisons/hosting-llms-ollama-localai-jan-lmstudio-vllm-comparison/); [llama-stack commit](https://git.kvant.cloud/phoenix-oss/llama-stack/src/commit/934446ddb4cf8801e011083fd6ae8d4a65724831/llama_stack/providers/remote/inference)
- mlx-lm server: a Medium guide (undated) says the tool-use PR (#217) was not yet merged. Current status is unknown [S]. vllm-mlx (third-party) provides `qwen`, `glm47` and `auto` tool parsers and shows an MLX GLM-4.7-Flash served with the `glm47` parser [S]. — [Medium](https://medium.com/@levchevajoana/a-job-postings-tool-a-guide-to-mlx-lm-server-and-tool-use-with-the-openai-client-edb9a5d75b4c); [vllm-mlx tool calling](https://vllm-mlx.is-a.dev/guides/tool-calling/)
- oMLX is an MLX server used for the throughput benchmarks above. Its tool-calling support was not checked [S]. — [oMLX](https://omlx.ai/benchmarks/fqabp6rx)
- Reasoning parsers per model (relevant to `reasoning_content` fields): Qwen3.6/3.8 use `qwen3`, GLM-4.7-Flash uses `glm45`, EXAONE 4.5 uses `qwen3`, and Kanana-2 uses `deepseek_r1` (vLLM) [V]. — vendor cards linked in Q1.

### Inferences
- Harness design implications: (1) parse tool calls that come back inside `content`, covering both Qwen-style `<tool_call>{json}</tool_call>` and GLM-style `<arg_key>`/`<arg_value>`; (2) don't rely on `tool_choice="required"` or `"none"` being enforced locally; validate and re-prompt instead; (3) handle `reasoning_content` being present, absent or inlined as `<think>` tags depending on the server; (4) pin server versions per model.
- For GLM-family transfer testing, vllm-mlx's `glm47` parser or llama.cpp `--jinja` (recent build plus re-downloaded quants) are the candidate paths. Test both [U].

### Gaps
- Official docs for current Ollama, LM Studio and mlx-lm tool-calling behavior (tool_choice, parallel tool calls, streaming tool-call deltas, reasoning fields) were not fetched.
- LM Studio specifics are entirely unchecked.
- "vLLM-metal" (the official vLLM Apple backend) was not researched. vllm-mlx is a separate community project.
- Measured tok/s for GLM-4.7-Flash, Gemma 4, Kanana-2 and EXAONE 4.5 on Apple Silicon: none found this session. Dense 27B figures are also missing.
