"""artifact_lifecycle의 결정적 계산: layout, 구조적 Packet view, 봉인(sealed) 집합, class.

이 모듈은 Packet schema를 소급하지 않는다. 다른 snapshot의 Packet도 state·scope·artifacts·delivery·
evidence_manifest 구조만 읽는다(core.yaml project_health.legacy).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from .project import Project, contract_version

DEFAULT_LAYOUT = {
    "canonical": [], "operational": [], "decision": [], "historical": [], "sealed": [],
    "evidence_root": ".harness/evidence",
    "raw_patterns": [".log", ".png", ".jpg", ".jpeg", ".webm", ".mp4", ".trace", ".har", ".zip"],
    "relocation_ledger": ".harness/relocations.yaml",
    "delivery_ledger": ".harness/deliveries.jsonl",
    "verification_registry": None,
}
HEX = re.compile(r"\b[0-9a-f]{7,40}\b")


def norm_path(path: str) -> str:
    return str(PurePosixPath(path)).rstrip("/") if path else path


def covers(outer: str, inner: str) -> bool:
    """outer가 inner와 같거나 inner의 상위 디렉터리다."""
    outer, inner = norm_path(outer), norm_path(inner)
    return inner == outer or inner.startswith(outer + "/")


def overlaps(a: str, b: str) -> bool:
    return covers(a, b) or covers(b, a)


@dataclass
class Layout:
    values: dict[str, Any]
    declared: bool

    def __getitem__(self, key: str) -> Any:
        return self.values.get(key)

    def is_raw(self, path: str) -> bool:
        return any(path.lower().endswith(p) for p in self.values.get("raw_patterns") or [])


def load_layout(project: Project) -> Layout:
    config = project.load(".harness/project.yaml").data
    raw = config.get("layout") if isinstance(config, dict) else None
    values = dict(DEFAULT_LAYOUT)
    if isinstance(raw, dict):
        values.update({k: v for k, v in raw.items() if v is not None})
    return Layout(values, isinstance(raw, dict))


@dataclass
class PacketView:
    """snapshot과 무관한 구조적 Packet view."""
    path: str
    id: str | None
    data: dict | None
    error: str | None
    contract: dict | None = None
    size: int = 0
    copy: bool = False  # evidence 위치 안의 Packet 사본(freeze copy). live Packet이 아니다

    @property
    def state(self) -> str | None:
        return ((self.data or {}).get("workflow") or {}).get("state") if self.data else None

    @property
    def closed(self) -> bool:
        return self.state == "CLOSED"

    @property
    def finished_not_closed(self) -> bool:
        """close 노드에서 ACCEPTED로 남은 이전 관행의 종료 Task(이전 snapshot이거나 receipt가 있음). 활성으로 보지 않는다."""
        data = self.data or {}
        return (self.state == "ACCEPTED" and (data.get("workflow") or {}).get("node") == "close"
                and (bool((data.get("delivery") or {}).get("receipt")) or not self.is_v3))

    @property
    def active(self) -> bool:
        return self.data is not None and not self.closed and not self.finished_not_closed and not self.copy

    @property
    def blocked(self) -> bool:
        return ((self.data or {}).get("recovery") or {}).get("status") == "blocked"

    @property
    def snapshot(self) -> str | None:
        return (self.data or {}).get("harness_snapshot")

    @property
    def cv(self) -> int:
        return contract_version(self.contract)

    @property
    def is_v3(self) -> bool:
        return self.cv >= 3

    def scope_write(self) -> list[str]:
        scope = (self.data or {}).get("scope")
        return [w for w in (scope.get("write") or []) if isinstance(w, str)] if isinstance(scope, dict) else []

    def artifacts(self) -> list[dict]:
        return [a for a in (self.data or {}).get("artifacts") or [] if isinstance(a, dict)]

    def manifest(self) -> dict[str, dict]:
        return {a["id"]: a for a in self.artifacts() if isinstance(a.get("id"), str)}

    def evidence_manifest(self) -> dict | None:
        value = (self.data or {}).get("evidence_manifest")
        return value if isinstance(value, dict) else None

    def evidence_paths(self) -> dict[str, list[str]]:
        """tier → 경로 목록. v3 evidence_manifest가 없으면 이전 Packet 규칙(kind evidence를 authoritative)으로 계산."""
        tiers: dict[str, list[str]] = {"authoritative": [], "supporting": [], "raw": [], "root": []}
        manifest = self.manifest()
        em = self.evidence_manifest()
        if em:
            if isinstance(em.get("root"), str):
                tiers["root"].append(em["root"])
            for tier in ("authoritative", "supporting"):
                for ident in em.get(tier) or []:
                    path = (manifest.get(ident) or {}).get("path")
                    if isinstance(path, str):
                        tiers[tier].append(path)
            tiers["raw"].extend(p for p in em.get("raw") or [] if isinstance(p, str))
        else:
            for item in self.artifacts():
                if item.get("kind") == "evidence" and isinstance(item.get("path"), str):
                    tiers["authoritative"].append(item["path"])
        return tiers


def load_packets(project: Project) -> list[PacketView]:
    views: list[PacketView] = []
    for path in project.source.list(project.task_root):
        if not path.endswith((".yaml", ".yml")):
            continue
        doc = project.load(path)
        size = len(project.source.read_bytes(path) or b"")
        if doc.error:
            views.append(PacketView(path, None, None, doc.error, size=size))
            continue
        data = doc.data
        if not isinstance(data, dict) or data.get("kind") != "task":
            continue
        pid = data.get("id") if isinstance(data.get("id"), str) else None
        views.append(PacketView(path, pid, data, None, project.contracts.get(data.get("harness_snapshot")), size))
    mark_copies(project, views)
    return views


def copy_places(project: Project, views: list[PacketView]) -> tuple[list[str], list[str]]:
    """Task YAML 사본을 둘 수 있는 위치. (Packet이 evidence로 선언한 경로, layout.evidence_root·layout.sealed).
    task_root 자체나 그 상위를 덮는 위치는 쓰지 않는다(10차 검토 R10-03)."""
    layout = load_layout(project)
    task_root = norm_path(project.task_root)
    declared: list[str] = []
    for view in views:
        if view.data is None:
            continue
        tiers = view.evidence_paths()
        declared.extend(p for tier in ("root", "authoritative", "supporting", "raw") for p in tiers[tier]
                        if not p.endswith((".yaml", ".yml")) or p != view.path)
    configured = [layout["evidence_root"], *(layout["sealed"] or [])]
    keep = lambda places: [norm_path(p) for p in places if p and not covers(norm_path(p), task_root)]
    return keep(declared), keep(configured)


def is_copy(path: str, pid: str | None, task_root: str, declared: list[str], configured: list[str],
            live_ids: set[str]) -> bool:
    """사본 판정. evidence 위치(Packet의 evidence 선언·layout.evidence_root·layout.sealed) 안이어야 한다. task_root 밖이면
    사본이고, task_root 안에서는 같은 id의 live Packet이 그 위치들 밖에 있을 때만 사본이다. 봉인·evidence 선언이 실제
    Packet을 사본으로 바꾸지 못한다(11차 검토 R11-02, 12차 검토 R12-02)."""
    path = norm_path(path)
    if not any(covers(place, path) and place != path for place in declared + configured):
        return False
    if not covers(task_root, path):
        return True
    # task_root 안에서는 어떤 선언(다른 Task의 evidence 선언 포함)도 그것만으로 사본을 만들지 못한다(12차 검토 R12-02)
    return pid is not None and pid in live_ids


def mark_copies(project: Project, views: list[PacketView]) -> None:
    """evidence 위치 안의 task YAML은 사본이다(is_copy)."""
    declared, configured = copy_places(project, views)
    task_root = norm_path(project.task_root)
    live_ids = {v.id for v in views if v.data is not None and v.id
                and not any(covers(place, norm_path(v.path)) for place in declared + configured)}
    for view in views:
        if view.data is not None and is_copy(view.path, view.id, task_root, declared, configured, live_ids):
            view.copy = True


def sealed_paths(project: Project, packets: list[PacketView], layout: Layout) -> dict[str, str]:
    """봉인 경로 → 근거(소유 Task 또는 layout). 소유 Task가 CLOSED인 Packet과 그 evidence."""
    sealed: dict[str, str] = {}
    for path in layout["sealed"] or []:
        sealed[norm_path(path)] = "layout.sealed"
    places = [project.task_root, layout["evidence_root"], *(layout["sealed"] or [])]
    for view in packets:
        if not view.closed or view.copy:
            continue
        sealed[norm_path(view.path)] = f"{view.id} CLOSED Packet"
        tiers = view.evidence_paths()
        own = [p for p in tiers["root"]]
        for tier, paths in tiers.items():
            for path in paths:
                # 봉인은 evidence 위치 안에서만 추론한다. 제품 파일을 evidence로 적은 기록이 제품을 봉인하지 않는다.
                if any(covers(place, path) for place in places + own):
                    sealed.setdefault(norm_path(path), f"{view.id} evidence({tier})")
    return sealed


def sealed_owner(sealed: dict[str, str], path: str) -> str | None:
    for root, why in sealed.items():
        if covers(root, path):
            return why
    return None


def classify(path: str, layout: Layout, packets: list[PacketView], task_root: str) -> str:
    """경로의 artifact class(저장하지 않고 계산). 선언이 없으면 not_classified."""
    for view in packets:
        tiers = view.evidence_paths()
        if any(covers(p, path) for p in tiers["raw"]):
            return "raw_evidence"
        if any(covers(p, path) for p in tiers["authoritative"] + tiers["supporting"] + tiers["root"]):
            return "raw_evidence" if layout.is_raw(path) else "evidence"
    if covers(layout["evidence_root"], path):
        return "raw_evidence" if layout.is_raw(path) else "evidence"
    if covers(task_root, path):
        return "task" if path.endswith((".yaml", ".yml")) else ("raw_evidence" if layout.is_raw(path) else "evidence")
    for cls in ("historical", "decision", "canonical", "operational"):
        if any(covers(p, path) for p in layout[cls] or []):
            return cls
    return "not_classified"


def temperature(cls: str, closed_owner: bool | None) -> str:
    if cls in ("canonical", "operational"):
        return "hot"
    if cls in ("historical", "raw_evidence"):
        return "cold" if closed_owner is not False else "hot"
    if cls in ("evidence", "task"):
        return "warm" if closed_owner else "hot"
    if cls == "decision":
        return "warm"
    return "unknown"


def git_rev_tokens(revision: Any) -> list[str]:
    return HEX.findall(revision) if isinstance(revision, str) else []


def residual_closure(refs: set[str], terminal: set[str], successors: dict[str, set[str]]) -> tuple[set[str], set[str]]:
    """(닫힌 residual, 순환에 묶인 residual). 2차 검토 R2-03.

    successors[r]: r을 이어받은 residual(transferred·superseded의 to, inherited_from으로 이어받은 자식).
    r은 resolved·accepted 처분이 있거나(terminal), successor 경로가 순환 없이 다른 residual에 도달하면 닫힌다.
    모든 successor 경로가 순환으로 돌아오면 아무도 위험을 들고 있지 않으므로 r은 open이며 순환으로 보고한다.
    """
    closed: set[str] = set(terminal)
    cyclic: set[str] = set()
    for start in refs:
        if start in terminal or not successors.get(start):
            continue
        # start에서 출발해 start로 돌아오지 않고 도달 가능한 노드가 있으면 위험을 이어받은 residual이 존재한다
        seen, stack, escapes = {start}, list(successors[start]), False
        while stack:
            node = stack.pop()
            if node == start or node in seen:
                continue
            seen.add(node)
            nxt = successors.get(node) or set()
            if node in terminal or not (nxt - {start}) and node not in _reaches(successors, node, start):
                escapes = True
                break
            stack.extend(nxt)
        if escapes:
            closed.add(start)
        else:
            cyclic.add(start)
    return closed, cyclic


def _reaches(successors: dict[str, set[str]], node: str, target: str) -> set[str]:
    """node에서 target에 도달하면 {node}, 아니면 빈 집합(순환 판정 보조)."""
    seen, stack = set(), [node]
    while stack:
        cur = stack.pop()
        for nxt in successors.get(cur) or set():
            if nxt == target:
                return {node}
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return set()
