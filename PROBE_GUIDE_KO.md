# probe.py 사내 실행 가이드

목적: 사내 게이트웨이의 GLM-5.3-Flash가 도구 호출을 제대로 하는지, 어떤 옵션을 받는지, 얼마나 빠른지, 한국어가 토큰을 얼마나 쓰는지 실측해 **모델 프로필 0판**을 만든다. 하네스 성능을 증명하는 테스트가 아니라 그 전제 조건을 확인하는 테스트다.

## 0. 준비물

| 항목 | 예시 | 비고 |
|---|---|---|
| 요청 URL | `https://llm.사내도메인/v1/chat/completions` | base URL이 아니라 `/chat/completions`까지 포함한 전체 주소 |
| 모델 ID | `glm-5.3-flash` | 사내 안내의 정확한 값 |
| API 키 | (받은 키) | 파일·코드에 절대 적지 않는다 |
| 사내 인증서(선택) | `C:\certs\company-ca.pem` | SSL 오류가 날 때만 관리자에게 받는다 |

## 1. 파이썬 확인

```powershell
python --version        # 3.12.x 가 나오면 이후 "python" 사용
py -3.12 --version      # 이게 되면 이후 "py -3.12" 사용
uv python find 3.12     # 위 둘 다 안 되면 출력된 python.exe 전체 경로 사용
```

아래는 `python`으로 적었다. 확인 결과에 맞게 바꿔 쓴다. 추가 패키지 설치는 필요 없다(표준 라이브러리만 사용).

## 2. 코드 받기

```powershell
cd $env:USERPROFILE\work
git clone https://github.com/HyeonsangKim/harness-test.git
cd harness-test
```

이미 받아 두었다면 `git pull`로 최신으로 맞춘다. 추가 패키지 설치는 필요 없다.

## 3. 확인

```powershell
python -m py_compile probe.py
```

아무 출력이 없으면 통과.

## 4. 주소·모델 설정 (이 PowerShell 창에서만 유효)

```powershell
$env:LLM_URL = "https://...사내주소.../v1/chat/completions"
$env:LLM_MODEL = "정확한-모델-ID"
```

창을 닫으면 사라지므로 새 창에서는 다시 설정한다.

## 5. 키 넣고 실행

**권장: 실행할 때 입력**

```powershell
python probe.py --n 1 --burst 1
```

`API key:`가 뜨면 키를 붙여넣고(우클릭 또는 Ctrl+V) Enter. **화면에 아무것도 안 보이는 게 정상이다.** 키는 메모리에만 있고 결과 파일에 저장되지 않는다.

**대안: 환경변수** (여러 번 반복 실행할 때)

```powershell
$env:LLM_API_KEY = "키"
python probe.py --n 10
Remove-Item Env:LLM_API_KEY   # 끝나면 지운다
```

PowerShell 명령 기록에 키가 남을 수 있어 권장 방법을 우선한다.

## 6. 두 번에 나눠 실행

| 순서 | 명령 | 호출 수 | 목적 |
|---|---|---|---|
| 1. 연기 테스트 | `python probe.py --n 1 --burst 1` | 약 19회 | 주소·키·연결 확인 |
| 2. 본 테스트 | `python probe.py --n 10` | 약 40회 | 옵션 지원, 도구 왕복, 신뢰도 20회, 지연, 동시성, 토큰 보정 |

사고 모드는 끌 수 없어서 호출당 수십 초 걸릴 수 있다. 옵션:

- `--n 10` : 언어별 신뢰도 시험 횟수 (영어 10 + 한국어 10)
- `--burst 4` : 동시에 보낼 요청 수
- `--effort low` : 2~4단계의 사고량. `high`, `max`, 또는 `none`(서버 기본값=max)

## 7. 출력 읽는 법

