# Cairn — 프로젝트 로컬 Harness

이 디렉터리의 선언형 계약으로 작업한다. 사람이 읽는 설명·계획·보고·인계·주석은 한국어로 작성한다. 식별자·경로·API/CLI·고유 명칭·원근거·자동 도구 출력은 원표기를 유지한다.

## 최초 배치

1. 이 파일과 `.harness/`를 프로젝트 루트에 함께 둔다. 기존 지침이 있으면 덮어쓰지 말고 충돌을 검토해 병합한다.
2. [프로젝트 설정](.harness/project.yaml)의 `project_id`, `artifact_roots`, `task_root`와 실제 실행 경계를 채운다. 설정은 실행 권한을 새로 부여하지 않는다.
3. [Task Packet 예시](.harness/task.example.yaml)를 `task_root` 아래 새 작업 파일로 복사한다. 예시 자체는 실행하지 않는다. 현재 사용자 요청을 바탕으로 목적·범위·권한·기준을 채운다.
4. [배포 식별 정보](.harness/distribution.yaml)의 `content_id`를 작업의 `harness_snapshot`에 기록한다. 필수 값이 비어 있으면 `admit`에서 보완하며 제품을 변경하지 않는다.

이 번들은 agent가 해석하는 선언형 계약이다. 실행기·도구 어댑터·권한 강제 프로그램은 포함하지 않는다. 실제 런타임 기능을 확인하고 제공되지 않는 격리나 자동 검증을 성공으로 가정하지 않는다.

## 신규 프로젝트 bootstrap

프로젝트 핵심 설정이 비어 있고 활성 Task Packet이 없으며 사용자가 목표/요구를 제공했다면 현재 요청을 bootstrap 위임으로 사용한다. 사용자가 Harness 운영 규칙을 다시 적을 필요는 없다. 핵심 설정이 갖춰졌거나 활성 작업이 있으면 신규 초기화로 덮지 않고 현재 작업을 이어간다.

1. 현재 repository의 파일·기존 지침·변경 상태를 읽기 전용으로 확인한다. Git 여부도 확인하되 저장소 생성이나 history 변경을 자동 수행하지 않는다.
2. 이미 명시된 목표/요구를 출처와 함께 구조화한다. 기존 정보로 정해지는 값은 다시 질문하지 않는다.
3. 실제 결정이 필요한 unresolved decision만 식별한다. 미승인 제안은 확정 requirement와 분리한다.
4. 기본 작업 위치와 실제 실행 경계를 확인해 로컬 설정 및 bootstrap Task Packet을 채운다. 기존 standard-change의 admit → plan → execute를 사용하며 문서 쓰기 범위를 명시한다.
5. 프로젝트 목표·requirement baseline·핵심 사용자 흐름·필요한 초기 domain/data 개념을 프로젝트 정본에 준비한다. 필요하면 한 문서의 절로 합친다. 기존 정본은 재사용·대조한다. 최초 요청의 명시 requirement를 처음 기록하는 것은 사용자 권위의 기록이며 canonical_requirement 변경이 아니다. 이후 변경이나 agent의 새 정본 requirement 추가에는 인간 gate를 적용한다.
6. 공통 요구·architecture·security 등 governing 정본의 위치·ID/제목·짧은 적용 범위를 기존 정본 목차/요약에서 찾을 수 있게 준비한다. 명시 참조에서 작은 Artifact Map을 도출하고 아래 적용성 점검으로 관련 자료를 manifest에 포함한다. 관계를 추측하거나 모든 문서에 미리 edge를 연결하지 않는다. 별도 registry는 필요 없다.
7. 요구별 관찰 방법과 관련 음성/상호작용 검사를 포함하는 최소 검증 전략을 준비한다.
8. 첫 implementation Task Packet을 OPEN으로 생성하고 정본 baseline/근거를 참조한다. 이는 후속 작업이며 bootstrap 완료를 기다리는 child로 두지 않는다.
9. 필요한 Human Gate는 해당 변경/구현 전에 멈춘다. 준비 가능한 문서/Packet은 먼저 구체화하되 미결정 사항에 의존하는 효과는 실행하지 않는다. bootstrap도 검증·비producer 인수·종료를 거치며 실제 제품 구현 완료를 뜻하지 않는다. 후속 구현은 현재 위임과 준비된 Packet의 guard가 허용할 때만 시작한다.

