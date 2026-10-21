import pytest
import yaml
from skillforge.shared.config import load_config
from skillforge.shared.errors import ConfigError


def _write(root, name, data):
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / name).write_text(
        yaml.safe_dump(data, allow_unicode=True),
        encoding="utf-8",
    )


def _base():
    return {
        "settings": {
            "model": "m",
            "timeout_seconds": 1,
            "max_rewrite_rounds": 2,
            "skills_root": "skills",
            "queue_concurrency": 1,
        },
        "routing": {"similarity_threshold": 0.5, "clarify_gap": 0.1, "keywords": {}},
        "gates": {
            "pass_threshold": 0.8,
            "rules": {"cliche_check": {"enabled": True, "weight": 1.0}},
        },
        "logging": {"level": "INFO"},
    }


def _setup(tmp_path):
    for name, data in _base().items():
        _write(tmp_path, f"{name}.yaml", data)


def test_load_ok(tmp_path):
    _setup(tmp_path)
    cfg = load_config(root=tmp_path)
    assert cfg.settings.model == "m"
    assert cfg.gates.pass_threshold == 0.8


def test_missing_required_field_raises(tmp_path):
    _setup(tmp_path)
    bad = _base()["settings"]
    del bad["model"]
    _write(tmp_path, "settings.yaml", bad)
    with pytest.raises(ConfigError):
        load_config(root=tmp_path)


def test_non_mapping_yaml_raises(tmp_path):
    _setup(tmp_path)
    (tmp_path / "config" / "settings.yaml").write_text(
        "- not a mapping\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(root=tmp_path)


def test_env_override_int_float(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.setenv("SKILLFORGE_SETTINGS_TIMEOUT_SECONDS", "99")
    monkeypatch.setenv("SKILLFORGE_ROUTING_SIMILARITY_THRESHOLD", "0.9")
    cfg = load_config(root=tmp_path)
    assert cfg.settings.timeout_seconds == 99
    assert cfg.routing.similarity_threshold == 0.9


def test_validate_gates_phrases_type(tmp_path):
    _setup(tmp_path)
    gates = _base()["gates"]
    gates["rules"]["cliche_check"]["phrases"] = "not-a-list"
    _write(tmp_path, "gates.yaml", gates)
    with pytest.raises(ConfigError):
        load_config(root=tmp_path)
