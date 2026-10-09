# Cairn — 프로젝트 로컬 Harness

이 디렉터리의 선언형 계약으로 작업한다. 이 파일은 모든 runtime(Codex, Claude Code 등)이 공유하는 유일한 공통 운영 계약이다. 사람이 읽는 설명·계획·보고·인계·주석은 한국어로 작성한다. 식별자·경로·API/CLI·고유 명칭·원근거·자동 도구 출력은 원표기를 유지한다.

## 최초 배치

1. 이 파일, `CLAUDE.md`, `.harness/`를 프로젝트 루트에 함께 둔다. 기존 지침이 있으면 덮어쓰지 말고 충돌을 검토해 병합한다.
2. [프로젝트 설정](.harness/project.yaml)의 `project_id`, `artifact_roots`, `task_root`, `layout`과 지속 실행 경계를 채운다. 설정은 실행 권한을 새로 부여하지 않는다. Task별 위임은 설정에 누적하지 않고 Packet `scope.authorization`에 둔다.
3. [Task Packet 예시](.harness/task.example.yaml)를 `task_root` 아래 새 작업 파일로 복사한다. 예시 자체는 실행하지 않는다.
4. [배포 식별 정보](.harness/distribution.yaml)의 `content_id`를 작업의 `harness_snapshot`에 기록한다. 필수 값이 비어 있으면 `admit`에서 보완하며 제품을 변경하지 않는다.

이 번들은 agent가 해석하는 선언형 계약이다. 실행기·권한 강제 프로그램은 포함하지 않는다. 실제 런타임 기능을 확인하고 제공되지 않는 격리나 자동 검증을 성공으로 가정하지 않는다.

## Runtime과 인계

- 상태의 authority는 repository bytes·Git identity·Task Packet·durable evidence·사용자 결정 기록뿐이다. runtime 개인 메모리·thread·숨은 상태·대화 reasoning에만 있는 상태는 authority가 아니며 다른 runtime이 이어받을 수 없다.
- 계약 의미·상태·권한·다음 행동·인수 의미는 runtime과 무관하다. runtime별 도구 대응은 `.harness/adapters/<runtime>.md`에 있다. admit·recover 때 자기 runtime의 adapter를 읽는다(Codex는 [codex](.harness/adapters/codex.md), Claude Code는 `CLAUDE.md`가 [claude-code](.harness/adapters/claude-code.md)를 import한다). adapter는 수행 방법만 바꾸며 gate·인수·권한·요구를 바꾸지 못한다.
- 계약은 도구 이름이 아니라 capability(`read_files`·`edit_files`·`execute_commands`·`git`·`network`·`spawn_independent_context`·`browser_observation`·`production_read`·`production_write`·`human_interaction`)로 말한다. 필요한 capability는 admit·recover·runtime 전환 때 실제로 관찰해 `runtime_observations`에 상태(`available`·`unavailable`·`gated`·`not_checked`)로 남긴다. 없을 때의 처리(`alternate_path`·`not_available`·`not_run`·`blocker`)는 상태 칸에 쓰지 않고 따로 기록하며 요구를 완화하지 않는다. 선언은 권한이 아니다.
- 멈추거나 다른 runtime이 이어받을 수 있는 지점에서는 `workflow.node`/`state`와 `recovery.checkpoint`(base commit·의도된 미커밋 경로·완료/남은 단계)가 실제와 일치해야 한다.
- 이어받을 때는 Packet을 읽고 Git HEAD·working tree를 checkpoint와 대조한다. 불일치나 출처 불명 변경은 Packet에 기록하고 진행 전에 보고한다. 출처를 설명할 수 없으면 `recovery.status: blocked`로 두고 사용자 확인 전에는 다음 단계를 진행하지 않는다(쓰기 범위 밖이어도 같다). reset·clean·stash로 지우지 않고 완료 단계를 반복하지 않는다.
- 같은 working tree에서 두 runtime이 같은 Packet이나 겹치는 쓰기 범위를 동시에 진행하지 않는다.
- `actor.runtime`에 runtime family를 기록하고 actor ID는 `<runtime>-<task>-<role>`을 권장한다. runtime이 다르다는 사실은 독립 판단의 근거가 아니다.

규칙은 `core.yaml`의 `runtime`을 따른다.

## 신규 프로젝트 bootstrap

