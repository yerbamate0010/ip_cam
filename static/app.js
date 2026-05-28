const monitorStatus = document.getElementById('monitorStatus');
const recording = document.getElementById('recording');
const targetsVisible = document.getElementById('targetsVisible');
const fpsInfo = document.getElementById('fpsInfo');
const cameraInfo = document.getElementById('cameraInfo');
const yoloInfo = document.getElementById('yoloInfo');
const deviceInfo = document.getElementById('deviceInfo');
const streamSource = document.getElementById('streamSource');
const modelName = document.getElementById('modelName');
const events = document.getElementById('events');
const previewFrame = document.getElementById('previewFrame');
const previewImg = document.getElementById('preview');
const roiLayer = document.getElementById('roiLayer');
const roiBox = document.getElementById('roiBox');
const roiDraft = document.getElementById('roiDraft');
const roiEdit = document.getElementById('roiEdit');
const roiSave = document.getElementById('roiSave');
const roiClear = document.getElementById('roiClear');
const streamForm = document.getElementById('streamForm');
const streamInput = document.getElementById('streamInput');
const streamSave = document.getElementById('streamSave');

let currentRoi = null;
let draftRoi = null;
let editingRoi = false;
let dragStart = null;

function text(value, yes, no) {
  return value ? yes : no;
}

function sourceHost(value) {
  try {
    const url = new URL(value);
    return url.host;
  } catch (error) {
    return value || '-';
  }
}

function fitValue(element, maxSize = 13, minSize = 8) {
  element.style.setProperty('--value-size', `${maxSize}px`);
  for (let size = maxSize; size >= minSize; size -= 0.5) {
    element.style.setProperty('--value-size', `${size}px`);
    if (element.scrollWidth <= element.clientWidth) {
      return;
    }
  }
}

function fitCompactValues() {
  fitValue(streamSource);
  fitValue(modelName);
  fitValue(deviceInfo);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function renderEvents(items) {
  if (!items.length) {
    events.innerHTML = '<div class="event"><strong>Brak zdarzen</strong><span>Lista uzupelni sie po wykryciu psa albo czlowieka.</span></div>';
    return;
  }

  events.innerHTML = items.map((event) => {
    const path = event.video || event.image || '';
    const isVideo = Boolean(event.video);
    const url = isVideo ? `/${path.replace('output/', 'download/')}` : `/${path}`;
    const label = isVideo ? 'pobierz wideo' : 'otworz zdjecie';
    const link = path.startsWith('output/')
      ? `<a href="${escapeHtml(url)}" ${isVideo ? 'download' : 'target="_blank"'}>${label}</a>`
      : escapeHtml(path);
    return `<div class="event"><strong>${escapeHtml(event.time)} - ${escapeHtml(event.message)}</strong><span>${link}</span></div>`;
  }).join('');
}

function imageRect() {
  const frameRect = previewFrame.getBoundingClientRect();
  const imgRect = previewImg.getBoundingClientRect();
  return {
    left: imgRect.left - frameRect.left,
    top: imgRect.top - frameRect.top,
    width: imgRect.width,
    height: imgRect.height,
  };
}

function positionBox(element, roi) {
  if (!roi) {
    element.classList.remove('visible');
    return;
  }

  const rect = imageRect();
  element.style.left = `${rect.left + roi.x1 * rect.width}px`;
  element.style.top = `${rect.top + roi.y1 * rect.height}px`;
  element.style.width = `${(roi.x2 - roi.x1) * rect.width}px`;
  element.style.height = `${(roi.y2 - roi.y1) * rect.height}px`;
  element.classList.add('visible');
}

function renderRoi() {
  positionBox(roiBox, currentRoi);
  positionBox(roiDraft, draftRoi);
  roiSave.disabled = !draftRoi;
}

function clamp(value) {
  return Math.max(0, Math.min(1, value));
}

function eventPoint(event) {
  const rect = previewImg.getBoundingClientRect();
  return {
    x: clamp((event.clientX - rect.left) / rect.width),
    y: clamp((event.clientY - rect.top) / rect.height),
  };
}

function roiFromPoints(a, b) {
  return {
    x1: Math.min(a.x, b.x),
    y1: Math.min(a.y, b.y),
    x2: Math.max(a.x, b.x),
    y2: Math.max(a.y, b.y),
  };
}

function setEditing(enabled) {
  editingRoi = enabled;
  roiEdit.classList.toggle('active', editingRoi);
  roiLayer.classList.toggle('editing', editingRoi);
  if (!editingRoi) {
    dragStart = null;
  }
}

async function loadConfig() {
  const response = await fetch('/api/config', { cache: 'no-store' });
  const config = await response.json();
  currentRoi = config.roi || null;
  streamInput.value = config.stream_url || '';
  renderRoi();
}

async function saveRoi() {
  if (!draftRoi) {
    return;
  }

  const response = await fetch('/api/roi', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draftRoi),
  });
  if (!response.ok) {
    return;
  }
  const payload = await response.json();
  currentRoi = payload.roi || null;
  draftRoi = null;
  setEditing(false);
  renderRoi();
}

