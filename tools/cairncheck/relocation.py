"""relocation ledger 검사와 옛 locator 해석(core.yaml artifact_lifecycle.relocation).

identity는 Git object 식별자와 같은 방식으로 계산한다.
- 파일: git-blob = sha1("blob <len>\\0" + bytes)
- 디렉터리: git-tree = 추적 + 미무시 파일로 만든 Git tree 해시(작업 트리) 또는 `git rev-parse <rev>:<path>`
도구는 ledger·파일을 수정하지 않는다.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .lifecycle import covers, norm_path
from .project import FsSource, GitSource, Project

MAX_CHAIN = 16


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _tree_from_entries(entries: dict[str, tuple[str, str]]) -> str:
    """entries: 상대경로 → (mode, sha). 중첩 tree를 만든 뒤 루트 tree 해시를 낸다."""
    children: dict[str, dict] = {}
    for rel, value in entries.items():
        node = children
        parts = rel.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        node[parts[-1]] = value

    def build(node: dict) -> str:
        items = []
        for name, value in node.items():
            if name.endswith("/"):
                items.append((name[:-1], "40000", build(value), name))
            else:
                mode, sha = value
                items.append((name, mode, sha, name))
        # Git은 디렉터리 이름 뒤에 '/'를 붙인 것처럼 정렬한다.
        items.sort(key=lambda item: item[3].encode())
        body = b"".join(f"{mode} {name}".encode() + b"\0" + bytes.fromhex(sha) for name, mode, sha, _ in items)
        return hashlib.sha1(b"tree %d\0" % len(body) + body).hexdigest()

    return build(children)


def worktree_identity(root: Path, path: str) -> str | None:
    target = root / path
    if target.is_symlink():
        return "git-blob:" + blob_id(os.readlink(target).encode())
    if target.is_file():
        return "git-blob:" + blob_id(target.read_bytes())
    if not target.is_dir():
        return None
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z", "--", path],
                            capture_output=True)
    if listed.returncode != 0:
        return None
    entries: dict[str, tuple[str, str]] = {}
    prefix = norm_path(path) + "/"
    for raw in listed.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode()
        if not rel.startswith(prefix):
            continue
        full = root / rel
        if full.is_symlink():
            entries[rel[len(prefix):]] = ("120000", blob_id(os.readlink(full).encode()))
        elif full.is_file():
            mode = "100755" if os.access(full, os.X_OK) else "100644"
            entries[rel[len(prefix):]] = (mode, blob_id(full.read_bytes()))
    if not entries:
        return None
    return "git-tree:" + _tree_from_entries(entries)


def identity_of(project: Project, path: str) -> str | None:
    source = project.source
    if isinstance(source, GitSource):
        result = subprocess.run(["git", "-C", str(source.repo), "cat-file", "-t", f"{source.rev}:{path}"],
                                capture_output=True, text=True)
        if result.returncode != 0:
            return None
        kind = result.stdout.strip()
        sha = subprocess.run(["git", "-C", str(source.repo), "rev-parse", f"{source.rev}:{path}"],
                             capture_output=True, text=True).stdout.strip()
        return f"git-{kind}:{sha}" if kind in ("blob", "tree") else None
    if isinstance(source, FsSource):
        return worktree_identity(source.root, path)
    return None


def exists(project: Project, path: str) -> bool:
    source = project.source
    if isinstance(source, FsSource):
        return (source.root / path).exists()
    return identity_of(project, path) is not None


@dataclass
class LedgerReport:
    present: bool
    path: str
    entries: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)  # {severity, code, where, message}

    def add(self, severity: str, code: str, where: str, message: str) -> None:
        self.findings.append({"severity": severity, "code": code, "where": where, "message": message})


def load_ledger(project: Project, ledger_path: str, contract: dict | None = None) -> LedgerReport:
    """ledger를 읽고 계약 schema(relocation_ledger)로 검사한다. 잘못된 항목을 조용히 버리지 않는다(R5)."""
    report = LedgerReport(False, ledger_path)
    doc = project.load(ledger_path)
    if doc.text is None:
        return report
    report.present = True
    if doc.error or not isinstance(doc.data, dict):
        report.add("error", "relocation_ledger_unparseable", ledger_path, str(doc.error))
        return report
    if doc.data.get("kind") != "relocation_ledger":
        report.add("error", "relocation_ledger_kind", ledger_path, f"kind {doc.data.get('kind')!r}")
        return report
    if contract is not None and "relocation_ledger" in ((contract.get("schemas") or {}).get("document") or {}).get("definitions", {}):
        from . import schema
        errors = schema.validate_definition(contract, "relocation_ledger", doc.data)
        for error in errors:
            report.add("error", "relocation_ledger_schema", f"{ledger_path}{error.path}", error.message)
        if errors:
            return report  # schema 실패 뒤의 해석은 하지 않는다
    entries = doc.data.get("entries")
    if not isinstance(entries, list):
        report.add("error", "relocation_ledger_schema", f"{ledger_path}/entries", "entries가 목록이 아니다")
        return report
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            report.add("error", "relocation_ledger_schema", f"{ledger_path}/entries/{index}", "항목이 mapping이 아니다")
    if any(f["severity"] == "error" for f in report.findings):
        return report
    report.entries = entries
    return report


def _moves_under(report: LedgerReport, path: str) -> list[dict]:
    """path 아래(path 자신 제외)를 from으로 하는 항목: 이동된 디렉터리의 일부를 다시 옮긴 경우."""
    path = norm_path(path)
    return [e for e in report.entries if norm_path(str(e.get("from") or "")).startswith(path + "/")]


def validate(project: Project, report: LedgerReport, check_identity: bool = True) -> None:
    seen_ids: set[str] = set()
    seen_from: dict[str, str] = {}
    for entry in report.entries:
        eid = str(entry.get("id"))
        where = f"{report.path}#{eid}"
        if eid in seen_ids:
            report.add("error", "relocation_duplicate_id", where, "ledger id 중복")
        seen_ids.add(eid)
        src = norm_path(str(entry.get("from") or ""))
        if not src:
            report.add("error", "relocation_from_missing", where, "from이 없다")
            continue
        if src in seen_from:
            report.add("error", "relocation_duplicate_from", where, f"같은 from이 {seen_from[src]}에도 있다")
        seen_from[src] = eid
        kind, target = entry.get("kind"), entry.get("to")
        if kind == "move":
            if not isinstance(target, str) or not target:
                report.add("error", "relocation_target_missing", where, "move인데 to가 없다")
                continue
            if norm_path(target) == src:
                report.add("error", "relocation_cycle", where, "from과 to가 같다")
            elif covers(src, norm_path(target)):
                # 7차 검토 R7-03: 자기 하위로의 이동은 경로가 끝없이 확장되는 cycle이다
                report.add("error", "relocation_target_inside_source", where, f"to {target}가 from {src}의 하위다")
        elif kind == "retire":
            if target is not None:
                report.add("error", "relocation_retire_with_target", where, "retire는 to가 null이어야 한다")
            if not entry.get("retrievable_at"):
                report.add("error", "relocation_retire_unretrievable", where, "retire에는 회수 위치(retrievable_at)가 필요하다")
        else:
            report.add("error", "relocation_kind", where, f"kind {kind!r}")
    by_from = {norm_path(str(e.get("from") or "")): e for e in report.entries}
    # chain·cycle·target·identity. 각 move의 bytes는 chain 끝까지 같아야 한다(R1).
    for entry in report.entries:
        if entry.get("kind") != "move" or not isinstance(entry.get("to"), str):
            continue
        eid = str(entry.get("id"))
        where = f"{report.path}#{eid}"
        final, steps, problem = resolve(report, str(entry.get("from")))
        if problem:
            report.add("error", problem, where, f"chain 해석 실패({steps}단)")
            continue
        target = norm_path(str(entry["to"]))
        follower = by_from.get(target)
        if follower is not None and follower.get("identity") != entry.get("identity"):
            report.add("error", "relocation_chain_identity_break", where,
                       f"다음 항목 {follower.get('id')}의 identity {follower.get('identity')}가 이 이동의 identity "
                       f"{entry.get('identity')}와 다르다(중간 내용 교체)")
            continue
        if not check_identity:
            continue
        if any(True for _ in _moves_under(report, target)):
            report.add("unevaluated", "relocation_identity_unverifiable", where,
                       f"{target}의 일부가 다시 옮겨져 디렉터리 identity를 대조할 수 없다(직접 증명 필요)")
            continue
        end, _, end_problem = resolve(report, target)
        if end_problem:
            report.add("error", end_problem, where, "to 이후 chain 해석 실패")
            continue
        if end is None:
            continue  # 이후 retire. retire 항목의 identity가 같은지는 follower 비교로 확인했다
        current = identity_of(project, end)
        if current is None:
            report.add("error", "relocation_target_missing", where, f"최종 위치 {end}가 없다")
        elif current != entry.get("identity"):
            report.add("error", "relocation_identity_mismatch", where,
                       f"최종 위치 {end}의 identity {current}가 기록 {entry.get('identity')}와 다르다(내용 변경은 relocation이 아니다)")


def check_against_baseline(project: Project, report: LedgerReport, base: Project, label: str) -> set[str]:
    """변경 전 판본(base)과 대조한다(2차 검토 R2-02). 반환: baseline에서 검증할 수 없었던 새 항목 id.

    - append-only: base ledger의 각 항목은 현재 ledger에 같은 id·같은 내용으로 남아 있어야 한다.
    - 새 항목의 identity는 base 판본에서 from 경로의 실제 identity와 같아야 한다(이동 전 bytes).
    """
    from .lifecycle import load_layout
    base_path = load_layout(base)["relocation_ledger"]
    base_report = load_ledger(base, base_path)
    if base_report.present and not report.present:
        report.add("error", "relocation_ledger_deleted", base_path,
                   f"{label}에 있던 ledger가 없다. 채택된 ledger는 지우거나 옮기지 않는다(append-only)")
    if base_report.present and base_path != report.path:
        report.add("error", "relocation_ledger_moved", report.path,
                   f"{label}의 ledger 위치 {base_path}가 바뀌었다. 기존 ledger를 옮기지 않는다")
    current = {str(e.get("id")): e for e in report.entries}
    for entry in base_report.entries:
        eid = str(entry.get("id"))
        if current.get(eid) != entry:
            report.add("error", "relocation_ledger_rewritten", f"{report.path}#{eid}",
                       f"{label}의 ledger 항목이 바뀌거나 사라졌다. ledger는 append-only다")
    known = {str(e.get("id")) for e in base_report.entries}
    unverifiable: set[str] = set()
    for entry in report.entries:
        eid = str(entry.get("id"))
        if eid in known or entry.get("kind") not in ("move", "retire"):
            continue
        before = identity_of(base, norm_path(str(entry.get("from") or "")))
        if before is None:
            unverifiable.add(eid)
            report.add("unevaluated", "relocation_source_unverifiable", f"{report.path}#{eid}",
                       f"{label}에 from이 없어 이동 전 identity를 대조하지 못했다")
        elif before != entry.get("identity"):
            report.add("error", "relocation_source_identity_mismatch", f"{report.path}#{eid}",
                       f"{label}의 from identity {before}가 기록 {entry.get('identity')}와 다르다(이동 전 bytes가 아니다)")
    return unverifiable


def baseline_check(project: Project, report: LedgerReport, since: str | None = None) -> None:
    """working tree 프로젝트면 HEAD(와 since)의 ledger·from bytes와 대조한다. health·relocations·evidence가 공유한다."""
    if not isinstance(project.source, FsSource):
        return
    root = project.source.root
    checked = 0
    for rev in ["HEAD"] + ([since] if since else []):
        ok = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet", rev], capture_output=True)
        if ok.returncode != 0:
            continue
        from .project import open_project
        base, _ = open_project(GitSource(root, rev), dict(project.contracts))
        check_against_baseline(project, report, base, rev)
        checked += 1
    if not checked:
        # 5차 검토 R5-02: 변경 전 판본이 하나도 없으면 이동 전 identity를 증명할 수 없다. 정상 이동으로 반환하지 않는다.
        for entry in report.entries:
            if entry.get("kind") in ("move", "retire"):
                report.add("unevaluated", "relocation_baseline_unavailable", f"{report.path}#{entry.get('id')}",
                           "변경 전 Git 판본이 없어 이동 전 identity를 대조하지 못했다")


def valid_moves(report: LedgerReport) -> list[tuple[str, str]]:
    """결함이 없는 move 항목의 (from, to). 봉인 예외는 이 정확한 쌍에만 적용한다."""
    bad = {f["where"].split("#", 1)[-1] for f in report.findings if f["severity"] in ("error", "unevaluated")}
    return [(norm_path(str(e.get("from"))), norm_path(str(e.get("to"))))
            for e in report.entries if e.get("kind") == "move" and isinstance(e.get("to"), str) and str(e.get("id")) not in bad]


def paired(moves: list[tuple[str, str]], old: str, new: str | None) -> bool:
    """old → new가 어떤 유효 move의 정확한 대응인가(new None이면 old가 유효 move의 원위치인가)."""
    for src, dst in moves:
        if covers(src, old):
            target = dst + old[len(src):]
            if new is None or norm_path(new) == target:
                return True
    return False


def resolve_trace(report: LedgerReport, path: str) -> tuple[str | None, list[str], str | None]:
    """resolve와 같지만 실제로 사용한 ledger 항목 id 목록을 함께 낸다(4차 검토 R4-03)."""
    current = norm_path(path)
    visited, used = {current}, []
    for _ in range(MAX_CHAIN):
        match = None
        for entry in report.entries:
            src = norm_path(str(entry.get("from") or ""))
            if src and covers(src, current):
                if match is None or len(src) > len(norm_path(str(match.get("from")))):
                    match = entry
        if match is None:
            return current, used, None
        used.append(str(match.get("id")))
        if match.get("kind") == "retire":
            return None, used, None
        target = norm_path(str(match.get("to") or ""))
        if not target:
            return None, used, "relocation_target_missing"
        current = target + current[len(norm_path(str(match.get("from")))):]
        if current in visited:
            return None, used, "relocation_cycle"
        visited.add(current)
    return None, used, "relocation_chain_too_long"


def invalid_ids(report: LedgerReport) -> set[str]:
    return {f["where"].split("#", 1)[-1] for f in report.findings if f["severity"] in ("error", "unevaluated") and "#" in f["where"]}


def resolve(report: LedgerReport, path: str) -> tuple[str | None, int, str | None]:
    """옛 경로를 ledger로 해석한다. (최종 경로 또는 None(retire), 단계 수, 문제 코드)."""
    current = norm_path(path)
    visited = {current}
    for step in range(1, MAX_CHAIN + 1):
        match = None
        for entry in report.entries:
            src = norm_path(str(entry.get("from") or ""))
            if src and covers(src, current):
                if match is None or len(src) > len(norm_path(str(match.get("from")))):
                    match = entry
        if match is None:
            return (current, step - 1, None) if step > 1 else (current, 0, None)
        if match.get("kind") == "retire":
            return None, step, None
        target = norm_path(str(match.get("to") or ""))
        if not target:
            return None, step, "relocation_target_missing"
        src = norm_path(str(match.get("from")))
        current = target + current[len(src):]
        if current in visited:
            return None, step, "relocation_cycle"
        visited.add(current)
    return None, MAX_CHAIN, "relocation_chain_too_long"