프로젝트 핵심 설정이 비어 있고 활성 Task Packet이 없으며 사용자가 목표/요구를 제공했다면 현재 요청을 bootstrap 위임으로 사용한다. 핵심 설정이 갖춰졌거나 활성 작업이 있으면 신규 초기화로 덮지 않고 현재 작업을 이어간다.

1. repository 파일·기존 지침·변경 상태를 읽기 전용으로 확인한다. 저장소 생성이나 history 변경을 자동 수행하지 않는다.
2. 명시된 목표/요구를 출처와 함께 구조화하고 실제 unresolved decision만 식별한다. 미승인 제안은 확정 requirement와 분리한다.
3. 로컬 설정·`layout`과 bootstrap Packet을 채운다. standard-change의 admit → plan → execute를 쓰며 문서 쓰기 범위를 명시한다.
4. 목표·requirement baseline·핵심 사용자 흐름·초기 domain/data 개념·검증 전략을 정본에 준비한다. 사용자-facing UI가 있으면 design readiness(interaction·visual 기준과 승인 관찰 방법)를 확인한다. 최초 요청의 명시 requirement를 처음 기록하는 것은 canonical_requirement 변경이 아니다. 이후 변경에는 인간 gate를 적용한다.
5. governing 정본의 위치·ID/제목·짧은 적용 범위를 정본 목차(index)에 두고 첫 implementation Packet을 OPEN으로 준비한다. bootstrap도 검증·비producer 인수·종료를 거친다.

정본 준비는 `core.yaml.policies.bootstrap`에 따른다.

## 현재 작업 복구

사용자가 지정한 Task Packet부터 읽는다. 지정이 없으면 `task_root`의 ID/목적/현재 노드만 확인하고 여러 활성 작업 중 임의로 선택하지 않는다.

[로컬 계약](.harness/core.yaml)에서 필요한 key만 회수한다: 최초 사용 또는 snapshot 변경 시 `constitution`·`authority`·`runtime`·`states`, 현재 `workflow.graph`/`node`의 `graphs` 항목과 guard, 현재 역할의 `roles`, 필요한 `subgraphs`, 현재 Packet의 기준·manifest·설정. 다음 허용 행동은 `packet_semantics.next_action`의 vocabulary와 순서로 도출한다.

나머지는 ID/메타데이터 → 요약/제목 → 발췌 → 전체 순서로 읽는다. 다른 Task 기록은 temperature 순서로 회수한다. CLOSED Task는 objective·state·delivery와 `evidence_manifest.authoritative`만 기본으로 보고, 필요할 때만 supporting, 마지막으로 이유를 남기고 raw(log·screenshot)를 본다. YAML 전체·프로젝트 역사·raw evidence를 초기 맥락에 넣지 않는다.

계획/criteria를 확정하기 전 `core.yaml.context.applicability`의 bounded check를 한다. **graph 연결이나 manifest 항목이 없다는 사실은 관련 요구·보안·architecture 제약이 없다는 뜻이 아니다.** 정본 목차의 ID·제목·적용 범위에서 관련 공통 의무를 대조하고 관련 절만 내려간다. 점검 범위와 선택·제외 이유는 `plan.summary`에, 회수 자료는 `artifacts`/`plan.artifacts`에, 적용 의무는 `criteria`에 남긴다. 추정 edge를 만들지 않는다. 미발견·접근 불가·적용성 불명이면 unresolved로 기록하고 해당 claim·VERIFIED를 보류한다.

## 작업과 판단

guard는 충족 근거를 판단하는 선언이며 자동 실행 코드가 아니다. 현재 노드의 역할·Task 범위·실제 runtime 권한의 교집합 안에서만 행동한다. 위임 문장이 마지막 단계(예: 인수까지)를 정하면 그 단계의 완료와 상태 설정(예: ACCEPTED)까지 하고, `scope.allow`가 더 허용해도 다음 노드로 전이하지 않고 다음 행동만 보고한다. 새 세션의 위임은 `scope.authorization`에 날짜·actor와 함께 덧붙이며 기존 위임 문장을 지우지 않는다. Packet 기록을 편집하는 것으로 사용자 승인이나 검토 결과를 만들지 않는다.

