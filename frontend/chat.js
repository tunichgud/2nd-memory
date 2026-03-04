// chat.js – Chat-UI Logik für memosaur

const SOURCE_LABELS = {
  photos:       { label: 'Foto',              color: 'blue',   icon: '📷' },
  reviews:      { label: 'Bewertung',         color: 'emerald',icon: '⭐' },
  saved_places: { label: 'Gespeicherter Ort', color: 'amber',  icon: '📍' },
  messages:     { label: 'Nachricht',         color: 'purple', icon: '💬' },
};

// -------------------------------------------------------------------------
// Abfrage senden
// -------------------------------------------------------------------------
async function sendQuery() {
  const input = document.getElementById('chat-input');
  const query = input.value.trim();
  if (!query) return;

  input.value = '';
  appendUserMessage(query);
  const typingId = appendTypingIndicator();

  try {
    const res = await fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, n_results: 8, min_score: 0.25 }),
    });

    removeTyping(typingId);

    if (!res.ok) {
      const err = await res.json();
      appendErrorMessage(err.detail || 'Unbekannter Fehler');
      return;
    }

    const data = await res.json();
    appendAssistantMessage(data.answer, data.sources, data.parsed_query);

  } catch (e) {
    removeTyping(typingId);
    appendErrorMessage('Verbindungsfehler: ' + e.message);
  }
}

function quickQuery(text) {
  document.getElementById('chat-input').value = text;
  sendQuery();
}

// -------------------------------------------------------------------------
// Nachrichten rendern
// -------------------------------------------------------------------------
function appendUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'flex justify-end';
  div.innerHTML = `
    <div class="bg-blue-700 text-white rounded-2xl rounded-br-sm px-4 py-3 max-w-[80%] text-sm">
      ${escHtml(text)}
    </div>`;
  chatMessages().appendChild(div);
  scrollBottom();
}

function appendAssistantMessage(text, sources, parsedQuery) {
  const div = document.createElement('div');
  div.className = 'flex flex-col gap-3 max-w-[92%]';

  // Filter-Zusammenfassung (erkannte Suchparameter)
  if (parsedQuery && parsedQuery.filter_summary) {
    const filterDiv = document.createElement('div');
    filterDiv.className = 'flex flex-wrap gap-1 text-[11px]';

    // Kleine Chips für Personen, Zeitraum, Orte
    if (parsedQuery.persons && parsedQuery.persons.length > 0) {
      parsedQuery.persons.forEach(p => {
        filterDiv.appendChild(_filterChip('👤', p, 'bg-blue-900 text-blue-300'));
      });
    }
    if (parsedQuery.date_from) {
      const label = parsedQuery.filter_summary.match(/Zeitraum: ([^·]+)/)?.[1]?.trim()
        || `${parsedQuery.date_from} – ${parsedQuery.date_to || '…'}`;
      filterDiv.appendChild(_filterChip('📅', label, 'bg-gray-800 text-gray-400'));
    }
    if (parsedQuery.locations && parsedQuery.locations.length > 0) {
      parsedQuery.locations.forEach(l => {
        filterDiv.appendChild(_filterChip('📍', l, 'bg-amber-900 text-amber-300'));
      });
    }
    if (filterDiv.children.length > 0) {
      div.appendChild(filterDiv);
    }
  }

  // Antworttext
  const bubble = document.createElement('div');
  bubble.className = 'bg-gray-800 rounded-2xl rounded-bl-sm px-4 py-3 text-sm leading-relaxed';
  bubble.innerHTML = formatAnswer(text);
  div.appendChild(bubble);

  // Quellen – immer direkt sichtbar, nach Collection gruppiert
  if (sources && sources.length > 0) {
    // Nach Collection gruppieren für übersichtliche Darstellung
    const byCollection = {};
    sources.forEach(src => {
      if (!byCollection[src.collection]) byCollection[src.collection] = [];
      byCollection[src.collection].push(src);
    });

    const srcWrapper = document.createElement('div');
    srcWrapper.className = 'flex flex-col gap-2 ml-1';

    // Kopfzeile mit Quellenübersicht und Toggle
    const header = document.createElement('div');
    header.className = 'flex items-center gap-3 flex-wrap';

    // Badges pro Quellentyp
    Object.entries(byCollection).forEach(([col, items]) => {
      const info = SOURCE_LABELS[col] || { label: col, icon: '📄' };
      const badgeColors = {
        photos: 'bg-blue-900 text-blue-300 border-blue-700',
        reviews: 'bg-emerald-900 text-emerald-300 border-emerald-700',
        saved_places: 'bg-amber-900 text-amber-300 border-amber-700',
        messages: 'bg-purple-900 text-purple-300 border-purple-700',
      };
      const badge = document.createElement('span');
      badge.className = `text-xs px-2 py-0.5 rounded-full border ${badgeColors[col] || 'bg-gray-800 text-gray-400 border-gray-600'}`;
      badge.textContent = `${info.icon} ${info.label} (${items.length})`;
      header.appendChild(badge);
    });

    const toggle = document.createElement('button');
    toggle.className = 'text-xs text-gray-500 hover:text-gray-300 ml-auto';
    toggle.textContent = 'Details ausblenden';
    header.appendChild(toggle);
    srcWrapper.appendChild(header);

    // Quellenliste – standardmäßig SICHTBAR
    const srcList = document.createElement('div');
    srcList.className = 'flex flex-col gap-1';

    // Quellen nach Collection sortiert ausgeben
    const colOrder = ['photos', 'reviews', 'saved_places', 'messages'];
    const sortedCols = [...new Set([...colOrder, ...Object.keys(byCollection)])];
    sortedCols.forEach(col => {
      if (!byCollection[col]) return;
      byCollection[col].forEach(src => srcList.appendChild(renderSource(src)));
    });

    toggle.onclick = () => {
      const hidden = srcList.classList.toggle('hidden');
      toggle.textContent = hidden ? 'Details anzeigen' : 'Details ausblenden';
    };

    srcWrapper.appendChild(srcList);
    div.appendChild(srcWrapper);
  }

  chatMessages().appendChild(div);
  scrollBottom();
}

