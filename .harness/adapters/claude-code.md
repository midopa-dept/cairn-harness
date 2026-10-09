# Cairn runtime adapter — Claude Code

이 파일은 공통 계약(`AGENTS.md`, `.harness/core.yaml`)의 capability를 Claude Code 도구에 대응시킬 뿐이다. gate·인수·권한·요구·다음 행동 의미를 바꾸지 않는다. 충돌하면 공통 계약이 우선한다. runtime family는 `claude_code`, 권장 actor ID 접두는 `claude`다.

## 진입점

- `CLAUDE.md`가 `@AGENTS.md`와 이 파일을 import한다. Claude Code는 `CLAUDE.md`가 있으면 `AGENTS.md`를 직접 읽지 않으므로 이 import를 지운다면 공통 계약이 로드되지 않는다.
- Cairn 규칙을 `CLAUDE.local.md`·`.claude/rules/`·하위 디렉터리 `CLAUDE.md`·auto memory에 두지 않는다. Codex가 읽지 못한다.

## Capability 대응

| capability | Claude Code 수단 | 관찰 방법 |
|---|---|---|
| read_files | Read·Grep·Glob | 대상 파일 읽기 |
| edit_files | Edit·Write | permission mode가 plan이면 unavailable |
| execute_commands | Bash | permission mode·sandbox·deny 규칙에 따라 available 또는 gated |
| git | Bash의 `git` | `git status` 실행 |
| network | WebFetch·Bash 네트워크 | 실제 요청 성공 여부. 실패하면 unavailable |
| spawn_independent_context | Agent 도구로 **fork가 아닌** 이름 있는 subagent(예: general-purpose) 또는 별도 `claude -p` 새 프로세스 | 아래 독립 맥락 절 |
| browser_observation | 실제로 연결된 browser 도구(브라우저 MCP·Playwright 실행 등) | 도구 목록과 실제 화면 관찰. 없으면 unavailable |
| production_read / production_write | 위임된 CLI·자격으로 Bash 실행 | 계획·위임·Gate가 없으면 사용하지 않는다. 대개 gated |
| human_interaction | 대화형 세션의 AskUserQuestion | `-p` 비대화형이면 unavailable → 질문을 Packet에 남기고 blocker |

## 독립 맥락

- interactive 세션은 fork mode가 기본 on이다. fork subagent와 `subtask` 명령은 부모 대화 전체를 상속하므로 `spawn_independent_context`가 아니다.
- reviewer는 fork가 아닌 subagent type을 명시해 띄운다. 입력은 frozen candidate 식별자·criteria·계약 발췌·원근거 경로로 한정하고 producer reasoning·자기평가를 넣지 않는다. 사용한 subagent type과 입력 목록을 `independence`에 기록한다.
- 확실하지 않으면 별도 `claude -p` 프로세스(새 세션, resume·continue 아님)를 쓴다.
- reviewer에게 candidate를 수정하지 말라고 지시하고 판정은 reviewer가 쓴 기록을 요약 없이 Packet `decisions`에 옮긴다.

## Attempt 기록 순서

- attempt 기록 Edit을 먼저 끝내고 Packet이 YAML로 읽히는지 확인한 뒤 산출물을 쓰거나 검증을 실행한다. 같은 응답에서 기록과 효과 tool 호출을 병렬로 내지 않는다.
- 작업 트리 밖 scratch 파일 쓰기(`>` 재지정 포함)도 효과다. attempt 전에 큰 파일을 나눠 읽을 때는 scratch에 잘라 쓰지 말고 Read의 offset·limit이나 `sed -n` 출력으로 읽는다.
- attempt 전 상태 확인은 Read·Grep·Glob 도구를 먼저 쓴다. Bash는 literal 인자만 쓴 단일 조회 명령(`git` 조회, `ls`·`wc`·`sed -n '<줄>p'`, `command -v`, 프로젝트의 결정적 검사 도구)과 그것들을 `;`·`&&`·`|`로 이은 것만 attempt 전에 쓴다.
- 변수·`$?`·`$(…)`·glob(`*`)·`for`·`if`·`test`·`find -exec`·`sh -c`·대입·inline 코드는 읽기 목적이어도 효과 가능으로 판정된다. 이런 조회가 필요하면 먼저 attempt를 기록한다. Packet을 `python3`·`ruby` inline 코드로 읽는 것도 attempt 뒤에 한다.

## 메모리와 기록

- auto memory·session 기록·TodoWrite는 authority가 아니다. 작업 상태·Packet 내용을 그곳에만 저장하지 않는다. 재개에 필요한 상태는 Packet·Git·evidence에 둔다.
- commit에는 Claude Code의 Co-Authored-By trailer를 붙인다. `git_closeout` 정책은 동일하다.

## 선택 강제 수단

봉인 경로 쓰기를 막고 싶으면 프로젝트가 PreToolUse hook으로 Edit·Write 대상 경로를 거부할 수 있다. 계약 준수의 대체가 아니라 보조 수단이며 Core 요구가 아니다.