검증·인수·종료를 구분한다. 상위 작업은 하위 인수를 자기 인수로 승계하지 않는다. candidate를 생성·수정한 actor는 역할/context/runtime을 바꾸어도 그 candidate를 ACCEPT할 수 없다. 다른 실제 acceptance actor가 필요하며 같은 모델은 가능하다. 필수 독립 판단은 부모·producer 대화를 상속하지 않고 bounded input만으로 시작한 맥락에서 하고 수단과 입력을 기록한다. 그런 맥락은 직접 띄운 것(`spawn_independent_context`)이든 사용자·orchestrator가 그렇게 연 새 세션이든 같다. 현재 세션이 producer 대화를 이어받았거나 시작 입력을 확인할 수 없을 때만 새 맥락을 띄운다. 대화 fork·resume은 독립이 아니다. 새 세션은 선택 가능한 수단이며 기본 의무가 아니다. 비producer 적격 reviewer는 acceptance까지 수행할 수 있다. 다른 runtime의 reviewer도 같은 입력 규칙을 따른다.

작업을 child Task로 분해하면 parent가 Coverage Matrix 하나를 소유하고 `plan.coverage_matrix`로 가리킨다. 약속한 정본 normative section의 모든 구조 단위에 `owned`·`deferred`·`excluded`·`informative` 중 하나를 기록하고, child는 자기 행을 criterion으로 refine하거나 사유와 함께 되돌린다. 행을 판단으로 지우거나 줄이지 않는다. 정본 의무 제외에는 승인된 결정이 필요하고, `informative` 오분류는 parent 인수자가 표본 확인한다. parent 종료 전 미처분·미해결·drift 행이 없어야 한다. 규칙은 `packet_semantics.coverage`를 따른다.

검증은 요구가 가리키는 실제 사용 조건을 관찰한다. computed style로 touch를, 접근성 검사로 시각 품질을, desktop emulation으로 실제 기기를, 내부 지표로 체감 latency를, fallback 실행으로 1차 경로를 대신하지 않는다. 관찰 capability가 없으면 not_run이다.

이미 위임된 일상 수정·집중 검증은 추가 인간 승인 없이 진행한다. 고영향 변경은 해당 계획에 결합된 승인부터 확인한다. 유효한 과거 승인은 같은 범위에서만 재사용하고 새 변경에 자동 확대하지 않는다.

새 evidence는 자기 Task namespace(`layout.evidence_root` 아래 Task ID 디렉터리)에만 쓰고 `evidence_manifest`에 authoritative·supporting·raw로 분류한다. 과거 Task evidence 경로에 출력하지 않는다.

## 사용자 결정 질문과 escalation

판단은 세 class로 나눈다(`policies.escalation_classes`).

- derivable: 정본·결정·evidence에서 유일하게 도출되고 고영향 tag가 없다. 진행하고 도출 출처를 남긴다.
- ambiguous_semantic: 출처를 댈 수 있는 정당한 해석이 둘 이상이다. Human Gate 질문으로 올린다.
- high_impact: 의미는 명확하지만 `human_gate_tags`에 해당한다(production·migration·auth/security·정본 변경 등). Review Brief와 `plan.identity`에 결합한 명시 승인을 받는다.

질문은 한 번에 하나만 한다. 의미 있는 선택지 2~3개에 짧은 장단점, 추천안과 이유를 붙인다. 정해진 답은 재질문하지 않는다. 인간에게는 무엇을 승인하는가·바뀌는 것·안 바뀌는 것·위험·rollback·evidence·남은 모호성을 짧게 보이고 요청 시 ELI5·technical diff·evidence walkthrough를 제공한다. 모델 confidence나 자기평가로 class를 낮추거나 gate·검토를 생략하지 않는다. 결정적 경계에서 actor나 runtime의 판단이 다르면 escalation이 아니라 해석 결함이다. 효과 없는 결정 기록은 한 decision Task에 batch로 누적한다.

## 기록 수명주기

- artifact class(`canonical`·`operational`·`decision`·`task`·`evidence`·`raw_evidence`·`historical`)는 `layout`·Task 상태·`evidence_manifest`로 계산한다. 권장 구조는 `docs` = 사람이 현재 프로젝트를 이해하는 current documentation, `.harness` = Task·evidence·provenance다.
- 소유 Task가 CLOSED인 Packet과 evidence는 봉인(sealed)이다. 고치거나 덮어쓰거나 지우지 않는다. 재실행은 새 Task namespace를, 정정은 새 기록을 쓴다. 봉인 경로를 `scope.write`에 넣지 않는다.
- artifact 이동은 `layout.relocation_ledger`에 from·to·content identity를 append해서만 한다. 역사 Packet의 locator는 고치지 않고 ledger로 해석한다. 내용이 바뀌면 이동이 아니라 새 판본이다. 정리·압축은 삭제가 아니다.

