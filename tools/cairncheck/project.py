"""프로젝트 자료 읽기 계층(adapter). 파일시스템 또는 Git object(read-only)에서 읽는다."""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from . import yamlio


class Source:
    """원시 바이트를 읽고 UTF-8로 해석한다. 개행은 바꾸지 않는다(열거는 splitlines로 LF·CRLF를 같게 다룬다)."""

    label = "source"

    def __init__(self) -> None:
        self.undecodable: set[str] = set()

    def read_bytes(self, path: str) -> bytes | None:
        raise NotImplementedError

    def read(self, path: str) -> str | None:
        data = self.read_bytes(path)
        if data is None:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            self.undecodable.add(path)  # UTF-8 text가 아닌 artifact는 정규화·열거하지 않는다
            return None

    def list(self, root: str) -> list[str]:
        raise NotImplementedError


class FsSource(Source):
    def __init__(self, root: Path):
        super().__init__()
        self.root = Path(root).resolve()
        self.label = f"fs:{self.root.name}"

    def _path(self, path: str) -> Path | None:
        rel = PurePosixPath(path)
        if rel.is_absolute() or ".." in rel.parts:
            return None
        target = (self.root / rel).resolve()
        return target if str(target).startswith(str(self.root)) else None

    def read_bytes(self, path: str) -> bytes | None:
        target = self._path(path)
        if target is None or not target.is_file():
            return None
        return target.read_bytes()

    def list(self, root: str) -> list[str]:
        base = self._path(root)
        if base is None or not base.is_dir():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file())


class GitSource(Source):
    """`git show <rev>:<path>`만 사용한다. 작업 트리를 바꾸지 않는다."""

    def __init__(self, repo: Path, rev: str):
        super().__init__()
        self.repo = Path(repo)
        self.rev = rev
        self.label = f"git:{rev}"
        self._cache: dict[str, bytes | None] = {}

    def read_bytes(self, path: str) -> bytes | None:
        if path not in self._cache:
            result = subprocess.run(
                ["git", "-C", str(self.repo), "show", f"{self.rev}:{path}"],
                capture_output=True,
            )
            self._cache[path] = result.stdout if result.returncode == 0 else None
        return self._cache[path]

    def list(self, root: str) -> list[str]:
        result = subprocess.run(
            ["git", "-C", str(self.repo), "ls-tree", "-r", "--name-only", self.rev, root],
            capture_output=True, text=True,
        )
        return sorted(result.stdout.split()) if result.returncode == 0 else []


@dataclass
class Document:
    path: str
    text: str | None
    data: Any = None
    error: str | None = None


@dataclass
class Project:
    source: Source
    task_root: str = ".harness/tasks"
    content_id: str | None = None
    contracts: dict[str, dict] = field(default_factory=dict)
    documents: dict[str, Document] = field(default_factory=dict)

    def load(self, path: str) -> Document:
        if path not in self.documents:
            text = self.source.read(path)
            if text is None:
                reason = "UTF-8 text가 아니다" if path in self.source.undecodable else "파일 없음"
                self.documents[path] = Document(path, None, None, reason)
            else:
                data, error = yamlio.load(text)
                self.documents[path] = Document(path, text, data, error)
        return self.documents[path]


def contract_version(contract: dict | None) -> int:
    if not isinstance(contract, dict):
        return 0
    value = contract.get("contract_version")
    return value if isinstance(value, int) else 0


def open_project(source: Source, extra_contracts: dict[str, dict] | None = None) -> tuple[Project, list[str]]:
    """project.yaml·distribution.yaml·core.yaml을 읽어 계약 목록을 구성한다."""
    project = Project(source)
    notes: list[str] = []
    config = project.load(".harness/project.yaml")
    if isinstance(config.data, dict) and isinstance(config.data.get("task_root"), str):
        project.task_root = config.data["task_root"]
    distribution = project.load(".harness/distribution.yaml")
    if isinstance(distribution.data, dict):
        project.content_id = distribution.data.get("content_id")
    core = project.load(".harness/core.yaml")
    if isinstance(core.data, dict) and project.content_id:
        project.contracts[project.content_id] = core.data
    elif core.data is None:
        notes.append("프로젝트 core.yaml을 읽지 못했다")
    for content_id, contract in (extra_contracts or {}).items():
        project.contracts[content_id] = contract
    return project, notes


def text_digests(data: bytes) -> dict[str, str]:
    """바이트 해시와 개행 동치 표기의 해시.

    UTF-8 text이고 CRLF→LF 뒤에 단독 CR이 남지 않을 때만 CRLF→LF(`lf`)와 그 LF→CRLF(`crlf`)
    표기를 더한다. LF·CRLF가 섞인 파일은 `lf` 표기로 동치가 된다. 단독 CR(예: `\r\r\n`)·BOM·
    끝 개행·그 밖의 바이트는 바꾸지 않는다. UTF-8이 아니면 원시 바이트 해시(`raw`)만 낸다.
    """
    digests = {"raw": hashlib.sha256(data).hexdigest()}
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return digests
    lf = data.replace(b"\r\n", b"\n")  # UTF-8에서 CR·LF 바이트는 다중 바이트 문자 안에 나오지 않는다
    if b"\r" in lf:
        return digests  # 단독 CR이 있으면 개행 표기만의 차이로 볼 수 없다
    digests["lf"] = hashlib.sha256(lf).hexdigest()
    digests["crlf"] = hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest()
    return digests
