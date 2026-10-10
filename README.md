# Cairn Harness

Cairn은 LLM agent가 장기간 코드를 바꾸는 소프트웨어 프로젝트를 위한 **소형 선언형 Harness**입니다. 프로젝트 안에 두는 8개 파일이 권한·작업 상태·검증과 인수·증거·중단 후 복구·종료 절차를 계약으로 정합니다. Claude Code와 Codex 같은 기존 agent runtime이 이 계약을 읽고 따릅니다.

> **현재 공개 판본:** `1.0.0-candidate.5`(`contract_version` 3, Task `schema_version` 3) + companion validator `cairn_check` 0.3.0
> 최종 `1.0.0`이 아닌 release candidate입니다. 실제 프로젝트 적용을 이어가며 검증하는 단계입니다.
> 이 판본은 attempt 사전 기록 순서를 자동으로 검증하거나 강제하지 않습니다([현재 한계](#8-현재-한계)).
> 판본별 변경 내역은 [CHANGELOG](CHANGELOG.md)에 있습니다.

## 목차

1. [Cairn이란?](#1-cairn이란)
2. [왜 필요한가?](#2-왜-필요한가)
3. [빠른 시작](#3-빠른-시작)
4. [주요 기능](#4-주요-기능)
5. [실제 사용 예시](#5-실제-사용-예시)
6. [Validator와 보장 범위](#6-validator와-보장-범위)
7. [상세 문서·변경 이력·설계 배경](#7-상세-문서변경-이력설계-배경)
8. [현재 한계](#8-현재-한계)

---

## 1. Cairn이란?

Cairn은 **agent가 따르는 project-local 계약**입니다. 대상 프로젝트 루트에 복사한 파일 안에 다음을 선언합니다.

- 누가 어떤 단계에서 무엇을 할 수 있는가(권한과 역할)
- 작업이 어떤 단계를 거쳐 끝나는가(workflow와 Task Packet)
- 무엇을 검증으로, 무엇을 인수로, 무엇을 종료로 보는가
- 어떤 변경에서 사람의 승인을 받아야 하는가(Human Gate)
- 근거를 어디에 어떻게 남기고, 중단 뒤 어디서 이어가는가

Cairn은 **선언형 Harness이며 독립 실행 agent runtime이 아닙니다.** 명령을 실행하거나 권한을 강제하는 프로그램이 없습니다. 계약을 해석하고 지키는 주체는 그 위에서 일하는 agent와 사람입니다. 실제 runtime이 제공하지 않는 격리나 권한 강제를 Cairn이 제공한다고 가정하면 안 됩니다.

### Claude Code와 Codex에서 쓰는 방법

두 runtime은 **같은 Core 의미**를 씁니다. 공통 운영 계약은 `AGENTS.md` 하나뿐이고, runtime별 adapter는 그 의미를 바꾸지 않고 **수행 방법만** 적습니다.

| runtime | 진입점 | adapter |
|---|---|---|
| Claude Code | `CLAUDE.md`: `@AGENTS.md`와 `@.harness/adapters/claude-code.md`를 import하는 두 줄 | [`.harness/adapters/claude-code.md`](.harness/adapters/claude-code.md) |
| Codex | `AGENTS.md`를 native로 읽음 | [`.harness/adapters/codex.md`](.harness/adapters/codex.md)(admit·recover 때 읽음) |

adapter에는 capability와 실제 도구의 대응, 독립 맥락을 띄우는 방법, attempt 기록 순서, commit trailer 같은 runtime 관례가 있습니다. adapter는 Human Gate·인수·권한·요구·다음 행동의 의미를 바꾸지 못합니다. 둘이 충돌하면 공통 계약이 우선합니다.

### Cairn이 포함하지 않는 것

- agent runtime, agent spawning service
- model/provider adapter(runtime adapter 두 파일은 수행 방법을 적은 문서이며 실행 코드가 아닙니다)
- sandbox 또는 OS-level permission enforcement
- graph database, vector database / embeddings
- CI/CD framework, 자동 update service
- 범용 semantic validator(결정적 무결성 검사 도구 `cairn_check`는 선택 companion으로 제공합니다)
- attempt 사전 기록 순서의 자동 검증 또는 강제

---

## 2. 왜 필요한가?

LLM agent가 여러 세션에 걸쳐 같은 프로젝트를 바꾸면 "다음 작업을 잘 하는가"만으로는 부족합니다. 시간이 지날수록 다음 문제가 쌓입니다.

| 문제 | Cairn의 대응 |
|---|---|
| **맥락 손실과 비대화.** 세션이 바뀌면 이전 결정과 근거를 잃고, 전체 history를 계속 읽으면 context가 커집니다 | 작업 상태를 Task Packet 하나에 두고, 필요한 자료만 단계적으로 회수합니다([4.6](#46-progressive-retrieval)) |
| **권한과 작업 상태의 혼동.** 누가 무엇을 바꿀 수 있는지, 작업이 어디까지 왔는지가 흐려집니다 | 권한을 역할 ∩ 현재 단계 ∩ Task 범위로 계산하고, 상태를 정해진 어휘로만 씁니다([4.1](#41-authority와-역할), [4.2](#42-workflow와-task-packet)) |
| **검증과 인수의 혼동.** "테스트 통과", "검토 완료", "커밋·전달 완료"가 하나의 완료로 뭉개지고, 만든 agent가 스스로 인수합니다 | `VERIFIED`·`ACCEPTED`·`CLOSED`를 나누고 producer의 자기 인수를 금지합니다([4.3](#43-independent-review와-acceptance)) |
| **고위험 변경의 무심한 처리.** 인증·DB migration 같은 변경이 일반 작업과 같은 흐름으로 지나갑니다 | 정해진 위험 범주는 효과 전에 사람의 승인을 받습니다([4.4](#44-human-gate)) |
| **중단 후 복구 실패.** 재시작하면 이전 시도·실패·판정이 사라지거나 같은 효과가 중복 실행됩니다 | 시도와 재개 지점을 Packet에 남기고, 이어받을 때 Git 상태와 대조합니다([4.7](#47-recovery와-handoff)) |
| **과거 증거와 현재 정본의 혼재.** 이전 후보의 PASS가 현재 후보에도 유효한 것처럼 쓰이고, 오래된 문서가 현재 문서와 섞입니다 | 증거를 후보·범위에 결합하고, 종료된 기록을 봉인하며, 문서를 class와 temperature로 구분합니다([4.5](#45-evidence와-artifact-lifecycle)) |

Cairn의 목적은 모든 작업을 무겁게 만드는 것이 아닙니다. **routine 작업은 가볍게 두고, 위험한 변경에만 더 강한 계약을 적용합니다.**

---

## 3. 빠른 시작

### 3.1 설치

이 저장소를 받은 뒤 배포 파일 8개를 대상 프로젝트 루트에 복사합니다. 숨김 디렉터리 `.harness/`를 빠뜨리지 마세요. 아래 명령은 이 저장소를 받을 작업 디렉터리(대상 프로젝트 밖)에서 실행합니다. 첫 줄의 `TARGET` 값만 Cairn을 적용할 **이미 있는** 프로젝트 디렉터리로 바꾸세요.

```sh
TARGET="$HOME/my-project"
git clone https://github.com/midopa-dept/cairn-harness.git
cp cairn-harness/AGENTS.md cairn-harness/CLAUDE.md "$TARGET/" && cp -R cairn-harness/.harness "$TARGET/"
```

경로에 공백이 있어도 되도록 `"$TARGET"`을 항상 큰따옴표로 감쌉니다. `TARGET` 디렉터리가 없으면 첫 `cp`가 실패하고 `&&` 때문에 `.harness/` 복사도 실행되지 않습니다. 대상 프로젝트에 이미 `AGENTS.md`, `CLAUDE.md`, `.harness/` 또는 다른 agent 지침이 있으면 이 명령을 실행하지 말고, 충돌을 검토해 직접 병합합니다(`cp`는 같은 이름의 파일을 덮어씁니다). `tools/`는 복사 대상이 아닙니다.

| 배포 파일 | 역할 |
|---|---|
| `AGENTS.md` | 모든 runtime이 따르는 공통 운영 계약(사람이 읽는 형태). Codex의 진입점 |
| `CLAUDE.md` | Claude Code 진입점. `AGENTS.md`와 Claude Code adapter를 import |
| `.harness/core.yaml` | lifecycle, role, authority, guard, graph, subgraph, schema, 핵심 정책 |
| `.harness/project.yaml` | 프로젝트별 로컬 설정 |
| `.harness/task.example.yaml` | Task Packet 템플릿 |
| `.harness/distribution.yaml` | 배포 version, content ID, payload SHA-256 |
| `.harness/adapters/claude-code.md` | Claude Code 수행 방법 |
| `.harness/adapters/codex.md` | Codex 수행 방법 |

### 3.2 프로젝트 설정

`.harness/project.yaml`에서 프로젝트 고유 값을 정합니다.

- `project_id`, `artifact_roots`(agent가 회수할 자료 루트), `task_root`(기본 `.harness/tasks`)
- `runtime.access_boundary`·`judgment_boundary`: 여러 Task에 걸친 지속 실행 경계
- 선택 `layout`: 경로별 artifact class, evidence root, relocation·delivery ledger 위치
- 선택 `extra_human_gate_tags`: 기본 Human Gate 범주에 더할 프로젝트 범주

설정은 실행 권한을 새로 주지 않습니다. Task별 사용자 위임은 설정에 누적하지 않고 각 Task Packet의 `scope.authorization`에 둡니다. 처음부터 직접 채우지 않아도 됩니다. 아래 bootstrap에서 agent가 사용자 요청을 바탕으로 채웁니다.

### 3.3 첫 Task 시작(bootstrap)

설정이 비어 있고 활성 Task가 없는 상태에서 프로젝트 목표와 요구를 주면, agent는 그 요청을 bootstrap 위임으로 받아들입니다.

```text
이 프로젝트는 개인 독서 기록 서비스 Booklog다.
현재 프로젝트에 포함된 Cairn에 따라 bootstrap하고 진행하라.

주요 요구사항:
- ...
- ...
```

agent는 계약에 따라 다음을 준비합니다.

1. repository와 기존 지침을 읽기 전용으로 확인
2. 주어진 요구를 출처와 함께 구조화하고 실제 미결정 사항만 식별
3. `project.yaml`과 bootstrap Task Packet 작성(`task.example.yaml`을 `task_root`에 복사하고 `harness_snapshot`에 `distribution.yaml`의 `content_id` 기록)
4. 목표·요구·핵심 사용자 흐름·초기 domain/data 개념·검증 전략을 정본 문서로 정리
5. 정본 목차(index)와 첫 implementation Task Packet 준비
6. 필요한 Human Gate에서만 멈춤

bootstrap도 검증·비producer 인수·종료를 거칩니다. 사용자가 Harness 운영 규칙을 prompt마다 다시 설명할 필요는 없습니다.

### 3.4 Validator 사용(선택)

`cairn_check`는 이 저장소의 `tools/`에 있는 report-only 검사 도구입니다. 대상 프로젝트에 복사할 필요가 없고, `--project`로 대상 프로젝트를 가리켜 실행합니다. Python 3.9 이상과 `ruamel.yaml`이 필요합니다. 3.1과 같은 셸·같은 작업 디렉터리에서 `TARGET`을 그대로 씁니다. 시스템 Python을 바꾸지 않도록 가상환경에 설치합니다.

```sh
python3 -m venv cairn-venv
. cairn-venv/bin/activate
python3 -m pip install -r cairn-harness/tools/requirements-dev.txt
python3 cairn-harness/tools/cairn_check.py --version
python3 cairn-harness/tools/cairn_check.py --project "$TARGET" check
python3 cairn-harness/tools/cairn_check.py --project "$TARGET" health
```

Task Packet이 생긴 뒤에는 다음 행동을 확인할 수 있습니다. `PACKET`은 프로젝트 루트 기준 Packet 경로로 바꾸고, 대상 프로젝트는 Git 저장소여야 합니다(`--git`).

```sh
PACKET=".harness/tasks/my-first-task.yaml"
python3 cairn-harness/tools/cairn_check.py --project "$TARGET" next-action --packet "$PACKET" --git
```

`check`의 종료 코드는 0 `PASS`, 1 `FAIL`, 2 호출 오류, 3 `INCONCLUSIVE`입니다. Task Packet이 하나도 없는 새 프로젝트에서는 `no_packets` 때문에 3이 나오는 것이 정상입니다. 3은 성공이 아니라 사람이 미평가 이유를 확인해야 한다는 뜻입니다. 자세한 의미는 [6장](#6-validator와-보장-범위)과 [`tools/README.md`](tools/README.md)에 있습니다.

### 3.5 이전 판본을 쓰던 프로젝트

이미 `1.0.0-candidate.4` 이하를 적용한 프로젝트는 자동으로 바뀌지 않습니다. 별도 update Task에서 다음을 검토한 뒤 반영합니다.

- 두 배포본의 diff와 프로젝트 적용성. candidate.5에서 배포 파일이 5개에서 8개로 늘었습니다(기존 `CLAUDE.md`가 있으면 병합).
- 기존 Packet은 고치지 않습니다. 각 Packet은 자기 `harness_snapshot`의 계약으로 해석하며 새 규칙을 소급하지 않습니다.
- 새 Task Packet부터 `schema_version` 3과 새 `harness_snapshot`을 씁니다.
- `project.yaml`은 schema 1을 계속 쓸 수 있습니다. `layout`·`health`를 쓰려면 schema 2로 올립니다.
- validator를 0.3.0으로 올립니다(0.2.1의 under-checking은 [6.3](#63-자동으로-검증하지-않는-영역)). candidate.4 Packet은 candidate.4 `core.yaml`을 `--contract <content_id>=<path>`로 주면 그 계약으로 검사합니다.

판본별 차이는 [CHANGELOG](CHANGELOG.md)를 보세요.

---

## 4. 주요 기능

아래 기능은 모두 현재 판본에서 함께 작동하는 하나의 계약입니다. 규범 원문은 [`AGENTS.md`](AGENTS.md)와 [`.harness/core.yaml`](.harness/core.yaml)입니다.

### 4.1 Authority와 역할

agent의 실제 권한은 역할 이름 하나로 정해지지 않습니다.

```text
effective authority = 역할 allow ∩ 현재 workflow 노드 allow ∩ Task scope.allow
                      (모든 deny와 경로 제한을 추가 적용)
```

- 역할은 coordinator·specifier·designer·planner·executor·verifier·reviewer·integrator·steward 9개입니다. 예를 들어 executor는 산출물을 바꿀 수 있지만 인수할 수 없고, reviewer는 검토·인수할 수 있지만 산출물을 고칠 수 없습니다.
- 하위 계층은 권한을 좁힐 수만 있고 조용히 넓힐 수 없습니다. 선언되지 않은 기능은 금지입니다.
- 쓰기는 `scope.write`, 읽기는 `scope.read`에 적힌 경로에만 적용됩니다.
- `scope.authorization`은 실제 사용자 위임의 위치와 내용입니다. agent가 스스로 권한을 만들 수 없고, 새 세션의 위임은 날짜·actor와 함께 덧붙이기만 합니다.
- 위임 문장이 마지막 단계(예: 인수까지)를 정하면 그 단계까지만 하고, 다음 단계는 보고만 합니다.

### 4.2 Workflow와 Task Packet

작업 하나는 **Task Packet** 하나(YAML)입니다. Packet은 목적, 범위와 위임, 현재 단계와 actor, 인수 기준(criteria), 관련 자료 manifest, 후보(candidate), 검증 근거, 결정, 전달, 복구 상태를 한 곳에 담습니다. 계획서·검토서·보고서를 매번 따로 만들지 않고, 재개에 필요한 최소 상태를 복구 가능하게 유지하는 것이 기본입니다.

기본 workflow graph `standard-change`의 단계는 다음과 같습니다. 각 단계에는 참여 역할, 허용 기능, 진입 조건(guard)이 정해져 있습니다.

```text
admit → plan → execute → verify → accept → close
            (실패·중단 시 어느 단계에서든 recover로 이동한 뒤 복귀)
```

lifecycle 상태는 네 개이며 서로 대체되지 않습니다.

| 상태 | 뜻 |
|---|---|
| `OPEN` | 작업 의무를 수행 중이거나, 후보가 바뀌어 판단을 다시 준비함 |
| `VERIFIED` | 현재 후보의 필수 기준에 적용 가능한 검증 근거가 있음. 인수는 아님 |
| `ACCEPTED` | 권한 있는 비producer가 현재 후보를 인수함. 종료는 아님 |
| `CLOSED` | 인수·전달·잔여 의무 인계·정리가 끝남 |

```text
PASS ≠ ACCEPTED
VERIFIED ≠ CLOSED
commit/push ≠ product acceptance
child ACCEPTED ≠ parent ACCEPTED
```

- guard는 충족 근거를 판단하는 선언이며 자동 실행 코드가 아닙니다.
- 다음에 할 일은 정해진 어휘(`none`·`recover`·`reconcile_checkpoint`·`complete_admission`·`plan`·`request_human_gate`·`execute`·`verify`·`independent_review`·`accept`·`deliver`·`settle_close`)와 순서로 도출합니다. 같은 Packet과 Git 상태라면 어느 runtime이 읽어도 결과가 같아야 합니다.
- 큰 작업을 child Task로 나누면 parent가 **Coverage Matrix** 하나를 소유합니다. 약속한 정본 section의 모든 구조 단위를 `owned`·`deferred`·`excluded`·`informative` 중 하나로 처분하고, child는 자기 행을 criterion으로 구체화합니다. 행은 excerpt와 fingerprint로 정본에 결합되어 정본이 바뀌면 drift(`suspect`·`ambiguous`·`missing`)로 드러납니다.
- guard에 쓰지 않는 기록은 decision `kind: record`와 `subkind`로, 프로젝트 확장 정보는 `local`에 둡니다.
- 각 Packet은 자기 `harness_snapshot`(배포본 `content_id`)의 계약으로 해석합니다. Harness를 업데이트해도 기존 Packet에 새 규칙을 소급하지 않습니다.

### 4.3 Independent Review와 Acceptance

- **candidate를 만들거나 고친 producer는 그 candidate를 인수할 수 없습니다.** 역할·context·runtime·ID를 바꿔도 같습니다.
- 인수자는 producer와 다른 실제 actor여야 합니다. **같은 모델이어도 됩니다.**
- 필수 독립 판단은 성질로 판정합니다. producer와 다른 actor일 것, producer 대화를 상속하지 않을 것, frozen candidate·기준·원자료 같은 bounded input만으로 시작할 것. 대화 fork·resume·continue는 독립이 아닙니다.
- 수단은 runtime마다 다릅니다. Claude Code는 fork가 아닌 subagent나 새 `claude -p` 프로세스, Codex는 새 `codex exec` 프로세스를 씁니다(각 adapter). 사용자가 그렇게 연 새 세션도 됩니다. 사용한 수단과 입력은 기록합니다.
- runtime이 다르다는 사실만으로는 독립이 아닙니다. 다른 runtime이라도 producer reasoning을 입력받았다면 분리를 주장하지 않습니다.
- 적격한 비producer reviewer는 인수(`ACCEPTED`)까지 할 수 있습니다. reviewer가 후보를 고치면 그 reviewer는 producer가 됩니다.

### 4.4 Human Gate

다음 기본 범주의 변경은 효과가 발생하기 전에 사람의 명시적 승인이 필요합니다. 프로젝트는 범주를 더할 수만 있고 뺄 수 없습니다.

`architecture` · `authentication_security` · `db_migration` · `canonical_requirement` · `production_effect` · `equivalent_high_impact`

판단은 세 class로 나눕니다.

| class | 뜻 | 처리 |
|---|---|---|
| derivable | 정본·결정·근거에서 답이 하나로 도출되고 고위험 범주가 아님 | 진행하고 도출 출처를 남김 |
| ambiguous_semantic | 출처를 댈 수 있는 정당한 해석이 둘 이상 | Human Gate 질문 |
| high_impact | 의미는 명확하지만 위 범주에 해당 | 계획 식별(`plan.identity`)에 결합한 명시 승인 |

- 질문은 한 번에 하나만 합니다. 의미 있는 선택지 2~3개, 짧은 장단점, 추천안과 이유를 붙입니다. 이미 정해진 답은 다시 묻지 않습니다.
- 모델 confidence나 자기평가로 class를 낮추거나 Gate를 생략하지 않습니다.
- 과거 승인은 같은 범위에서만 재사용하고 새 변경으로 자동 확대하지 않습니다.

Human Gate는 모든 작업에 사람을 끼워 넣는 장치가 아니라, **agent가 스스로 넘어서는 안 되는 권위 경계**를 표시하는 장치입니다.

### 4.5 Evidence와 Artifact Lifecycle

- **증거는 후보·범위에 결합됩니다.** 과거의 PASS나 승인은 현재 후보·범위·판본과의 적용성을 대조한 뒤에만 씁니다. 후보가 바뀌면 필요한 범위를 다시 검증하거나 인수합니다.
- **대리 관찰 금지.** touch 요구를 CSS 검사로, 시각 품질을 구조·접근성 검사로, 실제 기기를 desktop emulation으로, 체감 latency를 내부 지표로, 1차 경로를 fallback 실행으로 대신한 관찰은 PASS가 아닙니다. 관찰 수단이 없으면 `not_run`입니다.
- **evidence manifest.** 각 Task의 새 evidence는 자기 namespace(`layout.evidence_root/<Task ID>`)에만 쓰고 authoritative(인수가 직접 기댄 기록)·supporting(설명·재현용 요약)·raw(log·screenshot 등)로 분류합니다.
- **artifact class와 temperature.** 문서는 canonical·operational·decision·task·evidence·raw_evidence·historical로 나뉘고, 회수 우선순위는 hot·warm·cold입니다. class는 저장하지 않고 `layout`·Task 상태·manifest로 계산합니다. 권장 구조는 `docs` = 현재 프로젝트를 이해하기 위한 문서, `.harness` = Task·evidence·provenance입니다.
- **봉인(sealed).** 소유 Task가 `CLOSED`인 Packet과 evidence는 고치거나 덮어쓰거나 지우지 않습니다. 재실행은 새 Task namespace에, 정정은 새 기록으로 남깁니다.
- **relocation ledger.** 문서를 옮길 때는 from·to·content identity를 ledger에 append합니다. 역사 Packet의 옛 경로는 고치지 않고 ledger로 해석합니다. 내용이 바뀌면 이동이 아니라 새 판본입니다. 정리·압축은 삭제가 아닙니다.
- **residual.** 남은 위험은 `risk`·`owner`·`condition` 구조로 넘기고(선택 `id`·`owner_kind`·`owner_ref`·`due`), 종료하는 Task 자신을 owner로 두지 않습니다. 이전 Task residual의 해소·대체·이전·수용은 후속 Packet의 `delivery.residual_dispositions`에 append합니다.

### 4.6 Progressive Retrieval

Cairn은 프로젝트 전체 history를 매번 초기 context로 넣지 않습니다.

```text
ID / metadata → 짧은 summary·제목 → 관련 excerpt → 필요한 경우에만 full artifact
```

- 계약 자체도 필요한 key만 읽습니다(현재 graph·node·역할·Packet 기준 등).
- 종료된 Task는 objective·state·delivery와 authoritative evidence만 기본으로 보고, supporting과 raw는 필요할 때 이유를 남기고 봅니다.
- 계획과 기준을 확정하기 전에 정본 목차의 ID·제목·적용 범위에서 관련 공통 의무(요구·보안·architecture 등)를 bounded하게 대조합니다(applicability check).
- 작은 task-local Artifact Graph는 정본의 **명시 참조에서만** 결정적으로 도출합니다. **graph에 edge가 없다는 사실을 관련 요구가 없다는 뜻으로 쓰지 않습니다.** 찾지 못했거나 적용성이 불명이면 unresolved로 기록하고 관련 claim을 보류합니다.

### 4.7 Recovery와 Handoff

- **상태의 authority는 repository bytes·Git identity·Task Packet·durable evidence·사용자 결정 기록뿐입니다.** runtime 메모리·thread·대화 reasoning에만 있는 상태는 authority가 아니며 다른 runtime이 이어받을 수 없습니다.
- 효과 있는 실행(파일 쓰기, 구현 단계, test·검증 실행, 검토·인수 중의 test·probe 실행, 외부 효과 명령)은 시작 전에 `recovery.attempts`에 기록하고 끝나면 상태와 receipt를 갱신합니다. Packet·Git 읽기, 다음 행동 파악, 결정적 계약 검사, capability 확인처럼 효과 없는 상태 확인은 attempt가 아닙니다.
- **효과 없음이 분명하지 않은 실행(inline 코드·script·변환 명령 등)은 효과가 있는 것으로 보고, attempt를 먼저 기록한 뒤 실행합니다.** 검토자와 인수자도 같습니다. 검토·인수 중에 test나 probe를 돌리기 전에 자기 attempt를 먼저 기록합니다. 기록은 효과와 같은 쓰기 묶음에 넣지 않고 먼저 저장해 Packet이 읽히는지 확인합니다.
- 이 순서는 **계약상 의무이며 이 판본에는 자동으로 검사하거나 강제하는 도구가 없습니다.**
- 시도 수는 Task별 유한 상한(`max_attempts`) 안에서 씁니다. 실패·중단 기록을 지우거나 상한을 임의로 초기화하지 않습니다.
- 멈추거나 다른 runtime이 이어받을 수 있는 지점에서는 `recovery.checkpoint`(base commit, 의도된 미커밋 경로, 완료/남은 단계)를 실제와 맞춰 둡니다.
- 이어받는 쪽은 Packet을 읽고 Git HEAD·working tree를 checkpoint와 대조합니다. 출처를 설명할 수 없는 변경이 있으면 `recovery.status: blocked`로 두고 사용자 확인 전에는 진행하지 않습니다. reset·clean·stash로 지우지 않습니다.
- 같은 working tree에서 두 runtime이 같은 Packet이나 겹치는 쓰기 범위를 동시에 진행하지 않습니다.

### 4.8 Cross-runtime Portability

- 계약은 도구 이름이 아니라 capability 10개로 말합니다: `read_files`·`edit_files`·`execute_commands`·`git`·`network`·`spawn_independent_context`·`browser_observation`·`production_read`·`production_write`·`human_interaction`.
- admit·recover·runtime 전환 때 필요한 capability를 실제로 관찰해 `runtime_observations`에 `available`·`unavailable`·`gated`·`not_checked`로 남깁니다. 없는 capability를 성공으로 가정하지 않고, 처리(`alternate_path`·`not_available`·`not_run`·`blocker`)를 따로 기록합니다. 선언은 권한이 아닙니다.
- `actor.runtime`에 runtime family를 기록하고, actor ID는 `<runtime>-<task>-<role>` 형식을 권장합니다.
- 결정적 경계(state·node·권한·Gate 필요·candidate identity·인수 적격)에서 runtime 사이 판단이 다르면 escalation이 아니라 계약 해석 결함으로 봅니다. `cairn_check next-action`이 이 경계의 기준값을 계산합니다.

### 4.9 Project Health

`cairn_check health`는 Task 단위 검사와 별도로 프로젝트 정보구조의 신선도를 봅니다. index 신선도, 참조 해결, relocation 무결성, 봉인 경로의 쓰기·수정, residual liveness, raw evidence 위치·크기, 동시 쓰기, 검증 surface drift, adapter drift를 `error`·`warning`·`info`·`not_checked`로 보고합니다. 선택 verification registry를 두면 "검증했다고 생각했지만 suite에서 빠진 runner"를 찾을 수 있습니다. health 결과는 권한·인수·Human Gate 판단이 아닙니다.

### 4.10 Git Closeout

Git 프로젝트에서 위임이나 정책이 commit/push를 허용하고, 정상 remote가 있고, Task 범위 안의 변경만 있으면 완료형 closeout을 기본으로 수행합니다. 완료는 단순 `git push`가 아니라 다음 흐름입니다.

```text
최종 diff 확인
→ 검증 / 비producer 인수 확인
→ 완료형 commit 하나
→ non-force push
→ local/remote target identity 확인
→ clean working tree 확인
→ 실제 delivery evidence 기록
```

- close commit처럼 Packet에 미리 쓸 수 없는 사실은 대화에만 두지 않고 `layout.delivery_ledger`(JSON Lines, append-only)에 기록합니다.
- force push, 파괴적 reconciliation, 범위 밖 변경 포함, 승인되지 않은 history rewrite는 하지 않습니다.
- Git 여부나 remote 존재는 권한이 아닙니다. Git·위임·remote가 없으면 제품 실패로 꾸미지 않고 필요한 좁은 사용자 행동만 알립니다.

---

## 5. 실제 사용 예시

책장 이름 수정 기능처럼 이미 승인된 요구 안의 routine 작업이 Claude Code에서 시작해 Codex로 넘어가는 흐름입니다. 단계 이름은 `standard-change` graph의 노드입니다.

1. **admit — 작업 접수.** 사용자가 Claude Code에 기능 구현을 맡깁니다. Claude는 새 Task Packet을 만들고 위임 원문을 `scope.authorization`에, 쓰기 범위를 `scope.write`에 적습니다. 필요한 capability를 관찰해 `runtime_observations`에 남깁니다.
2. **plan — 계획.** 관련 requirement와 공통 의무만 좁게 회수하고(applicability check), 인수 기준(criteria)과 attempt 상한을 정합니다. 고위험 범주가 없으므로 Human Gate는 없습니다.
3. **execute — 구현.** 파일을 쓰기 전에 attempt를 기록하고, 구현 뒤 상태와 receipt를 갱신합니다.
4. **중단과 인계.** 구현 도중 세션을 멈추며 `recovery.checkpoint`(base commit, 의도된 미커밋 경로, 완료/남은 단계)를 남깁니다. 다음 세션의 Codex는 Packet을 읽고 `cairn_check next-action --packet <Packet> --git`으로 checkpoint와 Git 상태를 대조한 뒤 남은 구현을 이어갑니다. 산출물 판본을 candidate로 고정할 때 Claude와 Codex 두 actor를 모두 producer로 기록합니다.
5. **verify — 독립 검토.** producer 대화를 상속하지 않은 새 reviewer 맥락(예: 새 `claude -p` 프로세스)에 frozen candidate·criteria·원자료 경로만 줍니다. producer와 다른 actor라면 같은 모델이어도 됩니다. reviewer는 후보를 고치지 않고 기준별로 판정해 Packet `decisions`에 기록합니다.
6. **accept — 인수.** reviewer가 producer 목록에 없는 적격 actor이고 필수 기준이 충족되면 `ACCEPTED`로 인수합니다. producer는 자기 후보를 인수하지 않습니다.
7. **close — 종료.** 최종 diff 확인, commit 하나, non-force push, local/remote identity와 clean 확인, delivery ledger 기록을 거쳐 `CLOSED`가 됩니다. 남은 위험은 owner와 조건을 붙여 넘깁니다.

로그인이나 session 인증 방식을 바꾸는 고위험 작업이라면 흐름은 같고 다음이 추가됩니다.

- authentication/security와 관련 architecture 정본을 회수하고 영향받는 ownership·session·persistence 의무를 확인합니다.
- 계획과 Review Brief를 구체화하고, **실제 변경 전에** 그 계획 식별에 결합한 Human Gate 승인을 받습니다.
- 영향 범위에 맞춰 검증을 넓히고, 필요한 독립 판단과 비producer 인수를 수행합니다.

---

## 6. Validator와 보장 범위

### 6.1 `cairn_check`의 역할

`cairn_check` 0.3.0은 Cairn 계약의 결정적 무결성 규칙(VS0~VS6)과 결정적 projection(next action·project health·relocation·evidence tier)을 계산하는 **report-only companion 도구**입니다.

- 8개 배포 파일에 포함되지 않습니다. 도구 판본은 계약 `content_id`의 일부가 아니며, 도구가 바뀌어도 계약 `content_id`는 바뀌지 않습니다.
- 도구는 authority가 아닙니다. Packet·Coverage Matrix·정본을 수정하지 않고 lifecycle 전이·decision·인수를 만들지 않습니다.
- 도구가 없어도 `core.yaml` `validation_contract.companion`의 규칙과 순서를 사람이나 agent가 직접 수행할 수 있습니다(method `manual`과 수행 범위를 기록).

| 명령 | 하는 일 |
|---|---|
| `check` | Packet·Coverage Matrix 검사(구문 → schema → 연결 → matrix → drift → 소유권) |
| `skeleton`·`rows`·`seed` | Coverage Matrix 초안 출력, child 행 회수, criterion 소유 행의 정본 전문 조립 |
| `next-action --packet PATH [--git]` | state·node·권한·Human Gate·candidate·인수 제외 actor·checkpoint 대조·다음 행동의 결정적 projection. runtime 사이 인계의 기준값 |
| `health` | project health 보고 |
| `relocations` | relocation ledger 검사와 옛 경로 해석 |
| `evidence` | Task별 evidence tier 집계 |

### 6.2 PASS와 ACCEPTED의 차이

| | 뜻 | 누가 |
|---|---|---|
| `cairn_check` `PASS` | 선언된 계약의 **결정적 무결성 검사**를 통과했다는 뜻뿐 | 도구(또는 같은 규칙의 수동 수행) |
| `VERIFIED` | 현재 후보의 필수 기준을 덮는 적격 검증 근거가 있음 | verifier와 필요한 독립 검토 |
| `ACCEPTED` | 권한 있는 비producer가 현재 후보를 인수함 | producer가 아닌 reviewer·coordinator 또는 사람 |

`PASS`는 정확성도, 제품 인수도, Human Gate 승인도 아닙니다. CI에서는 종료 코드 0만 성공으로 취급하고, 3(`INCONCLUSIVE`)은 사람이 미평가 이유를 확인합니다.

### 6.3 자동으로 검증하지 않는 영역

- **attempt가 효과 있는 실행보다 먼저 기록됐는지**(도구는 attempt 항목 schema와 `max_attempts` 상한만 검사합니다)
- 내용의 의미적 정확성, scope 선언과 분할의 충분성, `informative` 판정의 타당성, criterion이 정본 의무를 실제로 함의하는지, 관찰 방식의 충분성
- 인간 승인의 진정성, 실제 runtime actor 격리, OS 수준 권한 강제
- 임의의 shell 명령이 효과를 내는지에 대한 판별

알아 둘 동작:

- validator 0.2.1은 candidate.5 Packet을 거부하지 않고 v3 규칙을 모른 채 PASS할 수 있습니다. candidate.5 프로젝트에는 0.3.0 이상을 쓰세요.
- 도구보다 새 `contract_version`을 만나면 `contract_newer_than_tool`로 `INCONCLUSIVE`를 냅니다.
- `task_root`에서 kind 오타나 빈 YAML은 warning `unrecognized_yaml`만 남기고 판정에 영향을 주지 않습니다. 허용 kind는 다음 계약 개정에서 정합니다.

---

## 7. 상세 문서·변경 이력·설계 배경

### 7.1 문서

| 문서 | 내용 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | 모든 runtime의 공통 운영 계약(규범 원문) |
| [`.harness/core.yaml`](.harness/core.yaml) | lifecycle·role·authority·guard·graph·schema·정책의 정본 |
| [`.harness/adapters/claude-code.md`](.harness/adapters/claude-code.md) · [`.harness/adapters/codex.md`](.harness/adapters/codex.md) | runtime별 수행 방법 |
| [`.harness/task.example.yaml`](.harness/task.example.yaml) | Task Packet 템플릿과 field 설명 |
| [`tools/README.md`](tools/README.md) | `cairn_check` 명령·종료 코드·알려진 한계·판본 |
| [CHANGELOG](CHANGELOG.md) | 공개 판본별 변경 내역 |

### 7.2 판본과 배포본 식별

`.harness/distribution.yaml`은 version, distribution ID, content ID, 각 payload 파일의 SHA-256으로 exact distribution을 식별합니다. 복사한 뒤 바꾸는 `.harness/project.yaml` 값이나 실제 Task Packet은 이 identity의 일부가 아닙니다. 버전과 content ID는 출하본 비교용이며 다른 저장소를 조회하라는 지시가 아닙니다.

현재 공개본은 최종 `1.0.0`이 아니라 **`1.0.0-candidate.5`**이고, content ID는 `sha256:7a3d4d4f69a346ef9fa4c44973276a7625e52b94e9e56dde742dba5e4b5e00ca`입니다.

### 7.3 설계 배경과 참고자료

**Cairn은 Graph Engineering인가?** 부분적으로는 그렇습니다. Cairn은 두 종류의 graph를 구분합니다.

| 영역 | 역할 |
|---|---|
| Workflow Graph | 실행 순서, 역할, guard, 상태 전이, reusable subgraph |
| Artifact Graph | 관련 자료와 정본을 찾기 위한 context 회수 단서 |

최근 Graph Engineering 문헌은 task organization, agent coordination, runtime state management를 명시적 graph로 외재화하는 방향을 다루며, Cairn의 Workflow Graph도 이 문제영역과 겹칩니다. 그러나 Cairn의 범위에는 authority narrowing, Human Gate, evidence·candidate identity, progressive retrieval, acceptance isolation, recovery policy, distribution boundary, Git closeout도 포함됩니다. 따라서 **Graph Engineering은 Harness의 핵심 구성 요소 중 하나이지 Harness 전체와 동의어가 아닙니다.** Cairn은 LangGraph 같은 stateful orchestration runtime을 구현하지 않습니다.

Cairn은 "완전히 새로운 agent architecture"를 주장하지 않습니다. 여러 기존 아이디어와 가까운 engineering precedent를 참고하거나 사후 대조했고, 그 위에서 project-local lifecycle·authority·evidence 계약을 조합했습니다. **아래 자료는 Cairn의 성능이나 효과를 실험적으로 검증한 근거가 아닙니다.** "참고한 패턴", "비교 대상", "가까운 선례"를 구분해서 봐야 합니다.

초기 설계에서 참고한 자료:

- **OpenAI — [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)**: 저장소 안의 짧은 진입점과 project-local knowledge로 agent가 필요한 정본으로 이동하는 방식. progressive retrieval·로컬 운영 규칙과 가까운 참고점이지만, OpenAI의 개발 속도나 자동 review/merge 결과를 Cairn의 성능 주장으로 쓰지 않습니다.
- **Anthropic — [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)**: 필요한 정보를 그때그때 회수하고 context를 관리하는 접근. minimal seed + progressive retrieval과 연결되며, 과도한 요약의 정보 손실과 탐색 실패 가능성도 고려합니다.
- **Aider — [Repository map](https://aider.chat/docs/repomap.html)**: 파일 본문보다 구조와 symbol/signature를 먼저 보여 관련 코드를 고르는 아이디어를 task-local manifest와 비교했습니다. ranking 알고리즘이나 token budget을 채택하지는 않았습니다.
- **Microsoft — [GraphRAG](https://microsoft.github.io/graphrag/)**: 관계 기반 탐색을 Artifact Graph와 비교했습니다. Cairn은 LLM이 관계를 추론해 knowledge graph를 만들지 않고 **정본의 명시 참조만 결정적으로 투영**합니다.

Workflow / Graph / Agent orchestration 비교 자료:

- **Anthropic — [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)**: 미리 정의한 workflow, 환경 피드백, 인간 checkpoint, 유한한 반복 구조를 Workflow Graph·Human Gate·Recovery와 비교했습니다.
- **Feng et al. — [Graph Engineering in the Era of LLM Agents: From Individual Intelligence to System Intelligence](https://arxiv.org/html/2608.21156v2)**: task organization, agent coordination, runtime state management를 graph 관점에서 체계화한 survey. Cairn은 이 taxonomy 전체의 구현이 아니라 겹치는 project-local workflow/state contract를 가집니다.
- **LangGraph — [Overview](https://docs.langchain.com/oss/python/langgraph/overview), [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)**: StateGraph, checkpoint, interrupt/resume를 제공하는 stateful orchestration runtime의 비교 대상. Cairn은 runtime persistence나 automatic resume를 구현하지 않습니다.
- **luxiaolei — [Graph Engineering](https://github.com/luxiaolei/graph-engineering)**: project-local graph contract에 state, routing, guard, context, evaluation, governance를 함께 두는 가까운 precedent. Cairn은 YAML 기반 Core/Task Packet과 별도의 authority/evidence 의미를 씁니다.
- **context4ai — [Agent Graph](https://github.com/context4ai/agent-graph)**: 현재 Facts와 Outcome으로 다음 route, 필요한 resource, 완료 evidence를 제한하는 work-contract 접근. Task Packet/context routing과 문제의식이 일부 겹치지만 같은 runtime/SDK 모델은 아닙니다.

Evidence / provenance / 독립 판단 관련 자료:

- **Anthropic — [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)**: 생성과 평가의 분리, 장기 세션의 context 관리를 비producer acceptance와 bounded-context 독립 판단 정책과 비교했습니다. topology나 성과 수치를 Cairn의 검증 근거로 쓰지 않습니다.
- **W3C — [PROV-DM: The PROV Data Model](https://www.w3.org/TR/2013/REC-prov-dm-20130430/)**: entity, activity, revision의 구분을 candidate/artifact/evidence identity와 비교했습니다. W3C PROV ontology를 구현하거나 준수한다고 주장하지 않습니다.
- **Edge et al. — [From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/html/2404.16130v2)**: GraphRAG 원 논문. 문서 집합의 전역 질문/요약 성능을 Artifact Graph나 token 절감 효과로 잘못 전이하지 않도록 경계를 확인했습니다.

다음은 위 자료에서 그대로 가져온 규칙이 아니라 **Cairn이 project-local contract로 선택한 구체 의미**입니다.

- `Role ∩ Node ∩ Scope` 권한 계산
- `VERIFIED ≠ ACCEPTED ≠ CLOSED`
- child acceptance와 parent acceptance의 분리
- 모든 candidate에 대한 비producer acceptance
- Human Gate의 구체 위험 범주
- 한 번에 하나의 사용자 결정 질문
- 여덟 파일 distribution snapshot(공통 계약 하나와 얇은 runtime adapter)
- 정본의 명시 참조에서만 도출하는 Artifact Graph 관계
- 조건부 Git closeout

관련 아이디어가 기존 문헌에 있다는 것과, 그 문헌이 위 계약을 도출하거나 검증했다는 것은 구분합니다.

---

## 8. 현재 한계

`1.0.0-candidate.5`에서 확인된 범위:

- 선언형 계약과 배포 경계의 정적 일관성, exact distribution identity
- candidate.4 대비 authority·lifecycle·Human Gate 의미 불변(추가만)과 candidate.3/.4 Packet backward compatibility
- companion validator의 결정적 검사
- 소형 fixture에서 Claude Code와 Codex가 실제로 교대 실행한 conformance: Human Gate 판단, 양방향 인계, 비producer 인수, checkpoint가 두 runtime 사이에 같은 의미로 성립한 **관측 실행**. 관측된 시나리오 범위의 근거이며 매 실행을 보장하지 않습니다.

이 판본이 **보장하지 않는 것**:

- **attempt 사전 기록 순서의 자동 검증·강제.** 효과 있는 실행 전에 attempt를 기록하는 것은 계약상 의무이지만 이 판본에는 그 순서를 검사하거나 강제하는 도구가 없습니다. 준수는 runtime·actor와 독립 검토자가 확인해야 합니다. 실제 conformance에서도 runtime의 사전 기록 준수는 실행마다 흔들렸습니다.
- 임의의 shell 명령이 효과를 내는지에 대한 판별
- conformance 통과의 매 실행 재현. 시나리오별 반복 분산은 측정하지 않았고, browser가 있는 runtime 경로와 대화형 세션 기본값은 시험하지 않았습니다.
- subgraph 내부 노드의 `next-action` projection

아직 실증적으로 주장하지 않는 것:

- token 사용량 감소
- 작업 성공률 향상
- agent hallucination 감소
- 실제 runtime actor 격리의 강제
- 모든 프로젝트에서의 적합성
- graph 구조 자체의 독립적인 성능 향상

실제 프로젝트 적용에서 특히 확인해야 할 항목:

1. runtime에서 producer/acceptor 분리가 실제로 얼마나 안정적으로 유지되는가
2. Task Packet 유지 비용이 routine 작업에서 과도하지 않은가
3. progressive retrieval이 실제 context/token 부담을 줄이면서 누락을 만들지 않는가

---

## 기본 언어

현재 배포본은 사람이 읽는 설명, 계획, 보고, review note, handoff의 기본 언어로 **한국어**를 씁니다. 식별자, 경로, API/CLI 문법, 고유 명칭, 원근거, 자동 도구 출력은 원래 표기를 유지합니다.

## 라이선스

Cairn은 **MIT License**로 배포됩니다. 자세한 내용은 [`LICENSE`](LICENSE)를 확인하세요.
