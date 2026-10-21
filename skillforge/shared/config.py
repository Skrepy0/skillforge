"""配置加载：读取 config/*.yaml，做 schema 校验，支持环境变量覆盖。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from skillforge.shared.errors import ConfigError


@dataclass(frozen=True)
class Settings:
    model: str
    timeout_seconds: int
    max_rewrite_rounds: int
    skills_root: str
    queue_concurrency: int
    output_dir: str | None = None


@dataclass(frozen=True)
class RoutingConfig:
    similarity_threshold: float
    clarify_gap: float
    keywords: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class GatesConfig:
    pass_threshold: float
    rules: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    sample_rate: float = 1.0
    trace_header: str = "X-Trace-Id"


@dataclass(frozen=True)
class AppConfig:
    root: Path
    settings: Settings
    routing: RoutingConfig
    gates: GatesConfig
    logging: LoggingConfig

    @property
    def skills_root(self) -> Path:
        p = Path(self.settings.skills_root)
        return p if p.is_absolute() else self.root / p


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"配置文件不存在: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML 解析失败: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件顶层必须是映射: {path}")
    return data


def _coerce(raw: str, template: Any) -> Any:
    if isinstance(template, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(template, int):
        return int(raw)
    if isinstance(template, float):
        return float(raw)
    return raw


def _apply_env(section: str, data: dict[str, Any]) -> dict[str, Any]:
    prefix = f"SKILLFORGE_{section.upper()}_"
    out = dict(data)
    for key in list(out):
        env_key = prefix + key.upper()
        if env_key in os.environ:
            out[key] = _coerce(os.environ[env_key], out[key])
    return out


def _require(data: dict[str, Any], keys: set[str], section: str) -> None:
    missing = keys - set(data)
    if missing:
        raise ConfigError(f"{section} 缺少必需字段: {sorted(missing)}")


def _validate_gates(gates: GatesConfig) -> None:
    cliche = gates.rules.get("cliche_check", {})
    phrases = cliche.get("phrases")
    if phrases is not None:
        if not isinstance(phrases, list) or not all(isinstance(p, str) for p in phrases):
            raise ConfigError("gates.rules.cliche_check.phrases 必须是字符串列表")


def load_config(root: Path | None = None) -> AppConfig:
    repo = root or _repo_root()
    cfg_dir = repo / "config"

    raw_settings = _apply_env("settings", _read_yaml(cfg_dir / "settings.yaml"))
    _require(
        raw_settings,
        {"model", "timeout_seconds", "max_rewrite_rounds", "skills_root", "queue_concurrency"},
        "settings",
    )

    raw_routing = _apply_env("routing", _read_yaml(cfg_dir / "routing.yaml"))
    _require(raw_routing, {"similarity_threshold", "clarify_gap"}, "routing")

    raw_gates = _apply_env("gates", _read_yaml(cfg_dir / "gates.yaml"))
    _require(raw_gates, {"pass_threshold", "rules"}, "gates")

    raw_logging = _apply_env("logging", _read_yaml(cfg_dir / "logging.yaml"))
    gates = GatesConfig(**raw_gates)
    _validate_gates(gates)

    return AppConfig(
        root=repo,
        settings=Settings(**raw_settings),
        routing=RoutingConfig(**raw_routing),
        gates=gates,
        logging=LoggingConfig(**raw_logging),
    )
