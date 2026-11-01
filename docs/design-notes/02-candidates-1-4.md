# 2. 첫 적용과 candidate.4

[설계 노트 목차](README.md) · 이전: [1. 회고에서 메커니즘으로](01-origins.md) · 다음: [3. 열여섯 번의 REJECT](03-candidate5-reviews.md)

일곱 메커니즘을 배포 파일 다섯 개로 옮긴 뒤, 독립 감사를 거쳐 실제 프로젝트에 한 번 적용했습니다. 적용에서 나온 관찰이 candidate.4의 범위를 정했습니다.

## 2.1 candidate.1~3: 배포 경계와 감사

- **배포 경계.** 수정은 개발 저장소의 원본에서 하고, 복사용 배포본은 export 도구로 생성했습니다. 추출 문서와 설계 문서는 배포본에 넣지 않았습니다. 배포본에는 원 프로젝트의 경로나 commit을 남기지 않았습니다.
- **candidate.2 독립 감사(2026-09-21): `CORRECTION_REQUIRED`.** blocker 0, correction 1, observation 3. correction은 "Artifact Map에 연결되지 않은 공통 요구도 대조하라"는 탐색 지침이 없다는 것이었습니다. graph에 edge가 없다는 사실이 관련 요구가 없다는 뜻이 아니라는 문장이 이때 들어갔습니다(현재 `AGENTS.md`의 applicability check).
- **candidate.3 한정 재감사(같은 날): `READY_FOR_FIRST_APPLICATION`.** 해당 correction과 한정된 회귀 항목만 다시 보고 해소를 확인했습니다. 이 판정은 "첫 실제 적용을 시작해도 된다"는 뜻이었고, 공개 `1.0.0` 인수가 아니었습니다. candidate.3이 이 저장소에 처음 공개된 판본입니다.

## 2.2 Booklog 첫 적용에서 나온 관찰

candidate.3을 개인 독서 기록 서비스 Booklog에 그대로 적용해 여러 기능을 끝까지 진행했습니다. 그 뒤 Packet과 기록에서 관찰 15건(BK-01~15)을 고정했습니다. Cairn을 고치기 전에 관찰부터 동결한 이유는, 고친 뒤의 기억으로 원래 일어난 일을 다시 쓰지 않기 위해서였습니다.

| 관찰 | 내용 | 이후 처리 |
|---|---|---|
| BK-01·02 | 작업을 child Task로 나눌 때 정본 요구 일부가 어느 child에도 배정되지 않았습니다(orphaning). 통합 단계에서도 드러나지 않았습니다 | candidate.4 **Coverage Matrix** |
| BK-03 | 1차 경로가 아니라 대체(degraded) 경로만 관찰하고 PASS했습니다 | candidate.4 **대리 관찰 금지** |
| BK-05 | 실제 browser·gesture 요구를 CSS computed style 같은 구조 검사로 확인했습니다 | 대리 관찰 금지 |
| BK-06 | 구조·접근성 검사 PASS를 시각 품질 PASS처럼 썼습니다 | 대리 관찰 금지, 지각 판정은 사람 관찰 또는 명시 잔여 위험 |
| BK-07 | light 모드만 요구된 화면을 실제 mobile·dark 환경에서 보지 않았습니다 | 대리 관찰 금지 |
| BK-10 | 컬렉션 이름 변경에서 Human Gate가 적절히 걸렸습니다 | 긍정 사례. 변경 없음 |
| BK-12 | 미룬 잔여 위험에 소유자가 없었습니다 | candidate.4 **구조화된 residual**(`risk`·`owner`·`condition`) |
| BK-13 | Packet schema가 작업마다 조금씩 달라졌습니다 | companion validator `cairn_check` |
| BK-14 | 인수 뒤에도 교정이 반복됐습니다. 독립 검토는 명시된 criterion 안의 결함만 잡았고, criterion 자체가 빠진 것은 잡지 못했습니다 | Coverage Matrix로 일부. 독립 검토의 한계로 기록 |

BK-04는 뒤의 producer Task가, 앞서 인수된 consumer Task가 이미 쓰던 값의 의미를 바꾼 Task 간 의미 의존입니다. schema 후보로 올렸지만 사례가 하나뿐이고 명시 연결 없이 탐지할 방법이 없어 채택하지 않았습니다. BK-08(기능 폭과 latency)은 criteria 작성 규칙, BK-09(재시도 종료)는 제품 층의 문제로 분류해 Core에 넣지 않았습니다.

## 2.3 넣지 않기로 한 연구

candidate.4를 정하기 전에 범위를 넓힐 수 있는 두 방향을 따로 조사했고, 둘 다 Core에 넣지 않았습니다.

- **Artifact / Provenance Graph 재평가: `KEEP_MINIMAL_GRAPH`.** 관계를 더 풍부하게 그리면 탐색은 나아질 수 있지만, graph가 두 번째 정본이 되고 edge가 검증처럼 읽히는 위험이 컸습니다. relation 네 개짜리 탐색 단서로 유지하고, provenance는 Packet의 typed field에 두었습니다.
- **Judgment-aware 자율성 연구(외부 판단 점수 도구 Jev 연동 포함): `EXPERIMENT ONLY`.** 모델의 판단 신호로 사람 승인 여부를 조절하는 방식은 Core·배포본 밖의 별도 실험으로만 남겼습니다. 모델 confidence로 gate를 낮추지 않는다는 현재 계약 문장은 이 결론에서 왔습니다.

## 2.4 candidate.4: 독립 검토에서 한 번 REJECT

candidate.4(2026-09-29)는 Coverage Matrix, 대리 관찰 금지 다섯 규칙, 구조화된 residual, `record` decision, 소급 금지를 더했고, companion validator를 처음 함께 냈습니다.

첫 독립 nonproducer 검토는 **REJECT**였습니다. major finding 한 건이 validator에 있었고, 계약 bytes와 content_id는 바꿀 필요가 없었습니다. validator만 교정한 뒤 재검토에서 계약이 인수됐습니다. 재검토가 넘긴 validator 잔여 항목은 0.2.0에서 고쳤습니다. 0.2.0의 첫 독립 검토도 REJECT였고, 교정 뒤 인수됐습니다. 그 재검토에서 나온 항목은 0.2.1에서 고쳐 다시 독립 검토를 받았습니다. 공개한 것은 0.2.1입니다. 계약과 검사 도구의 판본을 따로 두는 지금의 구조(content_id에 validator가 들어가지 않음)가 여기서 굳었습니다.

이 시점의 실제 적용은 한 프로젝트였습니다. 관찰 15건은 그 한 프로젝트의 근거이며, 다른 종류의 프로젝트에서 같은 빈도로 나타난다는 뜻이 아닙니다.
