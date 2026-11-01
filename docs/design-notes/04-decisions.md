# 4. 바꾸지 않은 것과 사람이 정한 것

[설계 노트 목차](README.md) · 이전: [3. 열여섯 번의 REJECT](03-candidate5-reviews.md)

candidate.5의 설계 결정을 요약합니다. 대부분의 결정은 선택지 두세 개를 장단점과 함께 비교한 뒤 하나를 골랐습니다. 사람에게 올린 결정은 한 번에 질문 하나로 물었고, 답과 근거를 그대로 기록했습니다.

## 4.1 뒤집지 않는 것

candidate.5는 candidate.4의 다음 결정을 그대로 두고 시작했습니다.

- 권한 = role ∩ node ∩ scope, 자기 인수 금지, Human Gate 범주, 한 번에 질문 하나
- lifecycle 네 상태(OPEN·VERIFIED·ACCEPTED·CLOSED). **새 상태를 더하지 않는다**
- Coverage Matrix(project-local sidecar, drift는 저장하지 않고 계산), 검사 단계 VS0~VS6
- Artifact Graph는 relation 네 개짜리 탐색 단서, provenance는 Packet field
- 모델 판단 점수(외부 도구 Jev)는 Core 밖 실험
- validator는 authority·의미 판정·인수가 아니다

새 요구를 넣을 때의 순서도 정해 두었습니다. **재사용 → 정책 문장 → validator 검사 → 작은 선택 schema → 새 artifact → subsystem.** 앞 단계로 해결되면 뒤로 가지 않습니다.

## 4.2 candidate.5의 설계 결정

| 결정 | 고른 것 | 고르지 않은 것과 이유 |
|---|---|---|
| artifact class 표현 | 경로 layout 선언 + Task별 `evidence_manifest`. class와 temperature는 저장하지 않고 계산 | 파일별 front matter(log·png에 둘 수 없고 역사 bytes를 바꿔야 함), 중앙 registry(갱신 누락이 곧 drift) |
| 문서 이동 | append-only relocation ledger(`from`·`to`·content identity) | 역사 Packet의 경로 재작성(인수된 provenance의 소급 변경), 옛 경로의 stub·symlink(bytes가 달라지고 배포 경계에서 symlink 금지) |
| 역사 evidence 불변 | 계약 + 결정적 탐지(plan의 쓰기 범위 선언 때와 close 전 실제 수정 때) | 관례만(실제로 위반이 있었음), 파일 권한·hook 강제(runtime·OS 의존이라 Core에 둘 수 없음. adapter 선택 기능으로만 문서화) |
| 잔여 위험의 수명 | 후속 Packet의 append-only disposition + 계산형 liveness | 원 residual의 status 수정(CLOSED Packet 수정), 중앙 residual registry(저장 상태가 drift) |
| project health | Task 단위 `check`와 별도 명령 `health`. hard error는 위반이 확정적인 것만 | 모두 error로 처리(기존 프로젝트의 역사 상태가 영구 FAIL이 되어 신호가 죽음) |
| runtime adapter | 공통 계약 `AGENTS.md` 하나 + `CLAUDE.md`(import 두 줄) + runtime별 adapter 파일 | `AGENTS.md`만(일부 Claude Code 세션이 읽지 못함), `CLAUDE.md`에 mapping 내장(공통 계약에 runtime 문장이 섞임) |
| 두 runtime의 의미 일치 | 결정적 경계는 `cairn_check next-action`이 계산하고, 두 runtime이 같은 projection을 내야 함. 결정적 경계에서 다르면 escalation이 아니라 결함 | 자연어 계약만(달리 읽어도 탐지 불가), 한 runtime을 기준으로 지정(공식 dual-runtime이 아님) |
| 사람에게 올릴 판단 | 구조 trigger로 정하는 세 class(derivable·ambiguous_semantic·high_impact). confidence 점수는 쓰지 않음 | 모델 confidence로 gate 조절. 조사한 문헌에서 agent의 자기 예측이 실제 성공률과 크게 어긋났고, 사람 판단과의 일치 보장은 보정 데이터가 있을 때만 성립했음 |
| telemetry·전달 기록 | 고정 key, 관찰 못 하면 null. close commit처럼 Packet에 미리 쓸 수 없는 사실은 append-only delivery ledger에 | 계산 가능한 값을 agent가 쓰기(도구가 계산), 대화에만 남기기 |

## 4.3 사람이 정한 것

| ID | 날짜 | 질문 | 결정 |
|---|---|---|---|
| HD-C5-01 | 2026-10-08 | 판본 label과 `contract_version` | `1.0.0-candidate.5` + `contract_version` 3. 옛 Packet은 backward compatible, 새 Packet은 옛 validator로 해석할 수 없다는 forward incompatibility를 명시. 실제 conformance와 Booklog migration 모의 전이라 `rc.1`로 올리지 않음. 후속 조건 6개(호환성 matrix 검증, 의미 고정, 양방향 conformance, Booklog 읽기 전용, freeze 뒤 독립 검토, 공개는 별도 gate)를 인수 조건에 결합 |
| HD-C5-02 | 2026-10-09 | attempt 사전 기록의 경계 | 효과 있는 실행 전에 기록하는 의무 유지. Packet·Git 읽기·next action 파악·결정적 검사·capability 확인은 attempt가 아님. 순서 판정기와 회귀 fixture를 두고 양 runtime에서 재실행 |
| HD-C5-03 | 2026-10-09 | 16차 REJECT 뒤 진행 | release-scope 분리([3.5](03-candidate5-reviews.md#35-release-scope-분리)) |
| HD-C5-04 | 2026-10-10 | 공개 | exact identity(base·tree·README hash·content_id·`release_scope_id`)에 결합한 단일 commit의 non-force push. 하나라도 다르면 실행하지 않음 |

결정 기록마다 "이 결정이 승인하지 않는 것"을 함께 적었습니다. 예를 들어 HD-C5-01은 판본 표기만 정했고 계약 내용의 승인이나 후보의 인수가 아니었습니다. HD-C5-04는 실행 권한이었고, 공개 완료는 실제 push와 원격 identity 대조 뒤에만 기록했습니다.

## 4.4 정정 기록

구현 중 앞선 문장이 틀린 것으로 드러나면 원문을 고치지 않고 정정을 덧붙였습니다.

- **E-1(2026-10-08).** 호환성 분석에서 "옛 validator 0.2.1은 새 Packet을 schema 단계에서 거부한다"고 적었지만, 실제로는 거부하지 않고 새 규칙을 모른 채 PASS했습니다(under-checking). CHANGELOG "호환성 주의"의 첫 줄이 이 정정에서 나왔습니다.
- **E-2(2026-10-09).** "allowlist 안 명령의 효과 가능성은 각 형태의 option 검사로 닫았다"는 문장이 16차 검토의 반례로 반증됐습니다. 판정기는 release 보장이 아니므로 공개 계약은 바뀌지 않았습니다.
