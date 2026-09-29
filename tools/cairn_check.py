#!/usr/bin/env python3
"""Cairn companion validator 진입점(배포 5파일 밖의 별도 검사 도구). 사용법: python3 tools/cairn_check.py --help"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cairncheck.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
