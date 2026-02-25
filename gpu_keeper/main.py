"""GPU Keeper — 순수 CLI 프로그램.

실행하면 모든 대상 GPU에 워크로드를 시작하고,
모니터링 + 자동 재시작만 수행합니다.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import sys
import threading

from .config import Config
from .gpu_info import get_gpu_count, get_gpu_processes, init_nvml, shutdown_nvml
from .monitor import GpuMonitor
from .worker import GpuWorker

logger = logging.getLogger("gpu_keeper")

# ─── 메인 스레드 블로킹용 이벤트 ─────────────────────────────
_stop_event = threading.Event()


# ─── 로깅 설정 ──────────────────────────────────────────────


def _setup_logging(cfg: Config) -> None:
    root = logging.getLogger("gpu_keeper")
    root.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))
    root.propagate = False

    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s")

    # 콘솔
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # 파일 (RotatingFileHandler)
    if cfg.log_file:
        fh = logging.handlers.RotatingFileHandler(
            cfg.log_file, maxBytes=cfg.log_max_bytes, backupCount=cfg.log_backup_count
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)


def _is_gpu_busy(gpu_id: int) -> bool:
    """현재 GPU를 점유한 다른 프로세스가 있는지 확인."""
    try:
        processes = get_gpu_processes(gpu_id)
    except Exception:
        logger.exception("GPU %d 프로세스 조회 실패", gpu_id)
        # 조회 실패 시 안전하게 점유로 간주해 시작을 보류
        return True

    return any(proc.pid != os.getpid() for proc in processes)


# ─── 메인 로직 ──────────────────────────────────────────────


def main() -> None:
    """설정 로드 → NVML 초기화 → 워커 시작 → 모니터 시작 → 종료 대기."""
    workers: dict[int, GpuWorker] = {}
    monitor: GpuMonitor | None = None
    nvml_initialized = False

    # 재호출 시 즉시 종료 방지
    _stop_event.clear()

    # 설정 로드
    config_path = os.environ.get("GPU_KEEPER_CONFIG", None)
    config = Config.from_yaml(config_path)
    _setup_logging(config)
    logger.info("=== GPU Keeper 시작 ===")

    try:
        # NVML 초기화
        init_nvml()
        nvml_initialized = True
        gpu_count = get_gpu_count()
        target_ids = (
            config.gpu_ids if config.gpu_ids is not None else list(range(gpu_count))
        )
        # 중복 GPU ID 제거
        target_ids = list(dict.fromkeys(target_ids))
        logger.info("대상 GPU: %s (전체 %d개 중)", target_ids, gpu_count)

        # 워커 생성 및 즉시 시작
        for gid in target_ids:
            w = GpuWorker(gid, config.memory_fraction, config.matrix_size)

            if config.skip_busy_gpus_at_start and _is_gpu_busy(gid):
                logger.warning(
                    "GPU %d 점유 프로세스 감지 — 시작을 건너뜀. 모니터링으로 복구 대기",
                    gid,
                )
                workers[gid] = w
                continue

            w.start()
            workers[gid] = w

        # 모니터 시작 (워커 이후에 시작하여 초기 0% 오탐 방지)
        monitor = GpuMonitor(config, workers)
        monitor.start()

        # 시그널 핸들러 등록
        def _signal_handler(signum: int, _frame: object) -> None:
            sig_name = signal.Signals(signum).name
            logger.info("시그널 수신: %s — 종료 시작", sig_name)
            _stop_event.set()

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        logger.info("GPU Keeper 실행 중 (종료: Ctrl+C)")

        # 메인 스레드 블로킹
        _stop_event.wait()

    finally:
        # === Graceful Shutdown ===
        logger.info("=== GPU Keeper 종료 중 ===")

        if monitor is not None:
            monitor.stop()

        for gid, w in workers.items():
            if w.is_running:
                w.stop()

        if nvml_initialized:
            shutdown_nvml()
        logger.info("=== GPU Keeper 종료 완료 ===")


# ─── 엔트리포인트 ────────────────────────────────────────────


def run() -> None:
    """CLI 엔트리포인트."""
    main()


if __name__ == "__main__":
    run()
