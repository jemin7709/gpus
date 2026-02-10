# GPU Keeper

GPU utilization을 ~100%로 유지하는 더미 워크로드 프로그램.  
FastAPI 기반 REST API로 GPU별 개별 on/off 제어, 자동 재시작, 온도 안전장치를 제공합니다.

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

## API 사용

서버 시작 후 브라우저에서 Swagger UI 접속:

```
http://<서버IP>:8080/docs
```

### 주요 엔드포인트

| Endpoint | Method | 설명 |
|---|---|---|
| `/status` | GET | 전체 GPU 상태 조회 |
| `/gpu/{gpu_id}/status` | GET | 특정 GPU 상태 |
| `/gpu/{gpu_id}/start` | POST | 특정 GPU 워크로드 시작 |
| `/gpu/{gpu_id}/stop` | POST | 특정 GPU 워크로드 중지 |
| `/start-all` | POST | 전체 시작 |
| `/stop-all` | POST | 전체 중지 |
| `/config` | GET | 설정 조회 |
| `/config` | PUT | 설정 변경 (런타임) |
| `/health` | GET | 헬스체크 |

### curl 예시

```bash
# 전체 상태 확인
curl http://localhost:8080/status

# GPU 1 시작
curl -X POST http://localhost:8080/gpu/1/start

# GPU 1 중지
curl -X POST http://localhost:8080/gpu/1/stop

# 전체 시작
curl -X POST http://localhost:8080/start-all

# 자동 재시작 시간 변경 (600초로)
curl -X PUT http://localhost:8080/config \
  -H "Content-Type: application/json" \
  -d '{"auto_restart_timeout": 600}'
```

### API Key 인증 (선택)

`config.yaml`에서 `api_key`를 설정하면 모든 요청에 헤더 필요:

```bash
curl -H "X-API-Key: your-secret-key" http://localhost:8080/status
```

## 설정 (`config.yaml`)

| 항목 | 기본값 | 설명 |
|---|---|---|
| `api_port` | 8080 | API 서버 포트 |
| `api_host` | 0.0.0.0 | 바인딩 주소 |
| `api_key` | (빈값) | API 인증 키. 비면 인증 없음 |
| `auto_restart_enabled` | true | 자동 재시작 활성화 |
| `auto_restart_timeout` | 300 | util 0% 지속 시 재시작까지 대기(초) |
| `monitor_interval` | 10 | GPU 상태 체크 주기(초) |
| `memory_fraction` | 0.5 | GPU free memory 중 사용 비율 |
| `matrix_size` | null | 고정 행렬 크기. null이면 자동 계산 |
| `temperature_limit` | 83 | 온도 초과 시 자동 중지(°C) |
| `gpu_ids` | null | 관리 대상 GPU. null이면 전체 |
| `log_file` | gpu_keeper.log | 로그 파일 |

## 동작 원리

- **워크로드**: `torch.matmul` (FP32 정방행렬) 무한 루프. GPU free memory의 50%를 사용
- **프로세스 격리**: GPU별 별도 프로세스(`multiprocessing.Process`) — stop 시 GPU 메모리 확실히 해제
- **자동 재시작**: 워커가 꺼진 GPU에서 util 0%가 설정 시간 동안 지속되면 자동 시작
- **온도 안전장치**: 설정 온도 초과 시 자동 중지, 5°C 히스테리시스 후 재시작
- **모니터링**: pynvml로 주기적 GPU 상태(util, 온도, 전력, 메모리) 조회
