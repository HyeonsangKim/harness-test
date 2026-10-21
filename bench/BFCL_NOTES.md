# BFCL v4 multi_turn_base A/B

`bfcl_ab.py` runs BFCL v4 multi_turn_base through `hx.run` under conditions B / C / H (same as `ab.py`) and grades every conversation with BFCL's own `multi_turn_checker`. It needs the official `bfcl-eval` package, so it runs only on the Mac dev machine (not the closed network).

## Setup

```
uv venv .venv-bfcl
uv pip install --python .venv-bfcl/bin/python bfcl-eval
```

Pinned: `bfcl-eval 2026.3.23`, data `BFCL_v4_multi_turn_base.json` sha256 `1a21a995d06fd6f20ba55de7bced30ef953ec35e998f502ec2ecf4d66ef1c43a`, answers `possible_answer/BFCL_v4_multi_turn_base.json` sha256 `1fee67823b317571649177dd89d63969feaae4e810cc7448ee55ba797fb7c8fc`. `meta.json` of each run records both hashes.

## Commands

```
export LLM_URL=http://127.0.0.1:8080/v1/chat/completions LLM_MODEL=qwen3.5-9b
export LLM_EXTRA='{"temperature":0.7,"top_p":0.8,"top_k":20,"min_p":0,"presence_penalty":1.5,"chat_template_kwargs":{"enable_thinking":false}}'
.venv-bfcl/bin/python bfcl_ab.py selftest                     # grading path check, no server
.venv-bfcl/bin/python bfcl_ab.py run --out runs/bfcl --conds B,C,H --n 40 --seed 0 --workers 2
.venv-bfcl/bin/python bfcl_ab.py report --out runs/bfcl
```

`run` resumes: finished (id, cond, rep) rows in `results.jsonl` are skipped. Ids are `random.Random(seed).sample(sorted(ids), n)`; job order is shuffled with the same seed. Each run writes `traces/<id>__<cond>__<rep>.json` (executed calls per turn and step, ground truth, checker output, all messages).

`selftest` replays the ground truth of all 200 entries as tool calls through `hx.run` (B and H) and checks that it passes, that an empty run fails, and that dropping the last turn fails. Entry 173 is reported separately: its ground truth calls `close_ticket(ticket_id='ticket_001')` while the schema says integer, so H's argument validation blocks the ground-truth call.

## What follows the official procedure

Checked against `bfcl_eval` source (`BaseHandler.inference_multi_turn_FC`, `OpenAICompletionsHandler`, `eval_runner._evaluate_single_multi_turn_entry`, `multi_turn_checker`).

- Data: `load_dataset_entry("multi_turn_base")` (adds the function docs of `involved_classes` and the Python hint to descriptions) and `load_ground_truth_entry`. Base has no `missed_function` (holdout) turns; every turn is one user message. `excluded_function` is not used by BFCL code, so all functions of the involved classes are offered.
- Tools: `convert_to_tool(functions, GORILLA_TO_OPENAPI, ModelStyle.OPENAI_COMPLETIONS)`, sent unchanged (including the `response` field).
- Execution: each call becomes the string `convert_to_function_call` makes (`name(k=repr(v),...)`) and runs through `execute_multi_turn_func_call` on this conversation's instances; the returned string is the tool message.
- Turn end: the model replies without tool calls. More than `MAXIMUM_STEP_LIMIT` (20) tool steps in one turn force-quits the conversation (`hx.run` max_turns = 21), which fails as `multi_turn:force_terminated`.
- Grading: `multi_turn_checker(decoded, ground_truth, entry, "multi_turn_base", name)`, where `decoded` is per turn a list of non-empty steps, each the list of call strings actually executed. A shorter turn list fails as force_terminated, as in `eval_runner`. Each run uses its own instance name prefix and the instances are removed from `multi_turn_utils` globals afterwards.
- Base has 3 turns with empty ground truth (ids 167, 180). As in BFCL, those turns are not checked, but any calls made there still change state.

## Deviations

- System prompt: BFCL sends none for FC models. Here every condition gets the same neutral one: "You are a helpful assistant. Use the available tools to complete the user's requests."
- Sampling: Qwen's non-thinking settings (`LLM_EXTRA` above) instead of BFCL's default temperature 0.001. `max_tokens` 4096.
- Calls the harness does not run (H: invalid arguments, the third identical call; any condition: unknown tool name or arguments that are not JSON) are not recorded as executed. In BFCL an undecodable response ends the turn; here the model gets an error message and continues.
- Tool output is cut at 8000 characters by `hx` (base outputs are far shorter).
- Harness feedback messages (H, C) stay in the history of later turns.
- BFCL errors come back as strings (`Error during execution: ...` or `{"error": ...}`), not exceptions, so H's `tool_error` hint never fires; `validate` still checks arguments against the schema.
