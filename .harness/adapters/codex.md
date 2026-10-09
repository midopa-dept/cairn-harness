# Cairn runtime adapter — Codex

이 파일은 공통 계약(`AGENTS.md`, `.harness/core.yaml`)의 capability를 Codex 도구에 대응시킬 뿐이다. gate·인수·권한·요구·다음 행동 의미를 바꾸지 않는다. 충돌하면 공통 계약이 우선한다. runtime family는 `codex`, 권장 actor ID 접두는 `codex`다.

## 진입점

- Codex는 Git root에서 현재 디렉터리까지의 `AGENTS.md`를 연결해 읽는다. 기본 상한은 32 KiB(`project_doc_max_bytes`)이며 넘으면 뒤쪽 지침이 빠진다. 프로젝트 로컬 절을 더해도 `AGENTS.md`를 이 상한보다 충분히 작게 유지한다.
- `AGENTS.override.md`를 Cairn 프로젝트에 두지 않는다. Codex에서는 같은 디렉터리의 `AGENTS.md`를 대체하지만 Claude Code는 읽지 않아 의미가 갈라진다.
- `CLAUDE.md`와 `@path` import는 Codex가 해석하지 않는다. 공통 규칙은 `AGENTS.md`에만 있어야 한다.
- admit·recover 때 이 파일을 읽는다.

## Capability 대응

| capability | Codex 수단 | 관찰 방법 |
|---|---|---|
| read_files | 파일 읽기·shell 읽기 명령 | 대상 파일 읽기 |
| edit_files | 파일 편집(apply_patch 등) | sandbox `read-only`면 unavailable(승인 시 gated) |
| execute_commands | sandbox 안의 shell | sandbox 모드와 approval policy. 밖으로 나가면 gated. shell이 login 환경으로 PATH를 다시 구성할 수 있으므로 프로젝트 도구는 저장소 상대 경로나 절대 경로로 부르고 `command -v`로 관찰한다 |
| git | shell의 `git` | `git status` 실행. `.git` 쓰기가 막히면 commit은 unavailable 또는 gated |
| network | shell 네트워크 | sandbox 기본 차단일 수 있다. 실제 요청으로 관찰 |
| spawn_independent_context | 새 `codex exec` 프로세스(`exec resume`·`fork` 아님) 또는 부모 대화를 넘기지 않는 subagent에 bounded task만 전달 | 아래 독립 맥락 절 |
| browser_observation | 실제로 연결된 browser 도구 또는 shell의 browser 자동화 | 실제 화면 관찰. 없으면 unavailable |
| production_read / production_write | 위임된 CLI·자격으로 shell 실행 | 계획·위임·Gate가 없으면 사용하지 않는다. 대개 gated |
| human_interaction | 대화형 TUI의 질문 | `codex exec` 비대화형이면 unavailable → 질문을 Packet에 남기고 blocker |

## 독립 맥락

- `codex fork`·`codex exec resume`·이전 thread 이어가기는 부모 대화를 상속하므로 `spawn_independent_context`가 아니다.
- reviewer는 새 `codex exec` 세션 또는 bounded task만 받는 subagent로 띄운다. subagent가 부모 대화를 받는지 확실하지 않으면 새 `codex exec`를 쓴다. 입력은 frozen candidate 식별자·criteria·계약 발췌·원근거 경로로 한정하고 producer reasoning을 넣지 않는다. 사용한 수단과 입력 목록을 `independence`에 기록한다.
- reviewer에게 candidate를 수정하지 말라고 지시한다. 판정은 reviewer 기록을 그대로 Packet `decisions`에 옮긴다.

## Attempt 기록 순서

- `apply_patch` 한 번에 Packet의 attempt 기록과 산출물·evidence 변경을 함께 넣지 않는다. attempt 기록 patch를 먼저 적용하고 Packet이 YAML로 읽히는지 확인한 뒤 산출물을 고치거나 검증을 실행한다.
- `python3 -m py_compile`처럼 cache를 쓰는 검사도 attempt 뒤에 실행한다.
- attempt 전에 실행할 수 있는 shell 명령은 매우 좁다: literal 인자만 쓴 단일 조회 명령(`git` 조회, `cat`·`head`·`ls`·`wc`·`grep`·`sed -n '<줄>p'`, action 없는 `find`, `command -v`, 프로젝트의 결정적 검사 도구)과 그것들을 `;`·`&&`·`|`로 이은 것. 경로는 하나씩 적는다.
- 변수·`$?`·`$(…)`·glob(`*`)·`for`·`if`·`test`·`[`·`find -exec`·`sh -c`·대입·inline 코드는 읽기 목적이어도 효과 가능으로 판정된다. 이런 조회가 필요하면 먼저 attempt를 기록한다. Packet을 `python3`·`ruby` inline 코드로 읽는 것도 attempt 뒤에 한다.

## 메모리와 기록

- Codex thread·session 기록·memory는 authority가 아니다. 재개에 필요한 상태는 Packet·Git·evidence에 둔다.
- commit attribution은 Codex 관례를 따른다. `git_closeout` 정책은 동일하다.

## 선택 강제 수단

sandbox writable root를 좁혀 봉인 경로 쓰기를 막을 수 있다. 계약 준수의 대체가 아니라 보조 수단이며 Core 요구가 아니다.
