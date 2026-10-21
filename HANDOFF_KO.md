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

## 현재 하네스

- **최종판 후보:** v7 계열이다. 개발 시험 결과로 RT9, RT10, RT11 중 하나를 고른다. 선택 규칙은 `PREREG_KO.md`의 "v7" 절에 있다.
- **구성 (공통):** 파이썬 하나, 검사, 표 파일, 표 정규화(탭 표는 탭 유지), 바로 끝내기, 그리고 아래 장치.
  - 코드 강제는 숫자 답이나 표가 있을 때만 한다.
  - 흘려받기(`LLM_STREAM=1`)와 폭주 감지를 쓴다.
  - 잘린 도구 호출은 출력 상한을 두 배로 올려 복구한다.
- **판마다 다른 것:**
  - RT10: 요청에 없는 숫자 검사를 더한다.
  - RT11: RT10에 작업 규칙 v4를 더한다.
- **실행기:** `bench/ask.py`(질문 하나). 비교 시험은 `bench/ab.py`.

## 실험 상태 (밤사이)

| 실행 | 폴더 | 내용 | 상태 |
|---|---|---|---|
| 재대결 1의 P·PT | `runs/qwen9b-heldout` | 앞 재대결 100문항, 흘려받기 없음 | 진행 중 |
| 재대결 2 새 문항 P·PT | `runs/qwen9b-heldout2-ppt` | 새 100문항 | 진행 중 |
| 개발 시험 C·B | `runs/qwen9b-dev-v6`, `runs/qwen9b-messy-v6` | RT5, RT6, RT8 | 진행 중 |
| 범용성 P | `runs/qwen9b-gen-{ifeval,bbh,he}` | IFEval 150, BBH 108, HumanEval+ 163 | 진행 중 |
| 재대결 2 하네스 | (최종판 선택 후) | 200문항, `STREAM=1` | 대기 |
| 범용성 하네스 | (최종판 선택 후) | 위 세 벤치마크, `STREAM=1` | 대기 |

- **실행 스크립트:** 세션 임시 폴더에 있다(`run_tf.sh` 등). 다른 세션에서 다시 돌리려면 아래 "재현"을 쓴다.
- **분석:** 문항별 짝 비교는 `ab.py report` 또는 아래 명령으로 한다.

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

1. 개발 시험으로 최종판 선택, 재대결 2와 범용성 시험 하네스 실행
2. 분석:
   - 재대결 2: v7 − PT, 정답 오류 제외 175문항이 주 분석
   - 범용성: v7 − P, 비열등 −10%p
3. `HARNESS_REPORT_KO.html` 마무리: 제목 후보 "제한된 환경에서 작은 로컬 모델을 여러 업무에 쓰려면 무엇을 붙여야 하나"
4. 사내 GLM 시험(`PROBE_GUIDE_KO.md` 16절)에 `LLM_STREAM=1` 연결 확인 단계 추가
5. 다음 후보:
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
