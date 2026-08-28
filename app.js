const CONFIG = {
  // Set to your ESP32 WebSocket endpoint, e.g. ws://192.168.1.80/ws.
  // Leave empty to run the built-in live sensor simulation.
  websocketUrl: '',
  // Set to an ESP32-CAM stream URL, e.g. http://192.168.1.80:81/stream.
  cameraStreamUrl: '',
  // The Python RGB pipeline publishes these through the same local web server.
  vitaStatusUrl: 'outputs/live_status.json',
  vitaCameraUrl: 'outputs/live_camera.jpg',
  vitaDetectionUrl: 'outputs/live_preview.jpg',
  vitaPreviewMs: 100,
  vitaPollMs: 750,
  // Add network cameras here. MJPEG streams render directly in the scanner.
  // UV/IR cameras connected by USB also appear automatically after SCAN.
  cameraSources: [
    // { id: 'esp32', label: 'ESP32-CAM', type: 'mjpeg', url: 'http://192.168.1.80:81/stream', spectrum: 'visible' },
    // { id: 'uv-cam', label: 'UV CAMERA', type: 'mjpeg', url: 'http://192.168.1.81/stream', spectrum: 'ultraviolet' },
    // { id: 'ir-cam', label: 'IR CAMERA', type: 'mjpeg', url: 'http://192.168.1.82/stream', spectrum: 'infrared' },
  ],
};

const state = {
  temperature: 36.7,
  humidity: 61,
  healing: 68,
  packets: 1842,
  currentMetric: 'healing',
  currentRange: 24,
  cameraStream: null,
  vitaPollTimer: null,
  vitaPreviewTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function updateClock() {
  const now = new Date();
  $('#clock').textContent = now.toLocaleTimeString('en-GB', { hour12: false });
  $('#date').textContent = now.toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
  }).toUpperCase();
  $('.bottom-right').textContent = now.toLocaleTimeString('en-GB', { hour12: false });
}

function renderSensorData(data) {
  if (Number.isFinite(data.temperature)) state.temperature = data.temperature;
  if (Number.isFinite(data.humidity)) state.humidity = data.humidity;
  if (Number.isFinite(data.healing)) state.healing = data.healing;
  state.packets += 1;

  $('#tempValue').textContent = state.temperature.toFixed(1);
  $('#humidityValue').textContent = Math.round(state.humidity);
  $('#healingValue').textContent = Math.round(state.healing);
  $('#tempTrack').style.width = `${Math.min(100, Math.max(0, (state.temperature - 32) * 14))}%`;
  $('#humidityTrack').style.width = `${state.humidity}%`;
  $('#healingTrack').style.width = `${state.healing}%`;
  $('.pixel-progress').setAttribute('aria-label', `Healing progress: ${Math.round(state.healing)} percent`);
  $('#packetCount').textContent = String(state.packets).padStart(6, '0');
  $('#lastSync').textContent = 'NOW';

  if (state.currentMetric !== 'healing') drawTrendChart();
}

function startSensorConnection() {
  if (!CONFIG.websocketUrl) {
    setInterval(() => {
      renderSensorData({
        temperature: 36.7 + (Math.random() - 0.5) * 0.18,
        humidity: 61 + (Math.random() - 0.5) * 1.3,
        healing: 68 + (Math.random() - 0.5) * 0.12,
      });
    }, 2200);
    return;
  }

  const socket = new WebSocket(CONFIG.websocketUrl);
  socket.addEventListener('message', (event) => {
    try { renderSensorData(JSON.parse(event.data)); }
    catch (error) { console.warn('Invalid ESP32 sensor packet', error); }
  });
  socket.addEventListener('close', () => setTimeout(startSensorConnection, 3000));
}

function setCameraStatus(message, isError = false) {
  const status = $('#cameraSourceState');
  status.classList.toggle('error', isError);
  status.innerHTML = `<i></i> ${message}`;
}

function stopBrowserCamera() {
  if (!state.cameraStream) return;
  state.cameraStream.getTracks().forEach((track) => track.stop());
  state.cameraStream = null;
  $('#cameraVideo').srcObject = null;
}

