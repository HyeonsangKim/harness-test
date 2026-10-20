# Fact-check of `mac_local_models.md` (primary sources, 2026-10-20)

Method: I fetched HF model cards, `config.json` and `chat_template.jinja` files and the HF API (`createdAt`, license, safetensors totals) directly. I also used the vendor GitHub README (QwenLM), source trees (vLLM, llama.cpp, mlx-lm), the official docs of Z.ai, Ollama and LM Studio, the ollama.com library pages and GitHub issue search. The notes file was used only to find URLs.

## Summary

| Verdict | Count |
|---|---|
| CONFIRMED | 23 |
| PARTLY (right, but incomplete or overstated) | 8 |
| WRONG | 3 |
| UNVERIFIABLE from a primary source | 2 |

### Corrections to apply
1. **Qwen3.5 does report BFCL and τ² numbers.** The Gaps line "BFCL … not found on the vendor cards" is wrong for Qwen3.5. Every Qwen3.5 card has BFCL-V4 and TAU2-Bench rows (all in thinking mode):

   | Model | BFCL-V4 | TAU2 |
   |---|---|---|
   | 122B-A10B | 72.2 | 79.5 |
   | 27B | 68.5 | 79.0 |
   | 35B-A3B | 67.3 | 81.2 |
   | 9B | 66.1 | 79.1 |
   | 4B | 50.3 | 79.9 |
   | 2B | 43.6 | 48.8 |
   | 0.8B | 25.3 | 11.6 |

   The Qwen3.6-35B-A3B card does not report BFCL or tau2 (it reports TAU3); that part of the notes is correct.
