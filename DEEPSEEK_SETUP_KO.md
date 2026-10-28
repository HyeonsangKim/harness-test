# DeepSeek-V4.1-Flash 사내 시험 가이드

사내 DeepSeek-V4.1-Flash(1017)가 왜 느린지 재고, 하네스 두 가지로 실제 작업을 시켜 본다. 코드는 표준 라이브러리만 쓰므로 설치할 것이 없다.

| 순서 | 할 일 | 파일 | 시간 |
|---|---|---|---|
| 1 | 받기와 설정 | — | 5분 |
| 2 | 진단: 무엇이 느린지 | `deepseek/ds_check.py` | 10~30분 |
| 3 | 최소 에이전트로 연습 과제 | `deepseek/ds_agent.py` | 5~20분 |
| 4 | Claude Code로 같은 과제 | `deepseek/ds_proxy.py` | 10~30분 |
| 5 | 결과 옮기기 | — | 5분 |

## 배경: 왜 두 하네스인가

DeepSeek 모델 카드에 같은 모델을 하네스별로 잰 점수가 있다(추론 강도 최대 기준).

| 하네스 | DeepSWE v1.1 | Terminal-Bench 2.1 |
|---|---|---|
| mini-SWE (최소 구성) | 74.2 | 90.3 |
| DSH Minimal (bash + 문자열 치환 편집, 도구 2개) | 72.6 | 90.6 |
| Claude Code | 69.8 | 88.0 |

- 도구 두 개짜리 최소 하네스가 Claude Code보다 점수가 높다. 프롬프트도 훨씬 짧아서 느린 서버에서 유리하다.
- `ds_agent.py`는 그 최소 구성(셸 + 문자열 치환 편집)이다.
- Claude Code는 팀이 익숙한 도구라서 함께 잰다.
- 출처: `huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash` README. DeepSeek이 직접 잰 값이다.

## 1. 받기와 설정

```powershell
cd $env:USERPROFILE\work\harness-test
git pull
uv run --offline --no-project --python 3.12 -m py_compile deepseek\llm.py deepseek\ds_check.py deepseek\ds_agent.py deepseek\ds_proxy.py
```

아무 출력이 없으면 통과다. `uv` 옵션의 뜻은 `PROBE_GUIDE_KO.md` 1절에 있다.

### 주소·모델 (이 PowerShell 창에서만 유효)

```powershell
$env:LLM_URL = "https://<게이트웨이>/v1/chat/completions"    # /chat/completions까지 포함한 전체 주소
$env:LLM_MODEL = "<사내 안내의 DeepSeek 모델 ID>"
# SSL 오류가 날 때만
$env:LLM_CA_FILE = "C:\certs\company-ca.pem"
```

- API 키는 스크립트가 시작할 때 `API key:`로 묻는다. 붙여넣고 Enter를 누른다. 화면에 안 보이는 게 정상이다.
- 키는 파일·로그에 저장되지 않는다. 여러 번 돌릴 때만 `$env:LLM_API_KEY`를 쓰고, 끝나면 `Remove-Item Env:LLM_API_KEY`로 지운다.

### 요청에 늘 붙일 옵션: `LLM_EXTRA`

세 스크립트 모두 `LLM_EXTRA`(JSON)를 모든 요청에 합친다. 추론 강도는 여기서 정한다. 어떤 값이 먹는지는 2절 결과를 보고 정한다.

```powershell
$env:LLM_EXTRA = '{"reasoning_effort":"low"}'    # 예시. 2절 결과로 정한다
Remove-Item Env:LLM_EXTRA                         # 끄기
```

## 2. 진단: `ds_check.py`

```powershell
cd deepseek
uv run --offline --no-project --python 3.12 ds_check.py
```

| 단계 | 재는 것 | 호출 수 |
|---|---|---|
| connect | 연결, 스트리밍 지원 여부, 첫 토큰까지 시간 | 1 |
| effort | 같은 계산 문제(정답 439)를 추론 강도 옵션 7가지로. 시간, 사고 토큰, 정답 | 7 |
| speed | 300단어 글쓰기의 생성 속도(토큰/초) | 1 |
| cache | 긴 문서(약 4만 자)를 앞에 두고 질문만 바꿔 두 번. 둘째 호출이 빨라지는지 | 2 |
| tools | 도구 호출 한 번과 결과 왕복 | 2 |
| anthropic | 게이트웨이가 Claude Code 형식(`/v1/messages`)을 직접 받는지 | 1 |

