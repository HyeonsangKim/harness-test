# bench/skills

Short operating guidance for a small model, one file per tool family, placed in the system prompt.
Each file is 4–8 numbered rules of at most ~1,200 characters, written in English (the base system prompt is English; the user prompts are Korean, so Korean terms appear as examples).

| file | tool family |
|---|---|
| erp.md | list_tables, describe_table, query, aggregate, calculate |
| code.md | list_files, read_file, replace_in_file, write_file, run_tests |
| doc.md | list_documents, read_document |
| python.md | run_python only, data pasted in the prompt |

## Observations behind the rules (dev traces)

All 27 dev runs passed, so the rules target wasted turns, fragile habits and risks the tools make likely.

- erp 1 (pick the current table): every ERP trace calls list_tables, which lists a backup table next to the current one (erp_d01__B__0, erp_d02__B__1).
- erp 2 (look up the code first): erp_d02__B__1, erp_d02__C__1 spend a describe_table on the master table and then query it anyway; the needed step is name → code → filter.
- erp 3, 4 (all conditions as filters, aggregate): the passing runs put status, department code and both date ends into one aggregate call (erp_d02__H__1, erp_d02__H__2).
- erp 5 (page until next_offset is null): query returns at most 20 rows; erp_d03__H__0 used limit 20 and got 17 rows, so a result over 20 would have been cut off without paging.
- erp 6 (calculate only to combine numbers): calculate("21") and calculate("25670000") were wasted calls (erp_d01__B__1, erp_d02__H__2).
- erp 7, doc 6, python 7 (exact format): prose before the JSON (erp_d02__H__1) and a ```json fence (erp_d03__H__0) when the user asked for one JSON line only.
- code 2 (all requirements, not just tests): code_d02__H__1 removed every non-digit with re.sub, so input with letters is accepted instead of raising ValueError; the tests did not catch it.
- code 4, 5 (short unique `old`): code_d02__B__2, code_d02__H__0, code_d02__H__1 pasted the whole file as `old` to append one function.
- code 6 (imports at top): code_d02__H__0, code_d02__H__1 put `import re` inside the function.
- code 7 (no rerun without change): code_d01__C__0 ran run_tests twice in a row before editing; code_d01__H__0, code_d01__H__1 triggered the harness repeat note.
- doc 2 (chunks up to 3000, page on): doc_d02__C__0 asked length 5000 and doc_d02__C__2 length 2000; the tool caps at 3000 and continues by next_offset.
- doc 3, 4, 5 (use the stated value, look-alikes, conversion): doc_d01 quotes list 공급가액, 부가세 and 합계 side by side and write dates as "YYYY년 M월 D일" (doc_d01__B__0); the contract in doc_d02__H__2 has several day counts in different clauses.
- python: there are no run_python dev traces. The rules follow the run_python tool contract in env.py (stdlib only, fresh process per call, 20 s, stdout shown) and the habits above (mental arithmetic avoided, exact format).

## Files read

Only these, in the editor folder `/private/tmp/claude-501/-Users-hyeonman-Desktop-kim-wigtn-local-model-harness/966f3c36-f284-4abf-a343-68987afadabd/scratchpad/skill_editor/`:
`env.py`, `dev_tasks.json`, `dev_results.jsonl`, and all 27 files in `traces/`.
No file in this repository was read; this folder was only written.