2. **mlx-lm has official tool-call parsers.** The notes say "official mlx-lm tool-call support was not confirmed". `ml-explore/mlx-lm/mlx_lm/tool_parsers/` ships `qwen3_coder.py`, `glm47.py` and `gemma4.py`. GLM-4.7 fallback handling was fixed in Feb 2026 (#792) and tool-name trimming in Aug 2026 (#1756). The Medium article about "PR #217 not merged" is out of date.
3. **Ollama `tool_choice` is not supported.** The official OpenAI-compatibility doc lists `tools` as supported and `tool_choice` as **not supported** (`[ ] tool_choice`). The doc does list `reasoning_effort` and `reasoning.effort` as supported. Drop the secondary "Feb 2026 issue says `required` is accepted" claim, or mark it as contradicted.
4. **GLM-4.7-Flash context.** The card does not state a context length, but `config.json` has `max_position_embeddings: 202752`. Z.ai docs list **200K context / 128K max output**. The figure 131,072 is the card's *evaluation* `max new tokens`, not a default.
5. **Small Qwen3.5 models don't think by default.** Qwen3.5-0.8B and 2B run in **non-thinking mode by default**. The 4B and larger models, and Qwen3.6, think by default. The `enable_thinking` switch is the same for all of them.
6. **Kanana-2 license.** "Commercially usable" is overstated. The Kanana License lets you use the model in your own services. You need a separate commercial licence from Kakao to resell API, cloud or remote access, to ship it in SI or on-prem deployments, to embed it on-device for third parties, or if you have more than 10M MAU. Redistribution requires a "Powered by Kanana" notice and a "Kanana" name prefix on derived models.
7. **Kanana-2 has January 2026 refreshes the notes miss.** Kakao released `kanana-2-30b-a3b-{instruct,thinking}-2601` on 2026/01/15. Instruct-2601 scores BFCL-v3 Live 76.66 and Multi-Turn 38.63. Thinking-2601 scores Live 75.9 and Multi-Turn 43.7. Prefer the 2601 builds.
8. **Kanana-2 GGUF/MLX.** Only a few community GGUFs exist (e.g. `mykor/…-thinking-2601-GGUF`, `deul/…-instruct-2601-GGUF`, `ohora23/…-Instruct-GGUF`). I found no MLX build and no Ollama library entry (`ollama.com/library/kanana` returns 404).
9. **EXAONE 4.5 runtimes.** The official `LGAI-EXAONE/EXAONE-4.5-33B-GGUF` repo exists. Its card names only **llama.cpp (build b9453+)**, not Ollama or LM Studio. There is no `ollama.com/library/exaone4.5` page.
10. **zai-org dates are wrong as release dates.** HF `createdAt` gives GLM-5 = 2026-02-11, GLM-5.1 = 2026-04-03, GLM-5.2 = 2026-06-16, GLM-5.3 and 5.3-Flash = 2026-08-25. The notes' "GLM-5 Aug 11 / GLM-5.2 Sep 1" look like last-updated dates.
11. **"Only small GLM-family model" needs a qualifier.** GLM-4.6V-Flash (about 9B, VLM, Dec 2025) and AutoGLM-Phone-9B also exist. GLM-4.7-Flash is the only *recent small text/agentic* GLM.
12. **Mac speed is community data only.** The ~109 tok/s figure is community oMLX data, not a primary benchmark. 32-core 36GB M4 Max runs vary: one reached 109.9 tok/s at 1k context (2026-04-25), another only 64.0 tok/s (2026-05-12). Report a range of about 60–110 tok/s.
13. **Gemma 4 license, tool use and thinking are primary-confirmed.** Apache-2.0 (license_link `ai.google.dev/gemma/docs/gemma_4_license`), native function calling and configurable thinking on all models are now confirmed from the HF card. Upgrade these from [S] to [V].

## Per-claim results

### 1. GLM-4.7-Flash (zai-org)
| # | Claim | Verdict | Evidence / source |
|---|---|---|---|
| 1a | Exists; 30B total / ~3B active MoE; MIT | CONFIRMED | Card: "GLM-4.7-Flash is a 30B-A3B MoE model"; `license: mit`; safetensors total 31.2B; config: 64 routed experts, 4 per token, `glm4_moe_lite`. Repo created 2026-01-19. https://huggingface.co/zai-org/GLM-4.7-Flash |
| 1b | τ²-Bench 79.5; SWE-bench Verified 59.2 (vs Qwen3-30B-A3B-Thinking-2507 49.0/22.0, GPT-OSS-20B 47.7/34.0); BrowseComp 42.8 | CONFIRMED | Same card, benchmark table |
| 1c | Context length "not stated on card" | PARTLY | Card is silent, but `config.json` `max_position_embeddings` = 202,752. Z.ai docs: 200K context, 128K max output. https://huggingface.co/zai-org/GLM-4.7-Flash/blob/main/config.json ; https://docs.z.ai/guides/llm/glm-4.7 |
| 1d | vLLM `--tool-call-parser glm47 --enable-auto-tool-choice --reasoning-parser glm45` | CONFIRMED | The card's vLLM and SGLang blocks use `glm47` for tools and `glm45` for reasoning. In vLLM main, `glm45` and `glm47` are aliases for the same `Glm47Moe…` reasoning and tool parsers, so either name works. https://github.com/vllm-project/vllm/blob/main/vllm/reasoning/__init__.py |
| 1e | Tool-call text is `<tool_call>name<arg_key>…</arg_key><arg_value>…</arg_value></tool_call>`, same style as GLM-5 | CONFIRMED (now primary) | `chat_template.jinja` of GLM-4.7-Flash. GLM-5 and GLM-5.3-Flash templates also use `<arg_key>`. https://huggingface.co/zai-org/GLM-4.7-Flash/blob/main/chat_template.jinja |
| 1f | Recommends Preserved Thinking for multi-turn agentic tasks | CONFIRMED | Card: "For multi-turn agentic tasks (τ²-Bench and Terminal Bench 2), please turn on Preserved Thinking mode" |
| 1g | GGUF / MLX / Ollama / LM Studio availability | CONFIRMED | GGUF: `ggml-org/GLM-4.7-Flash-GGUF`, `unsloth/…`, `bartowski/…`, `lmstudio-community/GLM-4.7-Flash-GGUF`. MLX: `mlx-community/GLM-4.7-Flash-{4,5,6,8}bit`, `lmstudio-community/GLM-4.7-Flash-MLX-{4,6,8}bit`. Ollama: https://ollama.com/library/glm-4.7-flash (tags q4_K_M, q8_0, bf16; capabilities "tools", "thinking") |
| 1h | "The only small GLM-family model" | PARTLY | GLM-4.6V-Flash (VLM) and AutoGLM-Phone-9B also exist. https://huggingface.co/zai-org |

### 2. Qwen3.5 / Qwen3.6
| # | Claim | Verdict | Evidence / source |
|---|---|---|---|
| 2a | Release timeline: 397B 02-16; 122B/35B/27B 02-24; 9B/4B/2B/0.8B 03-02; 3.6-35B-A3B 04-16; 3.6-27B 04-22 (3.8: 08-12, 08-14) | CONFIRMED | QwenLM README news list. (HF repos for the small models were created 02-27/02-28; the public release was 03-02.) https://github.com/QwenLM/Qwen3.8 |
| 2b | Qwen3.5 sizes 0.8B/2B/4B/9B/27B, 35B-A3B, 122B-A10B; Apache-2.0; 262K | CONFIRMED | All cards: `apache-2.0`, "Context Length: 262,144 natively" (4B and up: extensible to 1,010,000). https://huggingface.co/Qwen/Qwen3.5-27B etc. |
| 2c | Qwen3.6-35B-A3B: 35B/3B, 256 experts (8 routed + 1 shared), 262,144 → ~1M, Apache-2.0 | CONFIRMED | https://huggingface.co/Qwen/Qwen3.6-35B-A3B |
| 2d | Thinking on by default; disable with `chat_template_kwargs: {"enable_thinking": false}`; `preserve_thinking` | PARTLY | True for Qwen3.6 and Qwen3.5 ≥4B. **Qwen3.5-0.8B and 2B are non-thinking by default** (stated on their cards). |
| 2e | Tool parser `qwen3_coder` (reasoning parser `qwen3`) | CONFIRMED | Qwen3.6 card vLLM/SGLang commands; Qwen3.5 small cards also use `--tool-call-parser qwen3_coder` |
| 2f | Qwen3.6-35B-A3B: TAU3 67.2, MCP-Atlas 62.8, TB2.0 51.5, SWE-V 73.4, MCPMark 37.0. Comparisons: Qwen3.5-27B 68.4/68.4/41.6/75.0; Gemma4-31B 67.5/57.2/42.9/52.0 | CONFIRMED | Qwen3.6 card table (columns: Qwen3.5-27B, Gemma4-31B, Qwen3.5-35B-A3B, Gemma4-26B-A4B, Qwen3.6-35B-A3B) |
| 2g | "BFCL/tau2 not reported" (Qwen3.6) / "BFCL not found on vendor cards" (Gaps) | WRONG (Gaps line; the Qwen3.6 part is correct) | Correct for the Qwen3.6 card. Wrong for Qwen3.5: see Correction 1 for the BFCL-V4 and TAU2 table. |

### 3. Gemma 4
| # | Claim | Verdict | Evidence / source |
|---|---|---|---|
| 3a | Five sizes E2B (2.3B eff / 5.1B), E4B (4.5B / 8B), 12B (11.95B), 26B-A4B (25.2B / 3.8B active), 31B (30.7B) | CONFIRMED | https://huggingface.co/google/gemma-4-12B-it (property tables) |
| 3b | Context 128K (E2B/E4B), 256K (12B/26B/31B) | CONFIRMED | Same card |
| 3c | Native tool use; thinking at all sizes | CONFIRMED | Card: "Function Calling – Native support for structured tool use"; "All models in the family are designed as highly capable reasoners, with configurable thinking modes" |
| 3d | Apache-2.0 | CONFIRMED (upgrade from S) | All five `-it` cards: `license: apache-2.0`, license_link https://ai.google.dev/gemma/docs/gemma_4_license |
| 3e | 12B "added ~June 2026" | PARTLY | HF repo `google/gemma-4-12B-it` was created 2026-05-23 (E2B/E4B on 03-02, 26B/31B on 03-11). I did not verify the public launch date. |
| 3f | A draft model for every size | CONFIRMED | `google/gemma-4-{E2B,E4B,12B,26B-A4B,31B}-it-assistant` repos exist |

### 4. Kanana-2-30B-A3B (Kakao)
| # | Claim | Verdict | Evidence / source |
|---|---|---|---|
| 4a | License "Kanana License" | CONFIRMED | `license_name: kanana-license`. https://huggingface.co/kakaocorp/kanana-2-30b-a3b-instruct/blob/main/LICENSE |
| 4a' | "Commercially usable" | PARTLY | See Correction 6 (§4.1–4.3 of the licence) |
| 4b | 32,768 native context, YaRN to 128K | CONFIRMED | Card "Context Length: 32,768" plus the YaRN override snippet (131072) |
| 4c | HAERAE 75.57 (vs Qwen3-30B-A3B-Instruct-2507 53.41); KMMLU 67.32/67.56; BFCL-v3 Live 74.30/73.93; Multi-Turn 35.38/38.77; Thinking Live 75.6 vs 82.9, MT 34.3 vs 53.6 | CONFIRMED | https://huggingface.co/kakaocorp/kanana-2-30b-a3b-instruct ; https://huggingface.co/kakaocorp/kanana-2-30b-a3b-thinking |
| 4d | Parsers: vLLM hermes (+ deepseek_r1 reasoning for thinking); SGLang qwen | CONFIRMED | Instruct card serve commands |
| 4e | GGUF / MLX availability | PARTLY | Community GGUF only; no MLX; no Ollama. 2601 refresh exists. https://huggingface.co/kakaocorp/kanana-2-30b-a3b-instruct-2601 |

### 5. EXAONE 4.5 33B (LG)
| # | Claim | Verdict | Evidence / source |
|---|---|---|---|
| 5a | License "EXAONE AI Model License Agreement 1.2 - NC"; 262,144 context; vLLM `hermes` + `qwen3` | CONFIRMED | https://huggingface.co/LGAI-EXAONE/EXAONE-4.5-33B |
| 5b | LG's table: KMMLU-Pro 67.6 vs Qwen3.5-27B 73.0; KoBALT 52.1/54.9; KMMMU 42.7/51.7; KRETA 91.9/96.5; τ² Retail 77.9/84.7, Airline 56.5/67.5, Telecom 73.0/99.3 | CONFIRMED | Same card (last column = Qwen3.5 27B (Reasoning)). Note that on KoBALT, GPT-5 mini (63.6) and K-EXAONE (61.8) also beat both. |
| 5c | "Official GGUF builds for llama.cpp, Ollama and LM Studio" | PARTLY | `LGAI-EXAONE/EXAONE-4.5-33B-GGUF` exists (created 2026-04-08), but its card names only llama.cpp b9453+ |

### 6. Smaller GLM-5.x than GLM-5.3-Flash?
| # | Claim | Verdict | Evidence / source |
|---|---|---|---|
| 6a | No GLM-5.x smaller than GLM-5.3-Flash; 5.3-Flash is 320B total / 18B active, MIT, multimodal | CONFIRMED | The full zai-org listing (154 models) has only GLM-5, 5.1, 5.2, 5.3 (≈753B each) and 5.3-Flash (321.3B, image-text-to-text, MIT), plus FP8/BF16 variants. https://huggingface.co/zai-org/GLM-5.3-Flash |
| 6b | Dates "GLM-5.2 Sep 1, GLM-5 Aug 11" | WRONG | See Correction 10 |

### 7. Apple Silicon speed, Qwen3.6-35B-A3B 4-bit
| # | Claim | Verdict | Evidence / source |
|---|---|---|---|
| 7a | ~109 tok/s on M4 Max | UNVERIFIABLE (primary); corroborated by community data | No vendor or Apple benchmark exists. oMLX community runs: M4 Max 40c/48GB 108.8 tok/s at 1k, 107.7 at 4k, peak 19.2 GB, batch 4 = 271 tok/s (2026-04-20) https://omlx.ai/benchmarks/fqabp6rx. M4 Max 32c/36GB 109.9 tok/s at 1k (2026-04-25) https://omlx.ai/benchmarks/8r66ysnf, but another 32c/36GB run got 64.0 tok/s (2026-05-12) https://omlx.ai/benchmarks/bxsf4gs8. Keep the [S] label and give a range of ~60–110 tok/s. |

### 8. Which Mac server returns OpenAI-format `tool_calls` most reliably?
| # | Claim | Verdict | Evidence / source |
|---|---|---|---|
| 8a | Ranking of Ollama / LM Studio / llama.cpp `--jinja` / mlx-lm | UNVERIFIABLE (no primary source ranks them) | Evidence per tool is listed below |
| 8b | mlx-lm tool calling "not confirmed" | WRONG | See Correction 2. https://github.com/ml-explore/mlx-lm/tree/main/mlx_lm/tool_parsers |
| 8c | Ollama `tool_choice` support "murky" | PARTLY (resolved: not supported) | See Correction 3. https://docs.ollama.com/api/openai-compatibility |

Evidence per tool (Oct 2026):
- **llama.cpp `llama-server --jinja`**:
  - `common/chat.cpp` has a dedicated "Qwen3-Coder XML" handler that explicitly covers Qwen3.5. GLM goes through the generic PEG/autoparser.
  - Parallel calls are off by default (`parallel_tool_calls: true` turns them on).
  - Open October issues: #30313 (GLM-4.7-Flash test-chat failure, 10-10), #30357 (Qwen3.5+ reasoning whitespace not round-trippable, 10-11), and draft-mtp crashes with Qwen3.6 (#30394).
  - https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
- **Ollama**:
  - The library pages for qwen3.5, qwen3.6, gemma4 and glm-4.7-flash carry the "tools" and "thinking" capabilities and offer `-mlx` tags for Qwen and Gemma.
  - `tool_choice` is unsupported.
  - Open bug #18658 (2026-09-26): the glm-4.7 parser strips a leading or trailing newline from string arguments.
  - MLX-runner tool-call memory leak #18620 (closed 09-24).
- **LM Studio**:
  - Official docs: "Native" tool parsing (hammer badge) applies when the template and format are recognised; otherwise LM Studio falls back to a "Default" prompt-injected format.
  - The docs do not list GLM.
  - Calls that fail to parse are returned in `message.content`.
  - The docs do not say whether `tool_choice` is honoured.
  - https://lmstudio.ai/docs/developer/openai-compat/tools
- **mlx-lm server**:
  - Has official `qwen3_coder` and `glm47` parsers.
  - Recent qwen3_coder fixes: #1811 (08-31), #1881 (09-12). Open #1907 (09-21): parameters without a top-level "type" come back as raw strings.
- **Practical verdict (inference)**: none of these servers is reliably better than the others for all of these models. For both families, llama.cpp `--jinja` (recent build) and mlx-lm ≥ the September 2026 fixes have dedicated parsers. Ollama is the easiest but cannot enforce `tool_choice`. LM Studio is unverified for GLM native parsing. The harness should still recover tool calls from `content`.
