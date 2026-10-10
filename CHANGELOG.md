# Changelog

이 문서는 이 저장소에 **공개된 Cairn 판본**의 변경 내역입니다. 최신 판본이 위에 옵니다. 현재 기능의 통합 설명은 [README](README.md)에 있습니다.

- 날짜는 이 저장소에 공개한 commit의 날짜(KST)입니다.
- 계약(배포 파일)의 판본과 companion validator `cairn_check`의 판본은 별개입니다. validator 판본은 계약 `content_id`의 일부가 아닙니다.
- 기존 Task Packet은 각자 `harness_snapshot`의 계약으로 해석합니다. 새 판본의 규칙은 이전 Packet에 소급하지 않습니다.
- 모든 판본은 release candidate이며 최종 `1.0.0`은 아직 없습니다. Git tag와 GitHub Release는 만들지 않았습니다.

## 1.0.0-candidate.5 — 2026-10-10

| 항목 | 값 |
|---|---|
| 공개 commit | `6627736` |
| 계약 | `1.0.0-candidate.5`, `contract_version` 3, Task `schema_version` 3 |
| content_id | `sha256:7a3d4d4f69a346ef9fa4c44973276a7625e52b94e9e56dde742dba5e4b5e00ca` |
| validator | `cairn_check` 0.3.0 |
| 배포 파일 | 8개(5개에서 `CLAUDE.md`, `.harness/adapters/claude-code.md`, `.harness/adapters/codex.md` 추가) |

### 바뀌지 않은 것

- lifecycle 네 상태, 역할, graph, guard 이름, authority 교집합, producer 자기 인수 금지, 한 번에 하나의 Human Gate 질문, Coverage Matrix, 검사 단계 VS0~VS6
- candidate.3/.4 Packet은 그대로 유효합니다.

### 추가: Cross-runtime portability

- `AGENTS.md`가 모든 runtime의 유일한 공통 계약입니다. Claude Code는 `CLAUDE.md`(`@AGENTS.md`와 `@.harness/adapters/claude-code.md`)로, Codex는 `AGENTS.md`를 native로 읽고 `.harness/adapters/codex.md`를 함께 씁니다. adapter는 수행 방법만 적고 gate·인수·권한·요구·다음 행동의 의미를 바꾸지 않습니다.
- Core가 도구 이름 대신 capability 10개로 말합니다. 관찰 상태는 `available`·`unavailable`·`gated`·`not_checked`이고, 없는 capability의 처리는 `alternate_path`·`not_available`·`not_run`·`blocker`로 따로 기록합니다.
- 상태 authority를 repository bytes·Git·Packet·evidence·사용자 결정 기록으로 한정했습니다. runtime 메모리는 authority가 아닙니다.
- 새 Packet field: `recovery.checkpoint`, `runtime_observations`, `actor.runtime`
- 독립 맥락을 성질로 정의했습니다(producer와 다른 actor, 대화 미상속, bounded input). fork·resume은 독립이 아닙니다.
- next action 어휘 12개와 결정 순서. 결정적 경계에서 runtime 판단이 다르면 해석 결함으로 봅니다.

### 추가: Knowledge lifecycle

- artifact class 7개(canonical·operational·decision·task·evidence·raw_evidence·historical)와 temperature(hot·warm·cold). 저장하지 않고 계산합니다.
- `evidence_manifest`(authoritative·supporting·raw). CLOSED Task는 authoritative만 기본으로 회수합니다.
- 봉인(sealed): CLOSED Task의 Packet·evidence는 고치지 않습니다.
- relocation ledger: 역사 Packet을 고치거나 옮기지 않고 옛 경로를 새 위치로 해석합니다. content identity로 이동과 내용 변경을 구분합니다.
- 권장 구조: `docs` = current documentation, `.harness` = Task·evidence·provenance

### 추가: Project health

- `health` 검사: index 신선도, 참조 해결, relocation, 봉인 쓰기·수정, residual liveness, raw evidence 위치·크기, 동시 쓰기, verification surface drift, adapter drift. 등급 error·warning·info·not_checked
- residual 선택 field(`id`·`owner_kind`·`owner_ref`·`due`·`inherited_from`)와 후속 Packet의 append-only `delivery.residual_dispositions`. 종료하는 Task 자신을 owner로 둘 수 없습니다.
- 선택 verification registry

### 추가: Gate·운영

- escalation class: derivable / ambiguous_semantic / high_impact. confidence 점수는 쓰지 않습니다. human_gate decision의 선택 `gate_class`
- 새 기본 Human Gate tag `production_effect`
- 효과 없는 결정 질문의 batch 기록(`decision_batching`)
- attempt 경계: Packet·Git 읽기, next action 파악, 결정적 계약 검사, capability 확인은 attempt가 아닙니다. 파일 쓰기, test·검증 실행, 외부 효과 명령 전에는 `recovery.attempts`에 먼저 기록합니다. **계약상 의무이며, 이 판본에는 그 순서를 자동으로 검사하거나 강제하는 도구가 없습니다.**
- close 때 index 행 갱신 또는 무변경 사유(`closeout_freshness`)
- delivery ledger: close commit처럼 Packet에 미리 쓸 수 없는 전달 사실을 대화에만 두지 않습니다.
- 고정 telemetry 어휘. 계산할 수 있는 값은 도구가 계산합니다.

### Validator 0.3.0