- 추론 강도가 최대이면 호출마다 몇 분 걸릴 수 있다. 호출당 최대 15분 기다린다.
- 일부만 돌리려면 `--only effort,cache`처럼 쓴다. 캐시 문서 길이는 `--cache-chars 80000`으로 바꾼다.
- 원본 기록은 `deepseek\runs\ds_check\<시각>\`에 남는다(키 없음).

### 결과 읽는 법

| 보이는 것 | 뜻 | 할 일 |
|---|---|---|
| effort 행 중 200이고 정답 Y인데 시간·사고 토큰이 기본보다 크게 적은 행이 있다 | 그 옵션이 먹는다 | 그 옵션을 `LLM_EXTRA`에 넣고 3·4절을 진행한다 |
| effort 행이 전부 기본과 비슷하다 | 게이트웨이가 옵션을 무시하거나 버린다 | 게이트웨이 담당자에게 추론 강도 전달 방법을 묻는다 |
| 첫토큰 시간이 길고 생성 속도는 괜찮다 | 입력 처리(긴 프롬프트)가 병목이다 | 캐시 결과를 본다 |
| 캐시 "안 됨" | 매 호출 프롬프트 전체를 다시 계산한다. Claude Code처럼 프롬프트가 긴 하네스에서 특히 느리다 | 서빙 담당자에게 prefix caching(vLLM `--enable-prefix-caching`, SGLang radix cache) 켜기를 요청한다 |
| 생성 속도가 초당 20토큰 아래 | 서버 생성이 느리다 | 서빙 담당자에게 추측 디코딩(DSpark 또는 MTP) 사용 여부를 묻는다 |
| 도구 호출 Y, 왕복 Y | 하네스를 붙일 수 있다 | 3절로 |
| Anthropic 형식 200 | Claude Code를 게이트웨이에 직접 붙일 수 있다 | 4절의 "직접 연결"도 가능하다 |

## 3. 최소 에이전트: `ds_agent.py`

연습 과제는 `deepseek\sample_task`에 있다. 테스트 3개가 실패하는 작은 파이썬 파일이다(금액 파싱, 평균, 팀별 합계). 원본을 건드리지 않게 복사해서 쓴다.

```powershell
Copy-Item -Recurse -Force sample_task $env:TEMP\ds_sample1
uv run --offline --no-project --python 3.12 ds_agent.py --task-file sample_task\TASK.txt --dir $env:TEMP\ds_sample1
```

- 명령이나 편집을 실행하기 전마다 `실행할까요? [y/n/a]`를 묻는다. `a`는 이후 모두 실행이다. 처음부터 묻지 않으려면 `--yes`를 쓴다.
- 모델 셸은 Windows에서 PowerShell이다. 작업 폴더에서 실행되고, 이름에 `KEY`, `TOKEN`이 들어간 환경변수와 `LLM_*`는 넘기지 않는다. 보안 격리 장치는 아니므로 중요한 파일이 있는 폴더를 `--dir`로 주지 않는다.
- 호출마다 `[3] 12.4초 (첫토큰 8.1초) 입력 8123(캐시 7900) 출력 512(사고 400)` 같은 줄이 나온다.
- 끝나면 `요약:` 한 줄과 기록 파일(`deepseek\runs\ds_agent\<시각>.json`) 위치가 나온다.
- 성공 확인: `cd $env:TEMP\ds_sample1; uv run --offline --no-project --python 3.12 -m unittest -v`가 3개 모두 ok.

내 업무에 쓸 때:

```powershell
uv run --offline --no-project --python 3.12 ds_agent.py "로그 폴더에서 오늘 ERROR 줄만 모아 errors.txt로 저장해" --dir D:\작업폴더
```

옵션: `--steps 40`(호출 상한), `--max-tokens 32768`(호출당 출력 상한). 환경변수 `AGENT_SHELL_TIMEOUT`(명령 시간 상한, 기본 120초), `AGENT_OUTPUT_CHARS`(도구 출력 자르기, 기본 1만 자).

## 4. Claude Code로 같은 과제

사내 PC에 Claude Code가 설치돼 있어야 한다. 게이트웨이가 OpenAI 형식만 받으면 `ds_proxy.py`가 중간에서 형식을 바꾼다. 프록시는 요청마다 시간·토큰 한 줄을 남기므로, 게이트웨이가 Anthropic 형식을 받더라도 처음에는 프록시로 재는 것을 권한다.

### 창 1: 프록시

```powershell
cd $env:USERPROFILE\work\harness-test\deepseek
$env:LLM_URL = "https://<게이트웨이>/v1/chat/completions"
$env:LLM_MODEL = "<모델 ID>"
$env:LLM_EXTRA = '{"reasoning_effort":"low"}'     # 2절에서 고른 값
uv run --offline --no-project --python 3.12 ds_proxy.py
```

- `API key:`에 게이트웨이 키를 넣는다. 키는 프록시 안에만 있고, Claude Code에는 가짜 값을 준다.
- `127.0.0.1:8787`에서만 듣는다(다른 PC에서 접속 불가).
- Claude Code가 보내는 모델 이름(메인, haiku, 하위 에이전트)은 모두 `LLM_MODEL`로 바뀐다.
- Claude Code의 `/effort`는 효과가 없다. 추론 강도는 프록시의 `LLM_EXTRA`로 정한다.
- 모델의 사고 내용은 Claude Code로 넘기지 않는다. 길이만 로그에 남긴다. 그래서 생각하는 동안 Claude Code 화면은 멈춘 것처럼 보인다.
- 로그 예: `#3 10:42:01 deepseek-flash→deepseek-flash msgs 12 tools 21 | 첫토큰 9.8s 전체 21.3s | 입력 24180(캐시 23900) 출력 410(사고 300, 사고글자 1100) | tool_use`. 같은 내용이 `deepseek\runs\ds_proxy\<시각>.log`에 남는다.

