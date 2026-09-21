# Cairn Harness

Cairn은 장기적인 **agentic software project**를 안정적으로 운영하기 위한 **소형 선언형 Harness**입니다.

LLM agent가 여러 단계에 걸쳐 코드를 수정하는 프로젝트에서는 단순히 “다음 작업을 잘 수행하는가”만으로 충분하지 않습니다. 시간이 길어질수록 다음 문제가 누적되기 쉽습니다.

- 누가 무엇을 바꿀 권한이 있는지 불명확해짐
- 검증(`VERIFIED`)과 인수(`ACCEPTED`)가 섞임
- 이전 작업의 근거가 현재 candidate에도 유효한지 추적하기 어려움
- 전체 프로젝트 history를 계속 읽으면서 context가 비대해짐
- high-risk 변경이 일반 작업과 같은 흐름으로 처리됨
- 실패 후 재시작하면서 이전 상태·판정·근거가 유실됨
- “테스트 통과”, “커밋 완료”, “실제 전달 완료”가 하나의 완료 의미로 뭉개짐

Cairn은 이런 문제를 **project-local contract**로 명시합니다. 전용 orchestration runtime을 제공하는 대신, 기존 agent/runtime 위에 얹을 수 있는 lifecycle·authority·evidence·context·approval·recovery 계약을 다섯 개의 배포 파일로 제공합니다.

> 현재 공개 배포본: **`1.0.0-candidate.3`**
> 현재 상태: 첫 실제 프로젝트 적용을 시작할 수 있는 release candidate이며, 최종 `1.0.0` release acceptance를 의미하지 않습니다.

---

## 핵심 아이디어

### 1. 권한은 Role × Node × Scope의 교집합

Cairn에서 agent의 실제 권한은 역할 이름 하나로 결정되지 않습니다.

**effective authority = role baseline ∩ current workflow node ∩ current task scope**

하위 계층은 권한을 더 좁힐 수 있지만 조용히 넓힐 수 없습니다. architecture, authentication/security, DB migration, canonical requirement 변경 등 고영향 변경에는 별도의 Human Gate가 필요합니다.

### 2. Workflow의 상태 의미를 분리

Cairn은 다음을 서로 다른 사건으로 취급합니다.

- `VERIFIED` — 요구된 검증 근거가 현재 candidate에 대해 성립함
- `ACCEPTED` — 적격한 비producer가 candidate를 인수함
- `CLOSED` — 필요한 전달·통합·잔여 의무까지 종료됨

따라서 다음 등식은 성립하지 않습니다.

```text
PASS ≠ ACCEPTED
VERIFIED ≠ CLOSED
commit/push ≠ product acceptance
child ACCEPTED ≠ parent ACCEPTED
```

candidate를 생성하거나 수정한 producer는 역할이나 context 이름을 바꾸더라도 자기 candidate를 ACCEPT할 수 없습니다.

### 3. Task Packet이 작업 단위의 계약

각 작업은 하나의 Task Packet으로 목적, scope, 현재 graph/node, actor, criteria, 관련 artifact, candidate, verification evidence, decision, recovery 상태를 함께 추적합니다.

별도 계획서·검토서·보고서를 항상 새로 만드는 대신, **현재 작업에 필요한 최소 상태를 한 곳에서 복구 가능하게 유지하는 것**이 기본 방향입니다.

### 4. Context는 누적하지 않고 필요한 만큼 회수

Cairn은 프로젝트 전체 history를 매번 초기 context로 넣는 방식을 기본으로 하지 않습니다.

대신 다음 순서로 회수합니다.

```text
ID / metadata
→ 짧은 summary
→ 관련 excerpt
→ 필요한 경우에만 full artifact
```

Task-local manifest와 작은 Artifact Graph를 탐색 단서로 사용하되, **graph에 edge가 없다는 사실을 관련 요구가 없다는 뜻으로 사용하지 않습니다.** 계획·검증 의무를 확정하기 전에 현재 정본 metadata에서 bounded applicability check를 수행합니다.

### 5. Human Gate는 위험도에 따라 사용

일상적인 변경은 이미 승인된 계약 안에서 자동으로 진행할 수 있습니다.

반면 실제 영향이 큰 변경은 해당 효과가 발생하기 전에 인간 판단을 요구합니다. 기본 고위험 범주는 다음을 포함합니다.

- architecture
- authentication / security
- database migration
- canonical requirement 변경
- 이에 준하는 high-impact 변경