function renderSource(src) {
  const info = SOURCE_LABELS[src.collection] || { label: src.collection, color: 'gray', icon: '📄' };
  const pct = Math.round(src.score * 100);
  const meta = src.metadata || {};

  const borderColors = {
    photos: 'border-blue-500',
    reviews: 'border-emerald-500',
    saved_places: 'border-amber-500',
    messages: 'border-purple-500',
  };
  const bgColors = {
    photos: 'bg-blue-950',
    reviews: 'bg-emerald-950',
    saved_places: 'bg-amber-950',
    messages: 'bg-purple-950',
  };
  const border = borderColors[src.collection] || 'border-gray-600';
  const bg = bgColors[src.collection] || 'bg-gray-900';

  const div = document.createElement('div');
  div.className = `${bg} rounded-lg border-l-4 ${border} overflow-hidden`;

  if (src.collection === 'photos') {
    div.appendChild(_renderPhotoSource(src, meta, info, pct));
  } else if (src.collection === 'reviews') {
    div.appendChild(_renderReviewSource(src, meta, info, pct));
  } else if (src.collection === 'saved_places') {
    div.appendChild(_renderSavedSource(src, meta, info, pct));
  } else if (src.collection === 'messages') {
    div.appendChild(_renderMessageSource(src, meta, info, pct));
  }

  return div;
}

// ---- Foto-Quelle: Thumbnail links + Metadaten rechts ----
function _renderPhotoSource(src, meta, info, pct) {
  const wrap = document.createElement('div');
  wrap.className = 'flex gap-0 text-xs';

  // Thumbnail
  const filename = meta.filename || '';
  const thumbUrl = filename ? `/api/media/${encodeURIComponent(filename)}?size=thumb` : '';
  const fullUrl  = filename ? `/api/media/${encodeURIComponent(filename)}?size=full`  : '';

  if (thumbUrl) {
    const imgWrap = document.createElement('div');
    imgWrap.className = 'flex-shrink-0 w-24 h-24 bg-gray-800 cursor-pointer relative group';
    imgWrap.title = 'Klicken für Vollbild';
    imgWrap.onclick = () => _openLightbox(fullUrl, meta);

    const img = document.createElement('img');
    img.src = thumbUrl;
    img.className = 'w-full h-full object-cover';
    img.onerror = () => { imgWrap.style.display = 'none'; };
    imgWrap.appendChild(img);

    // Hover-Overlay
    const overlay = document.createElement('div');
    overlay.className = 'absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-30 transition-all flex items-center justify-center';
    overlay.innerHTML = '<span class="text-white text-lg opacity-0 group-hover:opacity-100">🔍</span>';
    imgWrap.appendChild(overlay);

    wrap.appendChild(imgWrap);
  }

  // Metadaten
  const info_div = document.createElement('div');
  info_div.className = 'flex-1 px-3 py-2 flex flex-col gap-1 min-w-0';

  const header = `<div class="flex justify-between items-center">
    <span class="font-semibold text-gray-200">${info.icon} ${info.label}</span>
    <span class="text-gray-500 text-[10px]">${pct}%</span>
  </div>`;

  const metaParts = [];
  if (meta.date_iso)    metaParts.push(`📅 ${formatDate(meta.date_iso)}`);
  if (meta.place_name)  metaParts.push(`📍 ${meta.place_name}`);
  else if (meta.lat && meta.lat !== 0) metaParts.push(`🗺 ${meta.lat.toFixed(3)}°N`);
  if (meta.persons)     metaParts.push(`👤 ${meta.persons}`);

  const metaHtml = metaParts.length
    ? `<div class="text-gray-400 flex flex-wrap gap-x-2 gap-y-0.5">${metaParts.map(l => `<span>${escHtml(l)}</span>`).join('')}</div>`
    : '';

  // Bildbeschreibung aus Dokument extrahieren
  const descMatch = src.document.match(/Bildbeschreibung:\s*(.+?)(?:\n|$)/s);
  const desc = descMatch ? descMatch[1].trim().substring(0, 120) : '';
  const descHtml = desc
    ? `<div class="text-gray-500 leading-snug italic">${escHtml(desc)}${desc.length >= 120 ? '…' : ''}</div>`
    : '';

  info_div.innerHTML = header + metaHtml + descHtml;
  wrap.appendChild(info_div);
  return wrap;
}

