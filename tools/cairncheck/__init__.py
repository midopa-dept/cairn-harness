"""Cairn companion validator(배포 5파일 밖의 별도 검사 도구).

report-only 결정적 검사 도구다. Packet·Coverage Matrix를 수정하지 않고 판정·전이를 만들지 않는다.
"""

TOOL_NAME = "cairn_check"
# 도구 판본은 contract 판본과 별개다. 0.1.0 = candidate.4와 함께 인수된 첫 판본(commit 0c14ee5),
# 0.2.0 = 공개 전 closeout(N-1 개행 동치, N-2 종료 코드, N-3 seed 의존 closure),
# 0.2.1 = seed 거짓 PASS 교정(R-1 선택 행 Stage B 직접 대조, R-2 선택 artifact scope 판본 불일치 재확인).
TOOL_VERSION = "0.2.1"
# 이 판본이 규칙을 구현한 대상 contract. 각 Packet은 여전히 자기 harness_snapshot 계약으로 해석한다.
TARGET_CONTRACT = {"version": "1.0.0-candidate.4", "contract_version": 2}