정본 준비는 `core.yaml.policies.bootstrap`에 따른다. 최초 요구 기록의 예외는 아키텍처·인증/보안 등 다른 gate를 면제하지 않는다.

## 현재 작업 복구

사용자가 지정한 Task Packet부터 읽는다. 작업이 지정되지 않았다면 `task_root`의 ID/목적/현재 노드만 확인하고 여러 활성 작업 중 임의로 선택하지 않는다.

[로컬 계약](.harness/core.yaml)에서 다음 key만 회수한다.

- 최초 사용 또는 snapshot 변경 시 `constitution`, `authority`, `states`의 공통 의미
- 현재 `workflow.graph`/`workflow.node`에 해당하는 `graphs` 항목과 관련 guard
- 현재 역할의 `roles` 항목, 필요한 `subgraphs` 계약
- 현재 Packet의 기준과 manifest, 관련 프로젝트 설정

나머지 자료는 ID/메타데이터 → 원본 요약/제목 → 관련 발췌 → 필요한 전체 산출물 순서로 읽는다. YAML 전체·프로젝트 역사·전체 Artifact Graph를 매번 초기 맥락에 넣지 않는다. 같은 작업의 연속 진행에서는 변경된 부분만 확인한다.

계획/criteria와 검증 의무를 확정하기 전에는 task-local 이웃을 우선 보되 `core.yaml.context.applicability`의 bounded check도 수행한다. **graph 연결이나 manifest 항목이 없다는 사실은 관련 요구·보안·architecture 제약이 없다는 뜻이 아니다.** 허가된 프로젝트 정본 목차/목록의 ID·제목·짧은 적용 범위에서 현재 변경에 관련된 공통 의무를 대조한다. 목록이 부족하면 관련 경로/제목만 한정 탐색한다. 무관함이 충분히 확인되면 더 읽지 않고, 소유권 등 적용 가능성이 있는 자료만 관련 절로 내려간다. 전체 requirement 전문·history를 초기 context에 넣지 않는다.

점검 범위/판본과 선택·제외 이유는 `plan.summary`에, 회수한 관련 자료는 `artifacts`/`plan.artifacts`에, 적용 의무는 `criteria`에 남긴다. 명시 참조 없는 자료도 manifest에 넣을 수 있지만 추정 `governed_by` 등 edge를 만들지 않는다. 관련 정본이 미발견·접근 불가·적용성 불명이면 `unresolved`와 의존 기준을 기록하고 해당 계획 완전성·검증 claim·VERIFIED를 보류한다. 검증은 `not_run`/`inconclusive`로 남기며 필요한 좁은 회수/판단만 요청한다. 같은 scope/정본 판본의 점검은 재사용한다. 기존 의무를 읽고 반영하는 것만으로 Human Gate를 추가하지 않으며 정본 변경이나 고영향 변경에는 기존 gate를 적용한다.

## 작업과 판단

계약의 guard는 충족 근거를 판단하는 선언이며 자동 실행 코드가 아니다. 현재 노드의 역할·Task 범위·실제 런타임 권한의 교집합 안에서만 행동한다. Packet 기록을 편집하는 것으로 사용자 승인이나 검토 결과를 만들어내지 않는다.

검증·인수·종료를 구분한다. 상위 작업은 하위 인수 결과를 자기 인수로 승계하지 않는다. 현재 후보와 근거의 대상이 다르면 변경 적용성을 설명하거나 필요한 범위를 다시 검증한다. candidate를 생성·수정한 actor는 역할/context를 바꾸어도 그 candidate를 ACCEPT할 수 없다. 다른 실제 acceptance actor가 필요하며 같은 모델 사용은 가능하다. 필수 독립 판단은 추가로 생성자의 판단 맥락과 분리한다. 비producer인 적격 reviewer는 acceptance까지 수행할 수 있으며 별도 acceptor를 더 만들지 않는다. 새 세션은 선택 가능한 수단이며 기본 의무가 아니다. continuation/compaction도 실제 분리가 확인된 경우에만 독립 판단 수단으로 인정한다.