Human Gate는 모든 작업에 사람을 끼워 넣기 위한 장치가 아니라, **agent가 스스로 확장해서는 안 되는 권위 경계**를 표시하는 장치입니다.

### 6. Evidence는 candidate와 scope에 결합

과거의 PASS나 승인 기록은 무조건 재사용되지 않습니다.

현재 candidate·scope·artifact revision과의 적용 가능성을 대조한 뒤 사용할 수 있습니다. candidate가 달라졌다면 필요한 범위만 다시 검증하거나 인수합니다.

### 7. Recovery와 Closeout도 계약의 일부

실패·중단·재개 기록을 지우고 처음부터 성공한 것처럼 만들지 않습니다. 유한한 recovery budget과 resume 위치를 기록하며, 이미 발생한 실패와 판정은 보존합니다.

Git 프로젝트에서 commit/push까지 위임된 경우에도 완료는 단순 `git push`가 아니라 다음 흐름을 기본으로 합니다.

```text
최종 diff 확인
→ 검증 / 비producer 인수 확인
→ 완료형 commit
→ non-force push
→ local/remote target identity 확인
→ clean working tree 확인
→ 실제 delivery evidence 기록
```

---

## Cairn은 Graph Engineering인가?

부분적으로는 그렇습니다. 그러나 Cairn 전체가 graph runtime인 것은 아닙니다.

Cairn은 두 종류의 graph 개념을 구분합니다.

| 영역 | 역할 |
|---|---|
| **Workflow Graph** | 실행 순서, 역할, guard, 상태 전이, reusable subgraph를 표현 |
| **Artifact Graph** | 관련 자료와 정본을 찾기 위한 context 회수 단서를 제공 |

최근 Graph Engineering 문헌은 task organization, agent coordination, runtime state management를 명시적 graph 구조로 외재화하는 방향을 다룹니다. Cairn의 Workflow Graph도 이 문제영역과 겹칩니다.

하지만 Cairn의 Harness 범위에는 graph 외에도 다음이 포함됩니다.

- authority narrowing
- Human Gate
- evidence / candidate identity
- progressive retrieval
- acceptance isolation
- recovery policy
- distribution boundary
- Git closeout

따라서 Cairn에서 **Graph Engineering은 Harness의 핵심 구성 요소 중 하나**이지 Harness 전체와 동의어는 아닙니다. 또한 Cairn은 LangGraph 같은 stateful orchestration runtime을 구현하지 않습니다.

---

## 배포 파일

배포본은 의도적으로 작게 유지합니다.

```text
AGENTS.md
.harness/
├── core.yaml
├── project.yaml
├── task.example.yaml
└── distribution.yaml
```

| 파일 | 역할 |
|---|---|
| `AGENTS.md` | agent가 프로젝트에서 따라야 할 사람이 읽을 수 있는 운영 계약 |
| `.harness/core.yaml` | lifecycle, role, authority, guard, graph, subgraph, schema, 핵심 정책 |
| `.harness/project.yaml` | 프로젝트별 로컬 설정 |
| `.harness/task.example.yaml` | Task Packet 템플릿 |
| `.harness/distribution.yaml` | 배포 version, content ID, payload SHA-256 |

Cairn은 **선언형 Harness**입니다. 다음은 포함하지 않습니다.

- agent runtime
- model/provider adapter
- sandbox 또는 OS-level permission enforcement
- graph database
- vector database / embeddings
- agent spawning service
- CI/CD framework
- 범용 semantic validator
- 자동 update service

실제 runtime이 제공하지 않는 격리나 권한 강제를 Cairn이 제공한다고 가정해서는 안 됩니다.

---

## 프로젝트에 적용하기

대상 프로젝트 루트에 `AGENTS.md`와 `.harness/` 전체를 복사합니다.

기존 프로젝트에 이미 `AGENTS.md` 또는 다른 Harness 규칙이 있다면 그대로 덮어쓰지 말고 충돌을 검토해 병합합니다.

그 다음 프로젝트 목표와 주요 요구사항을 제공하면 됩니다.

예:

```text
이 프로젝트는 개인 독서 기록 서비스 Booklog다.
현재 프로젝트에 포함된 Cairn에 따라 bootstrap하고 진행하라.

주요 요구사항:
- ...
- ...
```

agent는 Cairn 계약에 따라 다음을 준비합니다.