### 창 2: Claude Code

```powershell
Copy-Item -Recurse -Force $env:USERPROFILE\work\harness-test\deepseek\sample_task $env:TEMP\ds_sample2
cd $env:TEMP\ds_sample2
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787"
$env:ANTHROPIC_AUTH_TOKEN = "local"                       # 프록시는 이 값을 쓰지 않는다
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
$env:ANTHROPIC_MODEL = "deepseek-flash"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL = "deepseek-flash"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL = "deepseek-flash"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL = "deepseek-flash"
$env:CLAUDE_CODE_SUBAGENT_MODEL = "deepseek-flash"
$env:CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = "1"
$env:CLAUDE_CODE_ATTRIBUTION_HEADER = "0"
$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
$env:CLAUDE_CODE_MAX_CONTEXT_TOKENS = "1000000"
$env:API_TIMEOUT_MS = "1800000"
claude
```

들어가면 `TASK.txt`의 내용을 그대로 붙여 넣는다.

| 설정 | 이유 |
|---|---|
| `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` | 프록시로 보낸다. 토큰은 가짜 값 |
| `ANTHROPIC_MODEL`과 `DEFAULT_*_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL` | 어떤 이름이든 프록시가 사내 모델로 바꾸지만, Claude Code 쪽 표시와 문맥 크기 계산을 맞춘다 |
| `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` | Claude 전용 시험 기능 필드를 보내지 않는다 |
| `CLAUDE_CODE_ATTRIBUTION_HEADER=0` | 시스템 프롬프트 맨 앞의 버전 정보 블록을 뺀다. 게이트웨이 쪽 캐시 적중에 유리하다(Claude Code 공식 문서) |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` | 자동 업데이트, 텔레메트리, 오류 보고를 끈다. 폐쇄망에서 바깥으로 나가려다 멈추는 일을 막는다 |
| `CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000` | 모르는 모델 이름이라 Claude Code가 문맥 크기를 짐작하지 않게 한다. 서버가 더 작은 문맥으로 떠 있으면 그 값으로 바꾼다 |
| `API_TIMEOUT_MS=1800000` | 응답 시작까지 30분 기다린다. 긴 프롬프트를 처음 계산할 때 기본값으로는 끊길 수 있다 |

- 처음에 `[claude-code:unrecognized_model]` 줄이 나와도 정상이다.
- 첫 요청은 Claude Code의 시스템 프롬프트와 도구 정의 전체를 처음부터 계산하므로 가장 느리다. 둘째 요청부터 프록시 로그의 `캐시` 숫자가 입력과 비슷하게 커지면 캐시가 동작하는 것이다.

### 직접 연결 (2절 Anthropic 형식이 200일 때만)

프록시 없이 게이트웨이에 바로 붙인다. 요청별 로그는 없다.

```powershell
$env:ANTHROPIC_BASE_URL = "https://<게이트웨이 루트>"      # /v1/messages 앞까지
$env:ANTHROPIC_AUTH_TOKEN = [Net.NetworkCredential]::new("", (Read-Host "API key" -AsSecureString)).Password
# 나머지 환경변수는 위와 같다. 모델 이름은 사내 모델 ID를 그대로 쓴다.
claude
```

추론 강도는 Claude Code의 `/effort`로 정한다. 게이트웨이가 이 값을 모델에 넘기는지는 프록시 측정과 시간을 비교해 확인한다.

## 5. 옮길 것

1. `ds_check.py`의 `===== 옮길 것 =====` 블록 전체
2. 고른 `LLM_EXTRA` 값
3. `ds_agent.py` 연습 과제의 `요약:` 한 줄과 테스트 결과(통과 개수)
4. Claude Code 연습 과제의 프록시 로그 줄 전부(`#1 ...`부터), 테스트 결과, 걸린 시간
5. 막힌 곳이 있으면 오류 메시지 첫 줄

