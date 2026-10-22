# 인수인계

다른 세션이 이 작업을 이어받을 때 읽는 문서다. 레포 안내는 `README_KO.md`, 기법 목록과 복기는 `HARNESS_TECHNIQUES_KO.md`, 실험 기록(사전 등록, 결과, 정정)은 `bench/PREREG_KO.md`에 있다.

## 목표와 제약

- **목표:** 폐쇄망(사내 Windows, Python 3.12, uv)에서 작은 로컬 모델을 여러 직군 업무에 쓰게 만드는 범용 하네스를 팀 자산으로 만든다(`CLAUDE.md`).
  - 사고 모드보다 낫거나, 같은 정확도를 더 싸게 내야 한다.
  - 단순 과제가 아니라 실제 업무에서 통해야 한다.
- **지금 초점:** 업무 시스템과 연동하지 않는 **도구 없는 하네스**다. 모델에게 `run_python` 하나만 준다.
- **사내 코드 규칙:** 표준 라이브러리만 쓴다. API 키는 환경변수나 실행 중 입력으로만 받는다. TLS 검증은 끄지 않는다.
- **문서 규칙:** 문서는 최신 상태만 둔다. 사전 등록 문서는 예외로, 기록이다.
- **보고서:** `HARNESS_REPORT_KO.html`은 로컬 전용이다. git에 넣지 않고 클로드에도 배포하지 않는다.
- **진행 방식(사용자 요청):**
  - 바꾸기 전에 전후 상황과 판정 기준을 정리해 보여 준다.
  - 실행은 하나씩 한다.
  - 본 시험 전에 1~2문항으로 시험 실행을 한다.
  - 긴 실행은 10분마다 확인한다.
  - 답은 한국어로 한다.

## 현재 하네스

- **판단 (`ab.py`의 조건 `RT22`):**
  - `hx.wants_harness`가 참이면 `RT22H`, 아니면 사고 모드(PT)로 보낸다.
  - `wants_harness`가 참인 경우: 답 형식이 JSON이거나, 표·숫자 답·코드 요구가 있을 때.