- 새 명령: `next-action`, `health`, `relocations`, `evidence`
- v3 규칙: evidence_manifest 해결·tier 중복, residual id 중복, 종료 Task 자기 소유 residual
- 도구보다 새 `contract_version`은 `contract_newer_than_tool`로 `INCONCLUSIVE`
- 비ASCII 경로의 Git 목록 처리(`-z`)
- attempt 기록은 항목 schema와 `max_attempts` 상한만 검사합니다. 실행 순서는 검사하지 않습니다.

### 호환성 주의

- validator 0.2.1은 candidate.5 Packet을 거부하지 않고 v3 규칙을 모른 채 PASS할 수 있습니다. candidate.5 프로젝트에는 0.3.0 이상을 쓰세요.
- `project.yaml`은 schema 1을 계속 쓸 수 있습니다. `layout`·`health`를 쓰려면 schema 2로 올립니다.
- 기존 `CLAUDE.md`가 있으면 덮어쓰지 말고 병합합니다.
- candidate.4 Packet은 candidate.4 `core.yaml`을 `--contract <content_id>=<path>`로 주면 그 계약으로 검사합니다.

## 1.0.0-candidate.4 — 2026-09-29

| 항목 | 값 |
|---|---|
| 공개 commit | `e2e2289` |
| 계약 | `1.0.0-candidate.4`, `contract_version` 2, Task `schema_version` 2 |
| content_id | `sha256:6646a69ec53adf08f92fffc7e7a95c8567065b17b5ebf47187724b67e8fd5414` |
| validator | `cairn_check` 0.2.1(이 저장소에 처음 공개) |
| 배포 파일 | 5개. `.harness/project.yaml`은 candidate.3과 byte 동일 |

### 추가

- **Coverage Matrix**: 분해 Task(`scope.children`이 있는 Packet)는 `plan.coverage_matrix`로 project-local sidecar 하나를 가리킵니다. 선언한 정본 scope의 모든 구조 단위를 `owned`·`deferred`·`excluded`·`informative` 중 하나로 처분합니다. parent plan이 `owner_task`를 정하고(Stage A), child plan이 자기 criterion으로 `owner_criterion`을 채웁니다(Stage B). 각 행은 excerpt와 fingerprint로 정본에 결합되고, 정본이 바뀌면 drift(`suspect`·`ambiguous`·`missing`)로 드러납니다.
- **대리 관찰 금지**(`policies.proxy_substitution`): 요구가 가리키는 실제 사용 조건을 다른 관찰로 대신해 PASS로 쓰지 않습니다. 다음 다섯 규칙이 함께 도입됐습니다.
  - touch·gesture 요구를 CSS computed style이나 구조 검사로 대신하지 않습니다.
  - 시각·지각 품질을 구조·접근성 검사 PASS로 대신하지 않습니다. 지각 판정은 인간 관찰 결정이나 명시한 잔여 위험으로 남깁니다.
  - 실제 기기·환경 요구를 desktop emulation으로 대신하지 않습니다. 관찰하지 못한 대상 환경은 명시 결정 없이 PASS가 아닙니다.
  - 사용자 체감 latency를 provider throughput이나 내부 지표로 대신하지 않습니다.
  - 1차 경로 요구를 fallback 경로만의 실행으로 대신하지 않습니다. fallback을 허용해도 1차 경로의 실제 실행 관찰이 필요하며, fallback만으로 수용하려면 명시 결정이 필요합니다.
- **구조화된 residual**: 잔여 위험을 `{risk, owner, condition}` 구조로 넘깁니다. 소유자 없는 문자열 residual은 종료 인계로 인정되지 않습니다.
- **`record` decision과 `local` 확장**: guard에 쓰지 않는 기록은 `kind: record`와 프로젝트가 정한 `subkind`로 남깁니다. `local`은 guard가 읽지 않는 프로젝트 확장 기록입니다.
- **소급 금지**: 기존 Packet은 각자 `harness_snapshot`의 계약으로 해석합니다.
- **companion validator `cairn_check`**(선택, 배포 파일 밖): 결정적 무결성 규칙 VS0~VS6을 검사하는 report-only 도구입니다. 종료 코드 0 `PASS`·1 `FAIL`·2 호출 오류·3 `INCONCLUSIVE`. `PASS`는 정확성이나 인수가 아닙니다. 공개된 0.2.1은 개행 동치 대조, 판정·종료 코드 일치, seed 의존 closure와 seed 거짓 PASS 교정을 포함합니다(판본 표는 [`tools/README.md`](tools/README.md)).

## 1.0.0-candidate.3 — 2026-09-21

| 항목 | 값 |
|---|---|
| 공개 commit | `ab087b0`(첫 공개) |
| 계약 | `1.0.0-candidate.3` |
| content_id | `sha256:9c78d2433c5ae5e927e83e5df68f5357083584763d97a33184a429aeafe356f2` |
| validator | 없음 |
| 배포 파일 | 5개: `AGENTS.md`, `.harness/core.yaml`, `.harness/project.yaml`, `.harness/task.example.yaml`, `.harness/distribution.yaml` |

- 이 저장소의 첫 공개 판본입니다. 역할·노드·범위 교집합 권한, 고영향 변경의 Human Gate, 검증·인수·종료의 구분, producer 자기 인수 금지, progressive retrieval, 후보·범위에 결합된 evidence, 조건부 Git closeout을 포함합니다.
- 같은 판본 기간에 계약 파일을 바꾸지 않은 저장소 변경: MIT License 추가(`0f279f9`, 2026-09-21), README 한국어 번역(`b7fd5c2`, 2026-09-21), README 설계 배경·참고자료 확장(`98d2bf7`, 2026-09-22)
- candidate.3 이전 판본은 이 저장소에 공개되지 않았습니다.
