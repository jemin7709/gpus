"""GPU Keeper — FastAPI 앱 및 엔트리포인트."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Header, Request

from .config import Config
from .gpu_info import get_gpu_count, get_gpu_status, init_nvml, shutdown_nvml
from .monitor import GpuMonitor
from .worker import GpuWorker

# ─── 전역 상태 ───────────────────────────────────────────────

config: Config = None  # type: ignore[assignment]
workers: dict[int, GpuWorker] = {}
monitor: GpuMonitor = None  # type: ignore[assignment]
logger = logging.getLogger("gpu_keeper")


# ─── 로깅 설정 ──────────────────────────────────────────────


def _setup_logging(cfg: Config) -> None:
    root = logging.getLogger("gpu_keeper")
    root.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))
    root.propagate = False

    # lifespan이 여러 번 실행되면 핸들러가 중복 추가될 수 있어 초기화
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


# ─── Lifespan ────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: 초기화 및 종료."""
    global config, workers, monitor

    # 설정 로드
    config_path = os.environ.get("GPU_KEEPER_CONFIG", None)
    config = Config.from_yaml(config_path)
    _setup_logging(config)
    logger.info("=== GPU Keeper 시작 ===")

    if config.api_key == "" and config.api_host not in {"127.0.0.1", "localhost"}:
        logger.warning(
            "api_key가 비어있어 인증이 비활성화되어 있고, 외부 바인딩(%s)입니다. 다중 사용자 환경이면 api_key 설정을 권장합니다.",
            config.api_host,
        )

    # NVML 초기화
    init_nvml()
    gpu_count = get_gpu_count()
    target_ids = (
        config.gpu_ids if config.gpu_ids is not None else list(range(gpu_count))
    )
    logger.info("대상 GPU: %s (전체 %d개 중)", target_ids, gpu_count)

    # 워커 생성 (아직 시작하지 않음 — API로 제어)
    workers = {
        gid: GpuWorker(gid, config.memory_fraction, config.matrix_size)
        for gid in target_ids
    }

    # 모니터 시작
    monitor = GpuMonitor(config, workers)
    monitor.start()

    yield

    # === 종료 ===
    logger.info("=== GPU Keeper 종료 중 ===")
    monitor.stop()
    for gid, w in workers.items():
        if w.is_running:
            w.stop()
    shutdown_nvml()
    logger.info("=== GPU Keeper 종료 완료 ===")


# ─── FastAPI 앱 ──────────────────────────────────────────────

app = FastAPI(
    title="GPU Keeper",
    description="GPU utilization 유지 관리 API",
    version="0.1.0",
    lifespan=lifespan,
)


# ─── 인증 미들웨어 ───────────────────────────────────────────


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """API Key 검증. 설정에 키가 없으면 인증 비활성화."""
    if config is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    if config.api_key and x_api_key != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ─── 헬퍼 ────────────────────────────────────────────────────


def _validate_gpu_id(gpu_id: int) -> None:
    if gpu_id not in workers:
        raise HTTPException(
            status_code=404,
            detail=f"GPU {gpu_id}는 관리 대상이 아닙니다. 대상: {list(workers.keys())}",
        )


def _gpu_detail(gpu_id: int) -> dict[str, Any]:
    """단일 GPU의 상태 + 워커 정보."""
    status = get_gpu_status(gpu_id)
    w = workers[gpu_id]
    remaining = monitor.get_auto_restart_remaining(gpu_id) if monitor else None
    return {
        "gpu_id": gpu_id,
        "name": status.name,
        "worker_running": w.is_running,
        "utilization_gpu": status.utilization_gpu,
        "utilization_memory": status.utilization_memory,
        "memory_total_mb": status.memory_total_mb,
        "memory_used_mb": status.memory_used_mb,
        "memory_free_mb": status.memory_free_mb,
        "temperature_c": status.temperature,
        "power_draw_w": status.power_draw_w,
        "power_limit_w": status.power_limit_w,
        "auto_restart_remaining_s": remaining,
    }


# ─── 엔드포인트 ──────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status", dependencies=[Depends(verify_api_key)])
async def get_status():
    """전체 GPU 상태 조회."""
    return {
        "gpus": [_gpu_detail(gid) for gid in workers],
        "config": {
            "auto_restart_enabled": config.auto_restart_enabled,
            "auto_restart_timeout": config.auto_restart_timeout,
            "temperature_limit": config.temperature_limit,
        },
    }


@app.get("/gpu/{gpu_id}/status", dependencies=[Depends(verify_api_key)])
async def get_gpu_status_endpoint(gpu_id: int):
    """특정 GPU 상태 조회."""
    _validate_gpu_id(gpu_id)
    return _gpu_detail(gpu_id)


@app.post("/gpu/{gpu_id}/start", dependencies=[Depends(verify_api_key)])
async def start_gpu(gpu_id: int):
    """특정 GPU 워크로드 시작."""
    _validate_gpu_id(gpu_id)
    w = workers[gpu_id]
    # 설정 동적 반영
    w.memory_fraction = config.memory_fraction
    w.matrix_size = config.matrix_size
    started = w.start()
    if started:
        monitor.reset_zero_counter(gpu_id)
    return {
        "gpu_id": gpu_id,
        "action": "started" if started else "already_running",
        "worker_running": w.is_running,
    }


@app.post("/gpu/{gpu_id}/stop", dependencies=[Depends(verify_api_key)])
async def stop_gpu(gpu_id: int):
    """특정 GPU 워크로드 중지."""
    _validate_gpu_id(gpu_id)
    w = workers[gpu_id]
    w.stop()
    monitor.reset_zero_counter(gpu_id)
    return {"gpu_id": gpu_id, "action": "stopped", "worker_running": w.is_running}


@app.post("/start-all", dependencies=[Depends(verify_api_key)])
async def start_all():
    """전체 GPU 워크로드 시작."""
    results = []
    for gid, w in workers.items():
        w.memory_fraction = config.memory_fraction
        w.matrix_size = config.matrix_size
        started = w.start()
        if started:
            monitor.reset_zero_counter(gid)
        results.append(
            {"gpu_id": gid, "action": "started" if started else "already_running"}
        )
    return {"results": results}


@app.post("/stop-all", dependencies=[Depends(verify_api_key)])
async def stop_all():
    """전체 GPU 워크로드 중지."""
    results = []
    for gid, w in workers.items():
        w.stop()
        monitor.reset_zero_counter(gid)
        results.append({"gpu_id": gid, "action": "stopped"})
    return {"results": results}


@app.get("/config", dependencies=[Depends(verify_api_key)])
async def get_config():
    """현재 설정 조회."""
    return config.to_dict()


@app.put("/config", dependencies=[Depends(verify_api_key)])
async def update_config(request: Request):
    """설정 부분 업데이트. JSON body로 변경할 필드만 전송."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    # 런타임 변경 불가 항목 필터
    immutable = {
        "api_port",
        "api_host",
        "api_key",
        "log_file",
        "log_max_bytes",
        "log_backup_count",
        "log_level",
    }
    filtered = {k: v for k, v in body.items() if k not in immutable}
    try:
        changed = config.update(filtered)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"changed": changed, "current": config.to_dict()}


# ─── 엔트리포인트 ────────────────────────────────────────────


def run():
    """CLI 엔트리포인트."""
    import uvicorn

    # 설정 미리 로드 (포트 확인용)
    config_path = os.environ.get("GPU_KEEPER_CONFIG", None)
    cfg = Config.from_yaml(config_path)

    uvicorn.run(
        "gpu_keeper.main:app",
        host=cfg.api_host,
        port=cfg.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
