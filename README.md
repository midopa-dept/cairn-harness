# Cairn Harness

Cairn은 장기적인 agentic software project를 위한 **소형 선언형 Harness**입니다. 별도의 전용 runtime 없이도 lifecycle, authority, evidence, review, acceptance, recovery, closeout 계약을 프로젝트에 적용할 수 있도록 설계되었습니다.

> 현재 배포본: `1.0.0-candidate.3`

## 포함 내용

배포본은 의도적으로 최소한의 파일만 포함합니다.

- `AGENTS.md` — 프로젝트에서 agent가 따라야 할 사람이 읽을 수 있는 운영 계약
- `.harness/core.yaml` — lifecycle, role, authority, guard, subgraph, schema, 핵심 정책
- `.harness/project.yaml` — 프로젝트별 로컬 설정 템플릿
- `.harness/task.example.yaml` — Task Packet 템플릿
- `.harness/distribution.yaml` — 배포본 식별자와 payload 해시

Cairn은 **선언형 Harness**입니다. agent runtime, tool adapter, sandbox, policy enforcement daemon은 포함하지 않습니다. 따라서 실제 runtime 기능과 격리·권한 경계는 Cairn을 사용하는 환경에서 별도로 확인해야 합니다.

## 프로젝트에 적용하기

대상 프로젝트의 루트에 `AGENTS.md`와 `.harness/` 디렉터리 전체를 복사합니다.

기존 프로젝트에 이미 agent 지침이나 Harness 파일이 있다면 그대로 덮어쓰지 말고 충돌 여부를 확인한 뒤 병합해야 합니다.

그 다음 agent에게 프로젝트의 목표와 요구사항을 제공하고 **Cairn에 따라 bootstrap하고 진행하라**고 요청하면 됩니다. `.harness/project.yaml`의 프로젝트별 값과 첫 Task Packet은 bootstrap 과정에서 채워집니다.

## 핵심 계약

Cairn은 다음 원칙을 중심으로 동작합니다.

- 실제 권한은 role × workflow node × task scope의 교집합으로 제한됩니다.
- architecture, authentication/security, database migration, canonical requirement 변경 등 고영향 변경에는 Human Gate가 필요합니다.
- verification, acceptance, closeout은 서로 다른 상태로 구분합니다.
- candidate를 생성하거나 수정한 producer는 자기 candidate를 ACCEPT할 수 없습니다.
- 프로젝트 전체 history를 항상 읽는 대신 필요한 context를 단계적으로 회수합니다.
- evidence와 decision은 실제로 뒷받침하는 candidate와 scope에 결합됩니다.
- 이미 승인된 경계 안의 routine work는 불필요한 추가 인간 승인 없이 진행합니다.
- Git closeout이 위임되고 적용 가능한 경우 실제 remote 전달 상태까지 확인합니다.

구체적인 규범은 `AGENTS.md`와 `.harness/core.yaml`에 정의되어 있습니다.

## 기본 언어

현재 배포본은 사람이 읽는 설명, 계획, 보고, review note, handoff의 기본 언어로 **한국어**를 사용합니다.

식별자, 경로, API/CLI 문법, 고유 명칭, 원근거, 자동 도구 출력은 원래 표기를 유지합니다.

## 배포본 식별

`.harness/distribution.yaml`은 다음 정보를 이용해 정확한 배포본을 식별합니다.

- version
- distribution ID
- content ID
- 각 배포 파일의 SHA-256 해시

프로젝트별로 수정되는 `.harness/project.yaml` 값이나 실제 Task Packet은 이 immutable distribution identity에 포함되지 않습니다.

현재 이 저장소는 최종 `1.0.0`이 아니라 **release candidate인 `1.0.0-candidate.3`**를 공개하고 있습니다.

## 라이선스

Cairn은 **MIT License**로 배포됩니다. 자세한 내용은 `LICENSE`를 확인하세요.
