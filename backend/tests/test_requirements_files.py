"""requirements*.txt 只能有 ASCII：pip 在英文 Windows 用 cp1252 读这些档案，有中文就装不了（电脑 B，2026-10-12）。"""

from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", ["requirements.txt", "requirements-dev.txt", "requirements-lock.txt"])
def test_requirements_file_is_ascii(name):
    (BACKEND / name).read_bytes().decode("ascii")
