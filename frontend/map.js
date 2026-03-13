// map.js – Leaflet.js Kartenansicht für 2nd Memory

let _map = null;
let _markers = null;

const MARKER_COLORS = {
  photos:       '#3b82f6',   // blau
  reviews:      '#10b981',   // grün
  saved_places: '#f59e0b',   // amber
  messages:     '#8b5cf6',   // lila
};

function getMarkerIcon(source) {
  const color = MARKER_COLORS[source] || '#6b7280';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20">
    <circle cx="12" cy="12" r="8" fill="${color}" fill-opacity="0.9" stroke="white" stroke-width="2"/>
  </svg>`;
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [20, 20],
    iconAnchor: [10, 10],
    popupAnchor: [0, -12],
  });
}

async function loadMap() {
  const source  = document.getElementById('map-source')?.value  || '';
  const dateFrom = document.getElementById('map-from')?.value   || '';
  const dateTo   = document.getElementById('map-to')?.value     || '';

  // Karte initialisieren (nur einmal)
  if (!_map) {
    _map = L.map('map').setView([53.55, 10.0], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(_map);
    _markers = L.layerGroup().addTo(_map);
  }

  // Marker leeren
  _markers.clearLayers();

  // Daten laden
  const params = new URLSearchParams();
  if (source)   params.set('source',    source);
  if (dateFrom) params.set('date_from', dateFrom);
  if (dateTo)   params.set('date_to',   dateTo);

  try {
    const res = await fetch('/api/locations?' + params.toString());
    const data = await res.json();
    const points = data.points || [];

    document.getElementById('map-count').textContent = `${points.length} Punkte`;

    points.forEach(pt => {
      const icon = getMarkerIcon(pt.source);
      const marker = L.marker([pt.lat, pt.lon], { icon });

      const sourceLabel = {
        photos:       'Foto',
        reviews:      'Bewertung',
        saved_places: 'Gespeicherter Ort',
      }[pt.source] || pt.source;

      let extraHtml = '';
      if (pt.extra) {
        if (pt.extra.persons) extraHtml += `<div class="text-gray-400">👤 ${pt.extra.persons}</div>`;
        if (pt.extra.rating)  extraHtml += `<div class="text-yellow-400">${'⭐'.repeat(pt.extra.rating)}</div>`;
        if (pt.extra.address) extraHtml += `<div class="text-gray-400 text-xs">${pt.extra.address}</div>`;
        if (pt.extra.maps_url) extraHtml += `<a href="${pt.extra.maps_url}" target="_blank" class="text-blue-400 text-xs">Google Maps</a>`;
      }

      const dateStr = pt.date_iso
        ? new Date(pt.date_iso).toLocaleDateString('de-DE', {day:'2-digit',month:'2-digit',year:'numeric'})
        : '';

      marker.bindPopup(`
        <div style="min-width:180px; font-family:sans-serif; font-size:13px;">
          <div style="font-weight:600; margin-bottom:4px;">${pt.name}</div>
          <div style="color:#888; margin-bottom:4px;">${sourceLabel}${dateStr ? ' · ' + dateStr : ''}</div>
          ${extraHtml}
        </div>
      `);

      _markers.addLayer(marker);
    });

    // Karte auf Marker-Bereich zoomen
    if (points.length > 0) {
      const lats = points.map(p => p.lat);
      const lons = points.map(p => p.lon);
      const bounds = L.latLngBounds(
        [Math.min(...lats), Math.min(...lons)],
        [Math.max(...lats), Math.max(...lons)]
      );
      _map.fitBounds(bounds, { padding: [30, 30] });
    }

    // Karte neu rendern (wichtig wenn Tab versteckt war)
    setTimeout(() => _map.invalidateSize(), 100);

  } catch(e) {
    console.error('Karte laden fehlgeschlagen:', e);
  }
}
