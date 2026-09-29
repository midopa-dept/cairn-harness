"""cairn_check CLI. 모든 명령은 읽기 전용이며 결과를 표준 출력으로만 낸다.

종료 코드(check·seed·skeleton 공통):
  0  PASS          평가 대상 전부가 결정적 검사를 통과했다(정확성·인수가 아니다)
  1  FAIL          결정적 계약 결함이 하나 이상 있다(미평가가 함께 있어도 FAIL)
  2  USAGE         호출·입력·환경 오류(인자 오류, Cairn 제어 파일·입력 파일·revision을
                 읽지 못함, ruamel.yaml 없음)
  3  INCONCLUSIVE  결함은 없지만 미평가·재확인 대상이 있다(검사한 Packet 없음 포함,
                 성공으로 취급하지 않는다)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import TARGET_CONTRACT, TOOL_NAME, TOOL_VERSION, commands, yamlio
from .pipeline import EXIT_USAGE, Options, Run
from .project import FsSource, GitSource, open_project


CONTROL_FILES = (".harness/core.yaml", ".harness/project.yaml", ".harness/distribution.yaml")


def _verify_rev(root: Path, rev: str, option: str) -> None:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
                            capture_output=True)
    if result.returncode != 0:
        raise UsageError(f"{option} {rev!r}를 {root}의 Git commit으로 해석하지 못했다")


def _source(args: argparse.Namespace):
    root = Path(args.project)
    if args.git_rev:
        _verify_rev(root, args.git_rev, "--git-rev")
        source = GitSource(root, args.git_rev)
    else:
        if not root.is_dir():
            raise UsageError(f"--project {root}가 디렉터리가 아니다")
        source = FsSource(root)
    # 평가 대상이 없는 실행을 PASS로 끝내지 않는다: Cairn 제어 파일이 없으면 호출 오류다(V-1).
    missing = [path for path in CONTROL_FILES if source.read_bytes(path) is None]
    if missing:
        raise UsageError(f"{source.label}은 Cairn 프로젝트 루트가 아니다(없는 파일: {', '.join(missing)})")
    return source


class UsageError(Exception):
    """호출·입력 오류. 종료 코드 2."""


def _read_input(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise UsageError(f"입력 파일을 읽지 못했다: {path}: {error}") from error


def _contracts(values: list[str]) -> dict[str, dict]:
    result = {}
    for value in values or []:
        content_id, _, path = value.partition("=")
        data, error = yamlio.load(_read_input(path))
        if error:
            raise UsageError(f"계약을 읽지 못했다: {path}: {error}")
        result[content_id] = data
    return result


def _summary(report: dict) -> str:
    verdict = report["verdict"]
    lines = [f"판정: {verdict['status']} (exit {verdict['exit_code']}) · {verdict['meaning']}"]
    lines += [f"  미평가·재확인: {item}" for item in verdict["unevaluated"]]
    lines += [f"{report['tool']['name']} {report['tool']['version']} (대상 contract {report['tool']['target_contract']['version']}) · method {report['method']} · "
             f"parser {report['parser']['name']} {report['parser']['version']} (YAML {report['parser']['yaml_version']})",
             f"source {report['source']} · phase {report['phase']}" + (" · 진단 실행" if report["diagnostic"] else "")]
    for stage, info in report["stages"].items():
        count = sum(1 for f in report["findings"] if f["stage"] == stage and f["severity"] in ("defect", "recheck"))
        reason = f" ({info['reason']})" if info["reason"] else ""
        lines.append(f"  {stage} {info['name']}: {info['status']} · 차단 finding {count}{reason}")
    for finding in report["findings"]:
        if finding["severity"] in ("defect", "recheck", "warning"):
            lines.append(f"  [{finding['stage']}/{finding['severity']}] {finding['code']} {finding['where']}: {finding['message']}")
    for pid, complete in report["coverage_complete"].items():
        lines.append(f"coverage complete({pid}): {'예' if complete else '아니오'}")
    lines.append(f"PASS 의미: {report['pass_meaning']}")
    lines.append("검사하지 않은 것: " + "; ".join(report["not_checked"]))
    return "\n".join(lines)


EPILOG = __doc__.split("\n\n", 1)[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cairn_check", description="Cairn companion validator(report-only)",
                                     epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version",
                        version=f"{TOOL_NAME} {TOOL_VERSION} (대상 contract {TARGET_CONTRACT['version']})")
    parser.add_argument("--project", default=".", help="프로젝트 루트")
    parser.add_argument("--git-rev", help="파일 대신 이 Git revision의 object를 읽는다(read-only)")
    parser.add_argument("--contract", action="append", default=[], metavar="CONTENT_ID=PATH",
                        help="다른 harness_snapshot의 core.yaml을 추가 제공")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="VS0~VS6 검사")
    check.add_argument("--phase", choices=["plan", "close"], default="close")
    check.add_argument("--diagnostic", action="store_true", help="선행 단계 실패 뒤에도 진단으로 계속(완전성 주장 불가)")
    check.add_argument("--packet", action="append", help="검사할 Packet 경로(반복 가능)")
    check.add_argument("--since", help="이 Git revision의 matrix와 비교해 Stage A 변경을 보고")
    check.add_argument("--json", action="store_true")
    skel = sub.add_parser("skeleton", help="scope 파일로 disposition null matrix 초안 출력")
    skel.add_argument("--parent", required=True, help="parent Packet 경로")
    skel.add_argument("--scope", required=True, help="scope 목록 YAML 경로")
    rows = sub.add_parser("rows", help="child가 회수할 자기 행 출력")
    rows.add_argument("--matrix", required=True)
    rows.add_argument("--task", required=True)
    seed = sub.add_parser("seed", help="criterion이 소유한 행의 정본 전문 조립")
    seed.add_argument("--parent", required=True)
    seed.add_argument("--matrix", required=True)
    seed.add_argument("--criterion", required=True, help="<task ID>#<criterion ID>")
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except UsageError as error:
        print(f"오류: {error}", file=sys.stderr)
        return EXIT_USAGE


def _dispatch(args: argparse.Namespace) -> int:
    project, notes = open_project(_source(args), _contracts(args.contract))
    for note in notes:
        print(f"주의: {note}", file=sys.stderr)

    def load(path: str):
        doc = project.load(path)
        if doc.error or doc.data is None:
            raise UsageError(f"읽기 실패: {path}: {doc.error}")
        return doc.data

    if args.command == "check":
        baseline = None
        if args.since:
            _verify_rev(Path(args.project), args.since, "--since")
            base_project, _ = open_project(GitSource(Path(args.project), args.since))
            baseline = {}
            for path in base_project.source.list(base_project.task_root):
                doc = base_project.load(path)
                if isinstance(doc.data, dict) and doc.data.get("kind") == "coverage_matrix":
                    baseline[doc.data.get("task")] = doc.data
        report = Run(project, Options(phase=args.phase, diagnostic=args.diagnostic,
                                      packets=args.packet, stage_a_baseline=baseline)).execute()
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else _summary(report))
        return report["verdict"]["exit_code"]
    if args.command == "skeleton":
        parent = load(args.parent)
        scope, error = yamlio.load(_read_input(args.scope))
        if error:
            raise UsageError(f"scope를 읽지 못했다: {error}")
        matrix, errors = commands.skeleton(project, parent, scope)
        for item in errors:
            print(f"주의: {item}", file=sys.stderr)
        print(yamlio.dump(matrix), end="")
        return 3 if errors else 0  # 초안이 불완전하면 INCONCLUSIVE
    if args.command == "rows":
        print(yamlio.dump(commands.project_rows(load(args.matrix), args.task)), end="")
        return 0
    if args.command == "seed":
        seed = commands.assemble_seed(project, args.parent, args.matrix, args.criterion)
        for item in seed["problems"] + seed["unrelated"]:
            print(f"[{item['severity']}] {item['code']} {item['where']}: {item['message']}", file=sys.stderr)
        if seed["status"] == "FAIL":
            print("seed 조립 거부: closure 안에 결정적 결함이 있다", file=sys.stderr)
        print(json.dumps(seed, ensure_ascii=False, indent=2))
        return seed["exit_code"]
    return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
