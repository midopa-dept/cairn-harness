"""authoring 보조: skeleton 생성, child 행 projection, reviewer seed 조립.

도구가 결정적으로 만드는 것은 단위·provisional local_id·excerpt·fingerprint·hint뿐이다.
disposition·owner_task·owner_criterion·연기/제외 근거는 사람이나 agent가 선언한다.
"""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from . import mdunits
from .project import Project


def _artifact_text(project: Project, manifest: dict[str, dict], artifact: str) -> str | None:
    entry = manifest.get(artifact) or {}
    path = entry.get("path")
    return project.source.read(path) if isinstance(path, str) else None


def enumerate_scope(project: Project, manifest: dict[str, dict], scope: list[dict]) -> tuple[list[mdunits.Unit], list[str]]:
    units: list[mdunits.Unit] = []
    errors: list[str] = []
    for item in scope:
        artifact = item.get("artifact")
        if artifact is None:
            continue
        text = _artifact_text(project, manifest, artifact)
        if text is None:
            errors.append(f"{artifact}: 원문을 읽지 못했다")
            continue
        found, problems = mdunits.enumerate_sections(artifact, text, item.get("sections") or [])
        errors.extend(f"{artifact}: {p}" for p in problems)
        known = {(u.artifact, u.line) for u in units}
        units.extend(u for u in found if (u.artifact, u.line) not in known)
    return units, errors


def skeleton(project: Project, parent: dict, scope: list[dict]) -> tuple[dict, list[str]]:
    """disposition null 행으로 된 matrix 초안. 처분은 채우지 않는다."""
    manifest = {a["id"]: a for a in parent.get("artifacts") or [] if isinstance(a, dict) and "id" in a}
    units, errors = enumerate_scope(project, manifest, scope)
    rows: list[dict[str, Any]] = []
    by_artifact: dict[str, list[mdunits.Unit]] = {}
    for unit in units:
        by_artifact.setdefault(unit.artifact, []).append(unit)
    for artifact, group in by_artifact.items():
        universe = [u.norm for u in group]
        slug = re.sub(r"[^A-Za-z0-9]+", "-", artifact).strip("-").upper() or "DOC"
        for index, unit in enumerate(group, start=1):
            excerpt = mdunits.excerpt_for(unit.norm, universe)
            if sum(1 for other in universe if other.startswith(excerpt)) > 1:
                errors.append(f"{artifact}: 유일한 excerpt를 만들 수 없는 단위(hint 필요): {unit.hint}")
            rows.append({
                "local_id": f"OB-{slug}-{index:03d}",
                "source": {"artifact": artifact, "excerpt": excerpt, "fingerprint": unit.fp, "hint": unit.hint},
                "disposition": None,
            })
    matrix = {"kind": "coverage_matrix", "schema_version": 1, "task": parent.get("id"),
              "scope": scope, "obligations": rows}
    return matrix, errors


def project_rows(matrix: dict, task: str) -> list[dict]:
    """child가 회수할 자기 행: owner_task 또는 to가 자기인 행."""
    selected = []
    for row in matrix.get("obligations") or []:
        if not isinstance(row, dict):
            continue
        target = str(row.get("to") or "").split("#", 1)[0]
        if task in (row.get("owner_task") or []) or target == task:
            selected.append(row)
    return selected


# 결합 matrix 전체의 무결성 결함(행과 무관): seed가 기대는 matrix 자체가 깨졌다는 뜻이다.
MATRIX_LEVEL_CODES = {"matrix_task_mismatch", "matrix_unresolved", "matrix_revision_current", "coverage_matrix_missing",
                      "scope_null_with_sections"}


def _seed_status(problems: list[dict]) -> str:
    if any(p["severity"] == "defect" for p in problems):
        return "FAIL"
    return "INCONCLUSIVE" if any(p["severity"] == "unevaluated" for p in problems) else "PASS"


