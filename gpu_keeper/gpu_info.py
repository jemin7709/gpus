"""pynvml 기반 GPU 정보 조회 유틸리티."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pynvml

logger = logging.getLogger("gpu_keeper")

_initialized = False


def init_nvml() -> None:
    """NVML 라이브러리 초기화."""
    global _initialized
    if not _initialized:
        pynvml.nvmlInit()
        _initialized = True
        logger.info("NVML 초기화 완료 (드라이버: %s)", pynvml.nvmlSystemGetDriverVersion())


def shutdown_nvml() -> None:
    """NVML 라이브러리 종료."""
    global _initialized
    if _initialized:
        pynvml.nvmlShutdown()
        _initialized = False
        logger.info("NVML 종료")


def get_gpu_count() -> int:
    """시스템의 GPU 수 반환."""
    init_nvml()
    return pynvml.nvmlDeviceGetCount()


@dataclass
class GpuStatus:
    """GPU 상태 정보."""

    index: int
    name: str
    utilization_gpu: int  # %
    utilization_memory: int  # %
    memory_total_mb: int
    memory_used_mb: int
    memory_free_mb: int
    temperature: int  # °C
    power_draw_w: float  # Watts
    power_limit_w: float  # Watts


def get_gpu_status(gpu_id: int) -> GpuStatus:
    """특정 GPU의 현재 상태를 조회."""
    init_nvml()
    handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
    name = pynvml.nvmlDeviceGetName(handle)
    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
    mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
    try:
        power_draw = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0  # mW → W
    except pynvml.NVMLError:
        power_draw = 0.0
    try:
        power_limit = pynvml.nvmlDeviceGetEnforcedPowerLimit(handle) / 1000.0
    except pynvml.NVMLError:
        power_limit = 0.0

    return GpuStatus(
        index=gpu_id,
        name=name,
        utilization_gpu=util.gpu,
        utilization_memory=util.memory,
        memory_total_mb=mem.total // (1024 * 1024),
        memory_used_mb=mem.used // (1024 * 1024),
        memory_free_mb=mem.free // (1024 * 1024),
        temperature=temp,
        power_draw_w=round(power_draw, 1),
        power_limit_w=round(power_limit, 1),
    )


def get_all_gpu_status(gpu_ids: list[int] | None = None) -> list[GpuStatus]:
    """전체 또는 지정된 GPU들의 상태를 조회."""
    count = get_gpu_count()
    ids = gpu_ids if gpu_ids is not None else list(range(count))
    return [get_gpu_status(i) for i in ids if i < count]


def get_free_memory_mb(gpu_id: int) -> int:
    """특정 GPU의 사용 가능한 메모리(MB) 반환."""
    init_nvml()
    handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
    mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
    return mem.free // (1024 * 1024)
