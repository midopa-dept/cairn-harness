"""project health(core.yaml project_health). report-only이며 파일을 수정하지 않는다.

등급: error(계약 위반 확정) · warning · info · not_checked. 결과는 권한·인수·Human Gate 판단이 아니다.
다른 snapshot의 Packet은 schema를 소급하지 않고 구조만 읽으며 그 결과는 warning 이하다.
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import re
import subprocess
from pathlib import PurePosixPath
from typing import Any

from . import mdunits
from .lifecycle import (PacketView, classify, copy_places, covers, is_copy, git_rev_tokens, load_layout, load_packets, norm_path,
                        overlaps, sealed_owner, sealed_paths)
from .project import FsSource, GitSource, Project, contract_version
from .relocation import check_against_baseline, exists, load_ledger, paired, resolve, valid_moves, validate

SEVERITIES = ("error", "warning", "info", "not_checked")
MEANING = ("project health 결과는 선언된 계약에 대한 결정적 신호다. 권한·인수·Human Gate 판단·의미적 정확성이 아니다.")
NOT_CHECKED_ALWAYS = [
    "index 본문의 의미적 최신성(판본 표식 밖의 서술)",
    "adapter 문장의 의미적 authority 확대 여부(구조 신호만 검사)",
    "residual 해소 근거의 실질성",
    "검증 surface가 실제로 요구를 덮는가",
]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TASK_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")
DEFAULTS = {"raw_evidence_warn_bytes": 20 * 1024 * 1024, "packet_warn_bytes": 64 * 1024, "adapter_warn_bytes": 4096}
CODEX_LIMIT = 32 * 1024
INSTRUCTION_WARN = 24 * 1024


class Health:
    def __init__(self, project: Project, since: str | None = None, today: _dt.date | None = None):
        self.project = project
        self.since = since
        self.today = today or _dt.date.today()
        self.findings: list[dict] = []
        self.not_checked: list[str] = list(NOT_CHECKED_ALWAYS)
        self.layout = load_layout(project)
        self.packets = load_packets(project)
        self.by_id = {p.id: p for p in self.packets if p.id and not p.copy}
        self.sealed = sealed_paths(project, self.packets, self.layout)
        config = project.load(".harness/project.yaml").data
        self.config = config if isinstance(config, dict) else {}
        health = self.config.get("health") if isinstance(self.config.get("health"), dict) else {}
        self.settings = {**DEFAULTS, **{k: v for k, v in health.items() if k in DEFAULTS}}
        self.indexes = [i for i in health.get("indexes") or [] if isinstance(i, dict)]
        self.contract = project.contracts.get(project.content_id)
        self.ledger = load_ledger(project, self.layout["relocation_ledger"], self.contract)
        self._sealed_base = dict(self.sealed)
        self._validated = False

    @staticmethod
    def _propagate(sealed: dict[str, str], ledger, valid: set[str] | None = None) -> dict[str, str]:
        """봉인 경로(또는 그 일부)를 옮기면 각 이동 단계의 새 위치도 봉인이다(R2-02·R6-02).
        유효 move만, 자기 하위로의 move는 제외하고, 최대 MAX_CHAIN 라운드로 한정한다(7차 검토 R7-03)."""
        from .relocation import MAX_CHAIN
        if not ledger.present or not ledger.entries:
            return dict(sealed)
        moves = []
        for entry in ledger.entries:
            if entry.get("kind") != "move" or not isinstance(entry.get("to"), str):
                continue
            if valid is not None and str(entry.get("id")) not in valid:
                continue
            src, dst = norm_path(str(entry.get("from") or "")), norm_path(entry["to"])
            if not src or src == dst or covers(src, dst):
                continue
            moves.append((src, dst))
        result = dict(sealed)
        for _ in range(MAX_CHAIN):
            added: dict[str, str] = {}
            for src, dst in moves:
                why = sealed_owner(result, src)
                if why and dst not in result:
                    added.setdefault(dst, f"{why} → 이동")
                for root in list(result):
                    if covers(src, root) and root != src:
                        moved = dst + root[len(src):]
                        if moved not in result:
                            added.setdefault(moved, f"{result[root]} → 이동")
            if not added:
                break
            result.update(added)
        return result

    def _valid_ids(self) -> set[str]:
        from .relocation import invalid_ids
        bad = invalid_ids(self.ledger)
        return {str(e.get("id")) for e in self.ledger.entries} - bad

    def _ensure_validated(self) -> None:
        """ledger 결정적 검사와 변경 전 판본 대조를 한 번만 수행한다. 현재 ledger가 없어도 baseline에 있었으면 위반이다(R3-01)."""
        if self._validated:
            return
        self._validated = True
        if self.ledger.present and not any(f["severity"] == "error" for f in self.ledger.findings):
            validate(self.project, self.ledger)
        if not any(f["severity"] == "error" and f["code"].startswith("relocation_ledger_") and f["code"] not in
                   ("relocation_ledger_rewritten",) for f in self.ledger.findings):
            from .relocation import baseline_check
            baseline_check(self.project, self.ledger, self.since)
        # 봉인 전파는 bounded 검증 뒤에 한다(R7-03). 선언된 이동은 유효성과 무관하게 목적지를 봉인한다:
        # 전파는 보호를 늘리는 방향이므로 보수적이다. 면제(예외)에는 유효 move만 쓴다(valid_moves·_valid_ids).
        self.sealed = self._propagate(self._sealed_base, self.ledger)

    def add(self, severity: str, check: str, where: str, message: str, **extra: Any) -> None:
        self.findings.append({"severity": severity, "check": check, "where": where, "message": message, **extra})

    # ------------------------------------------------------------------ checks
    def packet_parse(self) -> None:
        copies = [v for v in self.packets if v.copy]
        if copies:
            self.add("info", "packet_copy_in_evidence", "(project)",
                     f"evidence 위치 안의 Packet 사본 {len(copies)}개는 live Packet 검사에서 제외했다")
        for view in self.packets:
            if view.copy:
                continue
            if view.error:
                self.add("warning", "packet_parse", view.path,
                         f"YAML 1.2로 해석하지 못해 이 Packet의 검사를 미평가로 둔다(역사 Packet은 재작성하지 않는다): {view.error[:160]}")
            elif view.size > self.settings["packet_warn_bytes"]:
                self.add("info", "packet_size", view.path, f"Packet {view.size} bytes(기준 {self.settings['packet_warn_bytes']}). retrieval 비용 신호")
            if view.data and view.finished_not_closed:
                self.add("info", "accepted_not_closed", view.path,
                         "close 노드에서 receipt와 함께 ACCEPTED로 남은 Packet. 활성으로 보지 않으며 봉인 판정은 CLOSED·layout.sealed 기준")

    def _resolve_link(self, index_path: str, target: str) -> str | None:
        target = target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            return None
        joined = PurePosixPath(index_path).parent / target
        parts: list[str] = []
        for part in joined.parts:
            if part == "..":
                if parts:
                    parts.pop()
            elif part != ".":
                parts.append(part)
        return "/".join(parts)

    def _exists_or_relocated(self, path: str) -> tuple[bool, str | None]:
        if exists(self.project, path):
            return True, None
        if self.ledger.present:
            final, steps, problem = resolve(self.ledger, path)
            if steps and not problem:
                if final is None:
                    return True, "retired"
                if exists(self.project, final):
                    return True, final
        return False, None

    def index(self) -> None:
        if not self.indexes:
            self.not_checked.append("index 검사: project.yaml health.indexes 미선언")
            return
        for entry in self.indexes:
            path = entry.get("path")
            text = self.project.source.read(path) if isinstance(path, str) else None
            if text is None:
                self.add("warning", "index_target_missing", str(path), "선언된 index 파일을 읽지 못했다")
                continue
            lines = text.splitlines()
            for section in entry.get("current_sections") or []:
                span, error = mdunits.resolve_section(lines, section)
                if span is None:
                    self.add("warning", "index_section_unresolved", f"{path}#{section}", str(error))
                    continue
                for line in lines[span[0]:span[1]]:
                    for link in LINK.findall(line):
                        target = self._resolve_link(path, link)
                        if not target:
                            continue
                        view = next((p for p in self.packets if norm_path(p.path) == target), None)
                        if view is not None and view.closed:
                            self.add("warning", "index_current_closed_task", f"{path}#{section}",
                                     f"current 절이 CLOSED Task {view.id}를 가리킨다(policies.closeout_freshness)", task=view.id)
            marker = entry.get("version_marker")
            for section in entry.get("canonical_sections") or []:
                span, error = mdunits.resolve_section(lines, section)
                if span is None:
                    self.add("warning", "index_section_unresolved", f"{path}#{section}", str(error))
                    continue
                for line in lines[span[0]:span[1]]:
                    for link in LINK.findall(line):
                        target = self._resolve_link(path, link)
                        if not target:
                            continue
                        cls = classify(target, self.layout, self.packets, self.project.task_root)
                        if cls == "historical":
                            self.add("warning", "index_canonical_historical", f"{path}#{section}", f"canonical 절이 historical {target}를 가리킨다")
                        if marker and target.endswith(".md"):
                            body = self.project.source.read(target) or ""
                            found = re.search(marker, "\n".join(body.splitlines()[:15]))
                            label = (found.groupdict().get("v") or found.group(0)) if found else None
                            listed = re.search(marker, line)
                            row_label = (listed.groupdict().get("v") or listed.group(0)) if listed else None
                            if label and row_label and row_label != label:
                                self.add("warning", "index_version_mismatch", f"{path}#{section}",
                                         f"index 행은 {target}를 {row_label}로 적지만 현재 판본은 {label}이다", target=target)
                            elif label and not row_label:
                                self.add("info", "index_version_not_listed", f"{path}#{section}",
                                         f"index 행에 {target}의 판본 표식이 없다(현재 {label}). 신선도를 결정적으로 대조할 수 없다", target=target)
            for link in LINK.findall(text):
                target = self._resolve_link(path, link)
                if target and not self._exists_or_relocated(target)[0]:
                    self.add("warning", "index_target_missing", path, f"index 링크 대상이 없다: {target}")

    def references(self) -> None:
        external = 0
        for view in self.packets:
            if not view.data or view.copy:
                continue
            for item in view.artifacts():
                path = item.get("path")
                if not isinstance(path, str) or not path:
                    continue
                if re.match(r"^[a-z][a-z0-9+.-]*:", path):
                    external += 1  # figma: 등 외부 locator는 저장소 경로가 아니다
                    continue
                ok, moved = self._exists_or_relocated(norm_path(path))
                if ok:
                    if moved:
                        self.add("info", "artifact_reference_relocated", f"{view.path}/artifacts/{item.get('id')}",
                                 f"{path} → {moved}(ledger 해석)")
                    continue
                historical = any(self._git_has(rev, path) for rev in git_rev_tokens(item.get("revision")))
                if historical:
                    continue  # 기록된 revision에서 회수된다
                severity = "error" if view.is_v3 and not view.closed else "warning"
                self.add(severity, "artifact_reference_unresolved", f"{view.path}/artifacts/{item.get('id')}",
                         f"{path}가 현재 트리·relocation ledger·기록 revision 어디에서도 해결되지 않는다", task=view.id)
        if external:
            self.add("info", "artifact_reference_external", "(project)", f"저장소 밖 locator {external}개는 해석하지 않았다")

    def _git_has(self, rev: str, path: str) -> bool:
        repo = self._repo()
        if repo is None:
            return False
        return subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{rev}:{path}"], capture_output=True).returncode == 0

    def _repo(self) -> str | None:
        source = self.project.source
        if isinstance(source, FsSource):
            return str(source.root)
        if isinstance(source, GitSource):
            return str(source.repo)
        return None

    def relocations(self) -> None:
        self._ensure_validated()
        if not self.ledger.present and not self.ledger.findings:
            self.not_checked.append(f"relocation 검사: ledger {self.layout['relocation_ledger']} 없음(opt-in, 변경 전 판본에도 없음)")
            return
        self._sealed_retire()
        self._packet_relocation()
        for item in self.ledger.findings:
            if item["severity"] == "unevaluated":
                # 6차 검토 R6-02: 증명하지 못한 relocation은 clean으로 보고하지 않는다
                self.not_checked.append(f"relocation identity 미평가: {item['where']}")
                self.add("warning", "relocation_integrity", item["where"], f"{item['code']}: {item['message']}", code=item["code"])
            else:
                self.add(item["severity"], "relocation_integrity", item["where"], f"{item['code']}: {item['message']}", code=item["code"])

    def _packet_relocation(self) -> None:
        """Task Packet은 relocation하지 않는다(ADR-1 class 표, 8차 검토 R8-03). 옮기면 inventory와 봉인이 사라진다.
        Task Packet은 확장자가 아니라 내용(`kind: task`, evidence 사본 제외)으로 판정한다(9차 검토 R9-04).
        현재·HEAD의 Packet 경로, task_root 전체, ledger identity가 가리키는 Git blob/tree 안의 task 문서를 본다."""
        packet_paths = [norm_path(p.path) for p in self.packets if not p.copy]
        repo = self._repo()
        if isinstance(self.project.source, FsSource) and repo is not None:
            ok = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", "HEAD"], capture_output=True)
            if ok.returncode == 0:
                from .project import open_project
                base, _ = open_project(GitSource(self.project.source.root, "HEAD"), dict(self.project.contracts))
                packet_paths += [norm_path(p.path) for p in load_packets(base) if not p.copy]
        task_root = norm_path(self.project.task_root)
        declared, configured = copy_places(self.project, self.packets)
        live_ids = {p.id for p in self.packets if p.data is not None and p.id and not p.copy}

        def live_location(path: str, pid: str | None) -> bool:  # live Task Packet 위치: task_root 안이고 사본 판정이 아님
            # 이동 source 자신은 현재 트리에 없으므로 live_ids에 들어 있는 같은 id는 다른 경로의 live Packet이다(12차 검토 R12-04)
            return covers(task_root, path) and not is_copy(path, pid, task_root, declared, configured, live_ids)
        for entry in self.ledger.entries:
            src = norm_path(str(entry.get("from") or ""))
            if not src:
                continue
            hit = next((p for p in packet_paths if covers(src, p)), None)
            if hit is None and covers(src, task_root):
                hit = task_root
            if hit is None and repo is not None:  # 이미 이동돼 현재·HEAD에 없는 Packet: 원 bytes의 live 위치 task 문서
                hit = self._identity_holds_packet(repo, str(entry.get("identity") or ""), src, live_location)
            if hit:
                self.ledger.add("error", "relocation_task_packet", f"{self.ledger.path}#{entry.get('id')}",
                                f"Task Packet({hit})은 relocation·retire하지 않는다. 역사 Packet은 task_root에 남는다")

    @staticmethod
    def _identity_holds_packet(repo: str, identity: str, src: str, live_location) -> str | None:
        """ledger identity(git-blob·git-tree)의 원 bytes 중 live Packet 위치(task_root 안, 사본 위치 밖)의 task 문서 경로.
        문서·evidence 안의 Packet snapshot은 사본이므로 이동할 수 있다(10차 검토 R10-04)."""
        from . import yamlio
        kind, _, oid = identity.partition(":")
        if kind == "git-blob":
            blobs = [(oid, src)]
        elif kind == "git-tree":
            listed = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "-z", oid], capture_output=True)
            blobs = []
            for row in listed.stdout.split(b"\0"):
                meta, _, name = row.partition(b"\t")
                parts = meta.split()
                if len(parts) == 3 and parts[1] == b"blob":
                    blobs.append((parts[2].decode(), f"{src}/{name.decode('utf-8', 'replace')}"))
        else:
            return None
        for oid, path in blobs:
            if not path.endswith((".yaml", ".yml")):
                continue
            shown = subprocess.run(["git", "-C", repo, "cat-file", "-p", oid], capture_output=True)
            if shown.returncode != 0:
                continue
            data, error = yamlio.load(shown.stdout.decode("utf-8", "replace"))
            if error is None and isinstance(data, dict) and data.get("kind") == "task" and isinstance(data.get("workflow"), dict) \
                    and live_location(path, data.get("id") if isinstance(data.get("id"), str) else None):
                return path
        return None

    def _sealed_retire(self) -> None:
        """봉인 기록(이동된 위치 포함)은 retire할 수 없다(core artifact_lifecycle.relocation.retire, 6차 검토 R6-02)."""
        if getattr(self, "_retire_checked", False):
            return
        self._retire_checked = True
        sealed = self._propagate(self._sealed_base, self.ledger)
        head = self._sealed_at("HEAD") if isinstance(self.project.source, FsSource) and self._repo() is not None else None
        if head:
            sealed.update(self._propagate(head, self.ledger))
        for entry in self.ledger.entries:
            if entry.get("kind") != "retire":
                continue
            src = norm_path(str(entry.get("from") or ""))
            why = sealed_owner(sealed, src) or next((w for r, w in sealed.items() if covers(src, r)), None)
            if why:
                self.ledger.add("error", "sealed_retired", f"{self.ledger.path}#{entry.get('id')}",
                                f"봉인 기록({why})은 retire할 수 없다. compaction·정리도 삭제가 아니다")

    def sealed_scope(self) -> None:
        self._ensure_validated()
        # 예외는 이 Task의 ledger move가 기록한 from·to 경로 안의 쓰기뿐이다(R3). 상위 디렉터리 전체는 면제하지 않는다.
        moves: dict[str, list[str]] = {}
        for e in self.ledger.entries:
            if e.get("kind") == "move":
                moves.setdefault(str(e.get("task")), []).extend(
                    norm_path(str(p)) for p in (e.get("from"), e.get("to")) if isinstance(p, str))
        for view in self.packets:
            if not view.active:
                continue
            exempt_roots = moves.get(view.id, [])
            for write in view.scope_write():
                hits = [(root, why) for root, why in self.sealed.items() if root != norm_path(view.path) and overlaps(write, root)]
                if not hits:
                    continue
                if any(covers(root, write) for root in exempt_roots):
                    self.add("info", "sealed_relocation_scope", f"{view.path}/scope/write",
                             f"{write}는 봉인 경로와 겹치지만 이 Task의 ledger move from·to 안이다")
                    continue
                severity = "error" if view.is_v3 else "warning"
                sample = ", ".join(f"{r}({w})" for r, w in hits[:3])
                self.add(severity, "sealed_write_scope", f"{view.path}/scope/write",
                         f"활성 Task {view.id}의 쓰기 범위 {write}가 봉인 경로 {len(hits)}개와 겹친다: {sample}",
                         task=view.id, overlaps=len(hits))

    def _status(self) -> list[tuple[str, str, str | None]]:
        """working tree 변경 (code, path, 원경로). 미추적 파일 포함."""
        out = subprocess.run(["git", "-C", self._repo(), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                             capture_output=True)
        items = [p.decode() for p in out.stdout.split(b"\0")]
        result, index = [], 0
        while index < len(items):
            entry = items[index]
            index += 1
            if len(entry) < 4:
                continue
            code, path, orig = entry[:2].strip(), entry[3:], None
            if code.startswith("R") or code.startswith("C"):
                orig = items[index] if index < len(items) else None
                index += 1
            result.append((code, path, orig))
        return result

    def _diff(self, rev: str) -> list[tuple[str, str, str | None]]:
        out = subprocess.run(["git", "-C", self._repo(), "-c", "core.quotepath=off", "diff", "--name-status", "-z", "-M", rev, "HEAD"],
                             capture_output=True)
        items = [p.decode() for p in out.stdout.split(b"\0")]
        result, index = [], 0
        while index < len(items):
            code = items[index]
            index += 1
            if not code:
                continue
            if code.startswith(("R", "C")):
                orig, path = items[index], items[index + 1]
                index += 2
            else:
                path, orig = items[index], None
                index += 1
            result.append((code, path, orig))
        return result

    def _sealed_at(self, rev: str) -> dict[str, str] | None:
        from .project import open_project
        try:
            base_project, _ = open_project(GitSource(self.project.source.root, rev), dict(self.project.contracts))
            base_layout = load_layout(base_project)
            sealed = sealed_paths(base_project, load_packets(base_project), base_layout)
            return self._propagate(sealed, load_ledger(base_project, base_layout["relocation_ledger"]))
        except Exception as error:  # pragma: no cover - 진단
            self.add("info", "sealed_baseline_unavailable", rev, str(error))
            return None

    def sealed_modified(self) -> None:
        """봉인 bytes의 수정·삭제와 봉인 namespace의 새 출력(R2). 기준은 변경 전 판본(HEAD·--since)의 봉인 집합이다.
        working tree에서 Packet을 OPEN으로 되돌리거나 manifest를 지워도 봉인이 풀리지 않는다."""
        if not isinstance(self.project.source, FsSource) or self._repo() is None:
            self.not_checked.append("봉인 수정 검사: Git working tree가 아니라 대조하지 않음")
            return
        head = subprocess.run(["git", "-C", self._repo(), "rev-parse", "--verify", "--quiet", "HEAD"], capture_output=True)
        if head.returncode != 0:
            self.not_checked.append("봉인 수정 검사: HEAD commit이 없음")
            return
        self._ensure_validated()
        moves = valid_moves(self.ledger)  # 결함 없는 move의 정확한 from→to 쌍만 예외
        checks = []
        base_head = self._sealed_at("HEAD")
        if base_head is not None:
            checks.append(("working tree", base_head, self._status()))
        if self.since:
            base_since = self._sealed_at(self.since)
            if base_since is not None:
                checks.append((f"{self.since}..HEAD", base_since, self._diff(self.since)))
        for label, baseline, changes in checks:
            for code, path, orig in changes:
                new = norm_path(path)
                old = norm_path(orig) if orig else None
                if code.startswith(("R", "C")) and old:
                    old_sealed, new_sealed = sealed_owner(baseline, old), sealed_owner(baseline, new)
                    if (old_sealed or new_sealed) and not paired(moves, old, new):
                        target = old if old_sealed else new
                        check = "sealed_modified" if old_sealed else "sealed_namespace_added"
                        self.add("error", check, target, f"{label}: {old} → {new} 이동이 유효한 ledger move의 정확한 대응이 아니다")
                    continue
                why = sealed_owner(baseline, new)
                if not why:
                    continue
                if code in ("A", "??"):
                    sources = [src + new[len(dst):] for src, dst in moves if covers(dst, new)]
                    if not any(sealed_owner(baseline, s) for s in sources):
                        self.add("error", "sealed_namespace_added", new,
                                 f"{label}: 봉인 namespace({why})에 새 파일이 생겼다. 새 출력은 현재 Task namespace에 쓴다")
                    continue
                if code.startswith("D") and paired(moves, new, None):
                    continue  # 유효 move의 원위치. 새 위치 존재와 bytes는 relocation 검사가 본다
                self.add("error", "sealed_modified", new, f"{label}: 봉인 경로({why})가 변경됐다(상태 {code}). 정정은 새 기록으로 덧붙인다")

    def residuals(self) -> None:
        raw_dispositions: list[tuple[str, dict]] = []
        refs: set[str] = set()
        raw_inherited: list[tuple[str, str]] = []
        for view in self.packets:
            if not view.data or view.copy:
                continue
            delivery = view.data.get("delivery") or {}
            for d in delivery.get("residual_dispositions") or []:
                if isinstance(d, dict) and isinstance(d.get("ref"), str):
                    raw_dispositions.append((view.id, d))
            for index, r in enumerate(delivery.get("residual_risks") or []):
                if isinstance(r, dict):
                    refs.add(f"{view.id}#{r.get('id') or index}")
                    if isinstance(r.get("inherited_from"), str):
                        raw_inherited.append((f"{view.id}#{r.get('id') or index}", r["inherited_from"]))
        # 처분은 연결이 결정적으로 해결될 때만 원 residual을 닫는다(R4·R2-03). 해결되지 않으면 원 위험은 open이다.
        dispositions: dict[str, list[str]] = {}
        successors: dict[str, set[str]] = {}
        terminal: set[str] = set()
        for owner, d in raw_dispositions:
            ref, status, target = d["ref"], d.get("status"), d.get("to")
            label = f"{owner}:{status}"
            if ref not in refs:
                self.add("warning", "residual_disposition_dangling", ref, f"disposition({label})이 존재하지 않는 residual을 가리킨다")
                continue
            if status in ("transferred", "superseded"):
                if not isinstance(target, str) or target not in refs or target == ref:
                    self.add("warning", "residual_disposition_dangling_target", ref,
                             f"{label}의 to {target!r}가 존재하는 다른 residual이 아니다. 원 residual을 open으로 유지한다")
                    continue
            dispositions.setdefault(ref, []).append(label)
            if status in ("transferred", "superseded"):
                successors.setdefault(ref, set()).add(target)
            else:
                terminal.add(ref)
        for ref, by in dispositions.items():
            if len(by) > 1:
                self.add("warning", "residual_disposition_duplicate", ref, f"여러 disposition: {', '.join(by)}")
        inherited: set[str] = set()
        for child, parent in raw_inherited:
            if parent not in refs or parent == child:
                self.add("warning", "residual_inherited_dangling", child, f"inherited_from {parent}가 존재하는 다른 residual이 아니다")
                continue
            inherited.add(parent)
            successors.setdefault(parent, set()).add(child)
        from .lifecycle import residual_closure
        closed_refs, cyclic = residual_closure(refs, terminal, successors)
        # 다른 residual의 위험을 이어받은 후속 residual. 담은 Packet이 진행 중이어도 owner·due를 본다(13차 검토 R13-02)
        carriers = {target for targets in successors.values() for target in targets}
        for ref in sorted(cyclic):
            self.add("warning", "residual_transfer_cycle", ref,
                     "이전·이어받기 연결이 순환해 위험을 실제로 이어받은 residual이 없다. 원 residual을 open으로 유지한다")
        legacy_unresolvable = 0
        for view in self.packets:
            if not view.data or view.copy:
                continue
            residuals = (view.data.get("delivery") or {}).get("residual_risks") or []
            for index, r in enumerate(residuals):
                where = f"{view.path}/delivery/residual_risks/{index}"
                if not isinstance(r, dict):
                    if view.is_v3 and view.closed:
                        self.add("error", "residual_ownerless", where, "소유자 구조 없는 residual로 종료됐다", task=view.id)
                    continue
                ref = f"{view.id}#{r.get('id') or index}"
                if ref in closed_refs or (not view.closed and ref not in carriers):
                    continue  # 처분됐거나, 아직 소유 Task가 진행 중인 자기 residual
                kind, owner_ref = r.get("owner_kind"), r.get("owner_ref")
                if isinstance(r.get("due"), str):
                    try:
                        if _dt.date.fromisoformat(r["due"]) < self.today:
                            self.add("warning", "residual_condition_elapsed", where, f"due {r['due']}가 지났는데 처분 기록이 없다", ref=ref)
                    except ValueError:
                        pass
                if owner_ref:
                    if kind in ("task", None) and owner_ref in self.by_id:
                        target = self.by_id[owner_ref]
                        if target.closed:
                            self.add("warning", "residual_owner_closed", where,
                                     f"open residual의 owner {owner_ref}가 CLOSED다{' (자기 자신)' if owner_ref == view.id else ''}", ref=ref)
                    elif kind == "task":
                        self.add("warning", "residual_owner_missing", where, f"owner Task {owner_ref}가 없다", ref=ref)
                    continue
                owner = str(r.get("owner") or "")
                ids = [t for t in TASK_ID.findall(owner) if t in self.by_id]
                if not ids:
                    if view.is_v3:
                        self.add("info", "residual_owner_unresolvable", where, f"owner_ref가 없어 owner를 해석할 수 없다: {owner[:60]}", ref=ref)
                    else:
                        legacy_unresolvable += 1
                    continue
                live = [t for t in ids if not self.by_id[t].closed]
                if not live:
                    self.add("warning", "residual_owner_closed", where,
                             f"open residual의 owner가 가리키는 Task {', '.join(ids)}가 모두 CLOSED다"
                             f"{' (자기 자신 포함)' if view.id in ids else ''}{'' if view.is_v3 else ' [이전 snapshot: 문자열 해석]'}",
                             ref=ref, legacy=not view.is_v3)
        if legacy_unresolvable:
            self.add("info", "residual_owner_unresolvable", "(이전 snapshot)",
                     f"자유문자열 owner로 Task를 해석할 수 없는 open residual {legacy_unresolvable}건(소급 강제하지 않음)")

    def evidence_growth(self) -> None:
        from .evidence import _resolver, task_evidence
        find = _resolver(self.project, self.layout)
        limit = self.settings["raw_evidence_warn_bytes"]
        total = {"authoritative": 0, "supporting": 0, "raw": 0}
        for view in self.packets:
            if not view.data or view.copy:
                continue
            row = task_evidence(self.project, view, self.layout, find)
            for tier in total:
                total[tier] += row["tiers"][tier]["bytes"]
            raw = row["tiers"]["raw"]["bytes"]
            if raw > limit:
                self.add("warning", "raw_evidence_growth", view.path, f"raw evidence {raw} bytes(기준 {limit})", task=view.id)
        self.add("info", "evidence_bytes", "(project)", f"tier별 bytes {total}")
        current = list(self.layout["canonical"] or []) + list(self.layout["operational"] or [])
        if not self.layout.declared or not current:
            self.not_checked.append("current 문서의 raw evidence 검사: layout.canonical/operational 미선언")
            return
        counts: dict[str, list[int]] = {}
        for root in current:
            for path in self.project.source.list(root) or []:
                if self.layout.is_raw(path):
                    top = "/".join(path.split("/")[:2])
                    counts.setdefault(top, []).append(len(self.project.source.read_bytes(path) or b""))
        for top, sizes in sorted(counts.items()):
            self.add("warning", "raw_evidence_in_current_docs", top, f"current 문서 영역의 raw evidence {len(sizes)}개 {sum(sizes)} bytes")

    def concurrency(self) -> None:
        active = [p for p in self.packets if p.active and not p.blocked]
        for i, a in enumerate(active):
            for b in active[i + 1:]:
                shared = sorted({x for x in a.scope_write() for y in b.scope_write() if overlaps(x, y)})
                shared = [s for s in shared if s not in (".harness/project.yaml",)]
                if shared:
                    self.add("warning", "concurrent_write_scope", f"{a.id} ↔ {b.id}", f"활성 Task 쓰기 범위가 겹친다: {shared[:5]}")

    def registry(self) -> None:
        path = self.layout["verification_registry"]
        if not path:
            self.not_checked.append("검증 surface registry: layout.verification_registry 미선언")
            return
        doc = self.project.load(path)
        if doc.text is None:
            self.add("error", "verification_registry_invalid", path, "선언된 registry 파일이 없다")
            return
        if doc.error or not isinstance(doc.data, dict) or doc.data.get("kind") != "verification_registry":
            self.add("error", "verification_registry_invalid", path, str(doc.error or "kind verification_registry 아님"))
            return
        if self.contract is not None and "verification_registry" in (self.contract.get("schemas", {}).get("document", {}).get("definitions", {})):
            from . import schema as _schema
            errors = _schema.validate_definition(self.contract, "verification_registry", doc.data)
            for error in errors:
                self.add("error", "verification_registry_invalid", f"{path}{error.path}", error.message)
            if errors:
                return
        registered: set[str] = set()
        for surface in doc.data.get("surfaces") or []:
            for p in surface.get("paths") or []:
                registered.add(norm_path(p))
                if not exists(self.project, p):
                    self.add("error", "verification_surface_missing", f"{path}#{surface.get('id')}", f"surface 구성 경로 {p}가 없다")
        excluded = {norm_path(e.get("path")) for e in doc.data.get("exclusions") or [] if isinstance(e, dict)}
        files = self._all_files()
        for pattern in doc.data.get("discovery") or []:
            for f in files:
                if fnmatch.fnmatch(f, pattern) and f not in registered and f not in excluded:
                    self.add("warning", "verification_surface_unregistered", f, f"discovery {pattern}로 찾았지만 등록·제외 어디에도 없다")

    def _all_files(self) -> list[str]:
        repo = self._repo()
        if repo is None:
            return []
        if isinstance(self.project.source, GitSource):
            out = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "-z", "--name-only", self.project.source.rev], capture_output=True)
        else:
            out = subprocess.run(["git", "-C", repo, "ls-files", "-z", "-co", "--exclude-standard"], capture_output=True)
        return [p.decode() for p in out.stdout.split(b"\0") if p]

    def coverage_owners(self) -> None:
        for view in self.packets:
            if not view.data or view.copy:
                continue
            ref = (view.data.get("plan") or {}).get("coverage_matrix") if isinstance(view.data.get("plan"), dict) else None
            entry = view.manifest().get(ref) if isinstance(ref, str) else None
            if not entry or not isinstance(entry.get("path"), str):
                continue
            matrix = self.project.load(entry["path"]).data
            if not isinstance(matrix, dict):
                continue
            for row in matrix.get("obligations") or []:
                if not isinstance(row, dict) or row.get("disposition") != "owned":
                    continue
                crit = [str(c).split("#", 1)[0] for c in row.get("owner_criterion") or []]
                for task in row.get("owner_task") or []:
                    child = self.by_id.get(task)
                    if child is not None and child.closed and task not in crit:
                        self.add("warning", "coverage_owner_closed_unrefined", f"{entry['path']}#{row.get('local_id')}",
                                 f"owner child {task}가 CLOSED인데 owner_criterion이 없다")

    def adapters(self) -> None:
        src = self.project.source
        agents = src.read("AGENTS.md")
        claude = src.read("CLAUDE.md")
        if agents is None:
            self.add("warning", "adapter_import_missing", "AGENTS.md", "공통 계약 AGENTS.md가 없다")
        else:
            size = len(agents.encode())
            if size > CODEX_LIMIT:
                self.add("error", "instruction_size_limit", "AGENTS.md", f"{size} bytes > Codex 기본 32 KiB. 뒤쪽 공통 규칙이 Codex에서 빠진다")
            elif size > INSTRUCTION_WARN:
                self.add("warning", "instruction_size_limit", "AGENTS.md", f"{size} bytes. Codex 기본 상한 32 KiB에 근접")
        if claude is not None and agents is not None:
            lines = [l.strip() for l in claude.splitlines()]
            if "@AGENTS.md" not in lines:
                self.add("error", "adapter_import_missing", "CLAUDE.md",
                         "CLAUDE.md가 @AGENTS.md를 import하지 않는다. Claude Code는 CLAUDE.md가 있으면 AGENTS.md를 직접 읽지 않는다")
        adapter_texts = {"CLAUDE.md": claude} if claude is not None else {}
        for path in src.list(".harness/adapters") or []:
            if path.endswith(".md"):
                adapter_texts[path] = src.read(path)
        common = set()
        if agents:
            common = {self._norm(p) for p in re.split(r"\n\s*\n", agents) if len(self._norm(p)) >= 60}
        for path, text in adapter_texts.items():
            if not text:
                continue
            body = "\n".join(l for l in text.splitlines() if not l.strip().startswith("@"))
            limit = self.settings["adapter_warn_bytes"] if path == "CLAUDE.md" else 2 * self.settings["adapter_warn_bytes"]
            if len(body.encode()) > limit:
                self.add("warning", "adapter_size", path, f"import 밖 본문 {len(body.encode())} bytes(기준 {limit}). 공통 규칙 복제 여부 확인")
            for para in re.split(r"\n\s*\n", text):
                for line in para.splitlines():
                    n = self._norm(line)
                    if len(n) >= 60 and any(n in c for c in common):
                        self.add("warning", "adapter_duplicates_common_contract", path, f"공통 계약 문장 복제: «{n[:50]}»")
                        break
        for path in self._all_files():
            name = path.rsplit("/", 1)[-1]
            if name == "AGENTS.override.md":
                self.add("warning", "instruction_override_present", path, "Codex만 읽는 override다. Claude Code와 의미가 갈라진다")
            elif name in ("AGENTS.md", "CLAUDE.md") and "/" in path and not path.startswith(("node_modules/", "dist/")):
                self.add("info", "nested_instruction", path, "하위 디렉터리 지침은 runtime마다 로드 시점이 다르다(Codex: 시작 시 경로 연결, Claude: 해당 디렉터리 파일 읽을 때)")
            elif name == "CLAUDE.local.md" or path.startswith(".claude/rules/"):
                self.add("info", "runtime_only_instruction", path, "Claude 전용 지침 위치다. Cairn 공통 규칙을 두지 않는다")

    @staticmethod
    def _norm(text: str) -> str:
        return mdunits.normalize(re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", text))

    def project_config(self) -> None:
        raw = self.project.source.read_bytes(".harness/project.yaml") or b""
        text = raw.decode("utf-8", "replace")
        mentioned = sorted({t for t in TASK_ID.findall(text) if t in self.by_id})
        if len(mentioned) >= 3 or len(raw) > 4096:
            self.add("info", "project_config_task_log", ".harness/project.yaml",
                     f"{len(raw)} bytes, Task ID {len(mentioned)}개 언급. Task별 위임은 Packet scope.authorization에 둔다")
        if not self.layout.declared:
            self.not_checked.append("layout 미선언: class 판정은 기본값(evidence_root 등)과 Task 기록만 사용")
        task_root = norm_path(self.project.task_root)
        for place in self.layout["sealed"] or []:
            if place and covers(norm_path(place), task_root):
                self.add("error", "layout_sealed_covers_task_root", ".harness/project.yaml",
                         f"layout.sealed {place}가 task_root를 덮는다. 진행 중 Packet까지 봉인되고 Task Packet class를 바꿀 수 없다")

    # ------------------------------------------------------------------ run
    def run(self, residuals_only: bool = False) -> dict:
        steps = [self.residuals] if residuals_only else [
            self.packet_parse, self.index, self.references, self.relocations, self.sealed_scope,
            self.sealed_modified, self.residuals, self.evidence_growth, self.concurrency, self.registry,
            self.coverage_owners, self.adapters, self.project_config]
        for step in steps:
            step()
        counts = {s: sum(1 for f in self.findings if f["severity"] == s) for s in SEVERITIES[:3]}
        status = "error" if counts["error"] else ("warning" if counts["warning"] else "clean")
        return {"status": status, "counts": counts, "findings": self.findings,
                "not_checked": sorted(set(self.not_checked)), "meaning": MEANING,
                "packets": len(self.packets), "sealed_paths": len(self.sealed),
                "source": self.project.source.label, "today": self.today.isoformat()}