1. repository와 기존 지침 확인
2. 이미 주어진 요구사항 구조화
3. 실제 unresolved decision만 식별
4. project-local 설정과 bootstrap Task Packet 준비
5. 목표·요구·핵심 사용자 흐름·초기 domain/data 개념을 정본화
6. 작은 Artifact Map과 bounded applicability check 준비
7. 최소 verification strategy 작성
8. 첫 implementation Task Packet 생성
9. 필요한 Human Gate에서만 중단

사용자가 Harness 운영 규칙을 prompt마다 다시 설명할 필요는 없습니다.

---

## Routine 작업과 High-risk 작업

### Routine 예시

이미 승인된 요구 안에서 책장 이름 수정 기능을 구현하는 작업이라면:

- 관련 requirement와 공통 의무만 좁게 회수
- 불필요한 전수 문서 로드 없음
- 추가 Human Gate 없음
- 필요한 범위만 검증
- producer와 다른 actor가 acceptance 수행

### High-risk 예시

로그인 또는 session authentication 방식을 바꾸는 작업이라면:

- authentication/security 및 관련 architecture 정본 회수
- 영향을 받는 ownership/session/persistence 의무 확인
- 계획과 Review Brief 구체화
- 실제 변경 전에 Human Gate
- 영향 범위에 맞춰 verification 확대
- 필요한 독립 판단과 비producer acceptance 수행

Cairn의 목적은 모든 작업을 무겁게 만드는 것이 아니라, **routine은 가볍게 유지하면서 위험한 변경에만 더 강한 계약을 적용하는 것**입니다.

---

## 설계 배경과 공개 Reference

Cairn은 “완전히 새로운 agent architecture”를 주장하지 않습니다. 여러 기존 아이디어와 가까운 engineering precedent를 참고하거나 사후 대조했고, 그 위에서 project-local lifecycle/authority/evidence 계약을 조합했습니다.

중요하게도 아래 자료들은 **Cairn의 성능이나 효과를 실험적으로 검증한 근거가 아닙니다.** “참고한 패턴”, “비교 대상”, “가까운 선례”를 구분해서 봐야 합니다.

### 초기 설계에서 참고한 자료

- **OpenAI — [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)**
  저장소 안의 짧은 진입점과 project-local knowledge를 통해 agent가 필요한 정본으로 이동하는 방식과 연결됩니다. Cairn의 progressive retrieval·로컬 운영 규칙과 가까운 참고점이지만, OpenAI의 개발 속도나 자동 review/merge 결과를 Cairn의 성능 주장으로 사용하지 않습니다.

- **Anthropic — [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)**
  필요한 정보를 그때그때 회수하고 context를 관리하는 접근과 Cairn의 minimal seed + progressive retrieval이 연결됩니다. 동시에 과도한 요약의 정보 손실과 탐색 실패 가능성도 고려합니다.