```
== 1. options (status, result, details)
plain          no_tool_call       0.06s  keys=['reasoning_content'] in_tok=8 cached=0 think_chars=11 out_tok=20 think_tok=12
auto           native_ok          ...
strict         http_400           0.06s  {"error":"strict not supported"}
server {"server": "uvicorn", "via": null, "x_headers": ["x-request-id"], "body_keys": [...], "choice_keys": [...], "id": "chatcmpl-...", "models": [{"id": "...", "owned_by": "vllm", "max_model_len": 202752}]}
base for 2-4: {"tool_choice": "auto", "reasoning_effort": "low"}
== 2. tool round trip
keep_reasoning: http_200 uses_result; drop_reasoning: http_200 uses_result; user_after_tool: http_200 uses_result
== 3. reliability: 10 x en + 10 x ko, one at a time
en {'native_ok': 10}
ko {'native_ok': 9, 'text_tool_call': 1}
text sample '<tool_call>get_weather<arg_key>city</arg_key>...'
latency {'p50': ..., 'p90': ..., 'max': ...}
== 4. burst: 4 requests at once
['native_ok 12.3s', 'http_429 0.1s', ...]
== 5. token calibration (characters per token)
{'ko': 1.5, 'en': 4.3, 'json': 3.1}
saved: C:\Users\...\probe_out\20261020-101500
```

| 결과 | 뜻 |
|---|---|
| `native_ok` | 정상. 정식 형식으로 `get_weather(city=...)` 호출 |
| `native_bad_json` / `native_bad_args` | 도구는 불렀지만 인자가 깨지거나 틀림 |
| `native_no_id` | 호출에 id가 없음. 결과를 돌려줄 수 없음 |
| `text_tool_call` | 도구 호출이 정식 필드가 아니라 본문 텍스트로 샘 (서버 파서 설정 문제 가능) |
| `no_tool_call` | 도구 없이 말로만 답함. **`plain` 줄은 도구가 없는 시험이라 이게 정상** |
| `length` | 출력 상한(4096)에서 잘림. 사고가 너무 김 |
| `http_400` 등 | 서버 거부. 오른쪽에 거부 이유 원문 |
| `http_0` | 연결 실패 (네트워크·인증서·타임아웃) |

| 항목 | 뜻 |
|---|---|
| `in_tok` | 입력 토큰 수. `plain`과 `auto`의 차이로 도구 정의가 차지하는 토큰을 가늠한다 |
| `cached` | 캐시된 입력 토큰 수. 같은 요청을 반복하는 3단계에서 0보다 크면 게이트웨이가 접두부 캐시를 쓴다. `None`이면 보고하지 않는 게이트웨이 |
| 왕복 `keep_reasoning` / `drop_reasoning` | 사고 내용을 붙여서/빼고 돌려줬을 때 도구 결과를 쓰는지 |
| 왕복 `user_after_tool` | 도구 결과 뒤에 사용자 메시지를 하나 더 붙여도 정상인지. 하네스 안내문을 어디에 넣을지 정하는 근거 |
| `text sample` | 본문으로 샌 도구 호출의 첫 120자. `text_tool_call`이 있을 때만 나온다. 형식을 보고 복구 파서를 맞춘다 |
| 5단계 `chars_per_token` | 한국어·영어·JSON이 토큰 하나당 몇 글자인지. 문맥 예산 계산의 초기값 |

`server` 줄은 게이트웨이 담당자에게 묻지 않고 서버 종류를 알아내기 위한 단서다. `/models` 주소에서 모델 목록도 받아 `models.json`으로 저장한다.

| 단서 | 뜻 |
|---|---|
| `owned_by: "vllm"`, `max_model_len`, `body_keys`에 `prompt_logprobs`·`kv_transfer_params`, `choice_keys`에 `stop_reason` | vLLM |
| `choice_keys`에 `matched_stop` | SGLang |
| `x_headers`에 `x-litellm-...` | LiteLLM 프록시를 거침 (뒤에 실제 서버가 따로 있음) |
| `max_model_len` | 서버가 허용하는 최대 문맥 길이. 모델 프로필에 기록 |
| `models`가 `HTTPError ... 404` 등 | 목록 주소를 막아 둔 게이트웨이. 다른 단서로 판단 |

주의: 옵션이 200이어도 서버가 조용히 무시했을 수 있다. `effort_top`의 `think_chars`/`out_tok`가 `auto`(기본 max)보다 확실히 작은지 비교한다.

