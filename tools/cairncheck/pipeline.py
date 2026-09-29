"""VS0~VS6 report-only 검사 pipeline(core.yaml validation_contract.companion)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from . import TARGET_CONTRACT, TOOL_NAME, TOOL_VERSION, mdunits, schema, yamlio
from .project import Project, contract_version, text_digests

STAGES = ["VS0", "VS1", "VS2", "VS3", "VS4", "VS5", "VS6"]
STAGE_NAMES = {
    "VS0": "syntax",
    "VS1": "schema_vocabulary",
    "VS2": "packet_artifact_child_links",
    "VS3": "coverage_matrix_integrity",
    "VS4": "source_drift",
    "VS5": "acceptance_deferral_residual_ownership",
    "VS6": "optional_advisory",
}
PASS_MEANING = (
    "통과는 선언된 contract의 결정적 무결성 검사 통과만 뜻한다. 정확성·제품 인수·시각 품질·"
    "coverage의 의미적 충분성을 뜻하지 않으며 acceptance decision을 만들지 않는다."
)
NOT_CHECKED = [
    "scope 선언의 충분성",
    "분할 적정성",
    "informative 판정의 타당성",
    "criterion이 정본 의무를 실제로 함의하는가",
    "관찰 방식의 충분성",
    "인간 승인의 진정성",
    "YAML 구문의 parser 간 이식성(휴리스틱 미구현)",
    *[f"Markdown 열거 한계: {item}" for item in mdunits.LIMITATIONS],
]
ACCEPTED_STATES = {"ACCEPTED", "CLOSED"}
BLOCKING = {"defect", "recheck"}
# 판정과 CLI 종료 코드(N-2). 2는 argparse와 같은 호출·입력 오류다.
EXIT_CODES = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 3}
EXIT_USAGE = 2
# 검사 대상 일부가 평가되지 않았음을 뜻하는 info finding
UNEVALUATED_CODES = {"snapshot_unknown", "contract_hash_unchecked", "no_packets", "orphan_coverage_matrix",
                     "scope_revision_differs"}
VERDICT_MEANING = {
    "PASS": "평가 대상 전부가 결정적 검사를 통과했다(PASS 의미 참조)",
    "FAIL": "결정적 계약 결함이 하나 이상 있다(미평가가 함께 있어도 FAIL)",
    "INCONCLUSIVE": "결함은 없지만 미평가·재확인 대상이 있어 통과를 주장하지 않는다",
}


@dataclass
class Finding:
    stage: str
    severity: str  # defect | recheck | warning | info
    code: str
    where: str
    message: str
    parent: str | None = None
    row: str | None = None


@dataclass
class Options:
    phase: str = "close"  # plan | close
    diagnostic: bool = False  # 선행 단계 실패 뒤에도 진단으로 계속(완전성 주장 불가)
    packets: list[str] | None = None  # 검사할 Packet 경로(없으면 task_root 전체)
    attach: dict[str, tuple[str, dict]] = field(default_factory=dict)  # 과거 기록 진단: parent → (matrix 경로, 계약)
    legacy_as_v4: bool = False  # 과거 기록 진단: 이전 계약 Packet에도 candidate.4 소유권 규칙을 진단 적용
    stage_a_baseline: dict[str, Any] | None = None  # parent → 이전 판본 matrix 데이터


@dataclass
class Parent:
    id: str
    path: str
    data: dict
    contract: dict | None
    manifest: dict[str, dict] = field(default_factory=dict)
    children: dict[str, dict | None] = field(default_factory=dict)
    matrix_path: str | None = None
    matrix: dict | None = None
    matrix_contract: dict | None = None
    units: dict[str, list[mdunits.Unit]] = field(default_factory=dict)
    row_status: dict[str, str] = field(default_factory=dict)
    pointer_failures: int = 0


class Run:
    def __init__(self, project: Project, options: Options | None = None):
        self.project = project
        self.options = options or Options()
        self.findings: list[Finding] = []
        self.status: dict[str, str] = {}
        self.reasons: dict[str, str] = {}
        self.packets: dict[str, dict] = {}  # id → {path, data, contract}
        self.parents: dict[str, Parent] = {}
        self.inventory: dict[str, Any] = {"record_subkinds": {}, "non_task_yaml": 0}

    # ------------------------------------------------------------------ util
    def add(self, stage: str, severity: str, code: str, where: str, message: str,
            parent: str | None = None, row: str | None = None) -> None:
        self.findings.append(Finding(stage, severity, code, where, message, parent, row))

    def failed(self, stage: str) -> bool:
        return any(f.stage == stage and f.severity == "defect" for f in self.findings)

    def gate(self, stage: str, blocked_by: str | None, reason: str) -> bool:
        """앞 단계 실패 시 미평가. diagnostic이면 진단으로 계속한다."""
        if blocked_by and (self.failed(blocked_by) or self.status.get(blocked_by) == "not_evaluated"):
            if self.options.diagnostic:
                self.reasons[stage] = f"진단 실행: {reason} (완전성 주장 불가)"
                return True
            self.status[stage] = "not_evaluated"
            self.reasons[stage] = reason
            return False
        return True

    def packet_contract(self, data: dict) -> dict | None:
        return self.project.contracts.get(data.get("harness_snapshot"))

    # ------------------------------------------------------------------ VS0
    def vs0(self) -> None:
        for core in (".harness/project.yaml", ".harness/core.yaml"):
            doc = self.project.load(core)
            if doc.error and doc.text is not None:
                self.add("VS0", "defect", "yaml_parse", core, doc.error)
        paths = self.options.packets
        if paths is None:
            paths = [p for p in self.project.source.list(self.project.task_root)
                     if p.endswith((".yaml", ".yml"))]
        matrices: list[str] = []
        for path in paths:
            doc = self.project.load(path)
            if doc.text is None:
                self.add("VS0", "defect", "file_missing", path, f"파일을 읽지 못했다({doc.error})")
                continue
            if doc.error:
                self.add("VS0", "defect", "yaml_parse", path, doc.error)
                continue
            kind = doc.data.get("kind") if isinstance(doc.data, dict) else None
            if kind == "task" and isinstance(doc.data.get("id"), str) and doc.data["id"]:
                if doc.data["id"] in self.packets:
                    self.add("VS0", "defect", "task_id_duplicate", path,
                             f"id {doc.data['id']!r}가 {self.packets[doc.data['id']]['path']}와 겹친다")
                    continue
                self.packets[doc.data["id"]] = {"path": path, "data": doc.data, "contract": self.packet_contract(doc.data)}
            elif kind == "task":
                self.add("VS0", "defect", "task_id_invalid", path, "kind task인데 문자열 id가 없어 Packet으로 식별할 수 없다")
            elif kind == "coverage_matrix":
                matrices.append(path)
            else:
                self.inventory["non_task_yaml"] += 1
                self.add("VS0", "warning", "unrecognized_yaml", path,
                         f"task·coverage_matrix가 아닌 YAML(kind {kind!r})이라 검사하지 않았다")
        # 분해 parent와 matrix 위치(연결 판정은 VS2)
        for pid, packet in self.packets.items():
            data = packet["data"]
            children = (data.get("scope") or {}).get("children") if isinstance(data.get("scope"), dict) else None
            plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
            if not (children or plan.get("coverage_matrix") or pid in self.options.attach):
                continue
            if packet["contract"] is None and pid not in self.options.attach:
                continue  # 다른 snapshot: VS1에서 미평가로 보고하고 새 계약을 소급하지 않는다
            parent = Parent(pid, packet["path"], data, packet["contract"])
            parent.manifest = {a["id"]: a for a in data.get("artifacts") or []
                               if isinstance(a, dict) and isinstance(a.get("id"), str)}
            self.parents[pid] = parent
        for pid, parent in self.parents.items():
            if pid in self.options.attach:
                path, contract = self.options.attach[pid]
                parent.matrix_path, parent.matrix_contract = path, contract
            else:
                ref = (parent.data.get("plan") or {}).get("coverage_matrix")
                entry = parent.manifest.get(ref) if isinstance(ref, str) else None
                if entry and isinstance(entry.get("path"), str):
                    parent.matrix_path = entry["path"]
                parent.matrix_contract = parent.contract
            if parent.matrix_path:
                doc = self.project.load(parent.matrix_path)
                if doc.text is None:
                    continue  # VS2에서 보고
                if doc.error:
                    self.add("VS0", "defect", "yaml_parse", parent.matrix_path, doc.error, pid)
                else:
                    parent.matrix = doc.data
        bound = {p.matrix_path for p in self.parents.values()}
        for path in matrices:
            task = self.project.load(path).data.get("task")
            if path not in bound and not (task in self.packets and self.packets[task]["contract"] is None):
                self.add("VS0", "info", "orphan_coverage_matrix", path,
                         f"어떤 검사 대상 parent에도 결합되지 않은 matrix(task {task!r})라 검사하지 않았다")
        if not self.packets:
            self.add("VS0", "info", "no_packets", self.project.task_root,
                     "task_root에서 검사할 Task Packet을 찾지 못했다(평가 대상 없음)")
        self.status["VS0"] = "fail" if self.failed("VS0") else "pass"

    # ------------------------------------------------------------------ VS1
    def vs1(self) -> None:
        if not self.gate("VS1", "VS0", "VS0 실패로 schema 검사 미평가"):
            return
        core = self.project.load(".harness/core.yaml")
        distribution = self.project.load(".harness/distribution.yaml")
        files = distribution.data.get("files") if isinstance(distribution.data, dict) else None
        core_bytes = self.project.source.read_bytes(".harness/core.yaml")
        if isinstance(files, dict) and ".harness/core.yaml" in files:
            # 원시 바이트로 대조하고, 다르면 LF·CRLF 개행 표기만 다른 동치인지 본다(N-1).
            recorded = files[".harness/core.yaml"]
            digests = text_digests(core_bytes) if core_bytes is not None else {}
            if core_bytes is None:
                self.add("VS1", "defect", "contract_hash_mismatch", ".harness/core.yaml",
                         "distribution.yaml에 해시가 기록된 core.yaml이 없다")
            elif recorded != digests["raw"]:
                if recorded in (digests.get("lf"), digests.get("crlf")):
                    self.add("VS1", "info", "contract_line_endings_differ", ".harness/core.yaml",
                             "core.yaml은 distribution.yaml 기록과 개행 표기(LF/CRLF)만 다르다(동치로 대조)")
                else:
                    self.add("VS1", "defect", "contract_hash_mismatch", ".harness/core.yaml",
                             "core.yaml 해시가 distribution.yaml 기록과 다르다(개행 동치로도 불일치, snapshot 불일치)")
        elif core_bytes is not None:
            self.add("VS1", "info", "contract_hash_unchecked", ".harness/distribution.yaml",
                     "distribution.yaml에 core.yaml 파일 해시가 없어 대조하지 못했다")
        for pid, packet in self.packets.items():
            data, path, contract = packet["data"], packet["path"], packet["contract"]
            if contract is None:
                self.add("VS1", "info", "snapshot_unknown", path,
                         f"harness_snapshot {data.get('harness_snapshot')!r}의 계약이 주어지지 않아 미평가")
                continue
            for error in schema.validate_definition(contract, "task", data):
                code = "schema"
                if error.path.startswith("/criteria/") and error.code == "additionalProperties":
                    code = "criteria_extra_key"
                elif error.path.startswith("/decisions/"):
                    code = "decision_vocabulary"
                self.add("VS1", "defect", code, f"{path}{error.path}", error.message, pid)
            for artifact in data.get("artifacts") or []:
                if isinstance(artifact, dict) and artifact.get("revision") == "current":
                    self.add("VS1", "warning", "weak_revision", f"{path}/artifacts/{artifact.get('id')}",
                             "revision current는 판본을 식별하지 않는다", pid)
            for decision in data.get("decisions") or []:
                if isinstance(decision, dict) and decision.get("kind") == "record":
                    sub = str(decision.get("subkind"))
                    self.inventory["record_subkinds"][sub] = self.inventory["record_subkinds"].get(sub, 0) + 1
            if "local" in data or ("local" in (data.get("plan") or {})):
                self.add("VS1", "info", "local_extension", path, "local 확장 기록 사용(guard 비대상)", pid)
        for pid, parent in self.parents.items():
            if parent.matrix is None:
                continue
            if parent.matrix_contract is None:
                self.add("VS1", "info", "snapshot_unknown", parent.matrix_path, "matrix 계약 미확보로 미평가", pid)
                continue
            for error in schema.validate_definition(parent.matrix_contract, "coverage_matrix", parent.matrix):
                self.add("VS1", "defect", "matrix_schema", f"{parent.matrix_path}{error.path}", error.message, pid)
        if self.inventory["record_subkinds"]:
            self.add("VS1", "info", "record_subkinds", "decisions",
                     f"record subkind 목록: {self.inventory['record_subkinds']}")
        self.status["VS1"] = "fail" if self.failed("VS1") else "pass"

    # ------------------------------------------------------------------ VS2
    def _task_artifact(self, parent: Parent, task_id: str) -> dict | None:
        entry = parent.manifest.get(task_id)
        if not entry or entry.get("kind") != "task" or not isinstance(entry.get("path"), str):
            return None
        doc = self.project.load(entry["path"])
        if doc.error or not isinstance(doc.data, dict) or doc.data.get("kind") != "task":
            return None
        return doc.data

    def vs2(self) -> None:
        if not self.gate("VS2", "VS1", "VS1 실패로 연결 검사 미평가"):
            return
        for pid, parent in self.parents.items():
            where = parent.path
            children = (parent.data.get("scope") or {}).get("children") or []
            for child in children:
                resolved = self._task_artifact(parent, child)
                parent.children[child] = resolved
                if resolved is None:
                    self.add("VS2", "defect", "child_unresolved", f"{where}/scope/children/{child}",
                             "child가 경로 있는 manifest task artifact로 해결되지 않는다", pid)
                else:
                    state = (resolved.get("workflow") or {}).get("state")
                    self.add("VS2", "info", "child_state", child, f"child 상태 {state}", pid)
            requires = contract_version(parent.contract) >= 2 and children and pid not in self.options.attach
            ref = (parent.data.get("plan") or {}).get("coverage_matrix")
            if requires and not ref:
                self.add("VS2", "defect", "coverage_matrix_missing", f"{where}/plan/coverage_matrix",
                         "분해 Packet에 Coverage Matrix 참조가 없다", pid)
            if ref and pid not in self.options.attach:
                entry = parent.manifest.get(ref)
                if entry is None:
                    self.add("VS2", "defect", "matrix_unresolved", f"{where}/plan/coverage_matrix",
                             f"manifest에 {ref}가 없다", pid)
                else:
                    if entry.get("revision") == "current":
                        self.add("VS2", "defect", "matrix_revision_current", f"{where}/artifacts/{ref}",
                                 "matrix manifest revision은 current일 수 없다", pid)
                    if entry.get("kind") != "plan":
                        self.add("VS2", "warning", "matrix_kind", f"{where}/artifacts/{ref}", "matrix는 kind plan이어야 한다", pid)
            if parent.matrix_path and self.project.load(parent.matrix_path).text is None:
                self.add("VS2", "defect", "matrix_unresolved", parent.matrix_path, "matrix 파일을 읽지 못했다", pid)
            matrix = parent.matrix
            if not isinstance(matrix, dict):
                continue
            if matrix.get("task") != pid:
                self.add("VS2", "defect", "matrix_task_mismatch", parent.matrix_path,
                         f"matrix task {matrix.get('task')!r} ≠ parent {pid}", pid)
            for item in matrix.get("scope") or []:
                artifact = item.get("artifact") if isinstance(item, dict) else None
                if artifact is None:
                    continue
                entry = parent.manifest.get(artifact)
                doc = self.project.load(entry["path"]) if entry and isinstance(entry.get("path"), str) else None
                if doc is None or doc.text is None:
                    detail = f"({doc.error})" if doc is not None else ""
                    self.add("VS2", "defect", "scope_artifact_unresolved", f"{parent.matrix_path}/scope/{artifact}",
                             f"scope artifact가 읽을 수 있는 manifest 항목으로 해결되지 않는다{detail}", pid)
            for row in matrix.get("obligations") or []:
                if not isinstance(row, dict):
                    continue
                rid = str(row.get("local_id"))
                failed = 0
                for task in row.get("owner_task") or []:
                    if task not in children:
                        failed += 1
                        self.add("VS2", "defect", "owner_task_not_child", f"{parent.matrix_path}#{rid}",
                                 f"owner_task {task}가 선언된 child가 아니다", pid, rid)
                    elif parent.children.get(task) is None:
                        failed += 1
                        self.add("VS2", "defect", "owner_task_unresolved", f"{parent.matrix_path}#{rid}",
                                 f"owner_task {task}의 Packet이 해결되지 않는다", pid, rid)
                for entry in row.get("owner_criterion") or []:
                    task = str(entry).split("#", 1)[0]
                    if task not in (row.get("owner_task") or []):
                        failed += 1
                        self.add("VS2", "defect", "owner_criterion_task_mismatch", f"{parent.matrix_path}#{rid}",
                                 f"{entry}의 Task가 owner_task에 없다", pid, rid)
                target = row.get("to")
                if isinstance(target, str):
                    task = target.split("#", 1)[0]
                    if self._task_artifact(parent, task) is None:
                        failed += 1
                        self.add("VS2", "defect", "to_unresolved", f"{parent.matrix_path}#{rid}",
                                 f"to {target}가 해결되지 않는다", pid, rid)
                if failed:
                    parent.pointer_failures += failed
                    parent.row_status[rid] = "unresolved"
        self.status["VS2"] = "fail" if self.failed("VS2") else "pass"

    # ------------------------------------------------------------------ VS3/VS4
    def _enumerate(self, parent: Parent) -> None:
        by_artifact: dict[str, list[str]] = {}
        for item in parent.matrix.get("scope") or []:
            if not isinstance(item, dict):
                continue
            artifact, sections = item.get("artifact"), item.get("sections") or []
            if artifact is None:
                if sections:
                    self.add("VS3", "defect", "scope_null_with_sections", parent.matrix_path,
                             "artifact null인 scope 항목은 sections가 비어 있어야 한다", parent.id)
                continue
            if item.get("revision") is None:
                self.add("VS3", "defect", "scope_revision_missing", f"{parent.matrix_path}/scope/{artifact}",
                         "scope 판본이 없다", parent.id)
            manifest_rev = (parent.manifest.get(artifact) or {}).get("revision")
            if manifest_rev and item.get("revision") and manifest_rev != item.get("revision"):
                self.add("VS3", "info", "scope_revision_differs", f"{parent.matrix_path}/scope/{artifact}",
                         "scope 판본과 manifest 판본이 다르다(재열거·재확인 대상)", parent.id)
            by_artifact.setdefault(artifact, []).extend(sections)
        for artifact, sections in by_artifact.items():
            entry = parent.manifest.get(artifact) or {}
            text = self.project.source.read(entry.get("path")) if isinstance(entry.get("path"), str) else None
            if text is None:
                parent.units[artifact] = []
                continue
            units, errors = mdunits.enumerate_sections(artifact, text, sections)
            for error in errors:
                self.add("VS3", "defect", "section_unresolved", f"{parent.matrix_path}/scope/{artifact}", error, parent.id)
            parent.units[artifact] = units

    def _locate(self, parent: Parent, row: dict) -> tuple[str, mdunits.Unit | None]:
        source = row.get("source") or {}
        units = parent.units.get(source.get("artifact"), [])
        found = mdunits.locate(str(source.get("excerpt", "")), units, source.get("hint"))
        if not found:
            return "missing", None
        if len(found) > 1:
            return "ambiguous", None
        unit = found[0]
        return ("ok" if unit.fp == source.get("fingerprint") else "suspect"), unit

    def vs3_vs4(self) -> None:
        run3 = self.gate("VS3", "VS1", "VS1 실패로 matrix 검사 미평가")
        run4 = self.gate("VS4", "VS1", "VS1 실패로 drift 검사 미평가")
        if not (run3 or run4):
            return
        pointers_ok = not self.failed("VS2")
        if not pointers_ok and not self.options.diagnostic:
            self.reasons["VS3"] = "VS2 실패로 Stage B 포인터 해결 미평가"
        for pid, parent in self.parents.items():
            matrix = parent.matrix
            if not isinstance(matrix, dict):
                continue
            self._enumerate(parent)
            rows = [r for r in matrix.get("obligations") or [] if isinstance(r, dict)]
            scope_artifacts = {i.get("artifact") for i in matrix.get("scope") or [] if isinstance(i, dict)}
            seen_ids: set[str] = set()
            covered: dict[tuple[str, int], list[dict]] = {}
            for row in rows:
                rid = str(row.get("local_id"))
                where = f"{parent.matrix_path}#{rid}"
                if rid in seen_ids:
                    self.add("VS3", "defect", "duplicate_local_id", where, "local_id 중복", pid, rid)
                seen_ids.add(rid)
                source = row.get("source") or {}
                if source.get("artifact") not in scope_artifacts:
                    self.add("VS3", "defect", "row_artifact_out_of_scope", where, "scope에 없는 artifact", pid, rid)
                disposition = row.get("disposition")
                if disposition is None:
                    self.add("VS3", "defect", "unassigned_row", where, "처분 없음(미배정)", pid, rid)
                    parent.row_status[rid] = "unassigned"
                elif disposition == "owned" and not row.get("owner_task"):
                    self.add("VS3", "defect", "owned_without_owner_task", where, "owned인데 owner_task가 없다", pid, rid)
                elif disposition == "deferred":
                    if not row.get("to"):
                        self.add("VS3", "defect", "deferred_without_target", where, "deferred인데 to가 없다", pid, rid)
                    elif (str(row["to"]).split("#", 1)[0] not in (parent.data.get("scope") or {}).get("children", [])
                          and not row.get("decision")):
                        self.add("VS3", "defect", "deferred_without_decision", where,
                                 "children 밖 연기인데 decision이 없다", pid, rid)
                    for key in ("reason", "resume_when"):
                        if not row.get(key):
                            self.add("VS3", "defect", f"deferred_without_{key}", where, f"deferred인데 {key}가 없다", pid, rid)
                elif disposition == "excluded":
                    if not row.get("decision"):
                        self.add("VS3", "defect", "excluded_without_decision", where, "excluded인데 decision이 없다", pid, rid)
                    if not row.get("reason"):
                        self.add("VS3", "defect", "excluded_without_reason", where, "excluded인데 reason이 없다", pid, rid)
                status, unit = self._locate(parent, row)
                if run4:
                    if status != "ok":
                        label = {"suspect": "fingerprint 불일치(재확인 필요, 실패 판정 아님)",
                                 "ambiguous": "excerpt가 여러 단위와 일치", "missing": "일치하는 단위 없음"}[status]
                        self.add("VS4", "recheck", status, where, label, pid, rid)
                        parent.row_status.setdefault(rid, status)
                if unit is not None:
                    covered.setdefault((unit.artifact, unit.line, unit.norm), []).append(row)
                    part = source.get("part")
                    if part and mdunits.normalize(str(part)) not in unit.norm:
                        self.add("VS3", "defect", "part_not_substring", where, "part가 단위 정규화 전문의 부분 문자열이 아니다", pid, rid)
                parent.row_status.setdefault(rid, "ok")
            if run3:
                for artifact, units in parent.units.items():
                    for unit in units:
                        shared = covered.get((artifact, unit.line, unit.norm), [])
                        if not shared:
                            self.add("VS3", "defect", "unassigned_unit", f"{parent.matrix_path}/{artifact}",
                                     f"처분 행이 없는 구조 단위: {unit.hint} «{unit.norm[:30]}»", pid)
                        elif len(shared) > 1:
                            parts = [r.get("source", {}).get("part") for r in shared]
                            related = ",".join(sorted(str(r.get("local_id")) for r in shared))
                            if any(p is None for p in parts):
                                self.add("VS3", "defect", "split_without_part", f"{parent.matrix_path}/{artifact}",
                                         f"한 단위의 여러 행 중 part 없는 행이 있다: {unit.hint}", pid, related)
                            elif len(set(parts)) != len(parts):
                                self.add("VS3", "defect", "double_disposition", f"{parent.matrix_path}/{artifact}",
                                         f"같은 단위·part의 이중 처분: {unit.hint}", pid, related)
                if pointers_ok or self.options.diagnostic:
                    self._stage_b(parent, rows)
                self._stage_a_diff(parent, rows)
        if run3:
            self.status["VS3"] = "fail" if self.failed("VS3") else "pass"
        if run4:
            blocking = any(f.stage == "VS4" and f.severity == "recheck" for f in self.findings)
            self.status["VS4"] = "attention" if blocking else "pass"

    def _stage_b(self, parent: Parent, rows: list[dict]) -> None:
        for row in rows:
            if row.get("disposition") != "owned":
                continue
            rid = str(row.get("local_id"))
            where = f"{parent.matrix_path}#{rid}"
            entries = [str(e) for e in row.get("owner_criterion") or []]
            for task in row.get("owner_task") or []:
                child = parent.children.get(task)
                if child is None:
                    continue  # VS2에서 보고
                criteria = {c.get("id") for c in child.get("criteria") or [] if isinstance(c, dict)}
                mine = [e for e in entries if e.split("#", 1)[0] == task]
                planned = bool((child.get("plan") or {}).get("identity"))
                if planned and not mine:
                    self.add("VS3", "defect", "stage_b_unrefined", where,
                             f"child {task}의 plan 뒤에도 owner_criterion이 없다(unresolved)", parent.id, rid)
                    parent.row_status[rid] = "unresolved"
                for entry in mine:
                    if entry.split("#", 1)[1] not in criteria:
                        self.add("VS3", "defect", "owner_criterion_dangling", where,
                                 f"{entry}가 child의 현재 criterion이 아니다", parent.id, rid)
                        parent.row_status[rid] = "unresolved"

    def _stage_a_diff(self, parent: Parent, rows: list[dict]) -> None:
        baseline = (self.options.stage_a_baseline or {}).get(parent.id)
        if not isinstance(baseline, dict):
            return
        keys = ("disposition", "owner_task", "to", "reason", "resume_when", "decision")
        before = {str(r.get("local_id")): r for r in baseline.get("obligations") or [] if isinstance(r, dict)}
        after = {str(r.get("local_id")): r for r in rows}
        changed = sorted(rid for rid in set(before) | set(after)
                         if rid not in before or rid not in after
                         or any(before[rid].get(k) != after[rid].get(k) for k in keys))
        if baseline.get("scope") != parent.matrix.get("scope"):
            changed.insert(0, "(scope)")
        if changed:
            self.add("VS3", "info", "stage_a_changed", parent.matrix_path,
                     f"이전 판본 대비 Stage A 변경(plan_change 기록 확인 필요): {changed[:20]}", parent.id)

    # ------------------------------------------------------------------ VS5
    def _approved_gate(self, parent: Parent, subject: Any) -> bool:
        return any(isinstance(d, dict) and d.get("kind") == "human_gate" and d.get("verdict") == "approved"
                   and d.get("subject") == subject and d.get("role") == "human"
                   and isinstance(d.get("actor"), dict) and d["actor"].get("kind") == "human"
                   for d in parent.data.get("decisions") or [])

    def vs5(self) -> None:
        if self.options.phase != "close":
            self.status["VS5"] = "not_evaluated"
            self.reasons["VS5"] = "phase plan: 종료 조건 미평가"
            return
        if not self.gate("VS5", "VS1", "VS1 실패로 소유권 검사 미평가"):
            return
        if self.failed("VS2") and not self.options.diagnostic:
            self.status["VS5"] = "not_evaluated"
            self.reasons["VS5"] = "VS2 실패로 인수·연기 포인터 미평가"
            return
        for pid, parent in self.parents.items():
            matrix = parent.matrix
            children = (parent.data.get("scope") or {}).get("children") or []
            for row in (matrix.get("obligations") or []) if isinstance(matrix, dict) else []:
                if not isinstance(row, dict):
                    continue
                rid, where = str(row.get("local_id")), f"{parent.matrix_path}#{row.get('local_id')}"
                disposition = row.get("disposition")
                if disposition == "owned":
                    entries = [str(e) for e in row.get("owner_criterion") or []]
                    for task in row.get("owner_task") or []:
                        child = parent.children.get(task)
                        if child is None:
                            continue
                        state = (child.get("workflow") or {}).get("state")
                        if state not in ACCEPTED_STATES:
                            self.add("VS5", "defect", "owner_child_not_accepted", where,
                                     f"owner child {task} 상태 {state}", pid, rid)
                        if not any(e.split("#", 1)[0] == task for e in entries):
                            self.add("VS5", "defect", "owner_criterion_missing_at_close", where,
                                     f"{task}의 owner_criterion 없이 종료할 수 없다", pid, rid)
                elif disposition == "deferred" and isinstance(row.get("to"), str) and row.get("decision"):
                    task = row["to"].split("#", 1)[0]
                    if task not in children and not self._approved_gate(parent, row.get("decision")):
                        self.add("VS5", "defect", "deferred_decision_unapproved", where,
                                 f"children 밖 연기({task})의 decision {row.get('decision')!r}가 approved human_gate가 아니다", pid, rid)
                elif disposition == "excluded" and row.get("decision"):
                    if not self._approved_gate(parent, row.get("decision")):
                        self.add("VS5", "defect", "excluded_decision_unapproved", where,
                                 f"decision {row.get('decision')!r}가 approved human_gate가 아니다", pid, rid)
        for pid, packet in self.packets.items():
            legacy = contract_version(packet["contract"]) < 2
            if legacy and not self.options.legacy_as_v4:
                continue
            data = packet["data"]
            lists = [("delivery/residual_risks", (data.get("delivery") or {}).get("residual_risks")),
                     ("plan/review_brief/residual_risks",
                      ((data.get("plan") or {}).get("review_brief") or {}).get("residual_risks")
                      if isinstance((data.get("plan") or {}).get("review_brief"), dict) else None)]
            for location, items in lists:
                for index, item in enumerate(items or []):
                    ok = isinstance(item, dict) and all(isinstance(item.get(k), str) and item.get(k) for k in ("risk", "owner", "condition"))
                    if not ok:
                        self.add("VS5", "defect", "residual_ownerless", f"{packet['path']}/{location}/{index}",
                                 "소유자·후속 조건 구조가 없는 잔여 위험", pid)
        self.status["VS5"] = "fail" if self.failed("VS5") else "pass"

    # ------------------------------------------------------------------ VS6
    def vs6(self) -> None:
        for pid, parent in self.parents.items():
            counts: dict[str, int] = {}
            for row in (parent.matrix or {}).get("obligations") or [] if isinstance(parent.matrix, dict) else []:
                for entry in (row.get("owner_criterion") or []) if isinstance(row, dict) else []:
                    counts[str(entry)] = counts.get(str(entry), 0) + 1
            for entry, count in sorted(counts.items()):
                if count >= 11:
                    self.add("VS6", "info", "coarse_criterion", entry, f"{count}개 행을 소유(거친 criterion 신호)", pid)
        self.status["VS6"] = "pass"

    # ------------------------------------------------------------------ run
    def execute(self) -> dict:
        self.vs0()
        self.vs1()
        self.vs2()
        self.vs3_vs4()
        self.vs5()
        self.vs6()
        return self.report()

    def verdict(self, diagnostic_blocked: bool) -> dict:
        """FAIL(결정적 결함) > INCONCLUSIVE(미평가·재확인) > PASS. 사람용 요약과 종료 코드가 이 값을 쓴다."""
        defects = sorted({f"{f.stage} {f.code}" for f in self.findings if f.severity == "defect"})
        pending: list[str] = []
        for stage in STAGES:
            if self.status[stage] == "not_evaluated" and not (stage == "VS5" and self.options.phase == "plan"):
                pending.append(f"{stage} 미평가: {self.reasons.get(stage) or '이유 없음'}")
        for stage in STAGES:
            if self.status[stage] == "attention":
                pending.append(f"{stage} 재확인 {sum(1 for f in self.findings if f.stage == stage and f.severity == 'recheck')}건")
        for code in sorted(UNEVALUATED_CODES):
            count = sum(1 for f in self.findings if f.code == code)
            if count:
                pending.append(f"{code} {count}건(해당 대상 미평가)")
        if diagnostic_blocked:
            pending.append("진단 실행: 선행 단계 실패 뒤의 결과라 완전성 주장 불가")
        status = "FAIL" if defects else ("INCONCLUSIVE" if pending else "PASS")
        return {"status": status, "exit_code": EXIT_CODES[status], "meaning": VERDICT_MEANING[status],
                "defects": defects, "unevaluated": pending}

    def report(self) -> dict:
        for stage in STAGES:
            self.status.setdefault(stage, "not_evaluated")
        diagnostic_blocked = any("진단 실행" in r for r in self.reasons.values())
        complete: dict[str, bool] = {}
        for pid, parent in self.parents.items():
            if parent.matrix is None:
                complete[pid] = False
                continue
            clean = all(self.status[s] == "pass" for s in STAGES[:6])
            mine = any(f.parent == pid and f.severity in BLOCKING and f.stage in STAGES[:6] for f in self.findings)
            complete[pid] = clean and not mine and not diagnostic_blocked and self.options.phase == "close"
        return {
            "verdict": self.verdict(diagnostic_blocked),
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION, "target_contract": TARGET_CONTRACT},
            "method": "tool",
            "parser": yamlio.PARSER,
            "source": self.project.source.label,
            "contracts": sorted(self.project.contracts),
            "phase": self.options.phase,
            "diagnostic": self.options.diagnostic,
            "stages": {s: {"name": STAGE_NAMES[s], "status": self.status[s], "reason": self.reasons.get(s)} for s in STAGES},
            "findings": [asdict(f) for f in self.findings],
            "rows": {pid: dict(sorted(p.row_status.items())) for pid, p in self.parents.items()},
            "pointer_failures": {pid: p.pointer_failures for pid, p in self.parents.items()},
            "coverage_complete": complete,
            "pass_meaning": PASS_MEANING,
            "not_checked": NOT_CHECKED,
        }
