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
        logger.info(
            "NVML 초기화 완료 (드라이버: %s)", pynvml.nvmlSystemGetDriverVersion()
        )


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


@dataclass
class GpuProcessInfo:
    """GPU에서 실행 중인 프로세스 정보."""

    pid: int
    name: str
    used_gpu_memory_mb: int
    command: str
    working_dir: str
    user: str


def get_gpu_processes(gpu_id: int) -> list[GpuProcessInfo]:
    """특정 GPU에서 실행 중인 프로세스 목록 조회."""
    from pathlib import Path

    init_nvml()
    handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)

    try:
        procs = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
    except pynvml.NVMLError:
        procs = []

    # 그래픽 프로세스도 포함
    try:
        gfx_procs = pynvml.nvmlDeviceGetGraphicsRunningProcesses(handle)
        # PID 중복 제거
        existing_pids = {p.pid for p in procs}
        for gp in gfx_procs:
            if gp.pid not in existing_pids:
                procs.append(gp)
    except pynvml.NVMLError:
        pass

    results: list[GpuProcessInfo] = []
    for proc in procs:
        pid = proc.pid
        mem_mb = (proc.usedGpuMemory or 0) // (1024 * 1024)

        # /proc 에서 프로세스 정보 읽기
        proc_path = Path(f"/proc/{pid}")
        name = ""
        command = ""
        working_dir = ""
        user = ""

        try:
            cmdline_raw = proc_path.joinpath("cmdline").read_bytes()
            parts = cmdline_raw.decode("utf-8", errors="replace").split("\x00")
            parts = [p for p in parts if p]
            command = " ".join(parts) if parts else ""
            name = parts[0].rsplit("/", 1)[-1] if parts else ""
        except (OSError, ValueError):
            name = f"pid:{pid}"

        try:
            working_dir = str(proc_path.joinpath("cwd").resolve())
        except OSError:
            working_dir = "(접근 불가)"

        try:
            status_text = proc_path.joinpath("status").read_text()
            for line in status_text.splitlines():
                if line.startswith("Uid:"):
                    uid = int(line.split()[1])
                    try:
                        import pwd

                        user = pwd.getpwuid(uid).pw_name
                    except (KeyError, ImportError):
                        user = str(uid)
                    break
        except OSError:
            user = "(알 수 없음)"

        results.append(
            GpuProcessInfo(
                pid=pid,
                name=name,
                used_gpu_memory_mb=mem_mb,
                command=command,
                working_dir=working_dir,
                user=user,
            )
        )

    return results
