/**
 * validation.js
 * Frontend-Logik für Label-Validierung von Gesichtsclustern.
 *
 * Workflow:
 * 1. Cluster mit Qualitätsmetriken vom Backend laden
 * 2. User validiert/rejected/split Cluster
 * 3. Validierungen als Ground Truth speichern
 * 4. Statistiken anzeigen
 */

const Validation = {
    currentClusters: [],
    currentIndex: 0,
    userId: "00000000-0000-0000-0000-000000000001", // Default User

    /**
     * Startet eine neue Validierungs-Session.
     */
    async startSession() {
        const loadingEl = document.getElementById('validation-loading');
        const contentEl = document.getElementById('validation-content');
        const emptyEl = document.getElementById('validation-empty');

        if (!loadingEl || !contentEl) return;

        // UI Reset
        loadingEl.classList.remove('hidden');
        contentEl.classList.add('hidden');
        if (emptyEl) emptyEl.classList.add('hidden');

        try {
            const res = await fetch('/api/v1/validation/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: this.userId,
                    sample_size: 50,
                    min_cluster_size: 2
                })
            });

            if (!res.ok) {
                throw new Error(`HTTP ${res.status}: ${await res.text()}`);
            }

            const data = await res.json();
            loadingEl.classList.add('hidden');

            if (!data.clusters || data.clusters.length === 0) {
                if (emptyEl) {
                    emptyEl.classList.remove('hidden');
                    emptyEl.innerHTML = `
                        <div class="text-center py-12">
                            <div class="text-6xl mb-4">✅</div>
                            <h3 class="text-xl font-semibold text-gray-200 mb-2">Alle Cluster validiert!</h3>
                            <p class="text-gray-400">Es gibt keine neuen Gesichter-Cluster zum Überprüfen.</p>
                        </div>
                    `;
                }
                return;
            }

            this.currentClusters = data.clusters;
            this.currentIndex = 0;

            // Statistik-Banner aktualisieren
            const statsEl = document.getElementById('validation-stats');
            if (statsEl) {
                statsEl.innerHTML = `
                    <div class="bg-blue-900/20 border border-blue-700/30 rounded-xl p-4 mb-6">
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                            <div>
                                <div class="text-2xl font-bold text-blue-400">${data.clusters.length}</div>
                                <div class="text-xs text-gray-400 uppercase tracking-wider">Cluster zu validieren</div>
                            </div>
                            <div>
                                <div class="text-2xl font-bold text-gray-300">${data.total_unvalidated}</div>
                                <div class="text-xs text-gray-400 uppercase tracking-wider">Unzugeordnete Gesichter</div>
                            </div>
                            <div>
                                <div class="text-2xl font-bold text-green-400" id="validated-count">0</div>
                                <div class="text-xs text-gray-400 uppercase tracking-wider">Validiert</div>
                            </div>
                            <div>
                                <div class="text-xl font-mono text-gray-400">ε = ${data.dbscan_eps.toFixed(2)}</div>
                                <div class="text-xs text-gray-400 uppercase tracking-wider">DBSCAN Epsilon</div>
                            </div>
                        </div>
                    </div>
                `;
            }

            // Ersten Cluster anzeigen
            contentEl.classList.remove('hidden');
            this.renderCluster(this.currentClusters[this.currentIndex]);

        } catch (err) {
            console.error("Fehler beim Starten der Validierungs-Session:", err);
            loadingEl.classList.add('hidden');
            if (contentEl) {
                contentEl.innerHTML = `
                    <div class="p-4 bg-red-900/50 border border-red-700 rounded-lg text-red-200 text-sm">
                        Fehler beim Laden der Daten: ${err.message}
                    </div>
                `;
                contentEl.classList.remove('hidden');
            }
        }
    },

    /**
     * Rendert einen einzelnen Cluster zur Validierung.
     */
    renderCluster(cluster) {
        const containerEl = document.getElementById('validation-cluster-card');
        if (!containerEl) return;

        const quality = cluster.quality_metrics;

        // Quality Indicators (Color-Coded)
        const getQualityColor = (metric, thresholds) => {
            if (metric >= thresholds.good) return 'text-green-400';
            if (metric >= thresholds.medium) return 'text-yellow-400';
            return 'text-red-400';
        };

        const intraSimilarityColor = getQualityColor(quality.avg_intra_similarity, { good: 0.75, medium: 0.6 });
        const detectionConfColor = getQualityColor(quality.avg_detection_conf, { good: 0.8, medium: 0.6 });

        // Bilder-Grid generieren
        const imagesHtml = cluster.images.map((path, idx) => {
            const thumbUrl = `/api/media/${encodeURIComponent(path)}`;
            const fullUrl = `/api/media/${encodeURIComponent(path)}?size=full`;
            return `
                <div class="relative group cursor-pointer" onclick="openLightbox('${fullUrl}', 'Bild ${idx + 1} aus Cluster ${cluster.cluster_id.substring(0, 8)}')">
                    <img src="${thumbUrl}"
                         class="w-full h-32 object-cover rounded-lg border border-gray-700 shadow-lg transition-all group-hover:scale-105 group-hover:border-blue-500/50"
                         loading="lazy"
                         onerror="this.src='data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNGI1NTYzIiBzdHJva2Utd2lkdGg9IjIiPjxyZWN0IHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgZmlsbD0iIzFmMjkzNyIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjNGI1NTYzIiBmb250LXNpemU9IjEwIj5OL0E8L3RleHQ+PC9zdmc+'">
                    <div class="absolute inset-0 bg-blue-500/0 group-hover:bg-blue-500/10 transition-colors rounded-lg flex items-center justify-center">
                         <span class="text-white opacity-0 group-hover:opacity-100 transition-opacity text-xl">🔍</span>
                    </div>
                    <div class="absolute top-1 right-1 bg-gray-900/80 text-gray-300 text-[10px] px-1.5 py-0.5 rounded">
                        ${idx + 1}
                    </div>
                </div>
            `;
        }).join('');

        containerEl.innerHTML = `
            <!-- Progress Header -->
            <div class="mb-6">
                <div class="flex justify-between items-center mb-2">
                    <span class="text-sm text-gray-400">Cluster ${this.currentIndex + 1} von ${this.currentClusters.length}</span>
                    <span class="text-xs text-gray-500">${cluster.cluster_id}</span>
                </div>
                <div class="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
                    <div class="bg-blue-500 h-full transition-all duration-300"
                         style="width: ${((this.currentIndex + 1) / this.currentClusters.length * 100).toFixed(1)}%"></div>
                </div>
            </div>

            <!-- Cluster Card -->
            <div class="bg-gray-800/50 border border-gray-700/50 rounded-2xl p-6 backdrop-blur-sm">

                <!-- Bilder-Grid -->
                <div class="grid grid-cols-3 md:grid-cols-5 gap-3 mb-6">
                    ${imagesHtml}
                </div>

                <!-- Qualitätsmetriken -->
                <div class="bg-gray-900/50 border border-gray-700/50 rounded-xl p-4 mb-6">
                    <h4 class="text-xs text-gray-400 uppercase tracking-wider font-bold mb-3">Qualitätsmetriken</h4>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                        <div>
                            <div class="text-2xl font-bold ${intraSimilarityColor}">${(quality.avg_intra_similarity * 100).toFixed(1)}%</div>
                            <div class="text-[10px] text-gray-500 uppercase mt-1">Intra-Similarity</div>
                        </div>
                        <div>
                            <div class="text-2xl font-bold text-gray-300">${(quality.min_intra_similarity * 100).toFixed(1)}%</div>
                            <div class="text-[10px] text-gray-500 uppercase mt-1">Min. Similarity</div>
                        </div>
                        <div>
                            <div class="text-2xl font-bold ${detectionConfColor}">${(quality.avg_detection_conf * 100).toFixed(0)}%</div>
                            <div class="text-[10px] text-gray-500 uppercase mt-1">Detection Conf.</div>
                        </div>
                        <div>
                            <div class="text-2xl font-bold text-blue-400">${quality.size}</div>
                            <div class="text-[10px] text-gray-500 uppercase mt-1">Gesichter</div>
                        </div>
                    </div>
                </div>

                <!-- Validierungs-Formular -->
                <div class="space-y-4">
                    <div>
                        <label class="text-xs text-gray-400 uppercase tracking-wider font-bold mb-2 block">
                            Wer ist auf diesen Bildern zu sehen?
                        </label>
                        <input type="text"
                               id="validation-label-input"
                               placeholder="z.B. Marie, Anna, oder 'Unbekannt'"
                               value="${cluster.suggested_label || ''}"
                               class="w-full bg-gray-950 border border-gray-700 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-gray-200">
                    </div>

                    <div>
                        <label class="text-xs text-gray-400 uppercase tracking-wider font-bold mb-2 block">
                            Wie sicher bist du? (1-5 Sterne)
                        </label>
                        <div class="flex gap-2" id="confidence-stars">
                            ${[1, 2, 3, 4, 5].map(star => `
                                <button type="button"
                                        class="confidence-star text-3xl transition-all hover:scale-110"
                                        data-value="${star}"
                                        onclick="Validation.selectConfidence(${star})">
                                    ☆
                                </button>
                            `).join('')}
                        </div>
                    </div>

                    <div>
                        <label class="text-xs text-gray-400 uppercase tracking-wider font-bold mb-2 block">
                            Notizen (optional)
                        </label>
                        <textarea id="validation-notes"
                                  rows="2"
                                  placeholder="z.B. 'Profil-Bilder schwer erkennbar'"
                                  class="w-full bg-gray-950 border border-gray-700 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-gray-200 resize-none"></textarea>
                    </div>

                    <!-- Action Buttons -->
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6">
                        <button onclick="Validation.submitValidation('validate')"
                                class="bg-green-600 hover:bg-green-500 text-white px-4 py-3 rounded-xl text-sm font-semibold transition-all shadow-lg hover:shadow-green-500/25 flex items-center justify-center gap-2">
                            <span>✅</span>
                            <span>Bestätigen</span>
                        </button>

                        <button onclick="Validation.submitValidation('reject')"
                                class="bg-red-600 hover:bg-red-500 text-white px-4 py-3 rounded-xl text-sm font-semibold transition-all shadow-lg hover:shadow-red-500/25 flex items-center justify-center gap-2">
                            <span>❌</span>
                            <span>Ablehnen</span>
                        </button>

                        <button onclick="Validation.submitValidation('split')"
                                class="bg-yellow-600 hover:bg-yellow-500 text-white px-4 py-3 rounded-xl text-sm font-semibold transition-all shadow-lg hover:shadow-yellow-500/25 flex items-center justify-center gap-2">
                            <span>✂️</span>
                            <span>Aufteilen</span>
                        </button>

                        <button onclick="Validation.skipCluster()"
                                class="bg-gray-700 hover:bg-gray-600 text-white px-4 py-3 rounded-xl text-sm font-semibold transition-all flex items-center justify-center gap-2">
                            <span>⏭️</span>
                            <span>Überspringen</span>
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Default: 3 Sterne
        this.selectConfidence(3);
    },

    /**
     * Setzt die Confidence (Sterne-Rating).
     */
    selectConfidence(value) {
        const stars = document.querySelectorAll('.confidence-star');
        stars.forEach((star, idx) => {
            if (idx < value) {
                star.textContent = '★';
                star.classList.add('text-yellow-400');
                star.classList.remove('text-gray-600');
            } else {
                star.textContent = '☆';
                star.classList.add('text-gray-600');
                star.classList.remove('text-yellow-400');
            }
        });
        this.selectedConfidence = value;
    },

    /**
     * Sendet eine Validierung an das Backend.
     */
    async submitValidation(action) {
        const cluster = this.currentClusters[this.currentIndex];
        const labelInput = document.getElementById('validation-label-input');
        const notesInput = document.getElementById('validation-notes');

        const label = labelInput?.value.trim() || null;
        const notes = notesInput?.value.trim() || null;
        const confidence = this.selectedConfidence || 3;

        // Validierung: Bei "validate" muss Label vorhanden sein
        if (action === 'validate' && (!label || label === 'Unbekannt')) {
            alert('Bitte gib einen Namen ein, um den Cluster zu validieren.');
            labelInput?.focus();
            return;
        }

        try {
            const res = await fetch('/api/v1/validation/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cluster_id: cluster.cluster_id,
                    action: action,
                    label: label,
                    confidence: confidence,
                    notes: notes,
                    face_ids: cluster.face_ids
                })
            });

            if (!res.ok) {
                throw new Error(`HTTP ${res.status}: ${await res.text()}`);
            }

            const data = await res.json();

            // Erfolgs-Feedback
            if (action === 'validate') {
                this.showToast(`✅ "${label}" validiert!`, 'success');
                this.updateValidatedCount();
            } else if (action === 'reject') {
                this.showToast('❌ Cluster abgelehnt', 'info');
            } else if (action === 'split') {
                this.showToast('✂️ Cluster für Aufteilung markiert', 'warning');
            }

            // Nächster Cluster
            this.nextCluster();

        } catch (err) {
            console.error("Fehler beim Validieren:", err);
            this.showToast(`Fehler: ${err.message}`, 'error');
        }
    },

    /**
     * Überspringt den aktuellen Cluster.
     */
    skipCluster() {
        this.showToast('⏭️ Übersprungen', 'info');
        this.nextCluster();
    },

    /**
     * Zeigt den nächsten Cluster an.
     */
    nextCluster() {
        this.currentIndex++;

        if (this.currentIndex >= this.currentClusters.length) {
            // Alle Cluster validiert
            const containerEl = document.getElementById('validation-cluster-card');
            if (containerEl) {
                containerEl.innerHTML = `
                    <div class="text-center py-16">
                        <div class="text-8xl mb-6">🎉</div>
                        <h3 class="text-2xl font-bold text-gray-200 mb-3">Session abgeschlossen!</h3>
                        <p class="text-gray-400 mb-6">Du hast alle ${this.currentClusters.length} Cluster überprüft.</p>
                        <button onclick="Validation.startSession()"
                                class="bg-blue-600 hover:bg-blue-500 text-white px-6 py-3 rounded-xl font-semibold transition-all shadow-lg">
                            Neue Session starten
                        </button>
                    </div>
                `;
            }
            return;
        }

        // Nächsten Cluster rendern
        this.renderCluster(this.currentClusters[this.currentIndex]);
    },

    /**
     * Aktualisiert den Zähler für validierte Cluster.
     */
    updateValidatedCount() {
        const countEl = document.getElementById('validated-count');
        if (countEl) {
            const current = parseInt(countEl.textContent) || 0;
            countEl.textContent = current + 1;
        }
    },

    /**
     * Zeigt eine Toast-Nachricht an.
     */
    showToast(message, type = 'info') {
        const colors = {
            success: 'bg-green-600',
            error: 'bg-red-600',
            warning: 'bg-yellow-600',
            info: 'bg-blue-600'
        };

        const toast = document.createElement('div');
        toast.className = `fixed top-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-xl shadow-2xl z-50 animate-[slide-up_0.3s_ease-out] transition-opacity`;
        toast.textContent = message;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    },

    /**
     * Repariert fehlende Personen aus Ground Truth.
     */
    async repairMigrateGroundTruth() {
        if (!confirm('Möchtest du fehlende Personen aus alten Validierungen reparieren?\n\nDies migriert Daten aus der Ground Truth nach ChromaDB und Elasticsearch.')) {
            return;
        }

        try {
            const res = await fetch('/api/v1/validation/repair/migrate-ground-truth', {
                method: 'POST'
            });

            const data = await res.json();

            if (data.success) {
                const personsList = Object.entries(data.persons)
                    .map(([name, count]) => `${name}: ${count} Gesichter`)
                    .join('\n');

                let message = `✅ Reparatur erfolgreich!\n\n${data.message}\n\n${personsList}`;

                // Warnungen anzeigen (Multi-Person-Labels)
                if (data.warnings && data.warnings.skipped_multi_person_labels) {
                    const skipped = data.warnings.skipped_multi_person_labels.join('\n');
                    message += `\n\n⚠️ Übersprungene Multi-Person-Labels:\n${skipped}\n\n${data.warnings.message}`;
                }

                alert(message);

                // Listen neu laden
                await this.loadPersonsList();
                await this.loadStats();
            } else {
                alert(`❌ ${data.message}`);
            }

        } catch (err) {
            console.error("Fehler bei der Reparatur:", err);
            alert(`Fehler: ${err.message}`);
        }
    },

    /**
     * Lädt Statistiken und zeigt sie an.
     */
    async loadStats() {
        try {
            const res = await fetch('/api/v1/validation/stats');
            const data = await res.json();

            const statsContainer = document.getElementById('validation-stats-overview');
            if (!statsContainer) return;

            const labels = Object.entries(data.label_distribution)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 10)
                .map(([label, count]) => `
                    <div class="flex justify-between items-center py-2 border-b border-gray-700/50 last:border-0">
                        <span class="text-gray-300">${label}</span>
                        <span class="text-blue-400 font-semibold">${count} Cluster</span>
                    </div>
                `).join('');

            statsContainer.innerHTML = `
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="bg-gray-800/50 border border-gray-700/50 rounded-xl p-6">
                        <h3 class="text-lg font-semibold text-gray-200 mb-4">Gesamt-Statistiken</h3>
                        <div class="space-y-3">
                            <div class="flex justify-between">
                                <span class="text-gray-400">Validierte Cluster:</span>
                                <span class="text-white font-bold">${data.total_clusters}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-400">Gesamt-Gesichter:</span>
                                <span class="text-white font-bold">${data.total_faces}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-400">Ø Cluster-Größe:</span>
                                <span class="text-white font-bold">${data.avg_cluster_size.toFixed(1)}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-400">Ø Qualität:</span>
                                <span class="text-white font-bold">${(data.avg_cluster_quality * 100).toFixed(1)}%</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-400">Letzte Änderung:</span>
                                <span class="text-white font-bold text-xs">${data.last_updated === 'never' ? 'Nie' : new Date(data.last_updated).toLocaleString('de-DE')}</span>
                            </div>
                        </div>
                    </div>

                    <div class="bg-gray-800/50 border border-gray-700/50 rounded-xl p-6">
                        <h3 class="text-lg font-semibold text-gray-200 mb-4">Top Personen</h3>
                        <div class="space-y-1">
                            ${labels || '<div class="text-gray-500 text-sm">Noch keine Validierungen</div>'}
                        </div>
                    </div>
                </div>
            `;

        } catch (err) {
            console.error("Fehler beim Laden der Statistiken:", err);
        }
    },

    /**
     * Lädt die Liste aller erkannten Personen (aus Entities + Validierung).
     */
    async loadPersonsList() {
        try {
            // Lade beide Listen: Entities und Validierte Personen
            const [entitiesRes, validationRes] = await Promise.all([
                fetch('/api/entities/list'),
                fetch('/api/v1/validation/persons')
            ]);

            const entitiesData = await entitiesRes.json();
            const validationData = await validationRes.json();

            const containerEl = document.getElementById('persons-list-container');
            if (!containerEl) return;

            // Merge beide Listen (Entities haben Vorrang, da sie älter/etablierter sind)
            const personsMap = new Map();

            // 1. Entities hinzufügen
            if (entitiesData.entities && entitiesData.entities.length > 0) {
                for (const entity of entitiesData.entities) {
                    const previewImg = entity.preview_face?.filename || '';
                    personsMap.set(entity.entity_id, {
                        name: entity.entity_id,
                        face_count: 0, // Wird später gezählt
                        preview_image: previewImg,
                        source: 'entities'
                    });
                }
            }

            // 2. Validierte Personen hinzufügen (falls nicht schon vorhanden)
            if (validationData.persons && validationData.persons.length > 0) {
                for (const person of validationData.persons) {
                    if (!personsMap.has(person.name)) {
                        personsMap.set(person.name, {
                            name: person.name,
                            face_count: person.face_count,
                            preview_image: person.preview_image,
                            source: 'validation'
                        });
                    }
                }
            }

            if (personsMap.size === 0) {
                containerEl.innerHTML = `
                    <div class="text-center py-12">
                        <div class="text-6xl mb-4">👤</div>
                        <h3 class="text-xl font-semibold text-gray-200 mb-2">Noch keine Personen erkannt</h3>
                        <p class="text-gray-400">Gehe zum <strong>Personen-Tab</strong>, um Gesichter zu benennen.</p>
                    </div>
                `;
                return;
            }

            const persons = Array.from(personsMap.values());

            // Für jede Person die tatsächliche Anzahl der Gesichter laden
            for (const person of persons) {
                try {
                    const facesRes = await fetch(`/api/entities/${encodeURIComponent(person.name)}/faces`);
                    const facesData = await facesRes.json();
                    person.face_count = facesData.faces ? facesData.faces.length : 0;
                } catch (err) {
                    console.warn(`Couldn't load face count for ${person.name}:`, err);
                }
            }

            // Sortieren nach Anzahl der Gesichter
            persons.sort((a, b) => b.face_count - a.face_count);

            const personsHtml = persons.map(person => `
                <div class="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4 hover:border-blue-500/50 transition-all cursor-pointer"
                     onclick="Validation.showPersonDetails('${person.name.replace(/'/g, "\\'")}')">
                    <div class="flex items-center gap-4">
                        <div class="w-16 h-16 rounded-lg overflow-hidden border border-gray-700 flex-shrink-0">
                            <img src="/api/v1/media/${window._userId}/${encodeURIComponent(person.preview_image)}"
                                 class="w-full h-full object-cover"
                                 onerror="this.src='data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNGI1NTYzIiBzdHJva2Utd2lkdGg9IjIiPjxyZWN0IHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgZmlsbD0iIzFmMjkzNyIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjNGI1NTYzIiBmb250LXNpemU9IjEwIj7wn5ikPC90ZXh0Pjwvc3ZnPg=='">
                        </div>
                        <div class="flex-1">
                            <h4 class="text-lg font-semibold text-gray-200">${person.name}</h4>
                            <p class="text-sm text-gray-400">${person.face_count} Gesichter</p>
                        </div>
                        <div class="text-2xl text-gray-600">›</div>
                    </div>
                </div>
            `).join('');

            containerEl.innerHTML = `
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    ${personsHtml}
                </div>
            `;

        } catch (err) {
            console.error("Fehler beim Laden der Personen-Liste:", err);
        }
    },

    /**
     * Zeigt Details zu einer Person (alle Gesichter).
     */
    async showPersonDetails(personName) {
        try {
            // Versuche zuerst den Entities-Endpunkt, dann Validierungs-Endpunkt
            let res = await fetch(`/api/entities/${encodeURIComponent(personName)}/faces`);
            let data = await res.json();

            // Falls keine Gesichter gefunden, versuche Validierungs-API
            if (!data.faces || data.faces.length === 0) {
                res = await fetch(`/api/v1/validation/persons/${encodeURIComponent(personName)}`);
                data = await res.json();
            }

            const modalEl = document.getElementById('person-details-modal');
            if (!modalEl) {
                // Modal erstellen
                const modal = document.createElement('div');
                modal.id = 'person-details-modal';
                modal.className = 'fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4';
                modal.innerHTML = `
                    <div class="bg-gray-900 border border-gray-700 rounded-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col">
                        <div class="flex justify-between items-center p-6 border-b border-gray-700">
                            <div>
                                <h2 class="text-2xl font-bold text-gray-200" id="person-modal-title"></h2>
                                <p class="text-sm text-gray-400" id="person-modal-subtitle"></p>
                            </div>
                            <button onclick="document.getElementById('person-details-modal').remove()"
                                    class="text-gray-400 hover:text-white text-3xl leading-none">×</button>
                        </div>
                        <div class="flex-1 overflow-y-auto p-6" id="person-modal-content"></div>
                    </div>
                `;
                document.body.appendChild(modal);
            }

            const titleEl = document.getElementById('person-modal-title');
            const subtitleEl = document.getElementById('person-modal-subtitle');
            const contentEl = document.getElementById('person-modal-content');

            titleEl.textContent = personName;
            const totalFaces = data.faces?.length || data.total_faces || 0;
            subtitleEl.textContent = `${totalFaces} Gesichter`;

            const faces = data.faces || [];
            const facesHtml = faces.map(face => {
                const faceUrl = `/api/v1/media/${window._userId}/${encodeURIComponent(face.filename)}`;
                const bbox = face.bbox;
                const faceUrlWithBbox = bbox ? `${faceUrl}?bbox=${bbox}` : faceUrl;

                return `
                <div class="relative group">
                    <img src="${faceUrlWithBbox}"
                         class="w-full h-32 object-cover rounded-lg border border-gray-700 shadow-lg cursor-pointer transition-all group-hover:scale-105"
                         onclick="openLightbox('${faceUrl}?size=full', '${face.filename}')">

                    <!-- Action-Buttons -->
                    <div class="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <!-- Neu zuordnen -->
                        <button onclick="event.stopPropagation(); Validation.reassignFace('${personName.replace(/'/g, "\\'")}', '${face.face_id}', '${face.filename.replace(/'/g, "\\'")}')"
                                class="bg-blue-600/90 hover:bg-blue-500 text-white rounded-lg p-1.5"
                                title="Neu zuordnen">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"></path>
                            </svg>
                        </button>

                        <!-- Entfernen -->
                        <button onclick="event.stopPropagation(); Validation.unlinkFace('${personName.replace(/'/g, "\\'")}', '${face.face_id}')"
                                class="bg-red-600/90 hover:bg-red-500 text-white rounded-lg p-1.5"
                                title="Gesicht entfernen">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                            </svg>
                        </button>
                    </div>

                    <!-- Info-Badge -->
                    <div class="absolute bottom-2 left-2 bg-gray-900/90 text-gray-300 text-[10px] px-2 py-1 rounded">
                        ${(face.confidence * 100).toFixed(0)}%
                    </div>
                </div>
            `;
            }).join('');

            contentEl.innerHTML = `
                <div class="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                    ${facesHtml}
                </div>
            `;

        } catch (err) {
            console.error("Fehler beim Laden der Personen-Details:", err);
            this.showToast(`Fehler: ${err.message}`, 'error');
        }
    },

    /**
     * Ordnet ein Gesicht einer neuen Person zu.
     */
    async reassignFace(currentPerson, faceId, filename) {
        const newPerson = prompt(`Wem soll dieses Gesicht zugeordnet werden?\n\n(Aktuell: ${currentPerson})`);

        if (!newPerson || newPerson.trim() === '') {
            return;
        }

        if (newPerson.trim() === currentPerson) {
            this.showToast('⚠️ Gleiche Person - keine Änderung', 'info');
            return;
        }

        try {
            // 1. Von aktueller Person entfernen
            let res = await fetch('/api/entities/unlink-face', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    entity_id: currentPerson,
                    face_id: faceId
                })
            });

            if (!res.ok) {
                res = await fetch('/api/v1/validation/persons/unlink-face', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        person_name: currentPerson,
                        face_id: faceId
                    })
                });
            }

            if (!res.ok) {
                throw new Error(`Entfernen fehlgeschlagen: HTTP ${res.status}`);
            }

            // 2. Neuer Person zuordnen
            res = await fetch('/api/entities/link-single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    face_id: faceId,
                    entity_name: newPerson.trim()
                })
            });

            if (!res.ok) {
                throw new Error(`Zuordnung fehlgeschlagen: HTTP ${res.status}`);
            }

            this.showToast(`✅ Gesicht von "${currentPerson}" → "${newPerson.trim()}"`, 'success');

            // Details neu laden
            await this.showPersonDetails(currentPerson);

        } catch (err) {
            console.error("Fehler beim Neu-Zuordnen:", err);
            this.showToast(`Fehler: ${err.message}`, 'error');
        }
    },

    /**
     * Entfernt ein Gesicht von einer Person.
     */
    async unlinkFace(personName, faceId) {
        if (!confirm(`Möchtest du dieses Gesicht wirklich von "${personName}" entfernen?`)) {
            return;
        }

        try {
            // Versuche zuerst den Entities-Endpunkt
            let res = await fetch('/api/entities/unlink-face', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    entity_id: personName,
                    face_id: faceId
                })
            });

            // Falls nicht erfolgreich, versuche Validierungs-API
            if (!res.ok) {
                res = await fetch('/api/v1/validation/persons/unlink-face', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        person_name: personName,
                        face_id: faceId
                    })
                });
            }

            if (!res.ok) {
                throw new Error(`HTTP ${res.status}: ${await res.text()}`);
            }

            const data = await res.json();

            this.showToast(`✅ Gesicht entfernt`, 'success');

            // Details neu laden
            await this.showPersonDetails(personName);

        } catch (err) {
            console.error("Fehler beim Entfernen des Gesichts:", err);
            this.showToast(`Fehler: ${err.message}`, 'error');
        }
    }
};

// Globale Referenz für onclick-Handler
window.Validation = Validation;