## 6. 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `환경변수 LLM_URL가 없습니다` | 새 창이라 설정이 없다 | 1절 설정을 다시 한다 |
| `SSLCertVerificationError` | 사내 인증서 | `LLM_CA_FILE`을 지정한다. 검증을 끄지 않는다 |
| connect에서 스트리밍 실패 후 성공 | 게이트웨이가 스트리밍을 막았다 | `ds_check`, `ds_agent`는 그대로 쓴다. 프록시와 Claude Code는 스트리밍이 필요하므로 게이트웨이 담당자에게 문의한다 |
| `[429] ...초 후 다시 시도` | 호출 한도 | 자동으로 기다린다. 계속되면 시간을 두고 다시 한다 |
| 에이전트가 같은 명령을 반복한다 | 모델이 막혔다 | Ctrl+C로 끊고 과제 설명을 더 구체적으로 쓴다 |
| Claude Code가 `API Error: 400` | 게이트웨이가 요청 필드를 거부했다 | 프록시를 `--dump`로 다시 띄우고 같은 일을 한 뒤 `deepseek\runs\ds_proxy\last_request.json`의 `openai` 부분과 프록시 로그의 오류 줄을 확인한다(대화 내용이 들어 있으니 밖으로 옮기지 않는다) |
| Claude Code가 응답 없이 오래 멈춤 | 모델이 생각 중이거나 첫 계산 중 | 프록시 창에 그 요청 줄이 아직 안 찍혔으면 계산 중이다. 2절의 추론 강도와 캐시를 먼저 해결한다 |
| 프록시 `Claude Code가 연결을 끊음(취소)` | Esc로 취소했거나 시간 초과 | 시간 초과라면 `API_TIMEOUT_MS`를 늘린다 |

## 7. 파일

| 파일 | 역할 |
|---|---|
| `deepseek/llm.py` | 공통 호출 코드(스트리밍, 재시도, 사고·캐시 토큰 읽기) |
| `deepseek/ds_check.py` | 2절 진단 |
| `deepseek/ds_agent.py` | 3절 최소 에이전트 |
| `deepseek/ds_proxy.py` | 4절 Claude Code용 형식 변환 프록시 |
| `deepseek/sample_task/` | 연습 과제(테스트 3개 실패 상태) |

사외 검증: 가짜 OpenAI 호환 서버(스트리밍, 사고 출력, 캐시 토큰, 도구 호출 흉내)로 세 스크립트를 돌렸고, Claude Code 2.1.312가 프록시를 거쳐 셸 도구를 호출하고 결과를 받아 끝나는 것까지 확인했다. 실제 DeepSeek 모델로는 사내에서 처음 잰다.
