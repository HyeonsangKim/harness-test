# 하네스 기능 근거 — 원문 검증표

검증일 2026-10-21. 원문(논문 PDF/HTML·abs, 공식 블로그, 공식 레포)을 직접 열어 확인한 것만 적는다. 판정: VERIFIED / PARTLY(다른 점 명시) / NOT FOUND.
PDF는 내려받아 표를 직접 읽었고(Huang et al., SWE-agent), 나머지 페이지는 가져오기 도구로 원문 인용을 받았다.

## 요약표

| # | 기능/주장 | 출처 | 핵심 수치·설정 | 판정 |
|---|---|---|---|---|
| 1 | recover: 텍스트로 나온 도구 호출 파싱 | vLLM 문서 + 레포 `vllm/tool_parsers/__init__.py`, `vllm/parser/qwen3.py`, `vllm/parser/glm47_moe.py` | 파서 이름 `qwen3_coder`·`qwen3_xml`(둘 다 Qwen3EngineToolParser), `glm45`·`glm47`(Glm47MoeModelToolParser), `hermes`(`<tool_call>` JSON). 문서: "vLLM extracts tool calls from raw text, so arguments may occasionally be malformed" | VERIFIED(형식). 성공률을 잰 논문은 NOT FOUND |
| 1 | 〃 | llama.cpp `docs/function-calling.md` | 기본 지원: Hermes 2/3, Qwen 2.5(Coder). GLM-4 템플릿은 "Generic". "Generic support may consume more tokens and be less efficient than a model's native format." | VERIFIED |
| 1/5 | 형식 실패율(작은 모델) | Tam et al., "Let Me Speak Freely?" arXiv 2408.02442 (2024) | LLaMA 3 8B GSM8K JSON 파싱 오류 22.75%, Claude 3 Haiku 60.07%(Table 3). 형식 제한 시 추론 성능 하락. "parsing errors … can be effectively mitigated through a simple corrective step" | VERIFIED(가져오기 도구 인용 기준) |
| 2 | validate: 실행 전 검사 + 구체적 오류 | Yang et al., "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering", arXiv 2405.15793 (NeurIPS 2024) | SWE-bench Lite(300건), GPT-4 Turbo, Table 3: 편집에 린트 가드레일 있음 18.0% / 없음 15.0% / 편집 명령 없음 10.3%. 덧붙여 문맥: 최근 관찰 5개 18.0% vs 전체 이력 15.0% | VERIFIED |
| 2 | 〃 | Anthropic "Writing effective tools for agents — with agents" (Ken Aizawa, 2025-09-11) | "prompt-engineer your error responses to clearly communicate specific and actionable improvements", 불투명한 오류 코드·traceback을 피하라. 수치 근거 없음(Claude Code 도구 응답 기본 25,000토큰 제한만) | VERIFIED(정성) |
| 3 | repeat: 반복·정체 대응 | Sydney Lewis, "Same Model, Different Harness: Different Coding-Agent Results", arXiv 2608.26218 (2026-08-26) | 처치 = 오래된 도구 결과 기계적 축약 + 반복/정체 대응. 좁은 창 Verified: 169건, 20,480토큰 창, 480초. 과제별 평균 F2PF 28%→49%, 완전 해결 43→72(건) | PARTLY: 28→49는 "해결률"이 아니라 F2PF(fail-to-pass 통과 비율). Qwen3.6은 넓은 창 비교에 언급되고 거기서는 Verified·Pro에서 두 팔 결과가 "close". 좁은 창 비교의 모델명은 초록에서 확인 못 함 |
| 3 | 〃 | LangChain (Vivek Trivedy, 2026-02-17) | LoopDetectionMiddleware: 파일별 편집 횟수 추적 후 재고 유도. 기여도 분리 수치 없음 | VERIFIED(기능 존재만) |
| 4 | budget: 남은 예산 알림 | Liu et al., "Budget-Aware Tool-Use Enables Effective Agent Scaling", arXiv 2511.17006 (Google, 2025-11-21) | Budget Tracker, 3회 평균. BrowseComp: Gemini-2.5-Pro 12.6→14.6, Claude-Sonnet-4 12.2→14.0; HLE-Search 20.5→21.8 / 20.5→23.0. 예산 10에서 ReAct 예산 100과 같은 정확도, 검색 호출 40.4%·비용 31.3% 감소 | VERIFIED (웹 검색 에이전트, 대형 모델만) |
| 5 | contract: 형식 검사 + 재요청 | Tam et al. 2408.02442 (위) | 교정 단계 재프롬프트로 Haiku·LLaMA 3 8B의 JSON/YAML 점수 개선(정성 서술) | PARTLY: 에이전트 최종답 스키마 재요청을 직접 측정한 원문은 못 찾음 |
| 6 | verify: 외부 검사 결과 되먹임 | Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning", arXiv 2303.11366 (NeurIPS 2023) | HumanEval Py pass@1 80.1(GPT-4)→91.0; Rust 60.0→68.0; MBPP Py 80.1→**77.1(하락)**. MBPP 거짓 양성 테스트율 16.3%(HumanEval 1.4%). 절제(HumanEval Rust 최난 50문제): 테스트 생성 없이 0.52 < 기준 0.60 | VERIFIED |
| 6 | 대조군 "다시 확인해" | Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet", arXiv 2310.01798 (ICLR 2024) | 아래 표. 외부 피드백 없는 자기 수정은 모든 모델·벤치마크에서 하락 | VERIFIED |
| 7 | evidence: 도구 없이 낸 답 되돌리기 | Soni, "ToolFailBench: Diagnosing Tool-Use Failures in LLM Agents", arXiv 2607.04686 (2026-07) | 1,000과제, 19모델, Tool-Skip·Output-Fabrication 등 라벨. 최고 Clean Tool-Use Rate 86.33%. 라벨별 비율은 초록에 없음 | PARTLY: 실패 유형 존재는 확인, 되돌리기 개입 효과 수치는 NOT FOUND |
| a | LangChain 하네스 엔지니어링 | "Improving Deep Agents with harness engineering", Vivek Trivedy, 2026-02-17 | Terminal-Bench 2.0(89과제), gpt-5.2-codex 고정, 52.8→66.5(+13.7). 실행 횟수 미기재. xhigh만 쓰면 53.9% | PARTLY: 반복 횟수·신뢰구간 없음 |
| b | kimchi 4개 하네스 | "Same Model, Different Results: What Actually Separates AI Coding Agents", Michal Ján Sallem, kimchi.dev, 2026-09-07 | GLM-5.2, **Terminal-Bench 2.1**(89과제), 과제당 5회 평균: Kimchi 72.6 / Cursor 69.0 / Claude Code 65.4 / Opencode 59.8. 추론 Moonshot API. CI 없음 | PARTLY: 2.0이 아니라 2.1. Opencode는 다른 시기 실행이라 저자도 "directional"이라 함. 벤더 자체 측정 |
| c | Vercel 도구 80% 제거 | "We removed 80% of our agent's tools", Andrew Qu, 2025-12-22 | Claude Opus 4.5, **5개 질의**: 4/5→5/5, 274.8s→77.4s, 토큰 ~102k→~61k, 단계 ~12→~7 | VERIFIED(단, n=5) |
| d | 하네스 공개 요구 | Zhang et al., "Stop Comparing LLM Agents Without Disclosing the Harness", arXiv 2605.23950 (2026-05-07) | 입장 논문. "current evaluation protocols therefore systematically misattribute harness-level gains to model improvements"; 하네스 분산이 모델 분산을 넘고 순위가 뒤집힐 수 있다; 공개 표준 제안 | VERIFIED |
| e | Can Bölük hashline | "We improved 15 LLMs at coding in one afternoon. Only the harness changed.", Can Bölük, 2026-02-12, https://stencil.so/blog/the-harness-problem (blog.can.ac/2026/02/12/the-harness-problem/가 여기로 302) | 16모델 × 180과제(React 코드 변이) × 3회, 형식 patch/replace/hashline. "Grok Code Fast 1 went from 6.7% to 68.3%"(기준은 patch로 읽힘). "hashline beats patch in 14/16 models". 최선 −61% 출력 토큰(Grok 4 Fast) | PARTLY: 표의 Δ는 +64.6으로 본문(61.6) 과 불일치. 제목 15 vs 본문 16. 저자가 hashline 구현자. replace 대비 이득은 작음 |
| M1 | τ-bench pass^k | Yao, Shinn, Razavi, Narasimhan, "τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains", arXiv 2406.12045 (2024-06-17) | "pass^k … defined as the chance that all k i.i.d. task trials are successful, averaged across tasks"; 추정량 E_task[C(c,k)/C(n,k)] (n회 중 c회 성공). gpt-4o retail pass^1 61.2, pass^8 <25% | VERIFIED |
| M2 | 오차 막대 | Evan Miller, "Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations", arXiv 2411.00640 (2024-11-01) + Anthropic 블로그 "A statistical approach to model evaluations" (2024-11-19) | 권고 5개: CLT 표준오차, 문항 묶음이면 군집 표준오차, 재표집으로 분산 감소, 두 모델 비교는 문항 단위 짝 차이로 추론, 검정력 분석 | VERIFIED |

