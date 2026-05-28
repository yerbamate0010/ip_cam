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
const detectionOpen = document.getElementById('detectionOpen');
const detectionModal = document.getElementById('detectionModal');
const detectionClose = document.getElementById('detectionClose');
const detectionForm = document.getElementById('detectionForm');
const detectionSave = document.getElementById('detectionSave');
const detectionStatus = document.getElementById('detectionStatus');
const detectionProfile = document.getElementById('detectionProfile');
const modelPath = document.getElementById('modelPath');
const yoloDevice = document.getElementById('yoloDevice');
const dogConf = document.getElementById('dogConf');
const personConf = document.getElementById('personConf');
const yoloImgsz = document.getElementById('yoloImgsz');
const detectWidth = document.getElementById('detectWidth');
const idleDetectSeconds = document.getElementById('idleDetectSeconds');
const activeDetectSeconds = document.getElementById('activeDetectSeconds');
const activeTrackSeconds = document.getElementById('activeTrackSeconds');
const postRollSeconds = document.getElementById('postRollSeconds');
const minHitsDog = document.getElementById('minHitsDog');
const minHitsPerson = document.getElementById('minHitsPerson');
const evidenceFps = document.getElementById('evidenceFps');
const triggerDog = document.getElementById('triggerDog');
const triggerPerson = document.getElementById('triggerPerson');
const previewEnabled = document.getElementById('previewEnabled');

let currentRoi = null;
let draftRoi = null;
let editingRoi = false;
let dragStart = null;
let detectionProfiles = {};
let fillingDetectionForm = false;

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

function displaySize(value) {
  return value === 'auto' || value === 0 ? 'auto' : `${value}`;
}

function fillDetectionForm(config) {
  fillingDetectionForm = true;
  detectionProfile.value = config.profile || 'custom';
  modelPath.value = config.model_path || '';
  yoloDevice.value = config.yolo_device || 'auto';
  dogConf.value = config.dog_conf;
  personConf.value = config.person_conf;
  yoloImgsz.value = displaySize(config.yolo_imgsz);
  detectWidth.value = displaySize(config.detect_width);
  idleDetectSeconds.value = config.idle_detect_seconds;
  activeDetectSeconds.value = config.active_detect_seconds;
  activeTrackSeconds.value = config.active_track_seconds;
  postRollSeconds.value = config.post_roll_seconds;
  minHitsDog.value = config.min_hits_dog;
  minHitsPerson.value = config.min_hits_person;
  evidenceFps.value = displaySize(config.evidence_fps);
  triggerDog.checked = (config.trigger_labels || []).includes('dog');
  triggerPerson.checked = (config.trigger_labels || []).includes('person');
  previewEnabled.checked = Boolean(config.preview_enabled);
  fillingDetectionForm = false;
}

function detectionPayload() {
  const triggerLabels = [];
  if (triggerDog.checked) triggerLabels.push('dog');
  if (triggerPerson.checked) triggerLabels.push('person');
  return {
    profile: detectionProfile.value,
    model_path: modelPath.value.trim(),
    yolo_device: yoloDevice.value,
    dog_conf: Number(dogConf.value),
    person_conf: Number(personConf.value),
    yolo_imgsz: yoloImgsz.value,
    detect_width: detectWidth.value,
    idle_detect_seconds: Number(idleDetectSeconds.value),
    active_detect_seconds: Number(activeDetectSeconds.value),
    active_track_seconds: Number(activeTrackSeconds.value),
    post_roll_seconds: Number(postRollSeconds.value),
    min_hits_dog: Number(minHitsDog.value),
    min_hits_person: Number(minHitsPerson.value),
    evidence_fps: evidenceFps.value,
    trigger_labels: triggerLabels,
    preview_enabled: previewEnabled.checked,
  };
}

async function openDetectionModal() {
  detectionModal.hidden = false;
  detectionStatus.textContent = 'Laduje...';
  const response = await fetch('/api/detection-config', { cache: 'no-store' });
  if (!response.ok) {
    throw new Error('detection config unavailable');
  }
  const payload = await response.json();
  detectionProfiles = payload.profiles || {};
  fillDetectionForm(payload.config || {});
  detectionStatus.textContent = payload.model_status?.message || '-';
}

function closeDetectionModal() {
  detectionModal.hidden = true;
}

async function saveDetectionConfig(event) {
  event.preventDefault();
  detectionSave.disabled = true;
  detectionStatus.textContent = 'Zapisuje...';
  try {
    const response = await fetch('/api/detection-config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(detectionPayload()),
    });
    const payload = await response.json();
    if (!response.ok) {
      detectionStatus.textContent = payload.error || 'Blad zapisu';
      return;
    }
    fillDetectionForm(payload.config);
    detectionStatus.textContent = payload.restarted ? 'Przeladowuje silnik' : 'Zapisano';
    refresh();
  } catch (error) {
    detectionStatus.textContent = 'Blad zapisu';
  } finally {
    detectionSave.disabled = false;
  }
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
      : status.engine_restarting
        ? 'restart'
        : status.engine_state === 'error'
          ? 'blad'
          : text(status.running, 'aktywny', 'stop');
    recording.textContent = text(status.recording, 'tak', 'nie');
    targetsVisible.textContent = status.target_visible
      ? `pies ${status.dog_count || 0} / osoba ${status.person_count || 0}`
      : 'brak';
    fpsInfo.textContent = `${status.actual_fps || '-'} / ${status.evidence_fps || '-'}`;
    cameraInfo.textContent = `${status.camera_resolution || status.frame_size || '-'} / ${status.camera_quality || '-'}`;
    yoloInfo.textContent = `${status.active_detect_width || '-'}px / ${status.requested_yolo_imgsz || '-'} / ${status.detect_interval || '-'}s`;
    deviceInfo.textContent = `${status.yolo_device || '-'} / ${status.roi_pixels || (status.roi_active ? 'ROI' : 'pelny')}`;
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
detectionOpen.addEventListener('click', () => openDetectionModal().catch(() => {
  detectionModal.hidden = false;
  detectionStatus.textContent = 'Blad konfiguracji';
}));
detectionClose.addEventListener('click', closeDetectionModal);
detectionModal.addEventListener('click', (event) => {
  if (event.target === detectionModal) {
    closeDetectionModal();
  }
});
detectionForm.addEventListener('submit', saveDetectionConfig);
detectionProfile.addEventListener('change', () => {
  const profile = detectionProfiles[detectionProfile.value];
  if (profile) {
    fillDetectionForm(profile);
    detectionStatus.textContent = 'Profil gotowy';
  }
});
detectionForm.addEventListener('input', (event) => {
  if (!fillingDetectionForm && event.target !== detectionProfile) {
    detectionProfile.value = 'custom';
  }
});

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
