"""入口集成：load_config / create_app / cli.main 能读到 .env。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from skillforge.shared.config import load_config

from tests.unit.test_api_out_path import _StubLLM


@pytest.fixture
def env_in_tmp(tmp_path, monkeypatch):
    """在临时目录放 .env 并把 cwd 切过去，隔离仓库根的 .env。"""
    (tmp_path / ".env").write_text(
        "SKILLFORGE_SETTINGS_TIMEOUT_SECONDS=999\n"
        "SKILLFORGE_LOGGING_LEVEL=DEBUG\n"
        "SKILLFORGE_API_KEY=from-dotenv-key\n"
        "SKILLFORGE_OUTPUT_DIR=./dotenv-out\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for key in (
        "SKILLFORGE_SETTINGS_TIMEOUT_SECONDS",
        "SKILLFORGE_LOGGING_LEVEL",
        "SKILLFORGE_API_KEY",
        "SKILLFORGE_OUTPUT_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def _copy_config(tmp_path: Path) -> None:
    """把仓库 config/ 复制到 tmp_path，让 load_config 能找到。"""
    import shutil

    src = Path(__file__).resolve().parents[2] / "config"
    shutil.copytree(src, tmp_path / "config")


def test_load_config_reads_env_file(env_in_tmp):
    _copy_config(env_in_tmp)
    cfg = load_config(root=env_in_tmp)
    assert cfg.settings.timeout_seconds == 999
    assert cfg.logging.level == "DEBUG"


def test_create_app_reads_env_file(env_in_tmp, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    _copy_config(env_in_tmp)

    from skillforge.l4_interface import api

    # 不传 api_key / allowed_output_dir，靠 .env
    app = api.create_app(llm=_StubLLM(), rate_limit_per_minute=0)
    assert app.state.output_root is not None
    assert str(app.state.output_root).endswith("dotenv-out")


def test_cli_main_loads_env_file(env_in_tmp, monkeypatch):
    _copy_config(env_in_tmp)

    # skills list 读 skills/index.json，指向仓库实际路径避免 FileNotFound
    skills_root = Path(__file__).resolve().parents[2] / "skills"
    (env_in_tmp / "skills").symlink_to(skills_root, target_is_directory=True)

    from skillforge.l4_interface import cli

    rc = cli.main(["skills", "list"])
    assert rc == 0
    # 关键：SKILLFORGE_OUTPUT_DIR 在 .env 里，main 加载后 os.environ 能看到
    assert os.getenv("SKILLFORGE_OUTPUT_DIR") == "./dotenv-out"
