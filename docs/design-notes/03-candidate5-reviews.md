# 3. 열여섯 번의 REJECT와 출하 범위 분리

[설계 노트 목차](README.md) · 이전: [2. 첫 적용과 candidate.4](02-candidates-1-4.md) · 다음: [4. 바꾸지 않은 것과 사람이 정한 것](04-decisions.md)

candidate.5(2026-10-10 공개)는 Cairn을 Claude Code와 Codex가 **같은 의미로** 쓰게 만드는 판본입니다. 이 판본은 독립 검토를 열여섯 번 받았고 열여섯 번 모두 REJECT였습니다. 그런데도 공개된 이유와 공개된 범위를 이 문서에 적습니다.

## 3.1 무엇을 시험했나

- **결정적 검사.** unittest 전체, 배포본 export 일치, Booklog 저장소 사본에서 migration 모의 실행(원본은 읽기만).
- **실제 cross-runtime conformance.** 저장소 밖 임시 fixture에서 Claude Code(`claude -p`)와 Codex(`codex exec`)를 새 프로세스로 번갈아 띄웠습니다. prompt에는 Cairn 규칙을 다시 쓰지 않았고 Packet 경로와 위임 한계만 줬습니다. 시나리오는 P1~P6, 양방향 12개입니다.
  - P1 next action projection 일치, P2 Human Gate와 escalation class 판단
  - P3 한 runtime이 구현하다 멈추고 다른 runtime이 이어받기
  - P4 한 runtime이 만든 후보를 다른 runtime이 독립 검토·인수하기
  - P5 출처 불명 변경을 만났을 때 멈추기(`recovery.status: blocked`)
  - P6 실패 evidence가 있을 때 PASS로 쓰지 않기
- 판정은 `cairn_check next-action`이 계산한 projection과 runtime 응답의 필드 비교, 파일 hash, Packet 구조로 했습니다. 모델이 모델을 채점하지 않았습니다.
- **독립 검토.** 매번 사용자가 연 새 nonproducer 세션이 producer 대화를 상속하지 않고 frozen candidate를 받아 기준별로 판정했습니다.

conformance는 계약 문장의 빈틈도 드러냈습니다. 예를 들어 하네스가 연 새 `claude -p` 세션을 Claude reviewer는 "독립 맥락은 내가 spawn해야 한다"로 읽고 멈췄고, Codex reviewer는 자기 세션을 독립으로 봤습니다. 두 runtime이 같은 문장을 다르게 읽은 것입니다. 그래서 독립 맥락을 **누가 띄웠는가가 아니라 성질**(다른 actor, 대화 미상속, bounded input)로 정의하도록 계약을 고쳤습니다. 현재 `AGENTS.md`의 "직접 띄운 것이든 사용자·orchestrator가 그렇게 연 새 세션이든 같다"가 그 결과입니다.

## 3.2 열여섯 번의 판정

| 차수 | 판정 | 주요 finding |
|---|---|---|
| 1 | REJECT | 9건. relocation이 내용 교체를 정상 이동으로 인정, 봉인 판정 우회 3종, conformance 판정기가 거절·요구 삭제를 PASS, P4의 producer가 실제 runtime이 아님 |
| 2~6 | REJECT | 각 3~6건. 1차 반례는 차례로 해소. 매 차수 relocation·봉인·residual 처리에서 validator 결함이 새로 나와 교정. 그 밖에 판정기의 다른 거짓 PASS와 **attempt 사후 기록**(runtime이 효과를 먼저 내고 기록을 나중에 씀) |
| 7·8 | REJECT | 실패 evidence·rejected 검토와 공존하는 인수를 PASS, `max_attempts` 초과를 PASS, CLOSED Packet을 옮기면 봉인이 사라짐. 실제 Codex 실행이 attempt 사전 기록을 어겼는데 판정기가 PASS(R8-01) |
| 9~13 | REJECT | 20건. 판정기 거짓 PASS 9건과 validator 결함 7건이 중심. 판정기는 shell·inline Python·Ruby 명령의 효과를 정적으로 판별하려다 막을 때마다 같은 계열의 다른 형태가 나옴 |
| 14·15 | REJECT | shell 확장, script에 붙인 `--help`, `printf -v PATH`, `for` loop 변수로 판정기의 무효과 판정을 우회 |
| 16 | REJECT | `sort -ro <밖> input`(결합 옵션의 파일 쓰기), `<<'EOF'X`(heredoc delimiter 절단으로 뒤 명령 은닉). 둘 다 판정기의 거짓 PASS. 나머지 기준(identity·validator·conformance run44 12/12·Booklog)은 PASS |

열여섯 번의 검토에서 R 번호를 붙인 finding은 69건(minor와 observation 일부 포함)이고, 이와 별도로 번호를 붙인 observation이 14건 있습니다. 15차의 첫 reviewer 세션은 판정 없이 중단돼 그 기록도 따로 보존했습니다. 모든 검토 원문과 원판정은 개발 저장소에 그대로 남겼고, 나중 판정으로 앞 판정을 고치지 않았습니다.

## 3.3 9~13차 뒤의 원인 분석

13차 뒤에 "교정 → conformance → 독립 검토"를 무한히 돌리지 않으려고 반복 REJECT의 원인을 분류했습니다. 이 분류는 producer의 분석이며 인수 판정이 아닙니다.