async function clearRoi() {
  const response = await fetch('/api/roi', { method: 'DELETE' });
  if (!response.ok) {
    return;
  }
  currentRoi = null;
  draftRoi = null;
  setEditing(false);
  renderRoi();
}

async function saveStream(event) {
  event.preventDefault();
  const streamUrl = streamInput.value.trim();
  if (!streamUrl) {
    return;
  }

  streamSave.disabled = true;
  try {
    const response = await fetch('/api/stream', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stream_url: streamUrl }),
    });
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    streamInput.value = payload.stream_url || streamUrl;
    streamSource.textContent = sourceHost(streamInput.value);
    streamSource.title = streamInput.value;
  } finally {
    streamSave.disabled = false;
  }
}

async function refresh() {
  try {
    const response = await fetch('/api/status', { cache: 'no-store' });
    const data = await response.json();
    const status = data.status;
    monitorStatus.textContent = status.recording
      ? 'nagrywa'
      : text(status.running, 'aktywny', 'stop');
    recording.textContent = text(status.recording, 'tak', 'nie');
    targetsVisible.textContent = status.target_visible
      ? `pies ${status.dog_count || 0} / osoba ${status.person_count || 0}`
      : 'brak';
    fpsInfo.textContent = `${status.actual_fps || '-'} / ${status.evidence_fps || '-'}`;
    cameraInfo.textContent = `${status.camera_resolution || status.frame_size || '-'} / ${status.camera_quality || '-'}`;
    yoloInfo.textContent = `${status.active_detect_width || '-'}px / ${status.detect_interval || '-'}s`;
    deviceInfo.textContent = `${status.yolo_device || '-'} / ${status.roi_active ? 'ROI' : 'pelny'}`;
    streamSource.textContent = sourceHost(status.stream_url);
    streamSource.title = status.stream_url || '';
    if (document.activeElement !== streamInput) {
      streamInput.value = status.stream_url || '';
    }
    modelName.textContent = status.model ? status.model.split('/').pop() : '-';
    if (!editingRoi && !draftRoi) {
      currentRoi = status.roi || null;
      renderRoi();
    }
    fitCompactValues();
    renderEvents(data.events || []);
  } catch (error) {
    monitorStatus.textContent = 'brak pol.';
  }
}

roiEdit.addEventListener('click', () => setEditing(!editingRoi));
roiSave.addEventListener('click', saveRoi);
roiClear.addEventListener('click', clearRoi);
streamForm.addEventListener('submit', saveStream);

roiLayer.addEventListener('pointerdown', (event) => {
  if (!editingRoi) {
    return;
  }
  dragStart = eventPoint(event);
  draftRoi = roiFromPoints(dragStart, dragStart);
  roiLayer.setPointerCapture(event.pointerId);
  renderRoi();
});

roiLayer.addEventListener('pointermove', (event) => {
  if (!editingRoi || !dragStart) {
    return;
  }
  draftRoi = roiFromPoints(dragStart, eventPoint(event));
  renderRoi();
});

roiLayer.addEventListener('pointerup', (event) => {
  if (!editingRoi || !dragStart) {
    return;
  }
  draftRoi = roiFromPoints(dragStart, eventPoint(event));
  dragStart = null;
  renderRoi();
});

loadConfig().catch(() => {});
refresh();
setInterval(refresh, 1000);
previewImg.addEventListener('load', renderRoi);
window.addEventListener('resize', renderRoi);
window.addEventListener('resize', fitCompactValues);
