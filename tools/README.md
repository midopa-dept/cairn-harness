# cairn_check — Cairn companion validator

`cairn_check`는 Cairn contract의 결정적 무결성 규칙(VS0~VS6)을 검사하는 **report-only companion 도구**입니다.

## 지위

- Cairn contract snapshot은 배포 5파일입니다: `AGENTS.md`, `.harness/core.yaml`, `.harness/project.yaml`, `.harness/task.example.yaml`, `.harness/distribution.yaml`. 이 도구는 그 5파일에 포함되지 않습니다. 따라서 도구의 판본과 contract `content_id`는 별개의 식별자입니다.
- 도구는 authority가 아닙니다. Packet·Coverage Matrix·정본 문서를 수정하지 않습니다. lifecycle 전이, decision, 인수를 만들지 않습니다.
- `PASS`는 선언된 contract의 결정적 무결성 검사를 통과했다는 뜻뿐입니다. 정확성도, 제품 인수(`ACCEPTED`)도, coverage의 의미적 충분성도 뜻하지 않습니다.
- 도구가 없어도 됩니다. `core.yaml` `validation_contract.companion`의 규칙과 순서를 사람이나 agent가 수동으로 수행할 수 있습니다. 그때는 method `manual`과 수행 범위를 기록합니다. 수동 열거는 결정적 열거를 주장하지 않습니다.

## 설치와 실행

Python 3.9 이상과 YAML 1.2 parser `ruamel.yaml`이 필요합니다.

```sh
python3 -m pip install -r tools/requirements-dev.txt
python3 tools/cairn_check.py --version
python3 tools/cairn_check.py --project . check
```

| 명령 | 하는 일 |
|---|---|
| `check [--phase plan\|close] [--packet PATH ...] [--json] [--diagnostic] [--since REV]` | VS0~VS6 검사. `--since`를 주면 그 Git revision의 matrix와 비교해 Stage A 변경을 보고합니다 |
| `skeleton --parent PATH --scope PATH` | scope 선언에서 disposition null 행으로 된 matrix 초안을 출력합니다. 처분은 채우지 않습니다 |
| `rows --matrix PATH --task ID` | child가 회수할 자기 행(`owner_task` 또는 `to`가 자기인 행)을 출력합니다 |
| `seed --parent PATH --matrix PATH --criterion TASK#CRITERION` | criterion이 소유한 행의 정본 전문을 현재 판본에서 조립합니다(저장하지 않음) |

공통 option은 다음과 같습니다.

- `--git-rev REV`: 작업 트리 대신 Git object를 `git show`로 읽습니다(read-only).
- `--contract CONTENT_ID=PATH`: 다른 `harness_snapshot`의 `core.yaml`을 추가로 제공합니다.

## 종료 코드

사람용 요약의 첫 줄 `판정: … (exit N)`과 JSON의 `verdict`는 종료 코드와 같은 값입니다.

| 코드 | 판정 | 뜻 |
|---|---|---|
| 0 | `PASS` | 평가 대상 전부가 결정적 검사를 통과했습니다. 정확성·인수가 아닙니다 |
| 1 | `FAIL` | 결정적 계약 결함이 하나 이상 있습니다. 미평가가 함께 있어도 `FAIL`입니다 |
| 2 | 호출 오류 | 인자 오류, Cairn 제어 파일(`.harness/core.yaml`·`project.yaml`·`distribution.yaml`)이 없는 `--project`, 해석되지 않는 `--git-rev`·`--since`, 읽지 못한 입력 파일, `ruamel.yaml` 없음 |
| 3 | `INCONCLUSIVE` | 결함은 없지만 미평가나 재확인 대상이 있습니다. 성공으로 취급하지 않습니다 |

`INCONCLUSIVE`가 되는 경우는 다음과 같습니다.

- 선행 단계 때문에 미평가된 단계가 있습니다. `--phase plan`에서 VS5를 평가하지 않는 것은 요청 범위이므로 여기에 들지 않습니다.
- 검사한 Task Packet이 하나도 없습니다(`no_packets`).
- VS4 drift 재확인(`suspect`·`ambiguous`·`missing`)이 있습니다.
- matrix scope 판본이 manifest 판본과 다릅니다(`scope_revision_differs`).
- 어떤 검사 대상 parent에도 결합되지 않은 matrix가 있습니다(`orphan_coverage_matrix`).
- 계약이 주어지지 않은 snapshot의 Packet이나 matrix가 있습니다(`snapshot_unknown`).
- `distribution.yaml`에 `core.yaml` 해시 기록이 없습니다(`contract_hash_unchecked`).
- `--diagnostic` 실행이라 완전성을 주장할 수 없습니다.

CI에서는 0만 성공으로 취급합니다. 3은 사람이 미평가 이유를 확인해야 한다는 뜻입니다.

task_root의 YAML 가운데 `kind: task`인데 문자열 id가 없거나 id가 겹치는 문서는 결함(1)입니다. `task`·`coverage_matrix`가 아닌 YAML(evidence 기록, 빈 파일, kind 오타 등)은 검사하지 않고 warning `unrecognized_yaml`로 목록만 보고합니다.

`skeleton`은 section 해석 실패나 유일하지 않은 excerpt가 있으면 3으로 끝납니다. 초안이 불완전하다는 뜻입니다.

## seed의 의존 closure

`seed`는 요청한 criterion에 실제로 필요한 자료에만 검사를 겁니다.