이미 위임된 일상 수정·집중 검증은 추가 인간 승인 없이 진행할 수 있다. 고영향 변경은 해당 계획에 결합된 인간 승인부터 확인한다. 과거의 유효한 승인을 같은 범위에서 재사용하되 새 변경에 자동 확대하지 않는다. 인간에게는 변경·이유·확인 사항·잔여 위험을 짧게 제공한다.

## 사용자 결정 질문

실제 unresolved decision 또는 Human Gate에서는 한 번에 결정 질문 하나만 한다. 의미 있는 선택지 2~3개에 각각 짧은 장단점을 붙이고 추천안과 추천 이유를 제시한다. 사용자 요구·정본·승인된 결정에서 답이 정해지면 재질문하지 않는다. 여러 질문을 묶지 않으며 단순 상태 보고나 명시적 승인 확인에 억지 선택지를 만들지 않는다. 이 정책을 이유로 정본 requirement나 계획을 임의 변경하지 않는다.

## 식별·보존·종료

Packet은 하나의 작업 기록이다. 별도 계획/보고/검토 문서를 항상 만들 필요는 없다. 원결과와 이전 판정은 덮어쓰지 않고 배열에 후속 기록을 추가하거나 프로젝트 안의 회수 가능한 이전 판본으로 보존한다. 후보를 구성하는 내용과 변화하는 작업 기록은 별도 대상으로 식별해 자기참조 해시를 피한다.

경로는 프로젝트 루트 기준 상대 경로다. 내부 참조는 이 복사본에서 해결하고 프로젝트 자료는 설정된 자료 루트 안에서 찾는다. URL·절대 경로·상위 경로 탈출을 실행 계약의 참조로 사용하지 않는다. 필요한 외부 작업은 사용자 위임과 실제 도구 권한을 별도로 확인하되 외부 자료 회수는 이 번들의 시작 조건이 아니다.

Git 프로젝트에서 현재 위임/프로젝트 정책이 commit/push를 허용하고 정상 remote가 있으며 task scope 안의 변경만 있으면 완료형 closeout을 기본 수행한다. 최종 diff·의도하지 않은 변경 → 검증/비producer 인수 확인 → 하나의 완료형 commit → 일반 non-force push → local/remote target identity 일치 → working tree clean → 실제 결과의 delivery evidence 기록 순서다. 기록 위치는 close 계획에서 정하며 사후 Packet 수정으로 dirty가 되면 clean으로 주장하지 않는다.

Git 여부나 remote 존재는 권한이 아니다. force push, 예상 밖 원격 변경의 파괴적 reconciliation, scope 밖 변경 포함, 승인되지 않은 branch/history rewrite를 하지 않는다. Git이 아니거나 위임/권한/remote가 없으면 제품 실패로 꾸미지 않는다. 필요한 delivery가 미완료면 그 조건과 필요한 좁은 사용자 행동만 알린다. 자세한 조건은 `core.yaml.policies.git_closeout`을 따른다.

Harness 변경은 명시적인 업데이트 작업이다. 새 배포본과 현재 복사본의 diff·파일 해시·프로젝트 설정 호환성을 검토하고 승인된 범위만 교체한다. 진행 중 작업의 `harness_snapshot`을 몰래 바꾸지 않는다. 작업 종료 또는 명시적 전환 뒤 새 snapshot을 채택한다. 버전·내용 ID는 출하본 비교용이며 다른 저장소를 조회하라는 지시가 아니다. 프로젝트 설정과 병합된 지침은 별도 로컬 판본으로 계획의 manifest에 포함한다. 출하 manifest를 로컬 설정에 맞춰 다시 계산하지 않는다.