## 식별·보존·종료

Packet은 하나의 작업 기록이다. guard에 쓰지 않는 기록은 decision `kind: record`와 `subkind`로, 프로젝트 확장 정보는 `local`에 둔다. 원결과와 이전 판정은 덮어쓰지 않고 추가 기록하거나 회수 가능한 이전 판본으로 보존한다. 후보를 구성하는 내용과 변화하는 작업 기록은 별도 대상으로 식별해 자기참조 해시를 피한다.

잔여 위험은 `risk`·`owner`·`condition`(권장 `id`·`owner_kind`·`owner_ref`)으로 인계한다. 종료하는 Task 자신을 owner로 두지 않는다. 이전 Task residual의 해소·대체·이전·수용은 후속 Packet `delivery.residual_dispositions`에 append한다. 종료된 Packet은 고치지 않는다.

경로는 프로젝트 루트 기준 상대 경로다. URL·절대 경로·상위 경로 탈출을 실행 계약의 참조로 사용하지 않는다.

Git 프로젝트에서 위임/정책이 commit/push를 허용하고 정상 remote가 있으며 task scope 안의 변경만 있으면 완료형 closeout을 기본 수행한다: 최종 diff → 검증/비producer 인수 확인 → 하나의 완료형 commit → 일반 non-force push → local/remote identity 일치 → clean → delivery evidence. close 계획은 이 Task가 바꾼 정본을 가리키는 index 행을 갱신하거나 무변경 사유를 남기고, 종료 Task를 current 실행 계획으로 남기지 않는다. close commit처럼 Packet에 미리 쓸 수 없는 사실은 대화에만 두지 않고 `layout.delivery_ledger`에 append한다. 사후 Packet 수정으로 dirty가 되면 clean을 주장하지 않는다. Git 여부나 remote 존재는 권한이 아니다. force push·파괴적 reconciliation·scope 밖 변경·승인되지 않은 history rewrite는 하지 않는다. Git·위임·remote가 없으면 제품 실패로 꾸미지 않고 필요한 좁은 사용자 행동만 알린다(`policies.git_closeout`).

효과 있는 실행(파일 쓰기, 구현 단계, test·검증 실행, 검토·인수 중의 test·probe 실행, 외부 효과 명령, 그 밖에 저장소·환경에 실질 효과를 주는 실행)은 시작 전에 `recovery.attempts`에 기록하고 끝나면 상태와 receipt를 갱신한다(`packet_semantics.attempts`). 기록은 효과와 같은 쓰기 묶음에 넣지 않고 먼저 저장해 Packet이 읽히는지 확인한다. cache를 쓰는 compile·lint도 효과다. Packet·Git 읽기, next-action 파악, 결정적 계약 검사, capability 확인 같은 효과 없는 상태 확인은 attempt가 아니다. Task Packet에 기록을 쓰는 것 자체는 효과가 아니다. 효과 없음이 분명하지 않은 실행(inline 코드·script·변환 명령)은 효과로 보고 attempt 뒤에 한다. 기존 attempt는 지우거나 고치지 않는다. Packet은 telemetry에 관찰한 사용량만 고정 key로 남긴다. 모르면 null이며 계산 가능한 값은 적지 않는다.

## 결정적 검사

Packet·matrix 검사(구문 → schema → 연결 → matrix → drift → 소유권), next action projection, project health(index·봉인·relocation·residual·adapter·검증 surface), evidence tier 계산은 선택 검사 도구가 있으면 도구로, 없으면 같은 규칙으로 직접 수행한다. 방법과 검사하지 않은 범위를 남긴다. 통과는 선언된 계약의 무결성만 뜻하며 정확성·인수·Human Gate가 아니다. 모델 판단 신호도 권한이나 결정이 아니다.

## Harness 변경

Harness 변경은 명시적 업데이트 작업이다. 새 배포본과 현재 복사본의 diff·파일 해시·설정 호환성을 검토하고 승인된 범위만 교체한다. 진행 중 Packet의 `harness_snapshot`을 몰래 바꾸지 않는다. 각 Packet은 자기 snapshot 계약으로 해석하며 새 규칙을 이전 Packet에 소급하지 않는다. 버전·내용 ID는 출하본 비교용이며 다른 저장소를 조회하라는 지시가 아니다. 프로젝트 설정·병합 지침은 별도 로컬 판본으로 manifest에 포함한다.