## 항목별 메모

### 1 recover
- vLLM 레포가 받는 형식(소스 docstring):
  - Qwen3: `<tool_call><function=func_name><parameter=key>value</parameter>…`
  - GLM-4.5/4.7: `<tool_call>func_name<arg_key>key</arg_key><arg_value>value</arg_value></tool_call>`
  - Hermes/Qwen2.5: `<tool_call>{json}</tool_call>` (`qwen3_json`도 hermes로 연결됨)
- 공식 문서 페이지에는 `qwen3_coder`가 없고 `qwen3_xml`만 나온다. `qwen3_coder`는 레포 레지스트리에 같은 클래스로 등록돼 있다.
- 문서: `tool_choice="auto"`는 "generates tool calls without any grammar". named/required 호출은 "guaranteed a validly-parsable function call - not a high-quality one."
- 함의: 서버 파서가 놓친 텍스트 호출이 생길 수 있다는 근거다. 그런데 작은 모델이 텍스트로 호출을 내는 **비율**을 잰 논문은 찾지 못했다.

### 2 validate
- SWE-agent 원문: "This intervention improves performance considerably (without linting, 15.0% ↓ 3.0)". 파일 뷰어 30줄 14.3, 전체 파일 12.7, 100줄 18.0.
- 린트 오류가 난 편집 뒤에 에이전트가 "recover more often than not"(Fig. 19 부근).

