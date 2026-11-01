# 설계 노트

한국어 · [English](README.en.md)

Cairn이 어떤 실패에서 출발했고, 판본마다 무엇을 시험해 무엇을 바꾸거나 바꾸지 않았는지를 정리한 문서입니다. 현재 계약의 정본은 저장소 루트의 [`AGENTS.md`](../../AGENTS.md)와 [`.harness/core.yaml`](../../.harness/core.yaml)입니다. 이 노트는 그 계약의 **배경**이며, 규칙을 더하거나 바꾸지 않습니다.

| 문서 | 내용 |
|---|---|
| [1. 회고에서 메커니즘으로](01-origins.md) | 장기 agent 개발 프로젝트의 회고 사례 28건을 일곱 메커니즘으로 합친 과정, 가져오지 않은 것 |
| [2. 첫 적용과 candidate.4](02-candidates-1-4.md) | 독립 감사, Booklog 첫 적용에서 나온 관찰 15건, Coverage Matrix·대리 관찰 금지가 들어온 이유 |
| [3. 열여섯 번의 REJECT와 출하 범위 분리](03-candidate5-reviews.md) | Claude Code ↔ Codex 실제 conformance, 독립 검토 16회 REJECT의 원인 분석, 종료 조건 고정, release-scope 분리와 공개 |
| [4. 바꾸지 않은 것과 사람이 정한 것](04-decisions.md) | candidate.5의 설계 결정과 고르지 않은 선택지, Human Decision, 정정 기록 |

## 흐름

| 날짜(KST) | 사건 |
|---|---|
| 2026-09-21 | 회고 사례 R01~R28 정리, 일곱 메커니즘 제안. candidate.2 독립 감사 `CORRECTION_REQUIRED` → candidate.3 재감사 `READY_FOR_FIRST_APPLICATION`, 첫 공개 |
| 2026-09-28 | candidate.3을 Booklog에 적용한 뒤 관찰 BK-01~15 동결 |
| 2026-09-29 | candidate.4 공개(Coverage Matrix, 대리 관찰 금지, 구조화된 residual, `cairn_check` 0.2.1) |
| 2026-10-08 | candidate.5 판본 결정(HD-C5-01), 구현과 첫 동결, cross-runtime conformance 시작, 1차 독립 검토 REJECT |
| 2026-10-09 | 16차 독립 검토 REJECT, release-scope 분리(HD-C5-03), release-scope 독립 검토 PASS + ACCEPT |
| 2026-10-10 | candidate.5 공개(HD-C5-04) |

## 읽을 때 주의할 것

- 이 노트는 비공개 개발 저장소의 설계 기록·검토 원문·실행 원자료를 요약한 것입니다. 원자료와 비공개 프로젝트의 경로·commit은 옮기지 않았습니다. Booklog는 저자의 개인 프로젝트이며 공개 저장소가 아닙니다.
- 수치는 당시 기록의 값입니다. 이 노트를 쓰면서 다시 실행하거나 재계산하지 않았습니다. 근거의 성격(직접 확인·당시 보고·회고)이 다른 값은 본문에서 구분했습니다.
- 여기에 나오는 효과는 관찰된 범위의 기록입니다. token 절감, 작업 성공률 향상 같은 효과는 측정하지 않았습니다([README "현재 한계"](../../README.md#8-현재-한계)).
