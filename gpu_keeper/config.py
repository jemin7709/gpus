"""GPU Keeper 설정 관리."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("gpu_keeper")

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@dataclass
class Config:
    """런타임 설정."""

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

    def validate(self) -> None:
        """설정값 타입/범위 검증. 문제가 있으면 ValueError를 발생."""
        if not isinstance(self.auto_restart_enabled, bool):
            raise ValueError("auto_restart_enabled는 bool이어야 합니다")
        if (
            not isinstance(self.auto_restart_timeout, int)
            or self.auto_restart_timeout < 0
        ):
            raise ValueError("auto_restart_timeout은 0 이상의 정수(초)여야 합니다")
        if not isinstance(self.monitor_interval, int) or self.monitor_interval <= 0:
            raise ValueError("monitor_interval은 1 이상의 정수(초)여야 합니다")

        if not isinstance(self.memory_fraction, (int, float)):
            raise ValueError("memory_fraction은 숫자여야 합니다")
        if not (0.0 < float(self.memory_fraction) <= 1.0):
            raise ValueError("memory_fraction은 (0.0, 1.0] 범위여야 합니다")
        # 내부적으로 float로 일관되게
        self.memory_fraction = float(self.memory_fraction)

        if self.matrix_size is not None:
            if not isinstance(self.matrix_size, int) or self.matrix_size <= 0:
                raise ValueError("matrix_size는 null 또는 양의 정수여야 합니다")

        if not isinstance(self.temperature_limit, int) or self.temperature_limit <= 0:
            raise ValueError("temperature_limit는 1 이상의 정수(°C)여야 합니다")

        if self.gpu_ids is not None:
            if not isinstance(self.gpu_ids, list) or any(
                not isinstance(x, int) or x < 0 for x in self.gpu_ids
            ):
                raise ValueError("gpu_ids는 null 또는 0 이상의 정수 리스트여야 합니다")

        if not isinstance(self.log_file, str):
            raise ValueError("log_file은 문자열이어야 합니다")
        if not isinstance(self.log_max_bytes, int) or self.log_max_bytes <= 0:
            raise ValueError("log_max_bytes는 양의 정수여야 합니다")
        if not isinstance(self.log_backup_count, int) or self.log_backup_count < 0:
            raise ValueError("log_backup_count는 0 이상의 정수여야 합니다")
        if not isinstance(self.log_level, str) or not self.log_level:
            raise ValueError("log_level은 비어있지 않은 문자열이어야 합니다")

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

        # 알 수 없는 키 경고
        known_keys = set(cls.__dataclass_fields__)
        unknown_keys = set(data.keys()) - known_keys
        if unknown_keys:
            logger.warning("알 수 없는 설정 키 무시: %s", unknown_keys)

        cfg = cls(**{k: v for k, v in data.items() if k in known_keys})
        cfg.validate()
        return cfg

    def to_dict(self) -> dict[str, Any]:
        """설정을 딕셔너리로 반환."""
        return {k: getattr(self, k) for k in self.__dataclass_fields__}
