"""실제 YAML parser(ruamel.yaml, YAML 1.2)로만 읽는다. YAML 의미를 재구현하지 않는다."""
from __future__ import annotations

import io
import sys
from typing import Any

try:
    import ruamel.yaml as _ruamel
    from ruamel.yaml import YAML
except ImportError as error:  # pragma: no cover - 환경 안내
    # 환경 오류는 계약 결함(1)과 섞지 않고 호출 오류(2)로 끝낸다.
    print("ruamel.yaml이 필요합니다: python3 -m pip install -r tools/requirements-dev.txt", file=sys.stderr)
    raise SystemExit(2) from error

PARSER = {
    "name": "ruamel.yaml",
    "version": _ruamel.__version__,
    "yaml_version": "1.2",
    "loader": "safe(pure)",
}


def _loader() -> YAML:
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    yaml.allow_duplicate_keys = False
    return yaml


def load(text: str) -> tuple[Any, str | None]:
    """(데이터, 오류)를 반환한다. 오류가 있으면 데이터는 None이다."""
    try:
        return _loader().load(text), None
    except Exception as error:  # parser 오류 종류는 그대로 보고한다
        message = str(error).strip().splitlines()
        return None, f"{type(error).__name__}: {' '.join(message)[:400]}"


def dump(data: Any) -> str:
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096
    stream = io.StringIO()
    yaml.dump(data, stream)
    return stream.getvalue()
