# 인수인계

다른 세션이 이 작업을 이어받을 때 읽는 문서다. 레포 안내는 `README_KO.md`, 기법 목록과 복기는 `HARNESS_TECHNIQUES_KO.md`, 실험 기록(사전 등록, 결과, 정정)은 `bench/PREREG_KO.md`에 있다.

## 목표와 제약

- **목표:** 폐쇄망(사내 Windows, Python 3.12, uv)에서 작은 로컬 모델을 여러 직군 업무에 쓰게 만드는 범용 하네스를 팀 자산으로 만든다(`CLAUDE.md`).
- **지금 초점:** 업무 시스템과 연동하지 않는 **도구 없는 하네스**다. 모델에게 `run_python` 하나만 준다.
- **사내 코드 규칙:**
  - 사내 코드는 표준 라이브러리만 쓴다.
  - API 키는 환경변수나 실행 중 입력으로만 받는다.
  - TLS 검증은 끄지 않는다.
- **문서 규칙:** 문서는 최신 상태만 둔다. 사전 등록 문서는 예외로, 기록이다.
- **보고서:** `HARNESS_REPORT_KO.html`은 로컬 전용이다. git에 넣지 않고 클로드에도 배포하지 않는다.
  - 1인칭 "참고 → 적용 → 생각" 말투로 쓴다.
  - 하네스는 하나로만 제시한다.

## 현재 하네스 (최종판 RT12 = v8)

- **판단 (`hx.wants_harness`):** 답 형식이 JSON이거나, 표·숫자 답·코드 요구가 있으면 하네스(RT9)를 켠다. 그 밖의 자유 글쓰기는 하네스 없이 바로 답한다.
  - 근거: IFEval에서 무조건 켜면 −11%p, 이렇게 판단하면 +4%p(−2 ~ +10)였다.
- **RT9 구성:**
  - 파이썬 하나, 검사, 표 정규화(탭 표는 탭 유지), 바로 끝내기
  - 코드 강제는 숫자 답·표일 때만(`evidence_auto`)
  - 흘려받기와 폭주 감지(`LLM_STREAM=1`, 8천 자 초과·주석 절반 이상이거나 같은 글 반복)
  - 잘린 도구 호출은 출력 상한을 두 배로 올려 복구
- **실행기:** `bench/ask.py`(같은 판단 규칙). 비교 시험은 `bench/ab.py`(조건 이름 `RT12`).
- **뺀 것:** 요청에 없는 숫자 검사(C, RT6/RT10)와 규칙 변수화 스킬 v4(B, RT8/RT11)는 효과를 보이지 못해 후보로만 남겼다.

## 실험 상태

| 실행 | 폴더 | 상태 (2026-10-22 07시) |
|---|---|---|
| 재대결 2 P | `runs/qwen9b-heldout`, `runs/qwen9b-heldout2-ppt` | 200/200 완료 |
| 재대결 2 PT | 같은 폴더 | 앞 묶음 약 80/100(재대결 2 하네스가 끝나면 자동 재개), 새 묶음 약 65/100 진행 중 |
| 재대결 2 RT9 (= RT12) | `runs/qwen9b-heldout2-rt9` | 약 165/200 진행 중 |
| IFEval P / RT12 / RT9 | `runs/qwen9b-gen-ifeval`, `-ifeval-r`, `-ifeval-h` | 150 / 150 / 80(조기 종료) |
| BBH P / RT9 | `runs/qwen9b-gen-bbh`, `-bbh-h` | 진행 중 |
| HumanEval+ P / RT9 | `runs/qwen9b-gen-he`, `-he-h` | P는 BBH P 다음 차례, RT9 진행 중 |

- **분석 방법:** 문항별 짝 비교는 `ab.py report --out A --also B`로 한다.
  - 재대결 2 주 분석은 `bench_ids_heldout2.txt`에서 `gsmhard_label_errors_heldout2.txt`를 뺀 175문항이다.
