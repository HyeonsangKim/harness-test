# 사외 개발 환경 셋업 (Mac + 로컬 모델)

새 팀원이 처음 세팅할 때 따라 하는 절차다. 단계마다 **확인할 것**과 **우리 Mac에서 실제로 나온 값**(2026-10-21, MacBook Pro M4 Pro 24GB, macOS 26.5)을 함께 적었다. 같은 값이 나오면 셋업이 맞게 된 것이다.

목적은 사내 GLM-5.3-Flash를 쓰기 전에 하네스를 사외에서 만들고 시험하는 것이다. 로컬 모델 결과는 그 모델의 성질이고 사내 GLM 결과가 아니다.

## 1. 장비 확인

```bash
sysctl -n hw.memsize machdep.cpu.brand_string
```

- 확인할 것: 메모리 24GB 이상.
- 우리 값: `25769803776`(24GB), `Apple M4 Pro`.
- 24GB Mac에서 GPU가 쓸 수 있는 메모리는 약 16GB다. 그래서 9B 이하 모델만 올린다(`DESIGN_KO.md` 6절).

## 2. 모델 서버 설치: llama.cpp

```bash
brew install llama.cpp
llama-server --version
```

- 우리 값: `version: 0.7.0 (build 11669, commit 620d2225c)`.
- llama.cpp를 고른 이유:
  - OpenAI 호환 API(`/v1/chat/completions`)를 준다. 사내 LiteLLM 게이트웨이와 요청 모양이 같아서, 하네스 코드를 바꾸지 않고 주소만 바꿔 쓴다.
  - `--jinja`를 주면 모델에 들어 있는 채팅 템플릿을 그대로 쓴다. 도구 호출이 `tool_calls` 칸으로 나와서 모델 본래의 도구 호출 형식을 시험할 수 있다.

## 3. 모델 받기와 무결성 확인

모델은 **Qwen3.5-9B Q8_0**(9.53GB)이다.

- 9B는 24GB Mac에 올라가는 가장 큰 급이다.
- Q8_0은 원본에 가장 가까운 양자화다. 공식 점수와 비교할 때 양자화로 생기는 오차를 줄이려고 골랐다.

```bash
mkdir -p ~/models && cd ~/models
curl -L -C - --fail -o Qwen3.5-9B-Q8_0.gguf \
  "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q8_0.gguf"
shasum -a 256 Qwen3.5-9B-Q8_0.gguf
```

- `-C -`: 받다가 끊기면 이어서 받는다.
- 확인할 것: 해시가 Hugging Face에 등록된 값과 같아야 한다.
  - 등록값은 `https://huggingface.co/api/models/unsloth/Qwen3.5-9B-GGUF/tree/main`의 `lfs.oid`에 있다.
  - 우리 값: `809626574d0cb43d4becfa56169980da2bb448f2299270f7be443cb89d0a6ae4`(일치). 저장소 커밋은 `3885219b`.
  - 다르면 파일이 깨진 것이니 다시 받는다.

## 4. 서버 띄우기

```bash
llama-server -m ~/models/Qwen3.5-9B-Q8_0.gguf --alias qwen3.5-9b --jinja \
  -c 131072 -np 8 --kv-unified -ngl 99 --host 127.0.0.1 --port 8080
curl -s http://127.0.0.1:8080/health        # {"status":"ok"} 이면 준비됨
```

| 옵션 | 뜻 | 이유 |
|---|---|---|
| `--alias qwen3.5-9b` | API에서 쓰는 모델 이름 | `LLM_MODEL` 값 |
| `--jinja` | 모델 내장 채팅 템플릿 사용 | 이게 없으면 도구 호출이 제대로 안 나온다 |
| `-c 131072` | 전체 문맥 토큰 수 | 긴 문서·긴 대화 시험용 |
| `-np 8` | 동시에 처리하는 요청 수 | 시험을 병렬로 돌린다 |
| `--kv-unified` | 여러 요청이 문맥 공간을 함께 씀 | 이게 없으면 문맥이 요청 수로 나뉜다(`-np 8`이면 요청당 16K). 로그에 `n_ctx_slot = 131072, kv_unified = 'true'`가 보여야 한다 |
| `-ngl 99` | 모든 층을 GPU에 올림 | 속도 |