### 3 repeat
- 2608.26218에서 28→49는 반복 처리만의 효과가 아니다. 도구 결과 축약과 반복/정체 대응을 묶은 처치의 효과이고, 지표는 F2PF다. 기능 하나의 효과로 인용하면 안 된다.

### 6 Huang et al. 2310.01798: 내재적 자기 수정 (Table 3, 4)
설정: GPT-3.5-Turbo는 전체 평가셋(GSM8K 1,319, CSQA 1,221, HotpotQA 100), 나머지는 데이터셋별 무작위 200(HotpotQA 100). 최대 2라운드. 프롬프트 "Review your previous answer and find problems with your answer."

| 모델 | 조건 | GSM8K | CSQA | HotpotQA |
|---|---|---|---|---|
| GPT-3.5 | 표준 | 75.9 | 75.8 | 26.0 |
| | 자기 수정 1 / 2 | 75.1 / 74.7 | 38.1 / 41.8 | 25.0 / 25.0 |
| GPT-4 | 표준 | 95.5 | 82.0 | 49.0 |
| | 자기 수정 1 / 2 | 91.5 / 89.0 | 79.5 / 80.0 | 49.0 / 43.0 |
| GPT-4-Turbo | 표준 → 2라운드 | 91.5 → 90.0 | 84.0 → 83.0 | – |
| Llama-2-70b-chat | 표준 → 2라운드 | 62.0 → 36.5 | 64.0 → 36.5 | – |

- 정답 레이블(oracle)로 멈추게 하면 오른다(Table 2: GPT-3.5 GSM8K 75.9→84.3, CSQA 75.8→89.7). 이득은 외부 신호에서 온다.
- 피드백 프롬프트를 3가지로 바꿔도(Table 5, 6) 하락은 그대로다. 작은 모델(Llama-2)이 가장 크게 떨어진다. 그래서 "다시 확인해" 대조군을 정당화할 수 있다.

### 하네스 비교 주장 정리
- a·b·c·e는 모두 벤더나 저자 자신의 측정이고 신뢰구간이 없다. c는 n=5, b의 Opencode는 통제되지 않은 비교다. "하네스가 결과를 바꾼다"는 방향을 보여 주는 근거로만 쓰고, 효과 크기로 인용하지 않는다.

## URL
- vLLM 도구 호출 문서 https://docs.vllm.ai/en/latest/features/tool_calling.html · 레포 https://github.com/vllm-project/vllm (vllm/tool_parsers/__init__.py, vllm/parser/qwen3.py, vllm/parser/glm47_moe.py)
- llama.cpp https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
- Let Me Speak Freely https://arxiv.org/abs/2408.02442
- SWE-agent https://arxiv.org/abs/2405.15793
- Anthropic tools https://www.anthropic.com/engineering/writing-tools-for-agents
- 2608.26218 https://arxiv.org/abs/2608.26218
- Budget-Aware https://arxiv.org/abs/2511.17006
- Reflexion https://arxiv.org/abs/2303.11366
- Huang et al. https://arxiv.org/abs/2310.01798
- ToolFailBench https://arxiv.org/abs/2607.04686
- LangChain https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering
- kimchi https://kimchi.dev/blog/same-model-different-harness-terminal-bench
- Vercel https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools
- 2605.23950 https://arxiv.org/abs/2605.23950
- Bölük https://stencil.so/blog/the-harness-problem
- τ-bench https://arxiv.org/abs/2406.12045
- Miller https://arxiv.org/abs/2411.00640 · Anthropic https://www.anthropic.com/research/statistical-approach-to-model-evals