- **Aider — [Repository map](https://aider.chat/docs/repomap.html)**
  전체 파일 본문보다 먼저 구조와 symbol/signature를 보여주어 관련 코드를 고르는 아이디어를 task-local manifest와 비교했습니다. Aider의 ranking 알고리즘이나 token budget 자체를 Cairn이 채택한 것은 아닙니다.

- **Microsoft — [GraphRAG](https://microsoft.github.io/graphrag/)**
  관계 기반 탐색이라는 아이디어를 Artifact Graph와 비교했습니다. Cairn은 LLM이 임의 관계를 추론해 knowledge graph를 만드는 방식이 아니라 **정본의 명시 참조만 결정적으로 투영**합니다.

### Workflow / Graph / Agent orchestration 비교 자료

- **Anthropic — [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)**
  미리 정의한 workflow, 환경 피드백, 인간 checkpoint, 유한한 반복 구조와 Cairn의 Workflow Graph·Human Gate·Recovery를 비교했습니다.

- **Feng et al. — [Graph Engineering in the Era of LLM Agents: From Individual Intelligence to System Intelligence](https://arxiv.org/html/2608.21156v2)**
  task organization, agent coordination, runtime state management를 graph 관점에서 체계화한 survey입니다. Cairn은 이 taxonomy 전체의 구현이 아니라, 이 문제영역과 겹치는 project-local workflow/state contract를 가집니다.

- **LangGraph — [Overview](https://docs.langchain.com/oss/python/langgraph/overview), [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)**
  StateGraph, checkpoint, interrupt/resume를 제공하는 stateful orchestration runtime의 비교 대상입니다. Cairn은 runtime persistence나 automatic resume를 구현하지 않으며 선언형 계약만 제공합니다.

- **luxiaolei — [Graph Engineering](https://github.com/luxiaolei/graph-engineering)**
  project-local graph contract에 state, routing, guard, context, evaluation, governance를 함께 두는 가까운 engineering precedent입니다. Cairn은 YAML 기반 Core/Task Packet과 별도의 authority/evidence 의미를 사용합니다.

- **context4ai — [Agent Graph](https://github.com/context4ai/agent-graph)**
  현재 Facts와 Outcome을 바탕으로 다음 route, 필요한 resource, 완료 evidence를 제한하는 work-contract 접근의 비교 대상입니다. Cairn의 Task Packet/context routing과 일부 문제의식이 겹치지만 동일한 runtime/SDK 모델은 아닙니다.

### Evidence / provenance / 독립 판단 관련 자료

- **Anthropic — [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)**
  생성과 평가의 분리, 장기 세션에서의 context 관리 문제를 Cairn의 비producer acceptance와 bounded-context 독립 판단 정책과 비교했습니다. 해당 글의 topology나 성과 수치를 Cairn의 검증 근거로 사용하지 않습니다.

- **W3C — [PROV-DM: The PROV Data Model](https://www.w3.org/TR/2013/REC-prov-dm-20130430/)**
  entity, activity, revision을 구분하는 provenance 개념을 candidate/artifact/evidence의 identity와 비교했습니다. Cairn이 W3C PROV ontology를 구현하거나 준수한다고 주장하지 않습니다.

- **Edge et al. — [From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/html/2404.16130v2)**
  GraphRAG의 원 논문을 비교해, 문서 집합의 전역 질문/요약 성능을 Cairn의 Artifact Graph나 token 절감 효과로 잘못 전이하지 않도록 경계를 확인했습니다.

### Cairn 자체의 설계 선택

다음 항목은 위 자료에서 그대로 가져온 규칙이 아니라 Cairn이 project-local contract로 선택한 구체 의미입니다.

- `Role ∩ Node ∩ Scope` 권한 계산
- `VERIFIED ≠ ACCEPTED ≠ CLOSED`
- child acceptance와 parent acceptance의 분리
- 모든 candidate에 대한 비producer acceptance
- Human Gate의 구체 위험 범주
- 한 번에 하나의 사용자 결정 질문
- 다섯 파일 distribution snapshot
- 정본의 명시 참조에서만 도출하는 Artifact Graph 관계
- 조건부 Git closeout

관련 아이디어가 기존 문헌에 존재한다는 것과, 그 문헌이 위 정확한 계약을 도출하거나 검증했다는 것은 구분합니다.

---

## 현재 한계

`1.0.0-candidate.3`에서 확인된 범위는 **선언형 계약과 배포 경계의 정적 일관성**입니다.

아직 다음을 실증적으로 주장하지 않습니다.

- token 사용량 감소
- 작업 성공률 향상
- agent hallucination 감소
- 실제 runtime actor 격리의 강제
- 모든 프로젝트에서의 적합성
- graph 구조 자체의 독립적인 성능 향상

실제 프로젝트 적용에서 특히 확인해야 할 항목은 다음과 같습니다.

1. runtime에서 producer/acceptor 분리가 실제로 얼마나 안정적으로 유지되는가
2. Task Packet 유지 비용이 routine 작업에서 과도하지 않은가
3. progressive retrieval이 실제 context/token 부담을 줄이면서 누락을 만들지 않는가

---

## 기본 언어

현재 배포본은 사람이 읽는 설명, 계획, 보고, review note, handoff의 기본 언어로 **한국어**를 사용합니다.

식별자, 경로, API/CLI 문법, 고유 명칭, 원근거, 자동 도구 출력은 원래 표기를 유지합니다.

---

## 배포본 식별

`.harness/distribution.yaml`은 다음으로 exact distribution을 식별합니다.

- version
- distribution ID
- content ID
- 각 payload 파일의 SHA-256

프로젝트에 복사한 뒤 수정되는 `.harness/project.yaml` 값이나 실제 Task Packet은 immutable distribution identity의 일부가 아닙니다.

현재 공개본은 최종 `1.0.0`이 아니라 **`1.0.0-candidate.3`**입니다.

---

## 라이선스

Cairn은 **MIT License**로 배포됩니다. 자세한 내용은 [`LICENSE`](LICENSE)를 확인하세요.