- 우리 값: 생성 속도는 요청 1개일 때 초당 약 26토큰, 4개를 동시에 돌리면 요청당 약 19토큰이다. 입력 처리는 초당 약 350토큰이다(3만 토큰 문서를 읽는 데 약 90초).
- 서버를 띄운 뒤 시스템 메모리 여유는 12%였다. 다른 큰 앱은 닫고 돌린다.

## 5. 요청 설정: 사고 끔 + 공식 권장 샘플링

사외 시험은 아래 값으로 고정한다. 하네스 코드에서는 `LLM_EXTRA` 환경변수로 넣는다.

```bash
export LLM_URL=http://127.0.0.1:8080/v1/chat/completions
export LLM_MODEL=qwen3.5-9b
export LLM_EXTRA='{"temperature":0.7,"top_p":0.8,"top_k":20,"min_p":0,"presence_penalty":1.5,"chat_template_kwargs":{"enable_thinking":false}}'
```

- **샘플링 값:** Qwen3.5-9B 공식 모델 카드의 "Instruct (or non-thinking) mode for general tasks" 권장값을 그대로 썼다(`huggingface.co/Qwen/Qwen3.5-9B` README).
- **사고 끔 이유:** probe의 6단계(사고량 확인)에서 직접 쟀다.

  | 요청 | 사고 글자 수 | 걸린 시간 | 정답 |
  |---|---|---|---|
  | 기본 | 3,855 | 63초 | 맞음 |
  | `reasoning_effort: low` | 11,375 | 203초 | 맞음 |
  | `reasoning_effort: high` | 7,013 | 118초 | 맞음 |

  - llama.cpp는 `reasoning_effort`를 받아도(200) 사고량에 반영하지 않는다. low를 줘도 사고가 줄지 않았다.
  - 사고를 켠 채로는 문제 하나에 1~3분이 걸려 수백 번 반복하는 비교를 하루에 못 돌린다. 그래서 `enable_thinking: false`로 끈다.
  - 사내 GLM은 게이트웨이를 거치면서 사고 옵션이 다르게 먹으니, 사내 설정은 사내 probe 결과로 따로 정한다.

## 6. 연결 확인: probe.py

```bash
LLM_API_KEY=local python3 probe.py --n 10
```

로컬 서버는 키를 확인하지 않으므로 아무 값이나 넣는다. 요약 10줄의 각 항목 뜻은 `PROBE_GUIDE_KO.md` 9절에 있다.

| 항목 | 로컬 Qwen3.5-9B (llama.cpp) | 사내 GLM-5.3-Flash (LiteLLM) |
|---|---|---|
| 옵션 9개 | 모두 200 | 모두 200 |
| 도구 호출 (영어/한국어) | 10/10, 10/10 | 10/10, 10/10 |
| 본문으로 샌 호출 | 없음 | 없음 |
| 도구 결과 왕복 3종 | 모두 Y | 모두 Y |
| 동시 4개 | 모두 성공 | 모두 성공 |
| 지연 p50 / p90 | 3.3 / 3.7초 | 2.3 / 3.5초 |
| 토큰당 글자 수 (한국어/영어/JSON) | 2.04 / 5.13 / 2.32 | 1.24 / 5.11 / 2.56 |
| 사고량 옵션 | 무시됨(위 5절) | 게이트웨이 호출 한도(429)로 미확인, 재시험 중 |

확인할 것: 도구 호출이 10/10 근처이고 왕복이 Y면 하네스 시험을 돌릴 수 있다.

## 7. 하네스 A/B 시험

```bash
cd bench
python3 ab.py run --out runs/qwen9b-eval --split eval --conds B,C,H --rep 3 --workers 6
python3 ab.py report --out runs/qwen9b-eval
```

조건, 과제, 결과와 해석은 `bench/RESULTS_KO.md`에 있다.

## 8. 겪은 문제와 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `-np 8`로 띄운 뒤 긴 문서 시험이 잘림 | 문맥이 요청 수로 나뉨(요청당 16K) | `--kv-unified` 추가 |
| 사고량 시험 하나에 3분 | llama.cpp가 `reasoning_effort`를 무시함 | 사외 시험은 사고 끔(5절) |
| `behavior.py`가 한 시간 넘게 걸림 | 위와 같은 이유로 매 호출 길게 생각함 | 사외에서는 `ab.py`로 시험한다. `behavior.py`는 사내 맛보기용 |
