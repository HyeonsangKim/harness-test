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
| 1. 연기 테스트 | `python probe.py --n 1 --burst 1` | 약 24회 | 주소·키·연결 확인 |
| 2. 본 테스트 | `python probe.py --n 10` | 약 45회 | 옵션 지원, 도구 왕복, 신뢰도 20회, 지연, 동시성, 토큰 보정, 사고량 비교 |

사고 모드는 끌 수 없어서 호출당 수십 초 걸릴 수 있다. 특히 6단계는 계산 문제를 서버 기본 사고량(max)으로도 풀게 하므로 한 번에 몇 분 걸릴 수 있다(호출당 최대 10분 대기). 옵션:

- `--n 10` : 언어별 신뢰도 시험 횟수 (영어 10 + 한국어 10)
- `--burst 4` : 동시에 보낼 요청 수
- `--effort low` : 2~4단계의 사고량. `high`, `max`, 또는 `none`(서버 기본값=max)

## 7. 출력 읽는 법

전달할 때는 9절의 요약 9줄만 옮기면 된다. 이 절은 화면을 직접 읽고 싶을 때 참고한다.

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
== 6. thinking effort on a harder question (answer should be 401)
default    {'think': 5210, 'seconds': 41.2, 'answer': 'Y'}  ...
top_low    {'think': 380, 'seconds': 4.1, 'answer': 'Y'}  ...
saved: C:\Users\...\probe_out\20261020-101500
== copy these lines
(요약 9줄. 9절 참고)
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

**맨 끝 `== copy these lines` 아래 9줄만 옮겨 적는다.** 위쪽의 긴 출력은 옮기지 않는다. 같은 내용이 결과 폴더의 `summary.txt`에도 저장된다.

```
S1 plain=none auto=ok required=ok named=ok strict=400 no_parallel=ok effort_top=ok effort_kwargs=400 thinking_obj=ok
T1 think auto=1840 top=210 kw=0
SV litellm ctx=202752 models=x info=ok
S2 keep=Y drop=Y user=Y
S3 en=10/10 ko=9/10,txt:1 txtfmt=glm p50=6.2 p90=11.4
S4 ok:3 429:1
S5 ko=1.5 en=4.3 json=3.1
T2 default=5210c/41.2s/Y top_low=380c/4.1s/Y top_high=2400c/19.0s/Y kw_low=380c/4.0s/Y kw_high=2400c/18.7s/Y
ER strict: {"error":"strict not supported"}
```

| 줄 | 내용 | 표기 |
|---|---|---|
| `S1` | 1단계 옵션 9개의 결과 | `ok`=정상 호출, `txt`=본문으로 샘, `none`=도구 안 씀(`plain`은 이게 정상), `len`=잘림, `400` 같은 숫자=HTTP 상태, `0`=연결 실패 |
| `T1` | 사고 글자 수: 기본(`auto`) / `effort_top` / `effort_kwargs` | 기본보다 확 작은 쪽이 실제로 먹힌 옵션 |
| `SV` | 서버 추정, 최대 문맥 길이, 모델 목록·모델 정보 응답 여부 | `?`=판별 못 함, `x`=그 주소가 막힘. LiteLLM이면 `/model/info`에서 문맥 길이를 찾는다 |
| `S2` | 도구 결과 왕복: 사고 포함 / 사고 제외 / 뒤에 사용자 메시지 | `Y`=결과를 씀, `N`=안 씀 |
| `S3` | 언어별 정상 호출 수/시도 수, 그 밖의 결과별 개수, 샌 호출 형식, 지연(초) | `txtfmt`: `glm`=GLM 형식, `json`=JSON 형식, `-`=샌 것 없음 |
| `S4` | 동시 요청 결과별 개수 | `429`=동시 요청 한도에 걸림 |
| `S5` | 토큰당 글자 수 | 비어 있으면 서버가 토큰 수를 안 알려줌 |
| `T2` | 계산 문제(정답 401)를 사고량별로 풀린 결과: 사고 글자 수 c / 걸린 초 s / 정답 여부 | `default`=서버 기본값(max). `top_*`와 `kw_*`는 사고량을 넣는 두 방식. 글자 수가 low < high < default로 갈리면 그 방식이 실제로 먹힌다 |
| `ER` | 첫 번째 오류 원문 70자 | `-`=오류 없음. 사내 주소가 들어 있으면 지우고 적는다 |

- 숫자 몇 개 틀려도 괜찮다. 판정이 애매하면 그 부분만 다시 물어본다.
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

## 12. 모델 동작 맛보기: behavior.py

probe.py가 "게이트웨이와 형식"을 본다면, behavior.py는 "모델이 일을 어떻게 하는지"를 작은 문제 6종으로 본다. probe.py와 같은 폴더에서, 같은 환경변수로 실행한다. 키는 다시 입력한다.

```powershell
python behavior.py --rep 3
```

약 40회 호출, 사고량은 기본 low(`--effort high`로 바꿀 수 있다). 끝나면 `== copy these lines` 아래 6줄만 옮긴다.

```
B-multi 3/3 calls=2,3,2
B-recover 2/3 calls=3,3,1
B-parallel 3/3 par=2,1,2
B-pick 3/3 first=get_receivable,get_receivable,get_receivable
B-needle 8000=Y/8120tok/3.1s 32000=N/32400tok/9.8s
B-json Y,Y,fence
```

| 줄 | 시험 | 보는 것 |
|---|---|---|
| `B-multi` | 가짜 ERP 표 3개(전표, 2023 백업 전표, 부서)에서 "9월 미결 전표 합계가 가장 큰 부서와 금액" 찾기 | 여러 번 도구를 불러 끝까지 가는지. 백업 표에 속지 않는지. 합계를 직접 맞게 더하는지. `calls`=도구 호출 수 |
| `B-recover` | 틀린 품목코드로 재고 조회 → 오류 메시지 → 검색 후 다시 조회 | 도구 오류를 읽고 스스로 고치는지. 같은 틀린 호출을 반복하는지 |
| `B-parallel` | "서울이랑 부산 날씨 둘 다" | 한 번에 도구를 2개 부르는지(`par`=한 응답의 최대 호출 수). 1이면 하나씩 부름 |
| `B-pick` | 도구 20개 중 미수금 조회 도구 고르기 | 도구가 많을 때 맞는 것을 고르는지. `first`=처음 부른 도구 |
| `B-needle` | 약 8천·3만 2천 토큰 한국어 글 가운데 숨긴 암호명 찾기 | 긴 문맥에서 정보를 놓치는지. `Y/N`, 실제 입력 토큰, 시간 |
| `B-json` | 전표 3건을 JSON으로만 출력 | 형식 지시를 지키는지. `fence`=코드블록으로 감쌈, `shape`=내용 틀림, `bad`=JSON 아님 |

`err=` 뒤에 `txt`(도구 호출이 본문으로 샘), `max_turns`(8번 안에 못 끝냄), `http_...`가 붙으면 그대로 옮긴다. 이 시험은 맛보기다. 하네스를 켜고 끈 비교는 실제 업무 예시로 2단계에서 한다.