- 계약: `core.yaml`, `project.yaml`, `distribution.yaml` 해시 기록
- parent Packet과, parent의 `plan.coverage_matrix`가 manifest로 가리키는 matrix(인자로 준 matrix가 그것이 아니면 `matrix_not_bound`)
- criterion의 child Packet. parent의 선언된 child이고, manifest에 경로가 있고, 그 criterion을 현재 가져야 합니다
- 선택된 행의 source artifact와, 그 artifact의 matrix scope 전체. excerpt 유일성은 scope 전체 열거에서만 성립합니다

- 선택된 행 자체와, 그 행과 같은 구조 단위를 공유하는 행의 VS2·VS3 결함(`owner_task_not_child`, `duplicate_local_id`, `split_without_part` 등), 결합 matrix 전체의 결함, 선택 행 artifact의 scope 항목 결함. 선택된 행은 `disposition: owned`여야 합니다(`seed_row_not_owned`)
- 선택된 행의 owner_criterion 무결성(Stage B: `owner_criterion_dangling`, `stage_b_unrefined`). 전체 `check`는 VS2 결함이 하나라도 있으면 Stage B를 미평가로 둡니다. seed는 무관한 child의 해결 실패와 상관없이 선택된 행에 한해 Stage B를 직접 대조합니다
- 선택 행 artifact의 scope 판본과 parent manifest 판본의 일치(`scope_revision_differs`)

다른 child나 다른 행의 결함, 다른 artifact의 판본 불일치는 이 seed의 closure 밖입니다. 전체 `check`는 그것을 여전히 FAIL 또는 INCONCLUSIVE로 보고합니다.

판정은 다음과 같습니다.

- closure 안에 구문·schema·연결 결함이 있으면 `FAIL`(1)입니다. `rows`를 내지 않습니다.
- closure 안에 계약 미확보, drift, 선택 행 artifact의 `scope_revision_differs`가 있으면 `INCONCLUSIVE`(3)입니다. 전문은 보여 주지만 정상 seed를 주장하지 않습니다.
- criterion이 소유한 행이 하나도 없으면 빈 `rows`와 함께 `INCONCLUSIVE`(3)입니다. 소유 행이 없는 것이 맞는지는 사람이 판단합니다.
- closure 밖 Packet의 구문 오류는 이 seed를 막지 않습니다. 대신 `unrelated`에 반드시 보고합니다. closure 밖 Packet은 구문만 확인하며 schema·연결은 검사하지 않습니다. 전체 무결성은 `check`로 확인합니다.

## 개행과 인코딩

- `distribution.yaml`의 `core.yaml` 해시는 원시 바이트로 대조합니다. 파일이 없거나 UTF-8이 아니어도 원시 바이트 대조는 합니다.
- 원시 바이트가 다르면 LF·CRLF 표기만 다른지(CRLF→LF, 그 LF→CRLF) 봅니다. 동치이면 info `contract_line_endings_differ`를 남기고 통과합니다. LF와 CRLF가 섞인 파일도 CRLF→LF 정규형이 같으면 동치입니다.
- 끝 개행 차이, BOM, 단독 CR(`\r\r\n` 포함), 그 밖의 바이트 차이는 정규화하지 않습니다. 이런 차이는 `contract_hash_mismatch`입니다.
- 이 대조 규칙은 배포본 `content_id` 계산을 바꾸지 않습니다.
- Markdown source artifact는 줄 단위로 열거하므로 LF와 CRLF 원문이 같은 단위·fingerprint를 냅니다. 실제 문구 변경은 여전히 `suspect`입니다.
- UTF-8이 아닌 artifact는 정규화하거나 열거하지 않습니다. 해결 실패로 보고합니다.

## 알려진 한계

- heading은 ATX(`#`)만 인식합니다. setext heading은 문단으로 취급합니다.
- table은 `|`로 시작하는 GFM table만 인식합니다.
- blockquote 안의 list·code는 문단 텍스트로 취급합니다.
- scope 선언의 충분성, 분할 적정성, informative 판정, criterion의 의무 함의, 관찰 충분성, 인간 승인의 진정성은 검사하지 않습니다. 이 목록은 모든 보고의 `not_checked`에 들어 있습니다.
- (관찰 R-3) task_root에서 `kind`가 `task`·`coverage_matrix`가 아닌 YAML(kind 오타, 빈 파일 포함)은 warning `unrecognized_yaml`만 남기고 판정에 영향을 주지 않습니다. 그런 파일만 있으면 `PASS`일 수 있습니다. evidence 기록 같은 비 Packet YAML과 구분할 기준이 contract에 아직 없기 때문입니다. task_root 허용 kind는 다음 contract 개정에서 정합니다. 그 전에는 요약의 warning을 직접 확인하십시오.

## 판본

`cairn_check --version`은 도구 판본과 대상 contract를 함께 출력합니다. 현재 도구 판본은 0.2.1이고, 대상 contract는 `1.0.0-candidate.4`, `contract_version` 2입니다. 각 Packet은 여전히 자기 `harness_snapshot`의 계약으로 해석하며, 새 계약을 소급 적용하지 않습니다.

도구 판본은 contract `content_id`의 일부가 아닙니다. 도구를 고쳐도 contract 판본과 `content_id`는 바뀌지 않습니다.

| 판본 | 변경 |
|---|---|
| 0.2.0 | 개행 동치 대조, 판정·종료 코드 일치, seed 의존 closure |
| 0.2.1 | seed 거짓 PASS 교정. 무관한 child 결함이 있어도 선택 행의 owner_criterion 결함을 FAIL로 보고합니다(R-1). 선택 행 artifact의 scope 판본 불일치를 INCONCLUSIVE로 보고합니다(R-2) |