// ---- Bewertungs-Quelle: Sterne + Freitext-Ausschnitt ----
function _renderReviewSource(src, meta, info, pct) {
  const div = document.createElement('div');
  div.className = 'px-3 py-2 text-xs flex flex-col gap-1';

  const stars = meta.rating ? '⭐'.repeat(Math.min(meta.rating, 5)) : '';
  const header = `<div class="flex justify-between items-center">
    <span class="font-semibold text-gray-200">${info.icon} ${escHtml(meta.name || info.label)}</span>
    <span class="text-gray-500 text-[10px]">${pct}%</span>
  </div>`;

  const metaParts = [];
  if (meta.address)  metaParts.push(`📍 ${meta.address}`);
  if (meta.date_iso) metaParts.push(`📅 ${formatDate(meta.date_iso)}`);
  if (stars)         metaParts.push(stars);

  const metaHtml = metaParts.length
    ? `<div class="text-gray-400 flex flex-wrap gap-x-2">${metaParts.map(l => `<span>${escHtml(l)}</span>`).join('')}</div>`
    : '';

  // Rezensions-Text aus Dokument extrahieren
  const rezMatch = src.document.match(/Rezension:\s*(.+?)(?:\n|$)/s);
  const rezText = rezMatch ? rezMatch[1].trim().substring(0, 180) : src.document.substring(0, 180);
  const rezHtml = rezText
    ? `<div class="text-gray-400 leading-snug bg-gray-900 rounded px-2 py-1 border-l-2 border-emerald-700">${escHtml(rezText)}${rezText.length >= 180 ? '…' : ''}</div>`
    : '';

  div.innerHTML = header + metaHtml + rezHtml;
  return div;
}

// ---- Gespeicherter Ort: Adresse + Maps-Link ----
function _renderSavedSource(src, meta, info, pct) {
  const div = document.createElement('div');
  div.className = 'px-3 py-2 text-xs flex flex-col gap-1';

  const header = `<div class="flex justify-between items-center">
    <span class="font-semibold text-gray-200">${info.icon} ${escHtml(meta.name || info.label)}</span>
    <span class="text-gray-500 text-[10px]">${pct}%</span>
  </div>`;

  const metaParts = [];
  if (meta.address)  metaParts.push(`🏠 ${meta.address}`);
  if (meta.country)  metaParts.push(`🌍 ${meta.country}`);
  if (meta.date_iso) metaParts.push(`📅 ${formatDate(meta.date_iso)}`);

  const metaHtml = metaParts.length
    ? `<div class="text-gray-400 flex flex-wrap gap-x-2">${metaParts.map(l => `<span>${escHtml(l)}</span>`).join('')}</div>`
    : '';

  const mapsHtml = meta.maps_url
    ? `<a href="${escHtml(meta.maps_url)}" target="_blank" class="text-amber-400 hover:text-amber-300 text-[10px]">In Google Maps öffnen →</a>`
    : '';

  div.innerHTML = header + metaHtml + mapsHtml;
  return div;
}

