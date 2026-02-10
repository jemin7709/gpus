"""GPU Keeper 설정 관리."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("gpu_keeper")

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@dataclass
class Config:
    """런타임 설정."""

    # API
    api_port: int = 8080
    api_host: str = "0.0.0.0"
    api_key: str = ""

    # 자동 재시작
    auto_restart_enabled: bool = True
    auto_restart_timeout: int = 300  # 초

    # 모니터링
    monitor_interval: int = 10  # 초

    # 워크로드
    memory_fraction: float = 0.5
    matrix_size: int | None = None

    # 안전장치
    temperature_limit: int = 83  # °C

    # 대상 GPU
    gpu_ids: list[int] | None = None

    # 로깅
    log_file: str = "gpu_keeper.log"
    log_max_bytes: int = 10_485_760  # 10 MB
    log_backup_count: int = 3
    log_level: str = "INFO"

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> Config:
        """YAML 파일에서 설정 로드. 파일이 없으면 기본값 사용."""
        config_path = Path(path) if path else DEFAULT_CONFIG_PATH
        data: dict[str, Any] = {}
        if config_path.exists():
            with open(config_path) as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    data = loaded
            logger.info("설정 파일 로드: %s", config_path)
        else:
            logger.warning("설정 파일 없음, 기본값 사용: %s", config_path)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict[str, Any]:
        """설정을 딕셔너리로 반환."""
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        """설정을 부분적으로 업데이트하고, 변경된 항목을 반환."""
        changed: dict[str, Any] = {}
        for key, value in updates.items():
            if key in self.__dataclass_fields__ and getattr(self, key) != value:
                setattr(self, key, value)
                changed[key] = value
        if changed:
            logger.info("설정 변경: %s", changed)
        return changed
