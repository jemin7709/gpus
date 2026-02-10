"""GPU Keeper 웹 대시보드 — 단일 HTML 페이지로 제공."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GPU Keeper Dashboard</title>
<style>
  :root {
    --bg: #0f1117;
    --card: #1a1d2e;
    --card-hover: #222640;
    --accent: #6c63ff;
    --accent2: #00d2ff;
    --green: #00e676;
    --red: #ff5252;
    --orange: #ffab40;
    --text: #e0e0e0;
    --text2: #9e9e9e;
    --border: #2a2d3e;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }
  .header {
    background: linear-gradient(135deg, #1a1d2e 0%, #2a2d4e 100%);
    padding: 20px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .header h1 {
    font-size: 1.5rem;
    font-weight: 700;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .header-actions {
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .refresh-indicator {
    font-size: 0.8rem;
    color: var(--text2);
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .refresh-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--green);
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
  .container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 24px;
  }

  /* 전체 제어 바 */
  .control-bar {
    display: flex;
    gap: 12px;
    margin-bottom: 24px;
    flex-wrap: wrap;
    align-items: center;
  }
  .btn {
    padding: 10px 20px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .btn:hover { transform: translateY(-1px); filter: brightness(1.1); }
  .btn:active { transform: translateY(0); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
  .btn-start { background: var(--green); color: #111; }
  .btn-stop { background: var(--red); color: #fff; }
  .btn-secondary { background: var(--border); color: var(--text); }

  /* GPU 카드 그리드 */
  .gpu-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
    gap: 20px;
    margin-bottom: 32px;
  }
  .gpu-card {
    background: var(--card);
    border-radius: 12px;
    padding: 24px;
    border: 1px solid var(--border);
    transition: all 0.2s;
  }
  .gpu-card:hover { background: var(--card-hover); border-color: var(--accent); }
  .gpu-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }
  .gpu-id {
    font-size: 1.1rem;
    font-weight: 700;
  }
  .gpu-name {
    font-size: 0.8rem;
    color: var(--text2);
    margin-top: 2px;
  }
  .status-badge {
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
  }
  .status-running { background: rgba(0,230,118,0.15); color: var(--green); }
  .status-stopped { background: rgba(255,82,82,0.15); color: var(--red); }

  /* 프로그레스 바 */
  .metric-row {
    margin-bottom: 12px;
  }
  .metric-label {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    color: var(--text2);
    margin-bottom: 4px;
  }
  .progress-bar {
    height: 8px;
    background: rgba(255,255,255,0.08);
    border-radius: 4px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease;
  }
  .fill-gpu { background: linear-gradient(90deg, var(--accent), var(--accent2)); }
  .fill-mem { background: linear-gradient(90deg, #ff6f00, #ffab40); }
  .fill-temp { background: linear-gradient(90deg, var(--green), var(--orange)); }
  .fill-temp.hot { background: linear-gradient(90deg, var(--orange), var(--red)); }
  .fill-power { background: linear-gradient(90deg, #00bcd4, #4dd0e1); }

  /* 수치 그리드 */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin: 16px 0;
  }
  .stat-box {
    background: rgba(255,255,255,0.04);
    border-radius: 8px;
    padding: 10px;
    text-align: center;
  }
  .stat-value {
    font-size: 1.2rem;
    font-weight: 700;
  }
  .stat-label {
    font-size: 0.7rem;
    color: var(--text2);
    margin-top: 2px;
  }

  /* 카드 내 버튼 */
  .card-actions {
    display: flex;
    gap: 8px;
    margin-top: 16px;
  }
  .card-actions .btn {
    flex: 1;
    justify-content: center;
    padding: 8px 12px;
    font-size: 0.85rem;
  }

  /* 설정 패널 */
  .config-panel {
    background: var(--card);
    border-radius: 12px;
    padding: 24px;
    border: 1px solid var(--border);
  }
  .config-panel h2 {
    font-size: 1.1rem;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .config-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
  }
  .config-item {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .config-item label {
    font-size: 0.8rem;
    color: var(--text2);
    font-weight: 600;
  }
  .config-item input, .config-item select {
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    color: var(--text);
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.2s;
  }
  .config-item input:focus, .config-item select:focus {
    border-color: var(--accent);
  }
  .config-actions {
    margin-top: 20px;
    display: flex;
    gap: 10px;
  }
  .btn-apply { background: var(--accent); color: #fff; }

  /* 자동 재시작 카운트다운 */
  .restart-countdown {
    font-size: 0.75rem;
    color: var(--orange);
    margin-top: 8px;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  /* 토스트 */
  .toast-container {
    position: fixed;
    top: 80px;
    right: 24px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .toast {
    padding: 12px 20px;
    border-radius: 8px;
    font-size: 0.85rem;
    font-weight: 500;
    animation: slideIn 0.3s ease;
    min-width: 250px;
  }
  .toast-success { background: rgba(0,230,118,0.9); color: #111; }
  .toast-error { background: rgba(255,82,82,0.9); color: #fff; }
  .toast-info { background: rgba(108,99,255,0.9); color: #fff; }
  @keyframes slideIn {
    from { transform: translateX(100px); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }

  /* 로딩 */
  .loading-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(15,17,23,0.7);
    z-index: 200;
    align-items: center;
    justify-content: center;
  }
  .loading-overlay.active { display: flex; }
  .spinner {
    width: 48px; height: 48px;
    border: 4px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* 반응형 */
  @media (max-width: 768px) {
    .gpu-grid { grid-template-columns: 1fr; }
    .config-grid { grid-template-columns: 1fr; }
    .header { padding: 16px; }
    .container { padding: 16px; }
    .stats-grid { grid-template-columns: repeat(2, 1fr); }
  }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>GPU Keeper Dashboard</h1>
  </div>
  <div class="header-actions">
    <div class="refresh-indicator">
      <div class="refresh-dot"></div>
      <span id="last-update">업데이트 중...</span>
    </div>
  </div>
</div>

<div class="container">

  <!-- 전체 제어 -->
  <div class="control-bar">
    <button class="btn btn-start" onclick="apiCall('/start-all', 'POST')">
      &#9654; 전체 시작
    </button>
    <button class="btn btn-stop" onclick="apiCall('/stop-all', 'POST')">
      &#9724; 전체 중지
    </button>
    <button class="btn btn-secondary" onclick="refreshStatus()">
      &#8635; 새로고침
    </button>
  </div>

  <!-- GPU 카드 -->
  <div class="gpu-grid" id="gpu-grid">
    <div class="gpu-card" style="opacity:0.5;text-align:center;padding:60px;">
      로딩 중...
    </div>
  </div>

  <!-- 설정 패널 -->
  <div class="config-panel">
    <h2>&#9881; 설정</h2>
    <div class="config-grid">
      <div class="config-item">
        <label>메모리 사용 비율 (memory_fraction)</label>
        <input type="range" id="cfg-memory-fraction" min="0.1" max="1.0" step="0.05" value="0.5"
               oninput="document.getElementById('cfg-mf-val').textContent = this.value">
        <span id="cfg-mf-val" style="font-size:0.9rem;color:var(--accent);font-weight:700;">0.5</span>
      </div>
      <div class="config-item">
        <label>온도 제한 (°C)</label>
        <input type="number" id="cfg-temp-limit" min="50" max="100" value="83">
      </div>
      <div class="config-item">
        <label>자동 재시작</label>
        <select id="cfg-auto-restart">
          <option value="true">활성화</option>
          <option value="false">비활성화</option>
        </select>
      </div>
      <div class="config-item">
        <label>자동 재시작 타임아웃 (초)</label>
        <input type="number" id="cfg-auto-restart-timeout" min="10" max="3600" value="300">
      </div>
      <div class="config-item">
        <label>모니터 주기 (초)</label>
        <input type="number" id="cfg-monitor-interval" min="1" max="120" value="10">
      </div>
    </div>
    <div class="config-actions">
      <button class="btn btn-apply" onclick="applyConfig()">적용</button>
      <button class="btn btn-secondary" onclick="loadConfig()">초기화</button>
    </div>
  </div>
</div>

<div class="toast-container" id="toasts"></div>
<div class="loading-overlay" id="loading"><div class="spinner"></div></div>

<script>
const API_KEY = '';  // config의 api_key가 있으면 여기에 설정
let refreshTimer = null;
const REFRESH_INTERVAL = 5000; // 5초

// ── 유틸 ──

function apiHeaders() {
  const h = { 'Content-Type': 'application/json' };
  if (API_KEY) h['X-API-Key'] = API_KEY;
  return h;
}

function showToast(msg, type='info') {
  const container = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = 'toast toast-' + type;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function showLoading(on) {
  document.getElementById('loading').classList.toggle('active', on);
}

// ── API 호출 ──

async function apiCall(path, method='GET', body=null) {
  try {
    const opts = { method, headers: apiHeaders() };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || '오류 발생', 'error');
      return null;
    }
    return data;
  } catch (e) {
    showToast('서버 연결 실패: ' + e.message, 'error');
    return null;
  }
}

// ── GPU 상태 ──

function tempColor(t, limit) {
  if (t >= limit) return 'var(--red)';
  if (t >= limit - 10) return 'var(--orange)';
  return 'var(--green)';
}

function renderGpuCard(gpu) {
  const memPct = gpu.memory_total_mb > 0
    ? Math.round(gpu.memory_used_mb / gpu.memory_total_mb * 100) : 0;
  const tempPct = Math.min(100, Math.round(gpu.temperature_c / 100 * 100));
  const powerPct = gpu.power_limit_w > 0
    ? Math.round(gpu.power_draw_w / gpu.power_limit_w * 100) : 0;
  const isHot = gpu.temperature_c >= 75;

  let restartHtml = '';
  if (gpu.auto_restart_remaining_s !== null && gpu.auto_restart_remaining_s !== undefined) {
    const mins = Math.floor(gpu.auto_restart_remaining_s / 60);
    const secs = Math.round(gpu.auto_restart_remaining_s % 60);
    restartHtml = `<div class="restart-countdown">&#9200; 자동 재시작까지 ${mins}분 ${secs}초</div>`;
  }

  return `
    <div class="gpu-card">
      <div class="gpu-card-header">
        <div>
          <div class="gpu-id">GPU ${gpu.gpu_id}</div>
          <div class="gpu-name">${gpu.name}</div>
        </div>
        <span class="status-badge ${gpu.worker_running ? 'status-running' : 'status-stopped'}">
          ${gpu.worker_running ? '실행 중' : '중지됨'}
        </span>
      </div>

      <div class="metric-row">
        <div class="metric-label"><span>GPU 사용률</span><span>${gpu.utilization_gpu}%</span></div>
        <div class="progress-bar"><div class="progress-fill fill-gpu" style="width:${gpu.utilization_gpu}%"></div></div>
      </div>

      <div class="metric-row">
        <div class="metric-label"><span>메모리</span><span>${gpu.memory_used_mb} / ${gpu.memory_total_mb} MB (${memPct}%)</span></div>
        <div class="progress-bar"><div class="progress-fill fill-mem" style="width:${memPct}%"></div></div>
      </div>

      <div class="metric-row">
        <div class="metric-label"><span>온도</span><span style="color:${tempColor(gpu.temperature_c, 83)}">${gpu.temperature_c}°C</span></div>
        <div class="progress-bar"><div class="progress-fill fill-temp ${isHot?'hot':''}" style="width:${tempPct}%"></div></div>
      </div>

      <div class="metric-row">
        <div class="metric-label"><span>전력</span><span>${gpu.power_draw_w}W / ${gpu.power_limit_w}W</span></div>
        <div class="progress-bar"><div class="progress-fill fill-power" style="width:${powerPct}%"></div></div>
      </div>

      <div class="stats-grid">
        <div class="stat-box">
          <div class="stat-value" style="color:${tempColor(gpu.temperature_c, 83)}">${gpu.temperature_c}°C</div>
          <div class="stat-label">온도</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">${gpu.power_draw_w}W</div>
          <div class="stat-label">전력</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">${gpu.memory_free_mb}</div>
          <div class="stat-label">여유 메모리(MB)</div>
        </div>
      </div>

      ${restartHtml}

      <div class="card-actions">
        <button class="btn btn-start" onclick="gpuAction(${gpu.gpu_id}, 'start')" ${gpu.worker_running?'disabled':''}>
          &#9654; 시작
        </button>
        <button class="btn btn-stop" onclick="gpuAction(${gpu.gpu_id}, 'stop')" ${!gpu.worker_running?'disabled':''}>
          &#9724; 중지
        </button>
      </div>
    </div>
  `;
}

async function refreshStatus() {
  const data = await apiCall('/status');
  if (!data) return;

  const grid = document.getElementById('gpu-grid');
  grid.innerHTML = data.gpus.map(renderGpuCard).join('');

  const now = new Date();
  document.getElementById('last-update').textContent =
    `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')} 업데이트`;
}

async function gpuAction(gpuId, action) {
  showLoading(true);
  const data = await apiCall(`/gpu/${gpuId}/${action}`, 'POST');
  showLoading(false);
  if (data) {
    showToast(`GPU ${gpuId} ${action === 'start' ? '시작됨' : '중지됨'}`, 'success');
    await refreshStatus();
  }
}

// ── 설정 ──

async function loadConfig() {
  const data = await apiCall('/config');
  if (!data) return;
  document.getElementById('cfg-memory-fraction').value = data.memory_fraction;
  document.getElementById('cfg-mf-val').textContent = data.memory_fraction;
  document.getElementById('cfg-temp-limit').value = data.temperature_limit;
  document.getElementById('cfg-auto-restart').value = data.auto_restart_enabled ? 'true' : 'false';
  document.getElementById('cfg-auto-restart-timeout').value = data.auto_restart_timeout;
  document.getElementById('cfg-monitor-interval').value = data.monitor_interval;
}

async function applyConfig() {
  const body = {
    memory_fraction: parseFloat(document.getElementById('cfg-memory-fraction').value),
    temperature_limit: parseInt(document.getElementById('cfg-temp-limit').value),
    auto_restart_enabled: document.getElementById('cfg-auto-restart').value === 'true',
    auto_restart_timeout: parseInt(document.getElementById('cfg-auto-restart-timeout').value),
    monitor_interval: parseInt(document.getElementById('cfg-monitor-interval').value),
  };
  showLoading(true);
  const data = await apiCall('/config', 'PUT', body);
  showLoading(false);
  if (data) {
    showToast('설정 적용 완료', 'success');
    await loadConfig();
  }
}

// ── 초기화 ──

async function init() {
  await refreshStatus();
  await loadConfig();
  // 자동 갱신
  refreshTimer = setInterval(refreshStatus, REFRESH_INTERVAL);
}

init();
</script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """웹 대시보드 메인 페이지."""
    return DASHBOARD_HTML
