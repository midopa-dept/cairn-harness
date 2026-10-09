"""evidence tier·크기·temperature의 결정적 계산(core.yaml telemetry.computed, context.evidence_retrieval)."""
from __future__ import annotations

from pathlib import Path

from .lifecycle import Layout, PacketView, load_layout, load_packets, norm_path
from .project import FsSource, Project


def _files(project: Project, path: str) -> list[tuple[str, int]]:
    source = project.source
    if isinstance(source, FsSource):
        target = source.root / path
        if target.is_file():
            return [(path, target.stat().st_size)]
        if target.is_dir():
            return [(p.relative_to(source.root).as_posix(), p.stat().st_size) for p in target.rglob("*") if p.is_file()]
        return []
    listed = source.list(path)
    if not listed:
        data = source.read_bytes(path)
        return [(path, len(data))] if data is not None else []
    return [(p, len(source.read_bytes(p) or b"")) for p in listed]


def _resolver(project: Project, layout: Layout):
    """evidence 집계도 relocation ledger로 옛 locator를 해석한다(R8)."""
    from .relocation import invalid_ids, load_ledger, resolve_trace, validate
    ledger = load_ledger(project, layout["relocation_ledger"], project.contracts.get(project.content_id))
    if ledger.present and not any(f["severity"] == "error" for f in ledger.findings):
        validate(project, ledger)
        from .relocation import baseline_check
        baseline_check(project, ledger)  # health·relocations와 같은 baseline 대조 결과를 쓴다(3차 검토 R3-03)
    bad = invalid_ids(ledger)
    ledger_broken = any(f["severity"] == "error" and "#" not in f["where"] for f in ledger.findings)

    def covered(path: str) -> bool:
        return any(isinstance(e.get("from"), str) and (path == e["from"].rstrip("/") or path.startswith(e["from"].rstrip("/") + "/"))
                   for e in ledger.entries) if ledger.present else False

    def find(path: str) -> tuple[str | None, bool]:
        if covered(path):
            # 5차 검토 R5-03: ledger가 옮긴 옛 locator는 현재 옛 경로의 파일로 해석하지 않는다(재생성은 오염이다)
            if _files(project, path):
                return None, False
        elif _files(project, path):
            return path, False
        if ledger.present and ledger.entries and not ledger_broken:
            final, used, problem = resolve_trace(ledger, path)
            # 실제로 사용한 chain의 모든 항목이 schema·identity·baseline 검사를 통과해야 한다(R2-05·R3-03·R4-03)
            if used and final and not problem and not (set(used) & bad) and _files(project, final):
                return final, True
        return None, False
    return find


def task_evidence(project: Project, view: PacketView, layout: Layout, find=None) -> dict:
    find = find or _resolver(project, layout)
    tiers = view.evidence_paths()
    unresolved: list[str] = []
    relocated = 0
    resolved_tiers: dict[str, list[str]] = {}
    for tier, paths in tiers.items():
        resolved_tiers[tier] = []
        for path in paths:
            actual, moved = find(path)
            if actual is None:
                unresolved.append(path)
                continue
            relocated += int(moved)
            resolved_tiers[tier].append(actual)
    tiers = resolved_tiers
    seen: set[str] = set()
    result = {"task": view.id, "state": view.state, "manifest": bool(view.evidence_manifest()),
              "packet_bytes": view.size, "tiers": {}}
    roots = tiers["root"]
    legacy = not view.evidence_manifest()
    buckets: dict[str, list[tuple[str, int]]] = {"authoritative": [], "supporting": [], "raw": []}
    for tier in ("authoritative", "supporting", "raw"):
        for path in tiers[tier]:
            for rel, size in _files(project, path):
                if rel in seen:
                    continue
                seen.add(rel)
                # 이전 Packet: kind evidence 아래의 원 log·screenshot은 raw로 취급한다(context.evidence_retrieval)
                target = "raw" if legacy and tier != "raw" and layout.is_raw(rel) else tier
                buckets[target].append((rel, size))
    for tier, files in buckets.items():
        result["tiers"][tier] = {"files": len(files), "bytes": sum(s for _, s in files)}
    # root 안에서 tier에 선언되지 않은 파일은 미분류(raw 패턴이면 raw로 계산)
    rest_raw, rest_other = [], []
    for root in roots:
        for rel, size in _files(project, root):
            if rel in seen:
                continue
            seen.add(rel)
            (rest_raw if layout.is_raw(rel) else rest_other).append(size)
    result["tiers"]["raw"]["files"] += len(rest_raw)
    result["tiers"]["raw"]["bytes"] += sum(rest_raw)
    result["tiers"]["unclassified"] = {"files": len(rest_other), "bytes": sum(rest_other)}
    result["relocated_locators"] = relocated
    result["unresolved_locators"] = unresolved  # 0 bytes와 구분한다
    closed = view.closed
    result["temperature"] = {"authoritative": "warm" if closed else "hot",
                             "supporting": "cold" if closed else "hot", "raw": "cold" if closed else "hot"}
    return result


def evidence_report(project: Project, task: str | None = None) -> dict:
    layout = load_layout(project)
    packets = [p for p in load_packets(project) if p.data is not None and (task is None or p.id == task)]
    find = _resolver(project, layout)
    rows = [task_evidence(project, view, layout, find) for view in packets]
    total = {tier: sum(r["tiers"][tier]["bytes"] for r in rows) for tier in ("authoritative", "supporting", "raw", "unclassified")}
    default_seed = sum(r["tiers"]["authoritative"]["bytes"] for r in rows if r["state"] == "CLOSED")
    return {"tasks": rows, "total_bytes": total,
            "closed_default_retrieval_bytes": default_seed,
            "note": "CLOSED Task의 기본 retrieval은 authoritative뿐이다. 이전 Packet은 kind evidence를 authoritative로 계산한다.",
            "layout_declared": layout.declared,
            "unresolved_locators": sum(len(r["unresolved_locators"]) for r in rows)}