def assemble_seed(project: Project, parent_path: str, matrix_path: str, criterion: str) -> dict:
    """criterion(<task ID>#<criterion ID>)이 소유한 행의 정본 전문을 현재 판본에서 조립한다(저장하지 않음).

    검사와 조립은 이 seed의 의존 closure에만 건다(N-3): 계약(core.yaml·project.yaml·distribution 기록),
    parent Packet, parent가 참조하는 matrix, criterion의 child Packet, 선택된 행의 source artifact 전체 scope.
    closure 밖 Packet의 구문 오류는 조립을 막지 않지만 `unrelated`로 반드시 보고한다.
    closure 안에 결정적 결함이 있으면 FAIL이고 행을 내지 않는다. 결함은 없지만 미평가·drift가 있으면
    INCONCLUSIVE이며 정상 seed를 주장하지 않는다.
    """
    from .pipeline import EXIT_CODES, PASS_MEANING, Options, Run  # 순환 import 회피

    problems: list[dict] = []
    closure: list[str] = [".harness/core.yaml", ".harness/project.yaml", ".harness/distribution.yaml", parent_path, matrix_path]

    def problem(severity: str, code: str, where: str, message: str) -> None:
        problems.append({"severity": severity, "code": code, "where": where, "message": message})

    def result(rows: list[dict] | None) -> dict:
        status = _seed_status(problems)
        unrelated = []
        for path in project.source.list(project.task_root):
            if path in closure or not path.endswith((".yaml", ".yml")):
                continue
            doc = project.load(path)
            if doc.error:
                unrelated.append({"severity": "warning", "code": "unrelated_malformed", "where": path,
                                  "message": f"seed closure 밖 Packet의 구문 오류(이 seed를 막지 않음): {doc.error}"})
        return {"status": status, "exit_code": EXIT_CODES[status], "criterion": criterion,
                "closure": closure, "rows": rows if status != "FAIL" else None,
                "problems": problems, "unrelated": unrelated,
                "note": ("closure 밖 Packet은 구문만 확인했고 schema·연결은 검사하지 않았다. "
                         "seed는 reviewer 입력 조립이며 판정·인수가 아니다."),
                "pass_meaning": PASS_MEANING}

    task, _, cid = criterion.partition("#")
    if not task or not cid:
        problem("defect", "criterion_format", criterion, "criterion은 <task ID>#<criterion ID>여야 한다")
        return result(None)
    parent_doc, matrix_doc = project.load(parent_path), project.load(matrix_path)
    for doc in (parent_doc, matrix_doc):
        if doc.error or not isinstance(doc.data, dict):
            problem("defect", "seed_dependency_malformed", doc.path, f"closure 문서를 읽거나 해석하지 못했다: {doc.error}")
    if problems:
        return result(None)
    parent, matrix = parent_doc.data, matrix_doc.data
    manifest = {a["id"]: a for a in parent.get("artifacts") or [] if isinstance(a, dict) and "id" in a}
    ref = (parent.get("plan") or {}).get("coverage_matrix") if isinstance(parent.get("plan"), dict) else None
    if (manifest.get(ref) or {}).get("path") != matrix_path:
        problem("defect", "matrix_not_bound", matrix_path, f"parent plan.coverage_matrix({ref!r})의 manifest 경로가 이 matrix가 아니다")
    if matrix.get("task") != parent.get("id"):
        problem("defect", "matrix_task_mismatch", matrix_path, f"matrix task {matrix.get('task')!r} ≠ parent {parent.get('id')!r}")
    children = (parent.get("scope") or {}).get("children") or [] if isinstance(parent.get("scope"), dict) else []
    entry = manifest.get(task) or {}
    child_path = entry.get("path") if entry.get("kind") == "task" and isinstance(entry.get("path"), str) else None
    if task not in children:
        problem("defect", "criterion_task_not_child", criterion, f"{task}가 parent의 선언된 child가 아니다")
    if child_path is None:
        problem("defect", "child_unresolved", criterion, f"{task}가 경로 있는 manifest task artifact로 해결되지 않는다")
    else:
        closure.append(child_path)
        child_doc = project.load(child_path)
        if child_doc.error or not isinstance(child_doc.data, dict):
            problem("defect", "seed_dependency_malformed", child_path, f"child Packet을 읽거나 해석하지 못했다: {child_doc.error}")
        elif cid not in {c.get("id") for c in child_doc.data.get("criteria") or [] if isinstance(c, dict)}:
            problem("defect", "criterion_unresolved", criterion, f"{cid}가 child {task}의 현재 criterion이 아니다")
    selected = [r for r in matrix.get("obligations") or [] if isinstance(r, dict) and criterion in (r.get("owner_criterion") or [])]
    selected_ids = {str(r.get("local_id")) for r in selected}
    scope = [i for i in matrix.get("scope") or [] if isinstance(i, dict)]
    needed = {(r.get("source") or {}).get("artifact") for r in selected}
    scope_wheres = {f"{matrix_path}/scope/{a}" for a in needed}
    # 계약·schema(VS0·VS1)는 closure Packet에만, 행 결함(VS2·VS3)은 선택된 행·그 행과 단위를 공유하는 행·
    # 결합 matrix 자체·선택 행 artifact의 scope 항목에만 건다(V-2). 다른 child·다른 행의 결함은 이 seed 밖이다.
    run = Run(project, Options(phase="plan", packets=[parent_path] + ([child_path] if child_path else [])))
    report = run.execute()
    findings = report["findings"]
    bound = run.parents.get(parent.get("id"))
    if bound is not None and run.failed("VS2") and run.status.get("VS3") != "not_evaluated":
        # R-1: Run은 VS2 결함이 하나라도 있으면 Stage B 전체를 생략한다. 무관한 child의 해결 실패가
        # 선택 행의 owner_criterion 무결성 검사까지 끄지 않도록, 선택 행에 한해 Stage B를 직접 수행한다.
        start = len(run.findings)
        run._stage_b(bound, selected)
        findings = findings + [asdict(f) for f in run.findings[start:]]
    for finding in findings:
        if finding["severity"] != "defect":
            if finding["code"] in ("snapshot_unknown", "contract_hash_unchecked") and finding["where"] in closure:
                problem("unevaluated", finding["code"], finding["where"], finding["message"])
            elif finding["code"] == "scope_revision_differs" and finding["where"] in scope_wheres:
                # R-2: 선택 행 artifact의 scope 판본이 manifest 판본과 다르면 전체 check와 같이 재확인 대상이다.
                problem("unevaluated", finding["code"], finding["where"], finding["message"])
            continue
        if finding["stage"] in ("VS0", "VS1"):
            if finding["parent"] in (None, parent.get("id")) or any(finding["where"].startswith(c) for c in closure):
                problem("defect", finding["code"], finding["where"], finding["message"])
        elif finding["stage"] in ("VS2", "VS3") and finding["parent"] == parent.get("id"):
            rows_hit = set(str(finding["row"]).split(",")) if finding["row"] else set()
            if (rows_hit & selected_ids or finding["code"] in MATRIX_LEVEL_CODES
                    or finding["where"] in scope_wheres):
                problem("defect", finding["code"], finding["where"], finding["message"])
    for row in selected:
        if row.get("disposition") != "owned":
            problem("defect", "seed_row_not_owned", f"{matrix_path}#{row.get('local_id')}",
                    f"owner_criterion이 있는 행의 disposition이 owned가 아니다({row.get('disposition')!r})")
    if any(p["severity"] == "defect" for p in problems):
        return result(None)

    units_by_artifact: dict[str, list[mdunits.Unit]] = {}
    for artifact in sorted(needed, key=str):
        items = [i for i in scope if i.get("artifact") == artifact]
        path = (manifest.get(artifact) or {}).get("path")
        if not items:
            problem("defect", "row_artifact_out_of_scope", str(artifact), "선택된 행의 artifact가 matrix scope에 없다")
            continue
        if isinstance(path, str):
            closure.append(path)
        text = project.source.read(path) if isinstance(path, str) else None
        if text is None:
            reason = "UTF-8 text가 아니다" if path in project.source.undecodable else "읽을 수 없다"
            problem("defect", "seed_artifact_unresolved", str(artifact), f"source artifact를 해결하지 못했다({reason})")
            continue
        # 같은 artifact의 scope 전체를 열거해야 excerpt 유일성이 성립한다.
        units, errors = mdunits.enumerate_sections(artifact, text, [s for i in items for s in i.get("sections") or []])
        for error in errors:
            problem("defect", "section_unresolved", str(artifact), error)
        units_by_artifact[artifact] = units
    if any(p["severity"] == "defect" for p in problems):
        return result(None)

    rows = []
    for row in selected:
        rid, source = row.get("local_id"), row.get("source") or {}
        if task not in (row.get("owner_task") or []):
            problem("defect", "owner_criterion_task_mismatch", str(rid), f"{criterion}의 Task가 owner_task에 없다")
        found = mdunits.locate(str(source.get("excerpt", "")), units_by_artifact.get(source.get("artifact"), []), source.get("hint"))
        status = "ok" if len(found) == 1 and found[0].fp == source.get("fingerprint") else (
            "suspect" if len(found) == 1 else ("ambiguous" if found else "missing"))
        if status != "ok":
            problem("unevaluated", f"drift_{status}", str(rid), "정본 전문이 기록 fingerprint와 결합되지 않아 seed가 불완전하다")
        rows.append({"local_id": rid, "artifact": source.get("artifact"), "part": source.get("part"),
                     "drift": status, "text": found[0].raw if len(found) == 1 else None})
    if not selected:
        # 빈 reviewer 입력은 정상 seed로 주장하지 않는다(V-8). 소유 행이 없는 것이 맞는지는 사람이 판단한다.
        problem("unevaluated", "criterion_owns_no_rows", criterion, "이 criterion이 소유한 matrix 행이 없어 조립할 정본 전문이 없다")
    return result(rows)
