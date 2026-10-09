"""packet_semantics.next_action의 결정적 projection.

같은 snapshot·Packet·Git 상태에서 어느 runtime이 실행해도 같은 결과가 나와야 하는 경계만 계산한다.
결과는 guard 충족 판정·권한·인수가 아니다. 판단이 필요한 guard 부분은 requires_judgment로 따로 낸다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .lifecycle import load_layout, load_packets, overlaps, sealed_paths
from .project import FsSource, Project, contract_version

VOCABULARY = ["none", "recover", "reconcile_checkpoint", "complete_admission", "plan", "request_human_gate",
              "execute", "verify", "independent_review", "accept", "deliver", "settle_close"]
# contract의 policies.human_gate_tags가 없을 때(이전 계약 미확보)만 쓰는 candidate.4 baseline
FALLBACK_GATE_TAGS = ["architecture", "authentication_security", "db_migration", "canonical_requirement",
                      "equivalent_high_impact"]
JUDGMENT = {
    "admit": ["admitted: 위임·목적·기준의 실제 유효성, 필요한 capability 관찰의 충분성"],
    "plan": ["plan_current: 계획 자기검토·applicability bounded check의 충분성", "태그로 표현되지 않은 실제 고영향 변경 여부"],
    "execute": ["candidate_ready: 산출물 판본 집합이 실제 변경을 덮는가"],
    "verify": ["evidence_current: 근거의 적용성·관찰 충분성", "independent_satisfied: 맥락 분리의 실제성"],
    "accept": ["accepted_current: 인수 판단의 근거 충분성", "parent_reconciled: 결합 영향 대조"],
    "close": ["delivery_current: 전달 대상과 인수 대상의 관계", "settled: residual 인계의 실질성"],
    "recover": ["recoverable: 비멱등 효과의 실제 상태"],
}


def _ids(actors: Any) -> list[str]:
    return sorted({a.get("id") for a in actors or [] if isinstance(a, dict) and isinstance(a.get("id"), str)})


def _git_state(root: Path) -> dict | None:
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return None
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                            capture_output=True)
    dirty: list[str] = []
    entries = status.stdout.split(b"\0")
    index = 0
    while index < len(entries):
        raw = entries[index].decode()
        index += 1
        if len(raw) < 4:
            continue
        code, path = raw[:2], raw[3:]
        dirty.append(path)
        if "R" in code or "C" in code:
            index += 1  # rename 원경로
    return {"head": head.stdout.strip(), "dirty": sorted(set(dirty))}


def _under(path: str, roots: list[str]) -> bool:
    return any(path == r.rstrip("/") or path.startswith(r.rstrip("/") + "/") for r in roots)


def project_next_action(project: Project, packet_path: str, observe_git: bool = False) -> dict:
    doc = project.load(packet_path)
    result: dict[str, Any] = {"packet": packet_path, "method": "tool"}
    if doc.error or not isinstance(doc.data, dict) or doc.data.get("kind") != "task":
        result.update({"error": f"Packet을 해석하지 못했다: {doc.error or 'kind task 아님'}", "next_action": None})
        return result
    data = doc.data
    snapshot = data.get("harness_snapshot")
    contract = project.contracts.get(snapshot)
    known = contract is not None
    config = project.load(".harness/project.yaml").data or {}
    # 계약이 없으면 프로젝트 현재 계약의 graph·role 의미를 빌리되 그 사실을 표시한다.
    basis = contract or project.contracts.get(project.content_id) or {}
    wf = data.get("workflow") or {}
    scope = data.get("scope") or {}
    plan = data.get("plan") or {}
    state, node, graph, role = wf.get("state"), wf.get("node"), wf.get("graph"), wf.get("role")
    specs = config.get("role_specializations") or {}
    role_spec = specs.get(role) if isinstance(specs, dict) else None
    base = role_spec.get("base") if isinstance(role_spec, dict) else role
    role_def = (basis.get("roles") or {}).get(base) or {}
    node_def = (((basis.get("graphs") or {}).get(graph) or {}).get("nodes") or {}).get(node) or {}
    allow = set(role_def.get("allow") or [])
    if isinstance(role_spec, dict):
        allow &= set(role_spec.get("allow") or [])
    allow &= set(node_def.get("allow") or [])
    allow &= set(scope.get("allow") or [])
    deny = set(role_def.get("deny") or []) | set(scope.get("deny") or [])
    if isinstance(role_spec, dict):
        deny |= set(role_spec.get("deny") or [])
    effective = sorted(allow - deny)

    tags_base = ((basis.get("policies") or {}).get("human_gate_tags")) or FALLBACK_GATE_TAGS
    gate_tags = set(tags_base) | set(config.get("extra_human_gate_tags") or [])
    tags = sorted(set(scope.get("risk_tags") or []) & gate_tags)
    identity = plan.get("identity")
    decisions = [d for d in data.get("decisions") or [] if isinstance(d, dict)]
    gate_ok = bool(identity) and any(
        d.get("kind") == "human_gate" and d.get("verdict") == "approved" and d.get("subject") == identity
        and d.get("role") == "human" and (d.get("actor") or {}).get("kind") == "human" for d in decisions)
    gate_required = bool(tags)
    gate_ok = gate_ok or not gate_required  # guards.gate_satisfied: gate가 없으면 충족

    candidate = data.get("candidate") if isinstance(data.get("candidate"), dict) else None
    cid = candidate.get("id") if candidate else None
    producers = _ids(candidate.get("producers")) if candidate else []
    recovery = data.get("recovery") or {}
    checkpoint = recovery.get("checkpoint") if isinstance(recovery.get("checkpoint"), dict) else None
    if not candidate:
        # next_action.excluded_actors: freeze 전 잠정 producer
        provisional = set()
        if checkpoint and checkpoint.get("completed") and isinstance(checkpoint.get("actor"), str):
            provisional.add(checkpoint["actor"])
        if node == "execute" and isinstance((wf.get("actor") or {}).get("id"), str):
            provisional.add(wf["actor"]["id"])
        producers = sorted(provisional)
    verification = data.get("verification") or {}
    criteria = [c.get("id") for c in data.get("criteria") or [] if isinstance(c, dict)]
    covered: set[str] = set()
    for ev in verification.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("subject") == cid and ev.get("availability") == "available" and ev.get("verdict") == "pass":
            covered |= set(ev.get("criteria") or [])
    missing = [c for c in criteria if c not in covered]
    # 7차 검토 R7-01: 현재 candidate에 결합된 available 실패·불확정 근거는 미해결 실패다(guards.evidence_current)
    failing = sorted({str(ev.get("id")) for ev in verification.get("evidence") or [] if isinstance(ev, dict)
                      and ev.get("subject") == cid and ev.get("availability") == "available"
                      and ev.get("verdict") in ("fail", "inconclusive")})
    independence_required = bool(verification.get("independence_required"))

    def decided(kind: str, verdict: str) -> bool:
        return bool(cid) and any(d.get("kind") == kind and d.get("verdict") == verdict and d.get("subject") == cid
                                 and (d.get("actor") or {}).get("id") not in producers for d in decisions)

    # 같은 candidate의 rejected 판정은 해소되지 않은 충돌이다. 새 candidate로만 다시 판단한다(R7-01)
    conflicts = sorted({f"{d.get('kind')}:{(d.get('actor') or {}).get('id')}" for d in decisions
                        if d.get("subject") == cid and cid and d.get("kind") in ("independent_review", "acceptance")
                        and d.get("verdict") == "rejected"})
    review_ok = decided("independent_review", "pass") and not any(c.startswith("independent_review:") for c in conflicts)
    accepted = decided("acceptance", "accepted") and not conflicts
    delivery = data.get("delivery") or {}
    residuals = delivery.get("residual_risks") or []
    ownerless = sum(1 for r in residuals if not (isinstance(r, dict) and all(r.get(k) for k in ("risk", "owner", "condition"))))
    self_owned = sum(1 for r in residuals if isinstance(r, dict) and (r.get("owner_ref") == data.get("id") or r.get("owner") == data.get("id")))
    blocked_by: list[str] = []
    layout_ledger = load_layout(project)["delivery_ledger"]
    git_info = None
    mismatch: list[str] = []
    if observe_git and isinstance(project.source, FsSource):
        git_info = _git_state(project.source.root)
        if git_info is not None and checkpoint is not None:
            expected = [p for p in checkpoint.get("uncommitted") or [] if isinstance(p, str)]
            own = [packet_path, layout_ledger]  # Packet 자신·delivery ledger 갱신은 인계 기록 자체다(next_action.order (3))
            for path in git_info["dirty"]:
                if not _under(path, expected + own):
                    mismatch.append(f"unrecorded_change:{path}")
            for path in expected:
                if not any(_under(d, [path]) for d in git_info["dirty"]):
                    mismatch.append(f"recorded_change_absent:{path}")
            base_rev = checkpoint.get("base")
            if isinstance(base_rev, str) and base_rev and not git_info["head"].startswith(base_rev) and base_rev != git_info["head"]:
                mismatch.append(f"base_mismatch:{base_rev}!={git_info['head'][:12]}")
        elif git_info is not None and checkpoint is None and git_info["dirty"]:
            outside = [p for p in git_info["dirty"] if p not in (packet_path, layout_ledger)]
            if outside and state != "CLOSED":
                mismatch.extend(f"unrecorded_change:{p}" for p in outside)

    # (1)~(4) packet_semantics.next_action.order
    if state == "CLOSED":
        action = "none"
    elif recovery.get("status") == "blocked":
        action = "recover"
        blocked_by.append(f"recovery.blocked: {recovery.get('reason')}")
    elif mismatch:
        action = "reconcile_checkpoint"
        blocked_by.extend(mismatch)
    elif node == "admit":
        gaps = [k for k, v in (("authorization", scope.get("authorization")), ("objective", data.get("objective")),
                                ("criteria", criteria), ("scope.write", scope.get("write")),
                                ("harness_snapshot", snapshot)) if not v]
        if snapshot and project.content_id and snapshot != project.content_id:
            gaps.append("harness_snapshot≠project")
        action = "complete_admission" if gaps else "plan"
        blocked_by.extend(f"admit:{g}" for g in gaps)
    elif node == "plan":
        if not identity or not plan.get("summary"):
            action = "plan"
        elif gate_required and not gate_ok:
            action = "request_human_gate"
        else:
            action = "execute"
    elif node == "execute":
        if gate_required and not gate_ok:
            action = "request_human_gate"
        else:
            action = "verify" if cid else "execute"
    elif node in ("verify", "accept", "close"):
        def close_step() -> str:
            if state != "ACCEPTED":
                return "accept"
            return "deliver" if delivery.get("required") and not delivery.get("receipt") else "settle_close"

        if node == "verify":
            if not cid:
                action = "execute"
            elif missing or failing or verification.get("verdict") != "pass":
                action = "verify"
            elif independence_required and not review_ok:
                action = "independent_review"
            else:
                action = "accept"
        elif node == "accept":
            if state not in ("VERIFIED", "ACCEPTED"):
                action = "verify"
            elif not accepted:
                action = "accept"
            else:
                action = close_step() if state == "ACCEPTED" else "accept"
        else:
            action = close_step()
    elif node == "recover":
        action = "recover"
    else:
        action = None
        blocked_by.append(f"unknown_node:{node}")
    if action in ("deliver", "settle_close") and ownerless:
        blocked_by.append(f"residual_ownerless:{ownerless}")
    if action in ("deliver", "settle_close") and self_owned and contract_version(contract) >= 3:
        blocked_by.append(f"residual_owner_is_self:{self_owned}")

    layout = load_layout(project)
    sealed = sealed_paths(project, load_packets(project), layout)
    write = [w for w in scope.get("write") or [] if isinstance(w, str)]
    sealed_overlap = sorted({w for w in write for s in sealed if overlaps(w, s) and s != packet_path})

    result.update({
        "task_id": data.get("id"),
        "snapshot": snapshot,
        "contract_known": known,
        "contract_basis": "packet_snapshot" if known else "project_contract(대체 해석, 확정 아님)",
        "state": state, "node": node, "graph": graph, "role": role, "role_base": base,
        "effective_allow": effective,
        "write_scope": write,
        "deny": sorted(deny),
        "sealed_write_overlap": sealed_overlap,
        "human_gate": {"required": gate_required, "tags": tags, "satisfied": gate_ok, "plan_identity": identity},
        "candidate": {"id": cid, "producers": producers},
        "verification": {"verdict": verification.get("verdict"), "missing_criteria": missing, "failing_evidence": failing,
                         "decision_conflicts": conflicts,
                         "independence_required": independence_required, "independent_review_present": review_ok},
        "acceptance": {"present": accepted, "excluded_actors": producers},
        "residuals": {"total": len(residuals), "ownerless": ownerless, "self_owned": self_owned},
        "checkpoint": {"present": checkpoint is not None, "git": git_info, "mismatch": mismatch},
        "next_action": action,
        "blocked_by": blocked_by,
        "requires_judgment": JUDGMENT.get(node, []),
        "meaning": "결정적 projection이다. guard 충족·권한·인수·Human Gate 판단이 아니다.",
    })
    return result