| 분류 | 내용 |
|---|---|
| Core 계약 결함 | 9~13차 기준 **없음**. 계약 문장의 해석 빈틈 2건(attempt 기록과 효과를 같은 쓰기 묶음에 넣음, capability 상태와 결손 처리 어휘 혼동)만 보강 |
| 판정기 거짓 PASS | 9건. 그중 5건이 같은 뿌리였습니다. **임의의 shell 프로그램이 효과를 내는지 정적 분석으로 증명하려 한 것** |
| 판정기 거짓 FAIL | 같은 분석의 반대쪽. 읽기용 inline 코드를 허용하려고 문법을 넓히면 거짓 PASS, 좁히면 거짓 FAIL |
| validator 결함 | 봉인·사본 판정 기준을 세 번 바꿈, residual liveness |
| fixture·문서 정합성 | 시나리오 정의 모호, 손으로 쓴 수치·hash → 이후 도구가 자동 생성·대조 |
| runtime 준수 편차 | 깨진 YAML, 기록과 효과를 한 patch에, 위임 끝 뒤 전이. 계약은 명시적이었고 판정기가 결정적으로 탐지 |

producer의 결론은 이랬습니다. **계약은 수렴했고, 수렴하지 않은 것은 판정기의 범위 설계였다.** 임의의 명령이 무효과인지 판별하는 문제는 열린 문제이고, 매번 한 형태를 막는 방식으로는 끝나지 않습니다.

## 3.4 종료 조건을 먼저 고정

그래서 남은 사이클의 끝을 미리 정했습니다(2026-10-09).

1. 판정기를 축소합니다. 무효과는 증명 가능한 좁은 읽기 형태(literal 인자의 Git 조회, 출력만 하는 읽기 프로그램, `sed -n '<줄>p'`, action 없는 `find`, `--version` 등)에만 인정하고, 나머지는 모두 효과 가능으로 봅니다. 거짓 FAIL은 설계상 허용합니다.
2. 계약에는 "효과 없음이 분명하지 않은 실행은 효과로 보고 attempt 뒤에 한다"는 보수적 해석만 덧붙입니다. 의무의 경계(Human Decision HD-C5-02)는 바꾸지 않습니다.
3. 한 동결본의 conformance는 최대 3회, 교정 뒤 재검토는 **최대 2회**입니다.
4. 그래도 blocking·major가 남으면 더 고치지 않고 사람에게 올립니다(재설계 또는 잔여 위험 수용).
5. 범용 프로그램 효과 분석, 새 기능, allowlist 밖 형태를 무효과로 인정해 달라는 요구는 인수 조건에 넣지 않습니다.

14→15차, 15→16차로 교정 기회 두 번을 모두 썼습니다. 16차도 판정기에서 major 두 건이 나왔고, 조건 4에 따라 멈췄습니다.

## 3.5 release-scope 분리

사용자 결정 HD-C5-03(2026-10-09)으로 인수 대상을 둘로 나눴습니다.

| 대상 | 지위 |
|---|---|
| 배포 계약 8파일(Core·`AGENTS.md`·`CLAUDE.md`·adapter 2개·설정·템플릿·manifest)과 companion validator `cairn_check` 0.3.0 | **release-scope**. 파일 24개의 hash로 `release_scope_id`를 고정하고 독립 검토 대상으로 삼음 |
| 명령 문자열 기반 attempt-effect 판정기(개발 전용 conformance 도구) | **미인수 개발 도구.** 공개 manifest에 넣지 않음. R16-01·02는 미해결로 유지 |

이 결정이 하지 않은 것도 같이 적었습니다.

- 16차 REJECT를 철회하지 않았고, candidate 전체를 ACCEPT하지 않았습니다.
- attempt 사전 기록 의무는 그대로 둡니다. 임의의 명령에 대해 그 준수를 자동 증명하는 기능만 이 release의 보장에서 뺐습니다. README "현재 한계"의 첫 줄이 이 내용입니다.
- 실행 순서 검증 강화는 backlog로 넘기고 새 구현을 시작하지 않았습니다.

release-scope는 별도의 새 Codex nonproducer 세션이 독립 판정했습니다. 결과는 **PASS + ACCEPT**(blocking 0, major 0, minor 2)였습니다. minor 두 건(공개 tree identity 재산출 경로, 파일 수 표기)을 고친 뒤 공개 Human Gate(HD-C5-04)를 따로 받았습니다. 승인 대상은 base commit, staging tree, README hash, content_id, `release_scope_id`였고, 하나라도 다르면 실행하지 않는 조건이었습니다. 공개는 non-force push 하나로 끝났고, 원격 identity를 대조한 뒤에야 완료로 기록했습니다.

## 3.6 남긴 교훈

- **검증 도구가 판정할 수 없는 것을 판정하게 하면 검토는 수렴하지 않는다.** 판정기를 고칠수록 반례의 형태만 바뀌었습니다. 범위를 좁히고 나머지는 의무와 사람·독립 검토의 몫으로 남기는 편이 정직했습니다.
- **종료 조건은 사이클 중간이 아니라 시작 전에 정한다.** 횟수와 인수 조건을 먼저 고정한 뒤에야 "한 번만 더"가 멈췄습니다.
- **REJECT를 지우지 않고 범위를 나눠 인수할 수 있다.** 인수한 범위와 인수하지 않은 범위, 미해결 finding을 같은 문서에 남기면 공개본의 보장이 무엇인지 읽는 사람이 판단할 수 있습니다.
- **실제 runtime의 준수는 실행마다 흔들린다.** 같은 동결본에서도 run43은 10/12, run44는 12/12였습니다. conformance 통과는 관측 범위의 근거이고 매 실행의 보장이 아닙니다.
