"""GPU utilization 모니터링 및 자동 재시작 관리."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from . import gpu_info

if TYPE_CHECKING:
    from .config import Config
    from .worker import GpuWorker

logger = logging.getLogger("gpu_keeper")


class GpuMonitor:
    """주기적으로 GPU 상태를 체크하고, 자동 재시작/안전장치 로직 수행."""

    def __init__(self, config: Config, workers: dict[int, GpuWorker]):
        self.config = config
        self.workers = workers

        # GPU별 util 0% 연속 시간 추적 (초)
        self._zero_util_duration: dict[int, float] = {gid: 0.0 for gid in workers}

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # 온도로 인해 자동 중지된 GPU 추적
        self._thermal_stopped: set[int] = set()

    def start(self) -> None:
        """모니터 스레드 시작."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="gpu-monitor"
        )
        self._thread.start()
        logger.info("GPU 모니터 시작 (주기: %ds)", self.config.monitor_interval)

    def stop(self) -> None:
        """모니터 스레드 중지."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=15)
            self._thread = None
        logger.info("GPU 모니터 중지")

    def _monitor_loop(self) -> None:
        """모니터링 메인 루프."""
        while not self._stop_event.is_set():
            try:
                self._check_all_gpus()
            except Exception:
                logger.exception("모니터링 중 에러")

            # 인터럽트 가능한 대기
            self._stop_event.wait(timeout=self.config.monitor_interval)

    def _check_all_gpus(self) -> None:
        """전체 GPU 상태 체크 및 자동 재시작/안전장치 로직."""
        for gpu_id, worker in self.workers.items():
            try:
                status = gpu_info.get_gpu_status(gpu_id)
            except Exception:
                logger.exception("GPU %d 상태 조회 실패", gpu_id)
                continue

            # === 안전장치: 온도 체크 ===
            if status.temperature > self.config.temperature_limit:
                if worker.is_running:
                    logger.warning(
                        "GPU %d 온도 초과 (%d°C > %d°C) — 워크로드 자동 중지",
                        gpu_id,
                        status.temperature,
                        self.config.temperature_limit,
                    )
                    worker.stop()
                    self._thermal_stopped.add(gpu_id)
                continue  # 온도 초과 상태에서는 재시작 안 함

            # 온도가 정상 복귀했고, 이전에 열로 중지됐던 GPU면 재시작
            if gpu_id in self._thermal_stopped:
                if (
                    status.temperature < self.config.temperature_limit - 5
                ):  # 5°C 히스테리시스
                    logger.info(
                        "GPU %d 온도 정상화 (%d°C) — 워크로드 재시작",
                        gpu_id,
                        status.temperature,
                    )
                    self._thermal_stopped.discard(gpu_id)
                    worker.memory_fraction = self.config.memory_fraction
                    worker.matrix_size = self.config.matrix_size
                    worker.start()
                    self._zero_util_duration[gpu_id] = 0.0
                continue

            # === 자동 재시작 로직 ===
            if not self.config.auto_restart_enabled:
                continue

            if not worker.is_running:
                if status.utilization_gpu == 0:
                    self._zero_util_duration[gpu_id] += self.config.monitor_interval
                    if (
                        self._zero_util_duration[gpu_id]
                        >= self.config.auto_restart_timeout
                    ):
                        logger.info(
                            "GPU %d util 0%%가 %d초 지속 — 자동 재시작",
                            gpu_id,
                            int(self._zero_util_duration[gpu_id]),
                        )
                        worker.memory_fraction = self.config.memory_fraction
                        worker.matrix_size = self.config.matrix_size
                        worker.start()
                        self._zero_util_duration[gpu_id] = 0.0
                else:
                    # util이 0이 아니면 카운터 리셋 (다른 프로세스가 사용 중)
                    self._zero_util_duration[gpu_id] = 0.0
            else:
                # 워커가 실행 중이면 카운터 리셋
                self._zero_util_duration[gpu_id] = 0.0