// ---- Nachrichten-Quelle: Chat-Ausschnitt mit Personen-Highlight ----
function _renderMessageSource(src, meta, info, pct) {
  const div = document.createElement('div');
  div.className = 'px-3 py-2 text-xs flex flex-col gap-1';

  const header = `<div class="flex justify-between items-center">
    <span class="font-semibold text-gray-200">${info.icon} ${escHtml(meta.chat_name || info.label)}</span>
    <span class="text-gray-500 text-[10px]">${pct}%</span>
  </div>`;

  const metaParts = [];
  if (meta.date_iso) metaParts.push(`📅 ${formatDate(meta.date_iso)}`);
  const personsToShow = meta.mentioned_persons || meta.persons;
  if (personsToShow) metaParts.push(`👤 ${personsToShow}`);

  const metaHtml = metaParts.length
    ? `<div class="text-gray-400 flex flex-wrap gap-x-2 mb-1">${metaParts.map(l => `<span>${escHtml(l)}</span>`).join('')}</div>`
    : '';

  // Chat-Zeilen aus Dokument extrahieren und als Blasen rendern
  const lines = src.document.split('\n').filter(l => l.match(/^\[.+\] .+:/));
  const chatHtml = lines.length
    ? `<div class="flex flex-col gap-0.5 bg-gray-900 rounded px-2 py-1 max-h-32 overflow-y-auto">
        ${lines.map(line => {
          const m = line.match(/^\[(.+?)\] (.+?): (.+)$/);
          if (!m) return `<div class="text-gray-500">${escHtml(line)}</div>`;
          const [, time, sender, text] = m;
          const isMe = sender.toLowerCase().includes('josh');
          return `<div class="flex gap-1 ${isMe ? 'justify-end' : ''}">
            <span class="text-gray-600 text-[9px] self-end">${escHtml(time)}</span>
            <span class="rounded px-1.5 py-0.5 text-[11px] max-w-[80%] ${isMe ? 'bg-blue-900 text-blue-100' : 'bg-gray-700 text-gray-100'}">
              ${isMe ? '' : `<span class="text-gray-400 text-[9px] block">${escHtml(sender)}</span>`}
              ${escHtml(text)}
            </span>
          </div>`;
        }).join('')}
      </div>`
    : `<div class="text-gray-500 leading-snug">${escHtml(src.document.substring(0, 200))}</div>`;

  div.innerHTML = header + metaHtml;
  div.insertAdjacentHTML('beforeend', chatHtml);
  return div;
}