function stopVitaPolling() {
  if (state.vitaPollTimer) clearTimeout(state.vitaPollTimer);
  if (state.vitaPreviewTimer) clearTimeout(state.vitaPreviewTimer);
  state.vitaPollTimer = null;
  state.vitaPreviewTimer = null;
}

function showCameraElement(type) {
  $('#cameraStage').classList.toggle('clean-camera', type !== 'demo');
  $('#cameraCanvas').hidden = type !== 'demo';
  $('#cameraFeed').hidden = !['mjpeg', 'vita'].includes(type);
  $('#cameraVideo').hidden = type !== 'browser';
}

function setSpectrumMode(mode) {
  const stage = $('#cameraStage');
  stage.classList.remove('mode-visible', 'mode-infrared', 'mode-ultraviolet', 'mode-thermal');
  stage.classList.add(`mode-${mode}`);
}

async function selectCameraSource(value) {
  stopBrowserCamera();
  stopVitaPolling();
  const image = $('#cameraFeed');
  image.onload = null;
  image.onerror = null;
  image.removeAttribute('src');
  $('#vitaMetrics').hidden = true;
  $('#vitaDetectionSnapshot').hidden = true;

  if (value === 'demo') {
    showCameraElement('demo');
    $('#activeCameraLabel').textContent = 'DEMO SCANNER';
    $('#activeCameraMeta').textContent = '640 × 480 / SYNTH';
    setCameraStatus('DEMO ACTIVE');
    return;
  }

  if (value === 'vita') {
    showCameraElement('demo');
    $('#vitaMetrics').hidden = false;
    $('#activeCameraLabel').textContent = 'VITA RGB / FUSEGNET';
    $('#activeCameraMeta').textContent = 'PYTHON PIPELINE / WAITING';
    setCameraStatus('CONNECTING TO INFERENCE');
    pollVitaPreview();
    pollVitaStatus();
    return;
  }

  if (value.startsWith('browser:')) {
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraStatus('CAMERA API UNAVAILABLE', true);
      return;
    }
    setCameraStatus('OPENING DEVICE');
    try {
      const deviceId = value.slice('browser:'.length);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { deviceId: { exact: deviceId } }, audio: false,
      });
      state.cameraStream = stream;
      const video = $('#cameraVideo');
      video.srcObject = stream;
      await video.play();
      showCameraElement('browser');
      const track = stream.getVideoTracks()[0];
      const settings = track.getSettings();
      $('#activeCameraLabel').textContent = (track.label || 'CONNECTED CAMERA').toUpperCase();
      $('#activeCameraMeta').textContent = `${settings.width || 'AUTO'} × ${settings.height || 'AUTO'} / LIVE`;
      setCameraStatus('DEVICE LIVE');
    } catch (error) {
      showCameraElement('demo');
      setCameraStatus(error.name === 'NotAllowedError' ? 'PERMISSION DENIED' : 'DEVICE ERROR', true);
    }
    return;
  }

  const source = CONFIG.cameraSources.find((item) => `network:${item.id}` === value);
  if (!source) return;
  image.onload = () => setCameraStatus('NETWORK FEED LIVE');
  image.onerror = () => {
    showCameraElement('demo');
    setCameraStatus('FEED UNREACHABLE', true);
  };
  image.src = source.url;
  showCameraElement('mjpeg');
  $('#activeCameraLabel').textContent = source.label.toUpperCase();
  $('#activeCameraMeta').textContent = 'NETWORK STREAM / LIVE';
  if (source.spectrum) {
    $('#spectrumSelect').value = source.spectrum;
    setSpectrumMode(source.spectrum);
  }
  setCameraStatus('CONNECTING');
}

function metricText(value, digits = 0, suffix = '') {
  return Number.isFinite(value) ? `${Number(value).toFixed(digits)}${suffix}` : '--';
}

