"""GPU 워크로드 프로세스 — torch.matmul 기반 GPU utilization 유지."""

from __future__ import annotations

import logging
import math
import multiprocessing as mp
import time

logger = logging.getLogger("gpu_keeper")


# 행렬 크기 상한 — matmul 1회가 ~1초 이내에 끝나야 stop_event 체크가 빠름
# H100 FP32: 16384×16384 matmul ≈ 0.3초, 충분히 util 100% 유지
_MAX_MATRIX_SIZE = 16384


def _compute_matrix_size(free_memory_mb: int, memory_fraction: float) -> int:
    """사용 가능한 메모리와 비율로 정방행렬 크기 계산.

    FP32 기준, A(N×N) + B(N×N) + C(N×N) = 3 × N² × 4 bytes.
    """
    usable_bytes = free_memory_mb * 1024 * 1024 * memory_fraction
    # 3 matrices of N×N float32
    n = int(math.sqrt(usable_bytes / (3 * 4)))
    # 256 단위로 내림 (Tensor Core 정렬)
    n = max(256, (n // 256) * 256)
    # 상한 적용 — 너무 크면 matmul 1회가 길어져서 stop이 느려짐
    n = min(n, _MAX_MATRIX_SIZE)
    return n


def _worker_loop(
    gpu_id: int,
    stop_event: mp.Event,
    memory_fraction: float,
    matrix_size: int | None,
) -> None:
    """GPU 워크로드 루프 (별도 프로세스에서 실행)."""
    import torch

    proc_logger = logging.getLogger(f"gpu_keeper.worker.{gpu_id}")
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s"))
    proc_logger.addHandler(handler)
    proc_logger.setLevel(logging.INFO)

    try:
        torch.cuda.set_device(gpu_id)
        device = torch.device(f"cuda:{gpu_id}")

        # 행렬 크기 결정
        if matrix_size and matrix_size > 0:
            n = matrix_size
        else:
            free_mb = torch.cuda.mem_get_info(gpu_id)[0] // (1024 * 1024)
            n = _compute_matrix_size(free_mb, memory_fraction)

        proc_logger.info(
            "GPU %d 워크로드 시작 (행렬 크기: %d×%d, "
            "메모리 ~%.0f MB)",
            gpu_id,
            n,
            n,
            3 * n * n * 4 / (1024 * 1024),
        )

        # 텐서 미리 할당 (FP32)
        a = torch.randn(n, n, device=device, dtype=torch.float32)
        b = torch.randn(n, n, device=device, dtype=torch.float32)
        c = torch.empty(n, n, device=device, dtype=torch.float32)

        iteration = 0
        while not stop_event.is_set():
            torch.matmul(a, b, out=c)
            iteration += 1
            # 주기적으로 동기화하여 stop_event 체크 기회 보장
            if iteration % 50 == 0:
                torch.cuda.synchronize(device)

        # 정리
        del a, b, c
        torch.cuda.empty_cache()
        proc_logger.info("GPU %d 워크로드 정상 종료 (반복: %d)", gpu_id, iteration)

    except Exception:
        proc_logger.exception("GPU %d 워크로드 에러", gpu_id)


class GpuWorker:
    """GPU별 워크로드 프로세스 관리."""

    def __init__(self, gpu_id: int, memory_fraction: float = 0.5, matrix_size: int | None = None):
        self.gpu_id = gpu_id
        self.memory_fraction = memory_fraction
        self.matrix_size = matrix_size
        self._process: mp.Process | None = None
        self._stop_event: mp.Event | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def start(self) -> bool:
        """워크로드 시작. 이미 실행 중이면 False 반환."""
        if self.is_running:
            logger.warning("GPU %d 이미 실행 중", self.gpu_id)
            return False

        self._stop_event = mp.Event()
        self._process = mp.Process(
            target=_worker_loop,
            args=(self.gpu_id, self._stop_event, self.memory_fraction, self.matrix_size),
            daemon=True,
            name=f"gpu-worker-{self.gpu_id}",
        )
        self._process.start()
        logger.info("GPU %d 워커 프로세스 시작 (PID: %d)", self.gpu_id, self._process.pid)
        return True

    def stop(self, timeout: float = 10.0) -> bool:
        """워크로드 중지. 정상 종료 시 True, 강제 종료 시 False."""
        if not self.is_running:
            logger.info("GPU %d 이미 중지됨", self.gpu_id)
            return True

        self._stop_event.set()
        self._process.join(timeout=timeout)

        if self._process.is_alive():
            logger.warning("GPU %d 워커 SIGTERM 전송", self.gpu_id)
            self._process.terminate()
            self._process.join(timeout=5)

        if self._process is not None and self._process.is_alive():
            logger.warning("GPU %d 워커 SIGKILL 강제 종료", self.gpu_id)
            self._process.kill()
            self._process.join(timeout=3)
            self._process = None
            self._stop_event = None
            return False

        logger.info("GPU %d 워커 정상 종료", self.gpu_id)
        self._process = None
        self._stop_event = None
        return True