// ---- Lightbox für Vollbild-Ansicht ----
function _openLightbox(fullUrl, meta) {
  // Bestehendes Lightbox entfernen
  document.getElementById('memosaur-lightbox')?.remove();

  const overlay = document.createElement('div');
  overlay.id = 'memosaur-lightbox';
  overlay.className = 'fixed inset-0 bg-black bg-opacity-90 z-50 flex items-center justify-center p-4';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

  const inner = document.createElement('div');
  inner.className = 'relative max-w-4xl max-h-full flex flex-col gap-2';

  const img = document.createElement('img');
  img.src = fullUrl;
  img.className = 'max-h-[80vh] max-w-full object-contain rounded-lg shadow-2xl';

  const caption = document.createElement('div');
  caption.className = 'text-white text-sm text-center flex flex-wrap justify-center gap-4';
  if (meta.date_iso)   caption.innerHTML += `<span>📅 ${formatDate(meta.date_iso)}</span>`;
  if (meta.place_name) caption.innerHTML += `<span>📍 ${escHtml(meta.place_name)}</span>`;
  if (meta.persons)    caption.innerHTML += `<span>👤 ${escHtml(meta.persons)}</span>`;

  const close = document.createElement('button');
  close.className = 'absolute -top-3 -right-3 w-8 h-8 bg-gray-700 hover:bg-gray-600 rounded-full text-white flex items-center justify-center text-lg leading-none';
  close.textContent = '×';
  close.onclick = () => overlay.remove();

  inner.appendChild(img);
  inner.appendChild(caption);
  inner.appendChild(close);
  overlay.appendChild(inner);
  document.body.appendChild(overlay);

  // ESC schließt Lightbox
  const escHandler = (e) => { if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', escHandler); } };
  document.addEventListener('keydown', escHandler);
}

function appendTypingIndicator() {
  const id = 'typing-' + Date.now();
  const div = document.createElement('div');
  div.id = id;
  div.className = 'flex items-center gap-1 p-3 bg-gray-800 rounded-2xl rounded-bl-sm w-16';
  div.innerHTML = `
    <span class="typing-dot w-2 h-2 bg-gray-400 rounded-full inline-block"></span>
    <span class="typing-dot w-2 h-2 bg-gray-400 rounded-full inline-block"></span>
    <span class="typing-dot w-2 h-2 bg-gray-400 rounded-full inline-block"></span>
  `;
  chatMessages().appendChild(div);
  scrollBottom();
  return id;
}

function removeTyping(id) {
  document.getElementById(id)?.remove();
}

function appendErrorMessage(text) {
  const div = document.createElement('div');
  div.className = 'text-red-400 text-sm bg-red-950 rounded-lg px-4 py-2 border border-red-800';
  div.textContent = '⚠ ' + text;
  chatMessages().appendChild(div);
  scrollBottom();
}

// -------------------------------------------------------------------------
// Ingestion (Import-Tab)
// -------------------------------------------------------------------------
async function ingestSource(source) {
  const progressDiv = document.getElementById('ingest-progress');
  const resultDiv = document.getElementById('ingest-result');
  const bar = document.getElementById('progress-bar');
  const pct = document.getElementById('progress-pct');
  const txt = document.getElementById('progress-text');

  progressDiv.classList.remove('hidden');
  resultDiv.innerHTML = '';
  bar.style.width = '0%';
  txt.textContent = 'Starte Ingestion…';

  const url = `/api/ingest/${source}`;

  try {
    const res = await fetch(url, { method: 'POST' });
    const data = await res.json();

    bar.style.width = '100%';
    progressDiv.classList.add('hidden');

    if (res.ok) {
      if (source === 'all') {
        let html = '';
        for (const [key, val] of Object.entries(data)) {
          html += `<div class="text-green-400">✓ ${key}: ${val.success || 0} indexiert</div>`;
        }
        resultDiv.innerHTML = html;
      } else {
        resultDiv.innerHTML = `<span class="text-green-400">✓ ${data.message}</span>`;
      }
      loadStatus();
    } else {
      resultDiv.innerHTML = `<span class="text-red-400">✗ ${data.detail || 'Fehler'}</span>`;
    }
  } catch(e) {
    progressDiv.classList.add('hidden');
    resultDiv.innerHTML = `<span class="text-red-400">✗ Verbindungsfehler: ${e.message}</span>`;
  }
}

async function uploadWhatsApp() {
  const file = document.getElementById('wa-file').files[0];
  if (!file) { alert('Bitte eine Datei auswählen.'); return; }

  const result = document.getElementById('wa-result');
  result.innerHTML = '<span class="text-gray-400">Hochladen…</span>';

  const fd = new FormData();
  fd.append('file', file);

  try {
    const res = await fetch('/api/ingest/whatsapp', { method: 'POST', body: fd });
    const data = await res.json();
    result.innerHTML = res.ok
      ? `<span class="text-green-400">✓ ${data.message}</span>`
      : `<span class="text-red-400">✗ ${data.detail}</span>`;
    if (res.ok) loadStatus();
  } catch(e) {
    result.innerHTML = `<span class="text-red-400">✗ ${e.message}</span>`;
  }
}

async function uploadSignal() {
  const file = document.getElementById('signal-file').files[0];
  if (!file) { alert('Bitte eine Datei auswählen.'); return; }

  const result = document.getElementById('signal-result');
  result.innerHTML = '<span class="text-gray-400">Hochladen…</span>';

  const fd = new FormData();
  fd.append('file', file);

  try {
    const res = await fetch('/api/ingest/signal', { method: 'POST', body: fd });
    const data = await res.json();
    result.innerHTML = res.ok
      ? `<span class="text-green-400">✓ ${data.message}</span>`
      : `<span class="text-red-400">✗ ${data.detail}</span>`;
    if (res.ok) loadStatus();
  } catch(e) {
    result.innerHTML = `<span class="text-red-400">✗ ${e.message}</span>`;
  }
}

// -------------------------------------------------------------------------
// Hilfsfunktionen
// -------------------------------------------------------------------------
function chatMessages() { return document.getElementById('chat-messages'); }
function scrollBottom()  { const c = chatMessages(); c.scrollTop = c.scrollHeight; }

function escHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function formatAnswer(text) {
  // Markdown-ähnliche Formatierung (fett, kursiv, Zeilenumbrüche)
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br>');
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('de-DE', { day:'2-digit', month:'2-digit', year:'numeric' });
  } catch { return iso; }
}

function _filterChip(icon, label, colorClass) {
  const span = document.createElement('span');
  span.className = `inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-transparent ${colorClass}`;
  span.textContent = `${icon} ${label}`;
  return span;
}
