# GPU Keeper

GPU utilization을 ~100%로 유지하는 더미 워크로드 프로그램.  
실행 시 각 GPU의 점유 상태를 확인한 뒤 워크로드를 시작하고, 모니터링 + 자동 재시작 + 온도 안전장치를 수행합니다.

## 설치

```bash
cd /home/work/hailolab/jemin/gpus
uv sync
```

## 실행

```bash
uv run gpu-keeper
```

또는 직접:

```bash
uv run python -m gpu_keeper.main
```

설정 파일 경로 지정:

```bash
GPU_KEEPER_CONFIG=/path/to/config.yaml uv run gpu-keeper
```

## 종료

`Ctrl+C`로 graceful shutdown됩니다. 모든 워커 프로세스가 안전하게 종료됩니다.

## 설정 (`config.yaml`)

| 항목 | 기본값 | 설명 |
|---|---|---|
| `auto_restart_enabled` | true | 자동 재시작 활성화 |
| `auto_restart_timeout` | 300 | util 0% 지속 시 재시작까지 대기(초) |
| `monitor_interval` | 10 | GPU 상태 체크 주기(초) |
| `memory_fraction` | 0.5 | GPU free memory 중 사용 비율 |
| `matrix_size` | null | 고정 행렬 크기. null이면 자동 계산 |
| `temperature_limit` | 83 | 온도 초과 시 자동 중지(°C) |
| `gpu_ids` | null | 관리 대상 GPU. null이면 전체 |
| `log_file` | gpu_keeper.log | 로그 파일 |
| `log_level` | INFO | 로그 레벨 (DEBUG, INFO, WARNING, ERROR) |

## 동작 원리

- **워크로드**: `torch.matmul` (FP32 정방행렬) 무한 루프. GPU free memory의 50%를 사용
- **프로세스 격리**: GPU별 별도 프로세스(`multiprocessing.Process`) — stop 시 GPU 메모리 확실히 해제
- **자동 시작**: 시작 시 GPU 점유 상태를 확인해 비어 있는 GPU만 워크로드 시작
- **충돌 회피**: 워크로드 실행 중 다른 프로세스가 GPU를 점유하면 워크로드 즉시 중지
- **자동 재시작**: 워커가 꺼진 GPU에서 util 0%가 설정 시간 동안 지속되면 자동 시작
- **온도 안전장치**: 설정 온도 초과 시 자동 중지, 5°C 히스테리시스 후 재시작
- **모니터링**: pynvml로 주기적 GPU 상태(util, 온도, 전력, 메모리) 조회
- **Graceful Shutdown**: SIGINT/SIGTERM 수신 시 모니터 → 워커 순으로 안전 종료