- **RT22H 구성:**
  - 도구와 작업 규칙: `run_python` 하나, 표 정규화 v2(`clean_tables="keep2"`), 도우미 모듈 `helpers.py`(`num`, `norm`, `date`), 작업 규칙 `skills/python_v7.md`
  - 사고 모드: 켬
  - 기능 묶음 `hx.FEATURES_NT13`:
    - 코드 없는 답 되돌리기
    - 빈 칸 검사
    - 규칙 점검표(`rulecheck`)
    - 어려운 요청에 두 번째 독립 프로그램(`crosshard`)
    - 오래된 출력 줄이기(`mask`)
    - 오류 신호 검사
    - 바로 끝내기
  - 턴 한도: 12 + min(8, 요청 길이 // 3000)
- **흘려받기:** `LLM_STREAM=1`. 폭주 감지와, 잘린 도구 호출을 출력 상한 두 배로 복구하는 기능이 붙어 있다.
- **아직 커밋하지 않은 수정 (`bench/hx.py`):** 남은 턴이 3개 미만이면 마지막 확인 요청(규칙 점검표, 두 번째 프로그램)을 건너뛴다.
  - 원인: 한국어 업무 hk_06에서 마지막 2턴에 두 번째 프로그램을 요구해 턴만 태웠다.
- **이전 최종판 RT12 (사고 모드 없는 하네스):** 공개 재대결 결과가 이 판으로 나왔다. `PREREG_KO.md` 참조.

## 확정된 결과 (리포트 근거)

| 시험 | 그냥 답하기 | 사고 모드 | 하네스 RT12 | 비고 |
|---|---|---|---|---|
| 재대결 2 (공개, 175) | 24.0% | 88.2% (n=152) | 84.6% | 사고 모드 대비 −2.0 [−7.2, +3.3], 출력 토큰 ×0.22, 시간 ×0.42 |
| BBH (108) | 59.3% | | 87.0% | +27.8 [+17.6, +38.0] |
| IFEval (150) | 76.0% | | 80.0% | 판단 규칙 덕분. 무조건 켜면 −11.2 |
| HumanEval+ (163) | 82.2% | | 83.4% | 시간 ×1.86 |

- **한국어 어려운 업무 (`tasks_hard_ko.py`, 60문항, 평균 1만 자):**
  - 그냥 답하기 0/60이다.
  - RT22는 hk_06 하나를 돌려 턴 한도를 넘겨 실패했다(38분, 입력 토큰 25만).
  - 9B 모델에게는 너무 길다고 보고 중단했다.
  - 기록은 `runs/qwen9b-hardko-rt22`에 있다.

## 다음 계획: 업무형 공개 시험 4묶음

- **배경:** 지금까지 시험이 표·숫자 계산에 치우쳤고, 과제를 AI가 만들어서 "업무에 쓴다"는 근거가 약하다. 그래서 실제 업무에서 나온, 리포트에서 방어할 수 있는 시험으로 바꾼다.

| 순서 | 시험 | 파일 | 문항 | 내용과 채점 | 상태 |
|---|---|---|---|---|---|
| 1 | IFBench (NeurIPS 2025) | `tasks_ifbench.py`, split `ifbench` | 50 | 제약 있는 글쓰기, 공식 prompt-level loose | 완성. 2문항 시험 실행 완료 |
| 2 | SpreadsheetBench Verified (NeurIPS 2024) | `tasks_ssb.py`, split `ssb` | 50 (`ssb_ids_50.txt`) | 실제 엑셀 포럼 질문, 대상 셀 값을 JSON으로 답 | 완성. 시험 실행 전 |
| 3 | CUAD (NeurIPS 2021) | `tasks_cuad.py`, split `cuad` | 40 | 계약서 조항 뽑기 → JSON, Jaccard ≥ 0.5 | 제작 중 |
| 4 | 한국어 기관 문서 QA (allganize) | `tasks_kodoc.py`, split `kodoc` | 60 | 실제 기관 PDF 쪽 ±1, 핵심 사실 체크리스트 | 제작 중 |

- **조건:**
  - P(그냥 답하기), PT(사고 모드), RT22(하네스)를 쓴다.
  - IFBench는 50문항 모두 판단 규칙이 사고 모드로 보낸다. RT22 = PT이므로 P, PT만 돌리고 RT22는 경로만 보고한다.
- **절차:**
  1. 각 묶음의 자체 점검을 확인한다: 정답은 통과, 빈 답과 바꾼 답은 실패.
  2. 사전 등록을 커밋한다.
  3. 1~2문항으로 시험 실행을 한다.
  4. 본 시험을 순서대로 하나씩 돌린다. 짝 비교 신뢰구간을 낸다.
- **실행 명령:** `run_tf.sh`는 세션 임시 폴더에 있다. 같은 내용을 직접 실행한다.

  ```bash
  cd bench
  export LLM_URL=http://127.0.0.1:8080/v1/chat/completions LLM_MODEL=qwen3.5-9b LLM_STREAM=1
  export LLM_EXTRA='{"temperature":0.7,"top_p":0.8,"top_k":20,"min_p":0,"presence_penalty":1.5,"chat_template_kwargs":{"enable_thinking":false}}'
  export LLM_THINK_EXTRA='{"temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0,"presence_penalty":1.5,"chat_template_kwargs":{"enable_thinking":true}}'
  python ab.py run --taskfile tasks_ifbench --split ifbench --out runs/qwen9b-ifbench --conds P,PT --rep 1 --workers 3 --tasks "<쉼표로 이은 id>"
  python ab.py run --taskfile tasks_ssb --split ssb --out runs/qwen9b-ssb --conds P,PT,RT22 --rep 1 --workers 3 --tasks "$(sed 's/^/ssb_/' ssb_ids_50.txt | paste -sd, -)"
  python ab.py report --out runs/qwen9b-ssb
  ```

  - 파이썬은 IFBench 채점에 `absl-py langdetect nltk immutabledict emoji syllapy`가 필요하다.
  - SpreadsheetBench 준비(`prep_ssb.py`)에는 openpyxl이 필요하다(`uv run --with openpyxl`).
- **시간 (Qwen 9B, 맥 한 대):**
  - 그냥 답하기는 문항당 5~15초다.
  - 사고 모드는 짧은 글쓰기도 6~13분이다(생각 토큰 약 8천).
  - 사고 모드가 시간 대부분을 차지한다.
  - 서버 공용 문맥 6만 5천에서 동시 실행 3을 넘기면 넘친다. `-c 131072`로 늘려 4개를 돌리는 안은 아직 시험하지 않았다.
- **SpreadsheetBench 알려진 점:**
  - 원래 과제는 수식 쓰기다. 여기서는 셀 값을 답하게 바꿨다.
  - 채점은 공식보다 조금 너그럽다(공백, 대소문자, 날짜 형식). `tasks_ssb.py` 머리말에 차이를 적어 두었다.
  - 하네스 표 추출기는 `ssb_47798`(첫 줄에 80자 넘는 칸)의 표를 놓친다.

## 모델 서버

`llama-server -m ~/models/Qwen3.5-9B-Q8_0.gguf --alias qwen3.5-9b --jinja -c 65536 -np 6 --kv-unified --load-mode mlock -ngl 99 --host 127.0.0.1 --port 8080` (`LOCAL_SETUP_KO.md`). 지금은 꺼 두었다.

## 남은 일

1. 위 4묶음 사전 등록, 시험 실행, 본 시험, 분석, `PREREG_KO.md` 기록.
2. 리포트 `HARNESS_REPORT_KO.html` 작성:
   - 중심은 업무형 4묶음이다.
   - 공개 재대결 결과는 보조 근거로 쓴다.
   - 사전 등록했다가 멈춘 시험(재대결 3, MultiHiertt, 한국어 어려운 업무)은 사실대로 짧게 적는다.
3. 사내 GLM 시험: `PROBE_GUIDE_KO.md` 16절. 사용자가 돌린다.
4. 공통 시스템 문장 수정: "숫자나 이름을 추측하지 마라"가 창작 요청을 거절하게 만든다.

## 주의

- **사전 등록 시각:** 커밋 시각만 쓴다.
- **결론의 근거:** 한 회차 결과로 결정하지 않는다. 개선안을 만든 문항으로 "이겼다"고 쓰지 않는다.
- **정답 감사:** 에이전트가 다시 풀고 메인 세션(Claude)이 일부를 대조한 것이다. 사람 확인은 아직 없다.
  - 한국어 문서 QA의 핵심 사실 체크리스트도 Claude가 정답에서 만든 것이다.
- **분석:** 인프라 오류(`http_`, `connection`)만 빼고, 하네스 실패(턴 한도 등)는 오답으로 센다.