## 8. 문제 해결

| 증상 | 원인·해결 |
|---|---|
| `KeyError: 'LLM_URL'` | 4번을 안 했거나 새 창. 다시 설정 |
| 전부 `http_0 ... CERTIFICATE_VERIFY_FAILED` | `$env:LLM_CA_FILE = "C:\certs\company-ca.pem"` 후 재실행. 인증서 검증을 끄지 않는다 |
| 전부 `http_0 ... timed out` / `refused` | 주소 오류 또는 프록시. `$env:NO_PROXY = "사내LLM도메인"` 시도 |
| 전부 `http_401` / `http_403` | 키 오류 또는 권한 없음 |
| 전부 `http_404` | URL 경로 오류. `/chat/completions` 포함 확인 |
| `plain`까지 전부 `http_400` | 모델 ID 오류. 오류 원문 확인 |

## 9. 결과 전달

- 화면의 `== 1.`부터 `saved:` 직전까지 약 25줄을 옮겨 적어 전달한다. 오류 원문은 앞부분만 적어도 된다.
- `probe_out` 폴더는 사내에 보관한다. 요청·응답 원문이 들어 있어 v1의 재생 테스트 자료로 다시 쓴다. 키는 들어 있지 않다. `.gitignore`에 들어 있어 실수로 push되지 않는다.

## 10. 이 테스트의 판정 기준

| 질문 | 판정 | 결과에 따른 다음 행동 |
|---|---|---|
| 게이트웨이가 어떤 옵션을 받나 | 옵션별 200/400 + 사고량 비교 | 모델 프로필에 기록 |
| 도구 결과 왕복이 되나 | `uses_result` 여부, 사고 내용 포함/제외 각각 | v1의 대화 이력 처리 방식 결정 |
| 기본 기능만으로 도구 호출이 안정적인가 | 언어별 `native_ok` 10/10 근처면 "안정" | 안정 → 복구 기능은 후순위, 구조·평가셋 집중 / 불안정 → 나온 실패 유형부터 복구 기능 구현 |
| 한국어가 토큰을 얼마나 쓰나 | `chars_per_token` | 문맥 예산 추정의 초기값으로 프로필에 기록 |
| 하네스 안내문 위치 | `user_after_tool`이 `uses_result`인지 | 아니면 안내문은 도구 결과 메시지 안에만 넣는다 |
| 얼마나 빠르고 몇 개까지 동시에 되나 | p50/p90, 429 발생 여부 | 실험 규모·시간 계산, 병렬 실행 수 결정 |

20회는 방향 결정용 선별 시험이며 통계적 증명이 아니다. 하네스 효과 비교는 다음 단계(v1)에서 한다.

## 11. 사외 Mac에서 미리 돌려보기 (선택)

사내에서 돌리기 전에 Mac의 로컬 모델로 probe.py를 돌려 보면 사용법과 출력 형식을 미리 익힐 수 있다. 결과는 그 로컬 모델의 성질일 뿐 사내 GLM 결과가 아니다.

| 서버 | 기본 주소 (`LLM_URL`) |
|---|---|
| Ollama | `http://localhost:11434/v1/chat/completions` |
| LM Studio | `http://localhost:1234/v1/chat/completions` |
| llama.cpp `llama-server --jinja` | `http://localhost:8080/v1/chat/completions` |

```bash
export LLM_URL=http://localhost:11434/v1/chat/completions
export LLM_MODEL=<서버에 올린 모델 이름>      # Ollama는 `ollama list`로 확인
export LLM_API_KEY=local                      # 로컬 서버는 아무 값이나 됨
python3 probe.py --n 3 --burst 2
```

- 권장 모델과 이유는 `DESIGN_KO.md` 6절 "사외 개발 환경" 참고. GLM 계열과 같은 형식을 보려면 GLM-4.7-Flash를 쓴다.
- Ollama는 `tool_choice`를 지원하지 않아 `required`/`named`가 200이어도 실제로 강제되지 않을 수 있다.