async function pollVitaStatus() {
  if ($('#cameraSourceSelect').value !== 'vita') return;
  try {
    const response = await fetch(`${CONFIG.vitaStatusUrl}?t=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();
    const status = data.complete ? 'ACQUISITION COMPLETE' : String(data.status || 'PROCESSING');
    const statusNode = $('#vitaModelStatus');
    statusNode.textContent = status;
    statusNode.classList.toggle('good', data.status === 'GOOD' || data.complete);
    statusNode.classList.toggle('warning', data.status !== 'GOOD' && !data.complete);
    $('#vitaArea').textContent = metricText(data.wound_area_px, 0, ' PX');
    $('#vitaConfidence').textContent = metricText(data.confidence, 2);
    $('#vitaRedRatio').textContent = metricText(data.normalized_red_ratio, 3);
    $('#vitaSamples').textContent = `${data.accepted_frames ?? 0}/${data.target_frames ?? 0}`;
    $('#activeCameraMeta').textContent = `CPU / ${metricText(data.inference_fps, 2, ' FPS')}`;

    const detection = $('#vitaDetectionImage');
    detection.onload = () => {
      if ($('#cameraSourceSelect').value === 'vita') $('#vitaDetectionSnapshot').hidden = false;
    };
    detection.src = `${CONFIG.vitaDetectionUrl}?t=${Date.now()}`;
    setCameraStatus(data.complete ? 'RESULT READY' : 'INFERENCE LIVE');
  } catch (error) {
    $('#vitaModelStatus').textContent = 'PIPELINE OFFLINE';
    $('#vitaModelStatus').className = 'warning';
    $('#activeCameraMeta').textContent = 'RUN PYTHON ACQUISITION';
    setCameraStatus('START VITA PIPELINE', true);
  } finally {
    if ($('#cameraSourceSelect').value === 'vita') {
      state.vitaPollTimer = setTimeout(pollVitaStatus, CONFIG.vitaPollMs);
    }
  }
}

function pollVitaPreview() {
  if ($('#cameraSourceSelect').value !== 'vita') return;
  const image = $('#cameraFeed');
  const scheduleNext = (delay = CONFIG.vitaPreviewMs) => {
    if ($('#cameraSourceSelect').value === 'vita') {
      state.vitaPreviewTimer = setTimeout(pollVitaPreview, delay);
    }
  };
  image.onload = () => {
    if ($('#cameraSourceSelect').value === 'vita') showCameraElement('vita');
    scheduleNext();
  };
  image.onerror = () => scheduleNext(350);
  image.src = `${CONFIG.vitaCameraUrl}?t=${Date.now()}`;
}

async function loadPixilThermometer() {
  try {
    const response = await fetch('Art/Thermometer.pixil');
    if (!response.ok) throw new Error(`asset ${response.status}`);
    const project = await response.json();
    const frame = project.frames?.[0];
    const source = frame?.preview || frame?.layers?.[0]?.src;
    const comma = source?.indexOf(',') ?? -1;
    if (comma < 0) throw new Error('No Pixilart frame found');
    $('#thermometerArt').src = `data:image/png;base64,${source.slice(comma + 1)}`;
  } catch (error) {
    console.warn('Could not load thermometer Pixilart project', error);
  }
}

function addCameraOption(value, label, group) {
  const select = $('#cameraSourceSelect');
  let container = [...select.querySelectorAll('optgroup')].find((item) => item.label === group);
  if (!container) {
    container = document.createElement('optgroup');
    container.label = group;
    select.appendChild(container);
  }
  const option = document.createElement('option');
  option.value = value;
  option.textContent = label;
  container.appendChild(option);
}

async function detectCameraSources(requestPermission = false) {
  const button = $('#scanCameras');
  button.classList.add('scanning');
  setCameraStatus('SCANNING INPUTS');
  const select = $('#cameraSourceSelect');
  select.querySelectorAll('optgroup').forEach((group) => group.remove());

  const configuredSources = [...CONFIG.cameraSources];
  if (CONFIG.cameraStreamUrl && !configuredSources.some((source) => source.url === CONFIG.cameraStreamUrl)) {
    configuredSources.unshift({ id: 'legacy-esp32', label: 'ESP32-CAM', type: 'mjpeg', url: CONFIG.cameraStreamUrl, spectrum: 'visible' });
  }
  configuredSources.filter((source) => source.url).forEach((source) => {
    addCameraOption(`network:${source.id}`, `${source.label} / ${source.spectrum || 'visible'}`.toUpperCase(), 'NETWORK / SENSOR FEEDS');
  });

  if (navigator.mediaDevices?.enumerateDevices) {
    try {
      if (requestPermission) {
        const permissionStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        permissionStream.getTracks().forEach((track) => track.stop());
      }
      const devices = await navigator.mediaDevices.enumerateDevices();
      const cameras = devices.filter((device) => device.kind === 'videoinput');
      cameras.forEach((camera, index) => {
        addCameraOption(`browser:${camera.deviceId}`, (camera.label || `CAMERA INPUT ${index + 1}`).toUpperCase(), 'CONNECTED CAMERAS');
      });
      setCameraStatus(cameras.length ? `${cameras.length} DEVICE${cameras.length > 1 ? 'S' : ''} FOUND` : 'NO LOCAL CAMERA');
    } catch (error) {
      setCameraStatus(error.name === 'NotAllowedError' ? 'PERMISSION DENIED' : 'SCAN FAILED', true);
    }
  } else {
    setCameraStatus('DETECTION UNSUPPORTED', true);
  }
  button.classList.remove('scanning');
}

function setupCameraFeed() {
  $('#cameraSourceSelect').addEventListener('change', (event) => selectCameraSource(event.target.value));
  $('#spectrumSelect').addEventListener('change', (event) => setSpectrumMode(event.target.value));
  $('#scanCameras').addEventListener('click', () => detectCameraSources(true));
  navigator.mediaDevices?.addEventListener?.('devicechange', () => detectCameraSources(false));
  detectCameraSources(false);
}

// A low-resolution procedural placeholder makes the camera panel feel live until
// an ESP32-CAM URL is supplied. It is deliberately pixelated to match the console.
function drawCameraPlaceholder() {
  const canvas = $('#cameraCanvas');
  const ctx = canvas.getContext('2d');
  const scale = 5;
  const width = Math.ceil(canvas.width / scale);
  const height = Math.ceil(canvas.height / scale);
  const buffer = document.createElement('canvas');
  buffer.width = width;
  buffer.height = height;
  const b = buffer.getContext('2d');
  let phase = 0;

  function frame() {
    phase += 0.025;
    const gradient = b.createRadialGradient(width * .51, height * .51, 4, width * .5, height * .5, width * .7);
    gradient.addColorStop(0, '#d9d8ff');
    gradient.addColorStop(.45, '#393dff');
    gradient.addColorStop(1, '#101018');
    b.fillStyle = gradient;
    b.fillRect(0, 0, width, height);

    // Cloth / skin contours.
    b.strokeStyle = 'rgba(255,254,247,.22)';
    b.lineWidth = 1;
    for (let y = 8; y < height; y += 9) {
      b.beginPath();
      for (let x = 0; x < width; x += 2) {
        const wave = y + Math.sin(x * .09 + phase + y * .04) * 3;
        x === 0 ? b.moveTo(x, wave) : b.lineTo(x, wave);
      }
      b.stroke();
    }

    // Organic wound region.
    b.save();
    b.translate(width * .51, height * .52);
    b.rotate(-.2);
    b.beginPath();
    for (let i = 0; i <= 36; i++) {
      const a = (i / 36) * Math.PI * 2;
      const radius = 25 + Math.sin(a * 3 + phase) * 4 + Math.cos(a * 5) * 3;
      const x = Math.cos(a) * radius * 1.55;
      const y = Math.sin(a) * radius * .82;
      i ? b.lineTo(x, y) : b.moveTo(x, y);
    }
    b.closePath();
    b.fillStyle = '#101018';
    b.fill();
    b.strokeStyle = '#fffef7';
    b.lineWidth = 2;
    b.stroke();

    b.beginPath();
    b.ellipse(0, 0, 27, 13, 0, 0, Math.PI * 2);
    b.fillStyle = '#1d21ff';
    b.fill();
    b.setLineDash([2, 2]);
    b.strokeStyle = '#fffef7';
    b.stroke();
    b.restore();

    // Pixel sampling markers.
    b.fillStyle = 'rgba(255,254,247,.75)';
    for (let i = 0; i < 30; i++) {
      const x = (i * 43) % width;
      const y = (i * 29) % height;
      b.fillRect(x, y, 1, 1);
    }

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(buffer, 0, 0, canvas.width, canvas.height);
    requestAnimationFrame(frame);
  }
  frame();
}

const chartData = {
  healing: {
    label: 'HEALING', unit: '%', min: 0, max: 100,
    expected: [4, 8, 13, 19, 27, 37, 48, 57, 65, 72, 78, 83, 88, 92],
    actual: [5, 10, 15, 22, 30, 41, 51, 60, 68, 75, 80, 85, 90, 94],
  },
  temperature: {
    label: 'TEMPERATURE', unit: '°C', min: 35, max: 39,
    expected: [37.4, 37.3, 37.2, 37.1, 37.0, 36.9, 36.8, 36.8, 36.7, 36.7, 36.7, 36.7, 36.7, 36.7],
    actual: [37.8, 37.6, 37.3, 37.2, 37.0, 36.9, 36.9, 36.8, 36.7, 36.8, 36.7, 36.7, 36.7, 36.7],
  },
  humidity: {
    label: 'HUMIDITY', unit: '%', min: 40, max: 80,
    expected: [65, 64, 63, 62, 61, 60, 60, 60, 60, 59, 59, 59, 58, 58],
    actual: [71, 68, 66, 64, 63, 62, 60, 61, 61, 60, 60, 59, 59, 58],
  },
};

function drawTrendChart() {
  const canvas = $('#trendCanvas');
  const box = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(600, box.width * ratio);
  canvas.height = Math.max(300, box.height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.scale(ratio, ratio);
  const w = canvas.width / ratio;
  const h = canvas.height / ratio;
  const pad = { left: 58, right: 30, top: 24, bottom: 42 };
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;
  const data = chartData[state.currentMetric];

  ctx.clearRect(0, 0, w, h);
  ctx.font = '10px "Space Mono", monospace';
  ctx.textBaseline = 'middle';

  for (let i = 0; i <= 5; i++) {
    const y = pad.top + (plotH / 5) * i;
    const value = data.max - ((data.max - data.min) / 5) * i;
    ctx.strokeStyle = i === 5 ? '#101018' : 'rgba(16,16,24,.17)';
    ctx.lineWidth = i === 5 ? 2 : 1;
    ctx.setLineDash(i === 5 ? [] : [3, 5]);
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke();
    ctx.fillStyle = '#575762';
    ctx.textAlign = 'right';
    ctx.fillText(`${Math.round(value * 10) / 10}${data.unit}`, pad.left - 10, y);
  }

  const point = (value, index) => ({
    x: pad.left + (index / (data.actual.length - 1)) * plotW,
    y: pad.top + ((data.max - value) / (data.max - data.min)) * plotH,
  });

  ctx.textAlign = 'center';
  ctx.fillStyle = '#575762';
  const dayStep = state.currentRange === 24 ? 'HR' : 'DAY';
  data.actual.forEach((_, i) => {
    if (i % 2 !== 0 && i !== data.actual.length - 1) return;
    const x = point(data.actual[i], i).x;
    ctx.fillText(`${dayStep} ${i + 1}`, x, h - 18);
  });

  function line(values, color, dashed, width) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.setLineDash(dashed ? [8, 7] : []);
    ctx.beginPath();
    values.forEach((value, index) => {
      const p = point(value, index);
      index ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y);
    });
    ctx.stroke();
  }

  line(data.expected, '#101018', true, 2);
  line(data.actual, '#1d21ff', false, 4);

  data.actual.forEach((value, index) => {
    const p = point(value, index);
    ctx.fillStyle = index === data.actual.length - 1 ? '#1d21ff' : '#fffef7';
    ctx.strokeStyle = '#1d21ff';
    ctx.lineWidth = 3;
    ctx.fillRect(p.x - 4, p.y - 4, 8, 8);
    ctx.strokeRect(p.x - 4, p.y - 4, 8, 8);
  });

  const current = data.actual[data.actual.length - 1];
  const expected = data.expected[data.expected.length - 1];
  const digits = data.unit === '°C' ? 1 : 0;
  $('#statCurrent').textContent = `${current.toFixed(digits)}${data.unit}`;
  $('#statExpected').textContent = `${expected.toFixed(digits)}${data.unit}`;
  const variance = current - expected;
  $('#statVariance').textContent = `${variance >= 0 ? '+' : ''}${variance.toFixed(digits)}${data.unit}`;

  canvas._chart = { data, point, pad, plotW, w, h };
}

function setupChartInteraction() {
  const canvas = $('#trendCanvas');
  const tooltip = $('#chartTooltip');
  canvas.addEventListener('mousemove', (event) => {
    if (!canvas._chart) return;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const chart = canvas._chart;
    const index = Math.max(0, Math.min(chart.data.actual.length - 1,
      Math.round(((x - chart.pad.left) / chart.plotW) * (chart.data.actual.length - 1))));
    const p = chart.point(chart.data.actual[index], index);
    tooltip.hidden = false;
    tooltip.style.left = `${Math.min(rect.width - 145, Math.max(8, p.x + 12))}px`;
    tooltip.style.top = `${Math.max(8, p.y - 55)}px`;
    tooltip.innerHTML = `DAY ${String(index + 1).padStart(2, '0')}<br>OBS: ${chart.data.actual[index]}${chart.data.unit}<br>EXP: ${chart.data.expected[index]}${chart.data.unit}`;
  });
  canvas.addEventListener('mouseleave', () => { tooltip.hidden = true; });
}

function showScreen(screenName) {
  if (!['overview', 'trends'].includes(screenName)) screenName = 'overview';
  document.body.dataset.screen = screenName;
  const overview = document.getElementById('overview');
  const trends = document.getElementById('trends');
  overview.style.display = screenName === 'overview' ? 'block' : 'none';
  trends.style.display = screenName === 'trends' ? 'block' : 'none';
  overview.classList.toggle('active', screenName === 'overview');
  trends.classList.toggle('active', screenName === 'trends');
  $$('.nav-item').forEach((button) => button.classList.toggle('active', button.dataset.screen === screenName));
  if (location.hash !== `#${screenName}`) history.replaceState(null, '', `#${screenName}`);
  if (screenName === 'trends') requestAnimationFrame(drawTrendChart);
}

function setupNavigation() {
  const drawer = $('#drawer');
  const toggle = $('#drawerToggle');
  toggle.addEventListener('click', () => {
    drawer.classList.toggle('open');
    toggle.setAttribute('aria-expanded', drawer.classList.contains('open'));
  });
  $$('.nav-item').forEach((button) => button.addEventListener('click', () => {
    showScreen(button.dataset.screen);
    drawer.classList.remove('open');
    toggle.setAttribute('aria-expanded', 'false');
  }));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Tab' && event.target === document.body) {
      event.preventDefault();
      const isOverview = $('#overview').classList.contains('active');
      showScreen(isOverview ? 'trends' : 'overview');
    }
    if (event.key === 'Escape') drawer.classList.remove('open');
  });
}

function setupChartControls() {
  $$('.metric-tabs button').forEach((button) => button.addEventListener('click', () => {
    $$('.metric-tabs button').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    state.currentMetric = button.dataset.metric;
    drawTrendChart();
  }));
  $$('.range-switcher button').forEach((button) => button.addEventListener('click', () => {
    $$('.range-switcher button').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    state.currentRange = Number(button.dataset.range);
    drawTrendChart();
  }));
}

updateClock();
setInterval(updateClock, 1000);
setupNavigation();
setupChartControls();
setupChartInteraction();
setupCameraFeed();
loadPixilThermometer();
drawCameraPlaceholder();
startSensorConnection();
showScreen(location.hash.slice(1) || 'overview');
window.addEventListener('hashchange', () => showScreen(location.hash.slice(1) || 'overview'));
window.addEventListener('resize', () => {
  if ($('#trends').classList.contains('active')) drawTrendChart();
});