- **세션 임시 스크립트:** `run_tf.sh`, `analyze.py`, `watch.sh` 등은 세션 임시 폴더에 있다. 새 세션은 아래 "재현" 명령을 쓰면 된다.

## 재현

```bash
cd bench
export LLM_URL=http://127.0.0.1:8080/v1/chat/completions LLM_MODEL=qwen3.5-9b
export LLM_EXTRA='{"temperature":0.7,"top_p":0.8,"top_k":20,"min_p":0,"presence_penalty":1.5,"chat_template_kwargs":{"enable_thinking":false}}'
export LLM_THINK_EXTRA='{"temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0,"presence_penalty":1.5,"chat_template_kwargs":{"enable_thinking":true}}'
# 공개 벤치마크 계열은 numpy 등이 필요해 venv 파이썬으로 돌린다
python ab.py run --taskfile tasks_bench2 --split bench --out runs/x --conds P,PT --rep 1 --workers 3 --tasks "$(cat bench_ids_heldout2.txt)"
LLM_STREAM=1 python ab.py run --taskfile tasks_bench2 --split bench --out runs/y --conds RT10 --rep 1 --workers 3 --tasks "$(cat bench_ids_heldout2.txt)"
python ab.py report --out runs/x --also runs/y
```

- **모델 서버:** `llama-server -m ~/models/Qwen3.5-9B-Q8_0.gguf --alias qwen3.5-9b --jinja -c 65536 -np 6 --kv-unified --load-mode mlock -ngl 99 --port 8080` (`LOCAL_SETUP_KO.md`).
- **데이터와 채점 코드:** `bench/ext/`에 둔다. gitignore 대상이라 따로 받아야 한다. 받는 곳은 각 `tasks_*.py` 머리말에 있다.

## 남은 일

1. **실행 마무리와 분석:**
   - 재대결 2: RT12(=RT9) − PT, 주 분석 175문항, 하한 > 0이면 "더 정확", > −10%p면 "같은 수준"
   - BBH, HumanEval+: RT12 − P, 비열등 −10%p
   - 결과는 `PREREG_KO.md`에 기록한다.
2. **리포트 숫자 갱신:** `HARNESS_REPORT_KO.html`(로컬 전용). 지금은 07시 중간 결과가 들어 있고 "실행 중" 표시가 있다.
3. **공통 시스템 문장 수정 (다음 판 1순위):** "숫자나 이름을 추측하지 마라"가 창작 요청을 거절하게 만든다. "한국 회사" 설정이 영어 지시에 한글을 쓰게 만든다.
4. **`ask.py` 판단 한계:** 숫자 답이 필요한 자유 질문인데 `--json`을 주지 않으면 하네스가 켜지지 않을 수 있다.
5. **사내 GLM 시험:** `PROBE_GUIDE_KO.md` 16절의 조건을 `P,RT12`로 하고 `LLM_STREAM=1` 연결 확인 단계를 추가한다.
6. **다음 후보:**
   - 생각 + 코드(RT5T)
   - 바로 끝내기가 정리 규칙을 놓치는 문제(중복·메모 줄 섞인 표 0/3)
   - 한글 금액 파싱
   - 실제 업무 예시로 과제 만들기
   - SWE-bench는 코딩 업무로 넓힐 때 2편으로

## 주의

- **사전 등록 시각:** 커밋 시각만 쓴다. 추정 시각을 적지 않는다.
- **결론의 근거:** 한 회차 결과로 결정하지 않는다. 개선안을 만든 문항으로 "이겼다"고 쓰지 않는다.
- **정답 감사:** 에이전트가 다시 풀고 메인 세션(Claude)이 일부를 대조한 것이다. 사람 확인은 아직 없다.
- **중간 점검:** 긴 실행 중에는 실패 기록을 직접 열어 본다. 결함 대부분을 이렇게 찾았다.
