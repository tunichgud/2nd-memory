/**
 * entities.js
 * Frontend-Logik für das Human-in-the-Loop Entity Resolution System (Personen-Onboarding).
 */

const Entities = {
    // Cache für Persona-Vorschläge
    personaSuggestions: null,

    /**
     * Lädt Persona-Vorschläge vom Backend und cached sie.
     */
    async loadPersonaSuggestions() {
        if (this.personaSuggestions) {
            return this.personaSuggestions;
        }

        try {
            const res = await fetch('/api/entities/persona-suggestions');
            this.personaSuggestions = await res.json();
            return this.personaSuggestions;
        } catch (err) {
            console.error('Fehler beim Laden der Persona-Vorschläge:', err);
            return { all_personas: [], unassigned_personas: [], assigned_personas: [] };
        }
    },

    /**
     * Lädt die unzugewiesenen Gesichter (Cluster) vom Backend und rendert sie.
     */
    async loadSuggestedClusters() {
        // Persona-Vorschläge im Hintergrund laden
        this.loadPersonaSuggestions();
        const listEl = document.getElementById('cluster-list');
        const loadingEl = document.getElementById('entities-loading');
        const emptyEl = document.getElementById('entities-empty');

        if (!listEl || !loadingEl || !emptyEl) return;

        // UI Reset
        listEl.innerHTML = '';
        loadingEl.classList.remove('hidden');
        emptyEl.classList.add('hidden');

        try {
            const res = await fetch('/api/entities/suggest-clusters', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_name: "USER", chat_identifier: "USER" })
            });

            const data = await res.json();
            loadingEl.classList.add('hidden');

            // 1. Cluster verarbeiten
            if (!data.suggestions || data.suggestions.length === 0) {
                emptyEl.classList.remove('hidden');
            } else {
                data.suggestions.forEach(cluster => {
                    const card = this._createClusterCard(cluster);
                    listEl.appendChild(card);
                });
            }

            // 2. Einzelne Gesichter verarbeiten
            const singleSection = document.getElementById('single-faces-section');
            const singleList = document.getElementById('single-faces-list');
            if (singleSection && singleList) {
                if (data.single_faces && data.single_faces.length > 0) {
                    singleSection.classList.remove('hidden');
                    singleList.innerHTML = '';
                    data.single_faces.forEach(face => {
                        const card = this._createSingleFaceCard(face);
                        singleList.appendChild(card);
                    });
                } else {
                    singleSection.classList.add('hidden');
                }
            }

        } catch (err) {
            console.error("Fehler beim Laden der Cluster-Vorschläge:", err);
            loadingEl.classList.add('hidden');
            listEl.innerHTML = `<div class="p-4 bg-red-900/50 border border-red-700 rounded-lg text-red-200 text-sm">Fehler beim Laden der Daten.</div>`;
        }
    },

    /**
     * Rendert eine HTML-Karte für ein einzelnes Gesichts-Cluster mit Karussell.
     */
    _createClusterCard(cluster) {
        const div = document.createElement('div');
        div.className = `cluster-card bg-gray-800/50 border border-gray-700/50 p-6 rounded-2xl flex flex-col md:flex-row gap-8 transition-all
                     opacity-0 translate-y-4 animate-[slide-up_0.3s_ease-out_forwards] backdrop-blur-sm`;

        // Karussell HTML generieren
        const hasImages = cluster.image_paths && cluster.image_paths.length > 0;
        const imagesHtml = hasImages
            ? cluster.image_paths.map((path, idx) => {
                const faceBbox = cluster.bboxes ? cluster.bboxes[idx] : null;
                const faceUrl = this._getFaceThumbUrl(path, faceBbox);
                const fullUrl = this._getFaceThumbUrl(path, null); // Vollbild ohne Crop
                return `
                <div class="carousel-slide relative cursor-pointer group" data-index="${idx}">
                    <!-- Gesichts-Ansicht (Standard) -->
                    <img src="${faceUrl}"
                         class="face-view w-full h-full object-cover rounded-xl shadow-2xl transition-transform hover:scale-105"
                         loading="lazy"
                         onclick="window.openLightbox('${this._getFaceThumbUrl(path, faceBbox, 'full')}', 'Gesicht aus Cluster ${cluster.cluster_id.substring(0, 8)}')"
                         onerror="this.src='data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNGI1NTYzIiBzdHJva2Utd2lkdGg9IjIiPjxwYXRoIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIgZD0iTTQgMTZoMTZNMCAwaDI0djI0SDB6IiBmaWxsPSJub25lIi8+PHBhdGggc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIiBkPSJNMTQgMjBsNC00bC00LTRNMTAgMjBsLTQtNGw0LTQiLz48L3N2Zz4='">

                    <!-- Vollbild-Ansicht mit Bounding Box (versteckt) -->
                    <div class="full-view hidden w-full h-full relative rounded-xl overflow-hidden shadow-2xl">
                        <img src="${fullUrl}"
                             class="w-full h-full object-contain bg-gray-900"
                             onclick="window.openLightbox('${this._getFaceThumbUrl(path, null, 'full')}', 'Vollbild aus Cluster ${cluster.cluster_id.substring(0, 8)}')"
                             loading="lazy">
                        ${faceBbox ? this._renderBoundingBox(faceBbox) : ''}
                    </div>

                    <!-- Toggle-Button -->
                    <button
                        onclick="event.stopPropagation(); window.Entities._toggleView(this)"
                        class="absolute top-2 right-2 bg-blue-600/90 hover:bg-blue-500 text-white text-xs px-2 py-1 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity z-10"
                        title="Ansicht wechseln">
                        <span class="view-toggle-text">📷 Vollbild</span>
                    </button>

                    <div class="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/20 transition-all pointer-events-none">
                        <span class="text-white opacity-0 group-hover:opacity-100 transition-opacity text-2xl">🔍</span>
                    </div>
                </div>
              `;
            }).join('')
            : `<div class="carousel-slide"><div class="w-full h-full bg-gray-700 rounded-xl flex items-center justify-center text-xs text-gray-500 border border-gray-600">Kein Bild</div></div>`;

        const dotsHtml = hasImages && cluster.image_paths.length > 1
            ? `<div class="carousel-dots">${cluster.image_paths.map((_, i) => `<div class="carousel-dot ${i === 0 ? 'active' : ''}" data-index="${i}" onclick="window.Entities._jumpToSlide(this, ${i})"></div>`).join('')}</div>`
            : '';

        const controlsHtml = hasImages && cluster.image_paths.length > 1
            ? `
                <button class="carousel-btn prev" onclick="window.Entities._moveSlide(this, -1)"><span>‹</span></button>
                <button class="carousel-btn next" onclick="window.Entities._moveSlide(this, 1)"><span>›</span></button>
              `
            : '';

        div.innerHTML = `
      <!-- Karussell-Einheit -->
      <div class="carousel-container w-full md:w-64 shrink-0 rounded-xl overflow-hidden border border-gray-700 bg-gray-900 shadow-inner group">
        <div class="carousel-track h-full" style="transform: translateX(0%);">
            ${imagesHtml}
        </div>
        ${controlsHtml}
        ${dotsHtml}
      </div>
      
      <!-- Infos & Formular -->
      <div class="flex-1 flex flex-col justify-center py-2">
        <div class="mb-5">
          <div class="flex items-center gap-3 mb-3">
             <span class="inline-flex items-center gap-1.5 bg-blue-500/10 text-blue-400 text-[10px] font-bold px-2 py-1 rounded border border-blue-500/20 uppercase tracking-widest">
                Gesichtserkennung
             </span>
             <span class="text-xs text-gray-500">•</span>
             <span class="text-xs text-gray-400">${cluster.face_count} Treffer</span>
          </div>
          <h4 class="text-lg font-semibold text-gray-100 mb-1">Unbekannte Person</h4>
          <p class="text-sm text-gray-400 leading-relaxed">
            Dieses Gesicht wurde auf <strong>${cluster.face_count} Fotos</strong> gefunden. Wer ist das?
          </p>
        </div>
        
        <form class="flex flex-col gap-4" data-face-ids='${JSON.stringify(cluster.face_ids || [])}' onsubmit="event.preventDefault(); window.Entities._handleLinkSubmit(this, '${cluster.cluster_id}')">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div class="flex flex-col gap-1.5">
                  <label class="text-[10px] text-gray-500 uppercase tracking-wider font-bold ml-1">Anzeigename</label>
                  <input type="text" name="entityName" placeholder="z.B. Marie" required
                         list="persona-suggestions-${cluster.cluster_id}"
                         class="bg-gray-950 border border-gray-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-gray-200">
                  <datalist id="persona-suggestions-${cluster.cluster_id}">
                    ${this._renderPersonaSuggestions()}
                  </datalist>
              </div>
              <div class="flex flex-col gap-1.5">
                  <label class="text-[10px] text-gray-500 uppercase tracking-wider font-bold ml-1">Chat-ID (Optional)</label>
                  <input type="text" name="chatAlias" placeholder="z.B. +49160..."
                         class="bg-gray-950 border border-gray-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-gray-200">
              </div>
          </div>
          
          <button type="submit" class="self-start mt-2 bg-blue-600 hover:bg-blue-500 text-white px-6 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-lg hover:shadow-blue-500/25 flex items-center gap-2">
             <span>Diese Person verknüpfen</span>
             <span class="text-xs opacity-50">→</span>
          </button>
        </form>
      </div>
    `;

        return div;
    },

    /**
     * Karussell-Steuerung: Nächster/Vorheriger Slide.
     */
    _moveSlide(btn, direction) {
        const container = btn.closest('.carousel-container');
        const track = container.querySelector('.carousel-track');
        const slides = track.querySelectorAll('.carousel-slide');
        const dots = container.querySelectorAll('.carousel-dot');

        let currentIndex = parseInt(track.dataset.currentIndex || "0");
        currentIndex = (currentIndex + direction + slides.length) % slides.length;

        this._updateCarouselState(track, dots, currentIndex);
    },

    /**
     * Karussell-Steuerung: Direkt-Sprung via Dot.
     */
    _jumpToSlide(dot, index) {
        const container = dot.closest('.carousel-container');
        const track = container.querySelector('.carousel-track');
        const dots = container.querySelectorAll('.carousel-dot');

        this._updateCarouselState(track, dots, index);
    },

    _updateCarouselState(track, dots, index) {
        track.dataset.currentIndex = index;
        track.style.transform = `translateX(-${index * 100}%)`;

        dots.forEach((d, i) => {
            d.classList.toggle('active', i === index);
        });
    },

    /**
     * Handelt den Submit des Verknüpfen-Formulars.
     */
    async _handleLinkSubmit(formElement, clusterId) {
        const btn = formElement.querySelector('button[type="submit"]');
        const nameInput = formElement.querySelector('input[name="entityName"]');
        const aliasInput = formElement.querySelector('input[name="chatAlias"]');

        // Face-IDs aus dem data-Attribut holen (wenn vorhanden)
        const faceIdsJson = formElement.dataset.faceIds;
        const faceIds = faceIdsJson ? JSON.parse(faceIdsJson) : [];

        const requestData = {
            entity_name: nameInput.value.trim(),
            chat_alias: aliasInput.value.trim() || null, // Optional
            cluster_id: clusterId,
            face_ids: faceIds  // NEU: Face-IDs mitschicken
        };

        // UI Feedback: Loading state on button
        const originalBtnContent = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>`;
        btn.classList.replace('bg-blue-600', 'bg-blue-800');

        try {
            const res = await fetch('/api/entities/link', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });

            const data = await res.json();

            if (!res.ok || !data.success) {
                throw new Error(data.detail || data.message || "Unbekannter Fehler beim Verknüpfen.");
            }

            // Success UI: Karte ausblenden und entfernen
            const card = formElement.closest('.cluster-card');
            card.classList.add('opacity-0', '-translate-y-4');
            setTimeout(() => {
                card.remove();
                // Wenn keine Karten mehr übrig, Empty State zeigen
                if (document.querySelectorAll('.cluster-card').length === 0) {
                    document.getElementById('entities-empty').classList.remove('hidden');
                }
            }, 300);

        } catch (err) {
            console.error("Link Error:", err);
            // Revert Button State
            btn.disabled = false;
            btn.innerHTML = originalBtnContent;
            btn.classList.replace('bg-blue-800', 'bg-red-600');
            btn.classList.add('hover:bg-red-500');

            const errorMsg = document.createElement('p');
            errorMsg.className = "text-red-400 text-xs mt-1 w-full";
            errorMsg.textContent = err.message;
            if (!formElement.querySelector('.text-red-400')) {
                formElement.appendChild(errorMsg);
            }
        }
    },

    /**
     * Lädt die bereits verknüpften Personen.
     */
    async loadLinkedEntities() {
        const listEl = document.getElementById('entities-list');
        const emptyEl = document.getElementById('entities-list-empty');

        if (!listEl || !emptyEl) return;

        try {
            const res = await fetch('/api/entities/list');
            const data = await res.json();

            listEl.innerHTML = '';
            if (!data.entities || data.entities.length === 0) {
                emptyEl.classList.remove('hidden');
                return;
            }

            emptyEl.classList.add('hidden');
            data.entities.forEach(entity => {
                const card = this._createEntityCard(entity);
                listEl.appendChild(card);
            });

        } catch (err) {
            console.error("Fehler beim Laden der Personen-Liste:", err);
        }
    },

    /**
     * Erstellt eine einfache Karte zur Verwaltung einer verknüpften Person.
     */
    _createEntityCard(entity) {
        const div = document.createElement('div');
        div.className = "p-4 bg-gray-800/60 border border-gray-700 rounded-2xl flex gap-4 group transition-all hover:border-gray-600 shadow-sm";

        const alias = (entity.chat_aliases && entity.chat_aliases.length > 0) ? entity.chat_aliases[0] : '';
        const preview = entity.preview_face;
        const thumbUrl = preview ? this._getFaceThumbUrl(preview.filename, preview.bbox) : null;

        div.innerHTML = `
            <!-- Preview Image -->
            <div class="w-16 h-16 shrink-0 rounded-xl overflow-hidden bg-gray-900 border border-gray-700">
                ${thumbUrl
                ? `<img src="${thumbUrl}" class="w-full h-full object-cover">`
                : `<div class="w-full h-full flex items-center justify-center text-[10px] text-gray-600">👤</div>`
            }
            </div>

            <!-- Content -->
            <div class="flex-1 min-w-0">
                <div class="flex justify-between items-start mb-1">
                    <div class="min-w-0">
                       <input type="text" value="${entity.entity_id}" class="entity-name-input bg-transparent border-b border-transparent focus:border-blue-500 text-gray-100 font-semibold focus:outline-none px-1 py-0.5 w-full truncate">
                       <input type="text" value="${alias}" placeholder="Keine Chat-ID" class="entity-alias-input bg-transparent border-b border-transparent focus:border-blue-500 text-[10px] text-gray-400 focus:outline-none px-1 py-0.5 w-full mt-0.5">
                    </div>
                </div>
                <div class="flex items-center gap-3">
                    <div class="text-[9px] text-gray-500 flex gap-1.5 items-center">
                        <span class="bg-blue-500/10 text-blue-400 px-1 py-0.5 rounded border border-blue-500/20">${entity.vision_clusters?.length || 0} Cluster</span>
                    </div>
                    <div class="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onclick="window.Entities.openManagePhotosModal('${entity.entity_id}')" class="text-[10px] bg-emerald-600/20 hover:bg-emerald-600 text-emerald-400 hover:text-white px-2 py-1 rounded-lg transition-colors" title="Bilder verwalten">🖼️</button>
                        <button onclick="window.Entities.openSplitModal('${entity.entity_id}')" class="text-[10px] bg-gray-700/50 hover:bg-gray-700 text-gray-400 hover:text-white px-2 py-1 rounded-lg transition-colors" title="Analysieren & Aufteilen">🔍</button>
                        <button onclick="window.Entities._handleUpdateEntity('${entity.entity_id}', this)" class="text-[10px] bg-blue-600/20 hover:bg-blue-600 text-blue-400 hover:text-white px-2 py-1 rounded-lg transition-colors" title="Speichern">💾</button>
                        <button onclick="window.Entities._handleUnlinkEntity('${entity.entity_id}', this)" class="text-[10px] bg-red-600/20 hover:bg-red-600 text-red-400 hover:text-white px-2 py-1 rounded-lg transition-colors" title="Löschen">🔓</button>
                    </div>
                </div>
            </div>
        `;
        return div;
    },

    async _handleUpdateEntity(oldName, btn) {
        const card = btn.closest('.group');
        const newName = card.querySelector('.entity-name-input').value.trim();
        const newAlias = card.querySelector('.entity-alias-input').value.trim();

        try {
            const res = await fetch('/api/entities/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ old_name: oldName, new_name: newName, new_alias: newAlias })
            });
            if (res.ok) {
                btn.textContent = '✅';
                setTimeout(() => btn.textContent = '💾', 1000);
            }
        } catch (err) {
            console.error("Update Fehler:", err);
        }
    },

    async _handleUnlinkEntity(entityId, btn) {
        if (!confirm(`Soll die Verknüpfung für '${entityId}' wirklich gelöst werden?`)) return;

        try {
            const res = await fetch(`/api/entities/unlink/${encodeURIComponent(entityId)}`, { method: 'DELETE' });
            if (res.ok) {
                btn.closest('.group').remove();
                this.loadSuggestedClusters(); // Vorschläge neu laden, da nun wieder frei
            }
        } catch (err) {
            console.error("Unlink Fehler:", err);
        }
    },

    /**
     * Erstellt eine Karte für ein einzelnes (noise) Gesicht.
     */
    _createSingleFaceCard(face) {
        const div = document.createElement('div');
        div.className = "bg-gray-800/40 border border-gray-700 p-3 rounded-2xl flex flex-col gap-3 group animate-[slide-up_0.3s_ease-out]";
        const thumbUrl = this._getFaceThumbUrl(face.image_path, face.bbox);
        div.innerHTML = `
            <div class="aspect-square rounded-xl overflow-hidden bg-gray-900 border border-gray-700 cursor-pointer group relative" onclick="window.openLightbox('${this._getFaceThumbUrl(face.image_path, face.bbox, 'full')}', 'Einzelgesicht')">
                <img src="${thumbUrl}" class="w-full h-full object-cover transition-transform group-hover:scale-110">
                <div class="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/20 transition-all">
                    <span class="text-white opacity-0 group-hover:opacity-100 transition-opacity">🔍</span>
                </div>
            </div>
            <form onsubmit="event.preventDefault(); window.Entities._linkSingleFace(this, '${face.face_id}')" class="flex flex-col gap-2">
                <input type="text" name="name" placeholder="Name..." required
                       list="persona-suggestions-single-${face.face_id}"
                       class="bg-gray-950 border border-gray-700 rounded-lg px-2 py-1 text-[10px] focus:border-blue-500 outline-none text-gray-200">
                <datalist id="persona-suggestions-single-${face.face_id}">
                    ${this._renderPersonaSuggestions()}
                </datalist>
                <button type="submit" class="bg-blue-600/20 hover:bg-blue-600 text-blue-400 hover:text-white text-[9px] py-1 rounded transition-all">Verknüpfen</button>
            </form>
        `;
        return div;
    },

    async _linkSingleFace(form, faceId) {
        const nameInput = form.querySelector('input');
        const name = nameInput.value.trim();
        const btn = form.querySelector('button');

        try {
            const res = await fetch('/api/entities/link-single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ face_id: faceId, entity_name: name })
            });

            if (res.ok) {
                btn.textContent = '✅';
                btn.disabled = true;
                setTimeout(() => {
                    this.loadLinkedEntities();
                    this.loadSuggestedClusters();
                }, 1000);
            }
        } catch (err) {
            console.error("Single Link Fehler:", err);
        }
    },

    /**
     * Öffnet das Split-Modal und startet die Analyse.
     */
    async openSplitModal(entityId) {
        const modal = document.getElementById('split-modal');
        const nameEl = document.getElementById('split-entity-name');
        const resultsEl = document.getElementById('split-results');
        const loadingEl = document.getElementById('split-loading');

        modal.classList.remove('hidden');
        nameEl.textContent = entityId;
        resultsEl.classList.add('hidden');
        loadingEl.classList.remove('hidden');

        try {
            const res = await fetch(`/api/entities/${encodeURIComponent(entityId)}/analyze-split`);
            const data = await res.json();

            loadingEl.classList.add('hidden');
            resultsEl.classList.remove('hidden');
            resultsEl.innerHTML = '';

            if (!data.sub_clusters || data.sub_clusters.length <= 1) {
                resultsEl.innerHTML = `
                    <div class="text-center py-8 text-gray-500">
                        Keine deutlichen Untergruppen gefunden. Diese Person scheint konsistent zu sein.
                    </div>
                `;
                return;
            }

            data.sub_clusters.forEach(sub => {
                const item = this._createSplitItem(entityId, sub);
                resultsEl.appendChild(item);
            });
        } catch (err) {
            console.error("Split-Analyse Fehler:", err);
        }
    },

    _createSplitItem(sourceEntity, sub) {
        const div = document.createElement('div');
        div.className = "bg-gray-800/30 border border-gray-700/50 p-5 rounded-2xl flex flex-col md:flex-row gap-6 items-center";

        const imagesHtml = sub.image_paths.map(path => `
            <img src="/api/media/${encodeURIComponent(path)}?size=thumb" class="w-16 h-16 rounded-lg object-cover border border-gray-700">
        `).join('');

        div.innerHTML = `
            <div class="flex gap-2 shrink-0">
                ${imagesHtml}
            </div>
            <div class="flex-1 text-center md:text-left">
                <div class="text-xs text-gray-500 mb-1 uppercase tracking-wider font-bold">${sub.face_count} Gesichter</div>
                <div class="text-sm text-gray-300">Gehört diese Gruppe eigentlich jemand anderem?</div>
            </div>
            <form onsubmit="event.preventDefault(); window.Entities._handleSplitApply(this, '${sourceEntity}', '${sub.cluster_id}')" class="flex gap-2 shrink-0">
                <input type="text" placeholder="Neuer Name..." required
                       list="persona-suggestions-split-${sourceEntity}-${sub.cluster_id}"
                       class="bg-gray-950 border border-gray-700 rounded-xl px-4 py-2 text-sm focus:border-blue-500 outline-none w-40">
                <datalist id="persona-suggestions-split-${sourceEntity}-${sub.cluster_id}">
                    ${this._renderPersonaSuggestions()}
                </datalist>
                <button type="submit" class="bg-blue-600 hover:bg-blue-500 text-white px-5 py-2 rounded-xl text-sm font-bold transition-all">Abspalten</button>
            </form>
        `;
        return div;
    },

    async _handleSplitApply(form, sourceEntity, clusterId) {
        const targetName = form.querySelector('input').value.trim();
        const btn = form.querySelector('button');

        try {
            const res = await fetch('/api/entities/split', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_entity: sourceEntity, target_entity: targetName, cluster_id: clusterId })
            });

            if (res.ok) {
                btn.textContent = '✅ Erledigt';
                btn.disabled = true;
                setTimeout(() => {
                    this.loadLinkedEntities();
                    this.loadSuggestedClusters();
                }, 1000);
            }
        } catch (err) {
            console.error("Split Apply Fehler:", err);
        }
    },

    /**
     * Öffnet das Modal zur Verwaltung der Fotos einer Person.
     */
    async openManagePhotosModal(entityId) {
        const modal = document.getElementById('manage-photos-modal');
        const nameEl = document.getElementById('manage-photos-entity-name');
        const gridEl = document.getElementById('manage-photos-grid');
        const loadingEl = document.getElementById('manage-photos-loading');

        modal.classList.remove('hidden');
        nameEl.textContent = entityId;
        gridEl.classList.add('hidden');
        loadingEl.classList.remove('hidden');

        try {
            const res = await fetch(`/api/entities/${encodeURIComponent(entityId)}/faces`);
            const data = await res.json();

            loadingEl.classList.add('hidden');
            gridEl.classList.remove('hidden');
            gridEl.innerHTML = '';

            if (!data.faces || data.faces.length === 0) {
                gridEl.innerHTML = `<div class="col-span-full py-12 text-center text-gray-500">Keine Bilder für diese Person gefunden.</div>`;
                return;
            }

            data.faces.forEach(face => {
                const item = this._createManagePhotoItem(entityId, face);
                gridEl.appendChild(item);
            });
        } catch (err) {
            console.error("Manage-Photos Fehler:", err);
        }
    },

    _createManagePhotoItem(entityId, face) {
        const thumbUrl = this._getFaceThumbUrl(face.filename, face.bbox);
        const div = document.createElement('div');
        div.className = "relative group aspect-square rounded-2xl overflow-hidden bg-gray-950 border border-gray-800 shadow-sm transition-transform hover:scale-[1.02] cursor-pointer";
        div.innerHTML = `
            <img src="${thumbUrl}" class="w-full h-full object-cover rounded-2xl" onclick="window.openLightbox('${this._getFaceThumbUrl(face.filename, face.bbox, 'full')}', 'Bild von ${entityId}')">
            <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center backdrop-blur-[2px]">
                <button onclick="window.Entities._handleUnlinkFace('${entityId}', '${face.face_id}', this)" 
                        class="bg-red-600 hover:bg-red-500 text-white p-2.5 rounded-full shadow-lg transition-all scale-75 group-hover:scale-100"
                        title="Diesen Foto-Tag löschen">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                </button>
            </div>
            <div class="absolute bottom-2 left-2 right-2 flex justify-center translate-y-8 group-hover:translate-y-0 transition-transform">
                <span class="bg-black/60 backdrop-blur-md text-[8px] text-gray-400 px-1.5 py-0.5 rounded-full border border-white/10 uppercase tracking-widest font-bold">
                    ${Math.round(face.confidence * 100)}%
                </span>
            </div>
        `;
        return div;
    },

    async _handleUnlinkFace(entityId, faceId, btn) {
        if (!confirm("Soll dieses Gesicht wirklich von dieser Person entkoppelt werden?")) return;

        try {
            const res = await fetch('/api/entities/unlink-face', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ face_id: faceId, entity_id: entityId })
            });

            if (res.ok) {
                const item = btn.closest('.relative');
                item.classList.add('opacity-0', 'scale-90');
                setTimeout(() => item.remove(), 300);
            }
        } catch (err) {
            console.error("Unlink-Face Fehler:", err);
        }
    },

    _getFaceThumbUrl(filename, bbox, size = 'thumb') {
        let url = `/api/v1/media/${window._userId}/${encodeURIComponent(filename)}?size=${size}`;
        if (bbox) url += `&bbox=${bbox}`;
        return url;
    },

    /**
     * Rendert eine SVG Bounding Box Overlay für das Vollbild.
     * bbox Format: "ymin,xmin,ymax,xmax" (absolute Pixel-Koordinaten)
     */
    _renderBoundingBox(bbox) {
        if (!bbox) return '';

        try {
            const [ymin, xmin, ymax, xmax] = bbox.split(',').map(Number);

            // SVG Overlay (100% = Bild-Größe, aber wir können relative Werte nicht direkt nutzen)
            // Stattdessen: Canvas-basiert mit absoluten Koordinaten
            // Für einfache Visualisierung: Nutze CSS-basierte Positionierung

            return `
                <div style="
                    position: absolute;
                    left: ${xmin}px;
                    top: ${ymin}px;
                    width: ${xmax - xmin}px;
                    height: ${ymax - ymin}px;
                    border: 3px solid #3b82f6;
                    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3), inset 0 0 0 2px rgba(59, 130, 246, 0.3);
                    pointer-events: none;
                    z-index: 10;
                " class="bounding-box-overlay"></div>
            `;
        } catch (e) {
            console.warn('Invalid bbox format:', bbox);
            return '';
        }
    },

    /**
     * Togglet zwischen Gesichts-Ansicht (gecroppt) und Vollbild-Ansicht (mit Box).
     */
    _toggleView(button) {
        const slide = button.closest('.carousel-slide');
        const faceView = slide.querySelector('.face-view');
        const fullView = slide.querySelector('.full-view');
        const toggleText = button.querySelector('.view-toggle-text');

        if (faceView.classList.contains('hidden')) {
            // Zurück zur Gesichts-Ansicht
            faceView.classList.remove('hidden');
            fullView.classList.add('hidden');
            toggleText.textContent = '📷 Vollbild';
        } else {
            // Zur Vollbild-Ansicht
            faceView.classList.add('hidden');
            fullView.classList.remove('hidden');
            toggleText.textContent = '👤 Gesicht';
        }
    },

    /**
     * Rendert Persona-Vorschläge für <datalist> Elemente.
     * Zeigt Personas ohne Gesichter zuerst (bevorzugt), dann die mit Gesichtern.
     */
    _renderPersonaSuggestions() {
        if (!this.personaSuggestions) {
            return '';
        }

        const suggestions = [];

        // 1. Personas OHNE Gesichter (bevorzugt - diese sollten zugeordnet werden)
        if (this.personaSuggestions.unassigned_personas) {
            this.personaSuggestions.unassigned_personas.forEach(name => {
                suggestions.push(`<option value="${name}" label="💬 ${name} (aus Chat)"></option>`);
            });
        }

        // 2. Personas MIT Gesichtern (bereits zugeordnet - für Korrekturen)
        if (this.personaSuggestions.assigned_personas) {
            this.personaSuggestions.assigned_personas.forEach(persona => {
                const label = `👤 ${persona.name} (${persona.face_count} Gesichter)`;
                suggestions.push(`<option value="${persona.name}" label="${label}"></option>`);
            });
        }

        return suggestions.join('\n');
    }

};

window.Entities = Entities;
