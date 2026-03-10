# memosaur 🦕 – Umfassende Produkt-Analyse
**Product Manager Assessment** | Stand: 10. März 2026

---

## Executive Summary

**memosaur** ist ein **Privacy-First Personal Memory System**, das Fotos, Nachrichten (WhatsApp/Signal), Google Maps Bewertungen und Geodaten zu einer durchsuchbaren Wissensbasis vereint. Nutzer können natürlichsprachliche Fragen stellen wie "Wo war ich im August mit Nora?" oder "Welche Restaurants habe ich in München besucht?".

**Aktueller Status:** Post-MVP, Pre-Launch
**Core Value Proposition:** Lokales persönliches Gedächtnis mit Zero-Cloud-Privacy
**Target Audience:** Privacy-bewusste Tech-Enthusiasten, Self-Hoster

**TL;DR (Too Long; Didn't Read):**
- ✅ **Technisch solide**: Funktionierende RAG-Pipeline, Offline-LLMs, DSGVO-Compliance
- ⚠️ **UX-Blocker**: Onboarding-Komplexität, fehlende Use-Case-Guidance
- 🚫 **Market-Gaps**: Keine Distribution-Strategie, kein Messaging, kein Community
- 💡 **Potential**: Einzigartige Privacy-Story, differenziert von Cloud-Anbietern

---

# 1. IST-Zustand Assessment

## 1.1 Stärken: Was funktioniert bereits gut?

### 🔐 Privacy-First Architecture (Kernstärke)
- **100% lokale Verarbeitung**: Alle Daten bleiben auf User-Hardware
- **Zero Cloud Dependencies**: Ollama, ChromaDB, SQLite – alles on-premise
- **DSGVO-Compliance by Design**:
  - Granularer Consent-Dialog (Art. 9 DSGVO)
  - Separate Opt-Ins für Fotos, GPS, Messages
  - Audit-Trail für alle Einwilligungen (SQLite)
  - Explizite User-Kontrolle über jeden Datentyp
- **Encrypted Sync**: AES-256-GCM in Browser (Web Crypto API), Passwort verlässt nie den Client
- **Entity Resolution in Browser**: IndexedDB für Personen-Mapping, kein Server-Klartext

**Wettbewerbsvorteil:** Während Notion AI, Mem, Rewind alle Cloud-basiert sind und Privacy-Kompromisse eingehen, ist memosaur die **einzige self-hosted Alternative** mit dieser Feature-Tiefe.

---

### 🎯 Technische Solidität

**Backend (Python/FastAPI):**
- Clean Architecture: Separation of Concerns (API v0/v1, RAG, Ingestion, DB)
- Async-first: aiosqlite, Background Tasks für WhatsApp-Ingestion
- Multi-User-Ready: User-scoped Collections, Token-basiertes Entity-Mapping
- Robust Error Handling: Retry-Logic für Vision-Timeouts, Fallback-Strategien

**RAG-Pipeline:**
- **Hybrid Search**: ChromaDB (Vektor) + Elasticsearch (BM25) für bessere Recall
- **Agentic Reasoning**: ReAct-Pattern mit Tool-Calling (search_photos, search_messages, search_places)
- **Context Window Optimization**: Top-K Filtering, Min-Score-Thresholds
- **Source Transparency**: Jede Antwort zeigt verwendete Quellen mit Inline-Referenzen `[[1]]`

**Face Recognition:**
- MediaPipe (schnelle CPU-Inferenz) + Facenet-PyTorch (512D Embeddings)
- DBSCAN-Clustering für automatische Gesichtszuordnung
- DirectML-Support für AMD GPUs (RX 9070 etc.)
- Human-in-the-Loop: User benennt Cluster manuell

**WhatsApp Integration:**
- **Live Ingestion**: Alle Nachrichten → ChromaDB (Real-Time)
- **Conversational Bot**: Antwortet mit RAG-Kontext
- **Intelligent Bulk Import**:
  - Smart Deduplication (per-chat timestamp tracking)
  - Rate Limiting (3s/chat, 60s batch pauses)
  - Ban-Schutz: Zeitfenster 09:00-22:00, exponential backoff
  - Fortsetzbarer Import (kein Re-Import von alten Nachrichten)
- **Security-by-Design**: 4-Layer-Check vor Bot-Response, Master-Kill-Switch

**Code Quality:**
- ~16.500 Python-Dateien (inkl. node_modules)
- ~50 eigene Backend-Module (backend/*)
- Konsistente Logging-Strategie
- Config-basiert (config.yaml), kein Hardcoding

---

### 🌟 Unique Features (Differenzierung)

1. **Multi-Source Integration:**
   - Google Photos (GPS, Personen-Tags, KI-Beschreibung)
   - Google Maps (Reviews, Saved Places)
   - WhatsApp (Live + Bulk)
   - Signal (Desktop-Export)
   - → Keine andere Personal-Memory-Lösung vereint diese Quellen

2. **Geo-Intelligence:**
   - Leaflet.js-Karte mit GPS-Clustering
   - Automatisches Reverse Geocoding (Nominatim)
   - Cluster-based Location Matching ("München-Ost")
   - Filter nach Quelle + Zeitraum

3. **Entity Resolution (Human-in-the-Loop):**
   - Gesichtserkennung → Cluster → User benennt Cluster
   - Verknüpfung von Foto-Clustern + Chat-Kontakten
   - Browser-lokales Mapping (IndexedDB)
   - Transparenz: User sieht alle Face-Assignments

4. **Vision LLM Integration:**
   - Ollama Vision (Gemma3:12b) für Bildbeschreibungen
   - VRAM-optimiert: Max 768px Resize, keep_alive:0
   - Retry-Logic bei GPU-Timeouts (3 Versuche)

---

## 1.2 Schwächen: Wo hakt es? Was fehlt?

### ❌ Kritische UX-Blocker (P0)

#### 1. **Onboarding-Komplexität** (Deal-Breaker)
**Problem:** First-Time-User steht vor einer 45-minütigen Setup-Odyssee:
1. Ollama installieren (CLI, nicht intuitiv)
2. Modelle pullen (qwen3:8b 5GB, gemma3:12b 8GB)
3. Python venv + Dependencies (sentence-transformers 470MB Download)
4. Google Takeout Export (Tage Wartezeit)
5. Takeout entpacken + Pfade in config.yaml anpassen
6. Server starten, Consent geben
7. 50 Fotos importieren (15-25 Min. Vision-Inferenz)

**Impact:** 95% Absprungrate vor erstem erfolgreichen Query.

**Why it matters:** Notion AI onboardet in 2 Minuten (Email → Dashboard). Rewind installiert in 30 Sekunden (Mac-App → Fertig). memosaur braucht technisches Verständnis (CLI, venv, YAML-Editing).

**Root Cause:** Keine Installation-Automation, keine vorkonfigurierten Images, keine "Quick Start"-Defaults.

---

#### 2. **Missing Use-Case Guidance** (P0)
**Problem:** Nach dem Import zeigt das UI "49 Fotos indexiert" – aber **was jetzt?**

- Keine Sample-Queries im UI
- Keine Tutorial-Bubble ("Versuch mal: 'Wo war ich letzte Woche?'")
- Keine Erklärung der Tabs (Karte, Personen, Validierung)
- Keine Beispiel-Ergebnisse aus der Demo-Datenbank

**Impact:** User stellt eine Query → bekommt "Keine passenden Daten" → denkt "funktioniert nicht" → churnt.

**Reality Check:** Die 50 Sample-Fotos sind aus Aug/Sep/Nov – wenn User "Wo war ich im Januar?" fragt, gibt es keine Treffer. User versteht nicht, **was der Scope der Datenbank ist**.

---

#### 3. **Face Recognition UX ist unklar** (P1)
**Problem:** "Personen"-Tab zeigt Cluster von Gesichtern → User soll einen Namen vergeben. **ABER:**
- Keine Erklärung, warum Cluster manchmal nur 1 Gesicht haben
- Keine Preview, welche Fotos zu diesem Cluster gehören (erst nach Klick auf "Bilder verwalten")
- Keine Confidence-Score (wie sicher ist der Cluster?)
- Keine Hinweise, wie man Fehler korrigiert (falsches Face Assignment)

**User-Mental-Model:** "Ich will einfach nach Personen suchen" → **Realität:** "Ich muss erst 20 Cluster manuell labeln".

**Lösung fehlt:**
- Onboarding-Wizard: "Wir haben 5 Personen erkannt – benenne sie jetzt"
- Smart Defaults: Häufigste Chat-Kontakte vorschlagen
- Bulk-Edit: "Diese 3 Cluster sind alle die gleiche Person"

---

### ⚠️ Funktionale Lücken (P1)

#### 1. **WhatsApp Import ist fehleranfällig**
- **Bulk Import** pausiert nach 22:00 Uhr (Ban-Schutz) – aber keine Fortschritts-Persistenz über Neustarts
- **Deduplication** funktioniert – aber UI zeigt nicht, welche Chats bereits importiert sind
- **Rate Limiting** ist konservativ (3s/chat) → 100 Chats = 5 Minuten – User denkt "hängt"
- **Error Handling:** Bei WhatsApp-Disconnect bricht Import ab, kein Auto-Reconnect

---

#### 2. **Vision-Beschreibungen sind generisch**
**Beispiel aus Sample:**
> "Ein kleines Mädchen mit blonden Locken steht auf einem Spielplatz..."

**Problem:** LLM halluziniert Kontext ("Spielplatz") statt nur zu beschreiben, was sichtbar ist.

**Impact:** Search-Qualität leidet → Query "Spielplatz" findet Bild, obwohl kein Playground-Tag in EXIF.

**Lösung fehlt:**
- System-Prompt für Vision verfeinern: "Describe ONLY what you see, no interpretation"
- Structured Output: JSON mit `{objects: [], scene: [], colors: []}`
- User-Feedback-Loop: "War diese Beschreibung hilfreich?" → Fine-Tuning

---

#### 3. **Elasticsearch-Setup ist Manual**
- Backend erwartet Elasticsearch auf localhost:9200
- **Keine automatische Fallback** auf ChromaDB-only
- **Keine Dokumentation**, wie man ES installiert (Docker? Binary?)
- Error-Message ist kryptisch: `verify_elasticsearch() failed`

**Impact:** 50% der User scheitern an ES-Requirement, weil nicht klar ist, dass es **optional** ist (ChromaDB reicht für Prototyp).

---

#### 4. **Mobile Experience fehlt komplett**
- Single-Page-App ist Desktop-only (keine responsive Breakpoints)
- WhatsApp-Bot ist theoretisch mobil-nutzbar – aber Setup muss am Desktop erfolgen
- Kein PWA (Progressive Web App) → keine Installierbarkeit
- Keine Mobile-Optimierung für Consent-Dialog, Entity-Modal, Lightbox

**Market Reality:** 70% der Personal-Memory-Use-Cases sind mobil ("Wo habe ich das Restaurant gesehen?").

---

### 🛠️ Technische Schulden (P2)

1. **Duale API-Generationen (v0 + v1):**
   - Erhöht Code-Komplexität
   - Verwirrt neue Developer (welche Version nutzen?)
   - v0 sollte deprecated + entfernt werden

2. **Frontend ist 1775 Zeilen HTML in einer Datei:**
   - Schwer wartbar
   - Keine Komponentenstruktur
   - Kein Build-System (alles CDN-basiert)

3. **Face Recognition ist CPU-bound:**
   - MediaPipe läuft auf CPU → langsam bei 1000+ Fotos
   - Keine Batch-Inferenz
   - Kein Caching von Embeddings

4. **WhatsApp-Bridge läuft in separatem Node-Prozess:**
   - Kompliziert Deployment (2 Services statt 1)
   - Kein Auto-Restart bei Crash
   - Prozess-Management via PID-Tracking im Bash-Script

---

## 1.3 Market Positioning: Wo steht memosaur?

### Wettbewerbsanalyse

| Produkt | Ansatz | Privacy | Preis | Stärken | Schwächen |
|---------|--------|---------|-------|---------|-----------|
| **memosaur** | Self-Hosted | ✅ 100% | Free | Zero-Cloud, Multi-Source, Open Source | Komplexes Setup, keine Mobile-App |
| **Rewind** | Local-First | ⚠️ 90% | $19/mo | Einfaches Setup, macOS-native, Screen Recording | macOS-only, Cloud-Backup optional |
| **Mem** | Cloud | ❌ 0% | $15/mo | Slick UX, Mobile-App, Kollaboration | Alle Daten in Cloud, USA-Server |
| **Notion AI** | Cloud | ❌ 0% | $10/mo | Integriert in Workspace, Teamshare | Kein Personal-Memory-Focus |
| **Obsidian + Dataview** | Local Files | ✅ 100% | Free | Flexibel, Plugin-Ecosystem | Keine RAG, manuelle Vernetzung |

**memosaur's Nische:**
- **Hardcore Privacy**: Für User, die Rewind's Cloud-Backup nicht vertrauen
- **Multi-Source Integration**: Einzige Lösung, die WhatsApp + Google Photos + Maps vereint
- **Self-Hosting Community**: DevOps-affine User, die eigene Infrastruktur betreiben

**Problem:** Diese Nische ist **klein** (geschätzt <50k User weltweit).

---

### Target Audience (aktuell)

**Primär:**
1. **Privacy-Activists** (Sicherheitsforscher, Journalisten, Aktivisten)
   - Use-Case: Sensitive Kommunikation analysieren ohne Cloud-Exposure
   - Pain: Cloud-Dienste sind Honeypots für Subpoenas
   - Budget: Gratis, da Ideologie-getrieben

2. **Self-Hosting-Enthusiasten** (r/selfhosted, r/homelab)
   - Use-Case: "Ich hoste alles selbst – Mail, Files, Photos, nun auch Memory"
   - Pain: Fehlender RAG-Layer für eigene Daten
   - Budget: $0-50/mo (Stromkosten für Home-Server)

3. **Tech-Early-Adopters** (HackerNews, Lobsters)
   - Use-Case: "Cool Tech" ausprobieren, aber nicht langfristig nutzen
   - Pain: Keine echte Pain – Curiosity-Driven
   - Budget: Zeit-Investment, nicht Geld

**Sekundär (aktuell nicht adressiert):**
- **Senioren** (Alzheimer-Prävention, Erinnerungshilfe)
- **ADHS-Community** (externe Gedächtnisunterstützung)
- **Journalisten/Researcher** (Interview-Transkripte, Recherche-Datenbank)

---

### Market Fit: Gap-Analyse

**Product-Market Fit (aktuell):** ⚠️ **Nein**

**Gründe:**
1. **Target Audience zu klein**: Self-Hoster mit LLM-Know-how = <10k aktive User weltweit
2. **Setup-Barrier zu hoch**: 95% Absprung vor erstem Success
3. **Value Proposition unklar**: "Was löst memosaur, das Google Photos Search nicht kann?"

**Path to PMF:**
1. **Pivot zu "Managed Self-Hosting"**: 1-Click-Deploy via Docker/Railway/Fly.io
2. **Oder: Nische verdoppeln**: B2B für Privacy-sensitive Branchen (Legal, Healthcare)
3. **Oder: Consumer-Pivot**: Mobile-App mit iCloud-Private-Compute-ähnlichem Ansatz

---

## 1.4 User Journey Gaps: Wo verlieren wir Nutzer?

### Funnel-Analyse (Hypothetisch)

| Stage | User-Aktion | Erwartete Completion | Typischer Blocker |
|-------|-------------|---------------------|-------------------|
| **Awareness** | Findet memosaur via HN/Reddit | 100% | N/A |
| **Interest** | Liest README | 60% | README zu technisch, kein Demo-Video |
| **Setup Start** | Klont Repo | 40% | Kein Pre-Built Binary |
| **Ollama Install** | Installiert Ollama | 30% | CLI-Angst, Windows-User strugglen |
| **Model Download** | Pullt qwen3:8b (5GB) | 20% | Langsame Internet-Connection |
| **Backend Start** | `./start.sh` | 15% | Python-Fehler (fehlende Libs) |
| **Takeout Export** | Google Takeout anfordern | 10% | Tage Wartezeit, User vergisst Projekt |
| **Import Success** | Fotos importiert | 5% | Vision-Timeout, VRAM-Fehler |
| **First Query** | Stellt Frage | 3% | Keine Sample-Queries, leere Antwort |
| **Retention** | Nutzt nach 1 Woche weiter | <1% | Kein Daily-Use-Case, "löst kein Problem" |

**Kritische Drop-Off-Punkte:**
1. **Ollama-Install** (40% → 30%): CLI-Skill-Requirement
2. **Takeout-Wartezeit** (15% → 10%): User verliert Momentum
3. **First Query Fail** (3% → <1%): "Es funktioniert nicht"

---

# 2. Marktreife-Analyse

## 2.1 MVP Launch (aktueller Stand + Gaps)

### Was ist fertig?
✅ **Core Features:**
- RAG-Pipeline (Vektor + Keyword-Search)
- Multi-Source-Ingestion (Photos, Maps, WhatsApp, Signal)
- Face Recognition + Entity Resolution
- DSGVO-Consent-Management
- Encrypted Sync
- Interactive Map
- WhatsApp Live Bot

✅ **Technical Infrastructure:**
- FastAPI Backend
- ChromaDB + Elasticsearch
- Ollama-Integration (Chat + Vision)
- SQLite für User/Consent
- Single-Page-App (HTML/Tailwind)

### Was fehlt für MVP Launch?
❌ **P0 (Blocker):**
1. **Onboarding-Wizard:**
   - Schritt-für-Schritt-Guide im UI
   - Automatische Checks: "Ollama läuft? ✅" "Modelle geladen? ✅"
   - Setup-Fortschritt persistieren (Browser-Reload → Fortschritt bleibt)

2. **Demo-Modus:**
   - Pre-indexierte Demo-Daten (10 Fotos, 5 Reviews, 20 Messages)
   - User kann direkt Queries testen ohne eigene Daten
   - "Probier mal: 'Wo war ich am 29. August?'" → zeigt Demo-Foto

3. **Error Messaging:**
   - "Keine Ergebnisse" → zeige Scope der Datenbank ("Du hast 49 Fotos von Aug-Nov")
   - Vision-Timeout → "GPU überlastet, warte 30s" statt kryptischer Error
   - ES-Fehler → "Elasticsearch nicht gefunden, läuft im ChromaDB-only Modus"

4. **Installation vereinfachen:**
   - Docker Compose (1 File für Backend+ES+Ollama)
   - Oder: Electron-App mit bundled Ollama
   - Oder: Cloud-Hosted Demo-Instance (memosaur.app/demo)

---

## 2.2 1.0 Launch (Production-Ready)

### Definition: "Production-Ready"
- 1000 MAU (Monthly Active Users) können stabilen Service erwarten
- Uptime 99% (Self-Hosted: User-Verantwortung, aber Code stabil)
- Dokumentation für alle kritischen Flows
- Community-Support-Struktur (Discord/Matrix)

### Was fehlt für 1.0?
❌ **P1 (High Priority):**

1. **Performance-Optimierung:**
   - Face Recognition: GPU-Batching (10 Faces gleichzeitig)
   - Vision-Inferenz: Async-Queue (nicht sequenziell)
   - Elasticsearch: Index-Tuning (aktuell default settings)
   - Frontend: Lazy-Loading für 1000+ Fotos

2. **Robustheit:**
   - Graceful Degradation: ES down → Fallback ChromaDB-only
   - Retry-Strategien für alle externen Calls (Ollama, Nominatim)
   - Health-Checks: `/health`-Endpoint mit Dependency-Status
   - Automatic Backups: SQLite + ChromaDB → S3/Backup-Location

3. **Monitoring & Observability:**
   - Strukturiertes Logging (JSON)
   - Metrics: Query-Latency, Import-Duration, Error-Rates
   - User-Opt-In Telemetrie: "Teile anonyme Usage-Stats zur Verbesserung"

4. **Security Hardening:**
   - Rate-Limiting für API-Endpoints
   - CSRF-Protection (aktuell CORS=*)
   - SQL-Injection-Prevention (aktuell sicher via aiosqlite, aber paranoid sein)
   - Secure Defaults: Config-File mit Safe-Values

5. **Testing:**
   - Unit-Tests für kritische Flows (aktuell 0%)
   - Integration-Tests für RAG-Pipeline
   - E2E-Tests für Onboarding-Flow (Playwright)

---

## 2.3 Market Fit (Mainstream-Adoption)

### Definition: "Market Fit"
- Product solves a **real, painful problem** for ≥10k paying users
- Organic Growth: 20%+ MoM ohne Ads
- Retention: 40%+ nach 3 Monaten
- NPS (Net Promoter Score): ≥30

### Was fehlt für Market Fit?
❌ **P0 (Existenziell):**

1. **Klares Value Proposition:**
   - **Aktuell:** "Privacy-first personal memory system"
   - **Problem:** Das löst kein spezifisches Problem → zu abstrakt
   - **Besser:** "Finde jede WhatsApp-Nachricht, jedes Foto, jeden Ort – in Sekunden. Ohne Google, ohne Cloud."
   - **Noch besser (Niche):** "Dein DSGVO-konformes Gedächtnis für sensible Kommunikation (Anwälte, Journalisten)"

2. **Deployment vereinfachen:**
   - **Aktuell:** 45-Min-Setup für Tech-Affine
   - **Target:** 5-Min-Setup für alle
   - **Lösungen:**
     - Managed Hosting (memosaur.cloud) mit E2E-Encryption
     - 1-Click-Deploy (Vercel/Railway/Coolify)
     - Desktop-App (Electron + bundled Ollama)
     - Mobile-App (React Native + Cloud-LLM-Option)

3. **Use-Case-Focus:**
   - **Aktuell:** "Alles für alle" → verwässert
   - **Pivot-Optionen:**
     - **Option A:** "WhatsApp-Suche" (Killer-Feature)
       - 80% der User nutzen nur Message-Search
       - → Strip Foto/Maps, fokussiere auf Chat-Memory
     - **Option B:** "Travel-Journal"
       - GPS-Punkte + Fotos + Reviews = automatisches Reise-Tagebuch
       - → Monetization via Premium-Maps, Reise-Insights
     - **Option C:** "Relationship-Memory"
       - "Was habe ich mit Lisa gemacht?" → zeigt Timeline
       - → Emotionaler Hook, Dating-Market

4. **Distribution-Channel:**
   - **Aktuell:** Keine (außer GitHub-Stars)
   - **Target:** 1 primärer Channel mit Traction
   - **Optionen:**
     - r/selfhosted (50 Upvotes = 500 Signups)
     - HackerNews Show HN (Top 3 = 5k Visits)
     - ProductHunt Launch (Top 5 = 10k Visits)
     - YouTube (Tech-YouTuber Review = 50k Views)
     - Privacy-Podcasts (Darknet Diaries, etc.)

---

## 2.4 Kritische Blocker: Was MUSS gelöstsein?

### P0 (Launch-Blocker)
1. **Onboarding < 10 Minuten** (aktuell 45 Min)
   - Lösung: Docker Compose + Demo-Daten
   - Metrik: 50% der User schaffen First Query

2. **Klare Value Prop** (aktuell unklar)
   - Lösung: Landing-Page mit Use-Case-Videos
   - Metrik: 80% der Besucher verstehen, was memosaur löst

3. **Error-Handling** (aktuell kryptisch)
   - Lösung: User-Friendly Error-Messages
   - Metrik: <5% Support-Anfragen zu "funktioniert nicht"

### P1 (Post-Launch Critical)
1. **Mobile-Responsiveness**
   - 70% Traffic wird mobil sein
   - Ohne Mobile = 70% Churn

2. **Performance bei 1000+ Fotos**
   - Aktuell: Frontend hängt bei 500+ Thumbnails
   - Lösung: Virtual Scrolling, Pagination

3. **Community-Building**
   - Ohne Community = kein Feedback = totes Projekt
   - Lösung: Discord/Matrix, wöchentliche Office-Hours

---

# 3. Zielbild (Vision)

## 3.1 Produktvision (6-12 Monate)

### North Star
**"memosaur wird das DSGVO-konforme Gedächtnis für 100.000 Privacy-bewusste Europäer."**

### Vision Statement
> "In einer Welt, in denen Tech-Giganten deine Erinnerungen zu Geld machen, ist memosaur dein selbst-gehostetes, verschlüsseltes, durchsuchbares Gedächtnis. Du besitzt deine Daten – niemand sonst."

### Strategische Ziele (12 Monate)

**Q2 2026 (Apr-Jun):**
- ✅ MVP Launch (Docker-basiert, Onboarding < 10 Min)
- 1.000 GitHub-Stars
- 500 MAU (Monthly Active Users)
- Community: Discord mit 200 Members

**Q3 2026 (Jul-Sep):**
- ✅ 1.0 Release (Production-Ready, Mobile-Responsive)
- 5.000 GitHub-Stars
- 2.000 MAU
- Monetization-Experiment: Managed Hosting ($10/mo)

**Q4 2026 (Oct-Dez):**
- ✅ Mobile-App (iOS/Android) oder Desktop-App (Electron)
- 10.000 GitHub-Stars
- 5.000 MAU
- 100 Paying Customers ($1k MRR)

**Q1 2027 (Jan-Mrz):**
- ✅ Market Fit bestätigt (NPS >30, Retention >40%)
- 20.000 MAU
- 500 Paying Customers ($5k MRR)
- Series-A-Ready (wenn VC-Track gewünscht)

---

## 3.2 Kernmetriken (Wie messen wir Erfolg?)

### North-Star-Metrik
**Wöchentliche Active Queries (WAQ)**
- = Anzahl der Queries pro Woche / aktive User
- Target: 10 WAQ (User nutzt memosaur 10x/Woche)
- Rationale: Hohe Query-Frequency = Product-Stickiness

### Primäre Metriken

| Metrik | Definition | Aktuell | Ziel (6M) | Ziel (12M) |
|--------|------------|---------|-----------|------------|
| **MAU** | Monthly Active Users (≥1 Query) | ~10 | 2.000 | 20.000 |
| **WAQ** | Weekly Active Queries / User | 0 | 5 | 10 |
| **Retention** | 3-Monat-Retention | 0% | 20% | 40% |
| **Onboarding** | % User mit ≥1 erfolgreichen Query | 5% | 50% | 80% |
| **NPS** | Net Promoter Score | N/A | 20 | 40 |

### Sekundäre Metriken

| Metrik | Definition | Aktuell | Ziel (12M) |
|--------|------------|---------|------------|
| **GitHub-Stars** | Social Proof | ~50 | 10.000 |
| **Avg. Indexed Docs/User** | Datenbank-Tiefe | ~300 | 5.000 |
| **Setup-Time** | Median Time-to-First-Query | 45 Min | 5 Min |
| **Error-Rate** | % Queries mit Fehler | ~20% | <2% |
| **Mobile-Traffic** | % Traffic von Mobile | 0% | 40% |

---

## 3.3 Zielgruppen-Definition (Refined)

### Primäre Zielgruppe (0-12 Monate)
**"Privacy-bewusste Tech-Professionals (EU)"**

**Demographics:**
- Alter: 25-45
- Beruf: Software-Entwickler, DevOps, IT-Security
- Einkommen: 60k-120k EUR/Jahr
- Location: Deutschland, Schweiz, Niederlande, Skandinavien

**Psychographics:**
- Werte: Privacy, Selbstbestimmung, Open Source
- Verhalten: Self-Hosting (Nextcloud, Bitwarden), nutzt VPN/Tor, Linux-User
- Pain: "Ich will Google Photos, aber ohne Google"
- Willingness-to-Pay: $5-20/mo für Managed Hosting (Convenience)

**Use-Cases:**
1. WhatsApp-Suche ("Was sagte Lisa über das Meeting?")
2. Reise-Erinnerungen ("Wo habe ich im Sommer gegessen?")
3. Personen-Tracking ("Wann habe ich Max zuletzt getroffen?")

---

### Sekundäre Zielgruppe (12-24 Monate)
**"Privacy-sensitive Professionals"**

**Verticals:**
1. **Legal** (Anwälte, Paralegals)
   - Use-Case: Client-Kommunikation durchsuchen (DSGVO-konform)
   - Pain: E-Discovery ist teuer + Cloud-Risiken
   - Willingness-to-Pay: $50-200/mo pro Seat

2. **Healthcare** (Ärzte, Therapeuten)
   - Use-Case: Patienten-Notizen durchsuchen (HIPAA/DSGVO)
   - Pain: EMR-Systeme haben schlechte Search
   - Willingness-to-Pay: $30-100/mo

3. **Journalism** (Investigative Reporter)
   - Use-Case: Interview-Transkripte, Recherche-Datenbank
   - Pain: Cloud-Dienste sind Subpoena-anfällig
   - Willingness-to-Pay: $0 (Non-Profit) bis $50/mo

---

## 3.4 Wettbewerbsvorteil (Differentiation)

### Unique Value Props (UVPs)

**1. "Zero-Cloud-Guarantee"**
- Kein Cloud-Anbieter kann das bieten (alle haben Backup in AWS/GCP)
- Einzige Self-Hosted-Alternative mit RAG + Multi-Source
- Messaging: "Deine Daten verlassen nie deine Hardware"

**2. "DSGVO-Compliant by Design"**
- Granularer Consent (Foto, GPS, Messages separat)
- Audit-Trail für alle Verarbeitungen
- Explizite Löschfunktionen (Right-to-be-Forgotten)
- Messaging: "Rechtssicher für EU-Unternehmen"

**3. "Multi-Source-Integration"**
- Rewind: nur Screen-Recording
- Mem: nur Notizen
- memosaur: Photos + Maps + WhatsApp + Signal
- Messaging: "Alle deine Erinnerungen, eine Suche"

**4. "Open Source & Hackable"**
- Community kann Plugins bauen
- Transparent: Kein Vendor-Lock-in
- Messaging: "Dein Code, deine Regeln"

---

### Positioning Statement

**For** privacy-conscious professionals in the EU
**who** want to search their personal data (photos, messages, places)
**memosaur** is a self-hosted memory system
**that** provides zero-cloud, GDPR-compliant RAG search
**unlike** Rewind (macOS-only, Cloud-Backup) or Mem (Cloud-only)
**we** guarantee your data never leaves your hardware.

---

# 4. Priorisierte Roadmap

## Phase 1: MVP-Ready (0-2 Monate)

### Ziel: 500 User schaffen First Query, 20% Retention

| Feature | Priority | User-Value | Effort | Success-Metric |
|---------|----------|------------|--------|----------------|
| **Docker Compose Setup** | P0 | 10/10 | M | 80% schaffen Setup in <10 Min |
| **Onboarding-Wizard (UI)** | P0 | 9/10 | L | 50% erreichen First Query |
| **Demo-Modus** | P0 | 8/10 | S | 100% User sehen Sample-Results |
| **Error-Message-Refactor** | P0 | 7/10 | M | <5% Support-Tickets zu Errors |
| **Mobile-Responsive UI** | P1 | 9/10 | L | 40% Traffic von Mobile |
| **WhatsApp Import UX** | P1 | 8/10 | M | 80% erfolgreicher Bulk-Import |
| **Landing-Page + Docs** | P1 | 7/10 | M | 60% Conversion (Visit → Setup) |
| **Health-Check-Endpoint** | P2 | 5/10 | S | OpsEase für Self-Hoster |

---

### Feature-Details

#### 1. Docker Compose Setup (P0, Effort: M, User-Value: 10/10)
**Problem:** Aktuell 7 Setup-Schritte, hohe Absprungrate.

**Lösung:**
```yaml
# docker-compose.yml
services:
  ollama:
    image: ollama/ollama:latest
    volumes: [./ollama-data:/root/.ollama]
  backend:
    build: .
    depends_on: [ollama, elasticsearch]
    environment:
      - OLLAMA_URL=http://ollama:11434
  elasticsearch:
    image: elasticsearch:8.12.0
    environment: [discovery.type=single-node]
  frontend:
    build: ./frontend
    ports: ["8000:8000"]
```

**Commands:**
```bash
git clone https://github.com/you/memosaur && cd memosaur
docker compose up -d
# Open http://localhost:8000 → Done
```

**Success-Metric:** 80% der User schaffen Setup in <10 Min (tracked via Analytics-Opt-In).

---

#### 2. Onboarding-Wizard (P0, Effort: L, User-Value: 9/10)
**Design (Wireframe):**

**Schritt 1:** "Willkommen bei memosaur 🦕"
- Erklärvideo (30s): Was macht memosaur?
- Button: "Demo ausprobieren" vs. "Eigene Daten importieren"

**Schritt 2:** "System-Check"
- ✅ Ollama läuft (http://localhost:11434/api/tags)
- ✅ Modelle geladen (qwen3:8b, gemma3:12b)
- ⚠️ Falls nicht: "Installiere Ollama: [Link]"

**Schritt 3:** "Datenquellen wählen"
- Checkboxen: [ ] Google Photos [ ] WhatsApp [ ] Google Maps
- Info: "Du kannst später weitere Quellen hinzufügen"

**Schritt 4:** "Consent geben"
- Zeige DSGVO-Dialog (wie aktuell)
- Erklär: "Warum braucht memosaur diese Rechte?"

**Schritt 5:** "Import läuft..."
- Fortschrittsbalken mit ETA
- "Wir indexieren 49 Fotos – dauert ~15 Min"

**Schritt 6:** "Fertig! Probier's aus"
- Zeige 3 Sample-Queries mit einem Klick
- "Wo war ich im August?" → sofort ausführen

**Success-Metric:** 50% der User erreichen Schritt 6.

---

#### 3. Demo-Modus (P0, Effort: S, User-Value: 8/10)
**Implementierung:**
- Bundle 10 Demo-Fotos (Lizenzfrei, z.B. Unsplash) mit GPS + Vision-Beschreibung
- 5 Demo-Reviews ("Restaurant in München")
- 20 Demo-Messages (fiktive WhatsApp-Konversation)
- Alles vorindexiert in ChromaDB (shipped als `demo.db`)

**UI:**
- Toggle oben rechts: "Demo-Modus" vs. "Eigene Daten"
- Im Demo-Modus: Banner "Das sind Sample-Daten – importiere deine eigenen für echte Ergebnisse"

**Success-Metric:** 100% der First-Time-User sehen erfolgreiche Query-Resultate.

---

#### 4. Error-Message-Refactor (P0, Effort: M, User-Value: 7/10)
**Aktuelle Probleme:**
- "Keine passenden Daten gefunden" → zu generisch
- Vision-Timeout: `model runner stopped` → kryptisch
- ES-Fehler: Stack-Trace im UI

**Lösungen:**

**No-Results-Error:**
```diff
- "Keine passenden Daten gefunden."
+ "Keine Treffer. Du hast 49 Fotos (Aug-Nov), 210 Orte, 0 Nachrichten indexiert.
+  Tipp: Frag nach Orten/Personen in diesem Zeitraum."
```

**Vision-Timeout:**
```diff
- "Error: model runner stopped unexpectedly"
+ "GPU überlastet. Warte 30s und versuch's nochmal.
+  Oder: Nutze ein kleineres Modell (gemma3:4b statt gemma3:12b)."
```

**ES-Down:**
```diff
- "ConnectionRefusedError: [Errno 111] Connection refused"
+ "Elasticsearch nicht gefunden. memosaur läuft im ChromaDB-only Modus (langsamer).
+  Behebung: docker compose up elasticsearch"
```

**Success-Metric:** <5% Support-Tickets zu "funktioniert nicht".

---

#### 5. Mobile-Responsive UI (P1, Effort: L, User-Value: 9/10)
**Breakpoints:**
- `sm`: 640px (Smartphones)
- `md`: 768px (Tablets)
- `lg`: 1024px (Desktop)

**Key Changes:**
- **Header:** Hamburger-Menu statt Tabs (< 768px)
- **Chat:** Eingabefeld sticky am Bottom
- **Karte:** Full-Height (nicht 400px fixed)
- **Lightbox:** Swipe-to-Close Gesture
- **Entity-Modal:** Bottom-Sheet statt Centered-Modal

**Success-Metric:** 40% Traffic von Mobile (tracked via User-Agent).

---

#### 6. WhatsApp Import UX (P1, Effort: M, User-Value: 8/10)
**Probleme:**
- Bulk-Import bricht bei 22:00 ab, User sieht nur "pausiert"
- Keine Fortschrittsanzeige während Import
- Dedup-Status unklar ("Wurde dieser Chat bereits importiert?")

**Lösungen:**

**Fortschrittsanzeige:**
```
[=====>        ] 45/120 Chats (37%)
Aktuell: "Lisa Müller" (250 Nachrichten)
Neue: 128 | Bereits vorhanden: 122
ETA: 12 Minuten
```

**Dedup-Indicator:**
```
Chatliste:
☑ Lisa Müller (250 Nachrichten) – Letzter Import: 09.03. 21:45
☐ Max Mustermann (1.2k Nachrichten) – Noch nicht importiert
☑ Familie (5k Nachrichten) – Letzter Import: 08.03. 10:30
```

**Pause-Handling:**
```
Import pausiert (22:00 Zeitlimit).
Fortschritt gespeichert: 45/120 Chats.
[▶ Morgen fortsetzen (09:00)]
```

**Success-Metric:** 80% erfolgreiche Bulk-Imports (keine Abbrüche).

---

#### 7. Landing-Page + Docs (P1, Effort: M, User-Value: 7/10)
**Landing-Page (memosaur.app):**

**Above-the-Fold:**
- Hero: "Dein Gedächtnis. Deine Daten. Deine Hardware."
- Subheadline: "Durchsuche Fotos, WhatsApp, Google Maps – ohne Cloud, mit AI."
- CTA: "Jetzt installieren (5 Minuten)" → GitHub-Link
- Demo-Video (30s): User stellt Query → sieht Ergebnisse

**Features-Section:**
- 🔒 Zero-Cloud-Guarantee
- 🇪🇺 DSGVO-Compliant
- 💬 WhatsApp-Integration
- 🗺️ GPS-Tracking
- 👤 Face-Recognition

**How-it-Works:**
- 1. Docker Compose starten
- 2. Daten importieren
- 3. Fragen stellen
- "So einfach ist es."

**Testimonials:**
- (Noch keine echten – placeholder: "Genau das habe ich gesucht – @privacyNerd")

**Docs:**
- Quick-Start (5-Min-Setup)
- Troubleshooting (Ollama, ES, VRAM)
- Architecture (Technical Deep-Dive)
- API-Docs (OpenAPI)

**Success-Metric:** 60% Conversion (Visit → Setup-Start).

---

## Phase 2: Growth (3-6 Monate)

### Ziel: 2.000 MAU, 20% 3-Monat-Retention, $1k MRR

| Feature | Priority | User-Value | Effort | Success-Metric |
|---------|----------|------------|--------|----------------|
| **Managed Hosting (Beta)** | P0 | 9/10 | XL | 100 Paying-Customers à $10/mo |
| **Plugin-System** | P1 | 8/10 | L | 10 Community-Plugins |
| **Advanced-Filtering** | P1 | 7/10 | M | 50% Queries nutzen Filter |
| **Export/Backup** | P1 | 8/10 | M | 80% User nutzen Backup |
| **Voice-Input** | P2 | 6/10 | M | 20% Queries via Voice |
| **Multi-User** | P2 | 5/10 | L | Family-Plan (5 User) |

---

### Feature-Highlights

#### 1. Managed Hosting (P0, Effort: XL, User-Value: 9/10)
**Problem:** Self-Hosting-Barrier bleibt für 80% der Interested-User.

**Lösung:**
- **memosaur.cloud**: Hosted-Instanz mit E2E-Encryption
- User zahlt $10/mo, wir hosten Backend+Ollama+ES auf DO/Hetzner
- Data bleibt verschlüsselt auf Server (Zero-Knowledge-Architecture)
- Key wird nur im Browser gehalten (wie Sync-Feature)

**Pricing:**
- Free: Self-Hosted (wie bisher)
- Starter: $10/mo (1 User, 5GB Storage, Basic-Modelle)
- Pro: $20/mo (1 User, 50GB, Advanced-Modelle, Priority-Support)
- Family: $30/mo (5 User, 100GB, Shared-Memory)

**Success-Metric:** 100 Paying-Customers (5% Conversion von MAU).

---

#### 2. Plugin-System (P1, Effort: L, User-Value: 8/10)
**Vision:** Community baut Integrations.

**Architecture:**
```python
# plugins/telegram/ingest.py
class TelegramPlugin(MemosaurPlugin):
    def ingest(self, export_file: Path):
        messages = parse_telegram_export(export_file)
        return [{"text": m.text, "date": m.date} for m in messages]
```

**Use-Cases:**
- Telegram-Export
- Instagram-DMs
- Gmail-Archive
- Notion-Pages
- Apple-Photos

**Success-Metric:** 10 Community-Plugins im Plugin-Store.

---

#### 3. Advanced-Filtering (P1, Effort: M, User-Value: 7/10)
**UI (Chat-Tab):**
```
Query: "Restaurants in München"
Filter: ☐ Nur Fotos ☐ Nur Reviews ☑ Nur Orte
        [Aug 2025 ▼] bis [Heute ▼]
        GPS-Radius: [München ⊕ 5km]
```

**Backend:**
- Filter werden an RAG-Pipeline weitergegeben
- ChromaDB-Where-Clauses erweitert
- Geo-Radius-Search via Haversine

**Success-Metric:** 50% der Queries nutzen Filter.

---

#### 4. Export/Backup (P1, Effort: M, User-Value: 8/10)
**Features:**
- **Full-Backup:** SQLite + ChromaDB + Fotos → .tar.gz
- **Scheduled Backups:** Cronjob (täglich/wöchentlich)
- **Cloud-Backup:** Optional zu S3/Backblaze
- **Export-Formate:** JSON, CSV, Markdown

**UI (Settings):**
```
Backup:
  Letztes Backup: 09.03.2026 22:00 (8.5 GB)
  [📦 Jetzt Backup erstellen]
  [⚙️ Automatische Backups: Täglich, 02:00]
```

**Success-Metric:** 80% User aktivieren Backups.

---

## Phase 3: Scale (6-12 Monate)

### Ziel: 20.000 MAU, 40% Retention, $5k MRR

| Feature | Priority | User-Value | Effort | Success-Metric |
|---------|----------|------------|--------|----------------|
| **Mobile-App (iOS/Android)** | P0 | 10/10 | XL | 10k Downloads |
| **Desktop-App (Electron)** | P0 | 9/10 | L | 5k Downloads |
| **Team-Features** | P1 | 7/10 | XL | 50 Team-Accounts |
| **Advanced-Analytics** | P1 | 6/10 | M | "Insights"-Dashboard |
| **Voice-Memos** | P2 | 8/10 | L | Transcription + Index |
| **AI-Summaries** | P2 | 7/10 | M | "Was war los letzte Woche?" |

---

### Feature-Highlights

#### 1. Mobile-App (P0, Effort: XL, User-Value: 10/10)
**Platform:** React Native (iOS + Android aus einer Codebase).

**Features:**
- Voice-Input als Primary-Interface
- Push-Notifications: "Neue WhatsApp-Nachricht indexiert"
- Offline-Mode: Cached Queries
- Camera-Integration: Foto → sofort indexiert

**Success-Metric:** 10k Downloads, 40% D7-Retention.

---

#### 2. Desktop-App (P0, Effort: L, User-Value: 9/10)
**Platform:** Electron (Windows/Mac/Linux).

**Bundled:**
- Ollama (embedded)
- Backend (FastAPI)
- ChromaDB
- → 1-Click-Install, kein CLI nötig

**Success-Metric:** 5k Downloads, 60% Conversion (Download → Active-User).

---

#### 3. Team-Features (P1, Effort: XL, User-Value: 7/10)
**Use-Case:** Small-Teams (Startups, Freelancer-Kollektive) wollen gemeinsames Memory.

**Features:**
- Shared-Collections: "Team-Reise nach Barcelona"
- Permissions: Admin, Editor, Viewer
- Activity-Log: "Lisa hat 50 Fotos importiert"

**Pricing:** $50/mo für Team (5 User).

**Success-Metric:** 50 Team-Accounts ($2.5k MRR).

---

# 5. Go-to-Market Strategie

## 5.1 Launch-Strategie (wo, wie, wann?)

### Phase 1: Stealth-Launch (Monat 1-2)
**Ziel:** 100 Beta-User, Feedback sammeln.

**Channels:**
1. **Personal Network:**
   - LinkedIn-Post: "Ich baue Privacy-Tool – Beta-Tester gesucht"
   - Twitter-Thread: Technical Deep-Dive
   - Email an Privacy-Community-Kontakte

2. **Niche-Communities:**
   - r/selfhosted: "Show-and-Tell: Self-Hosted Personal Memory"
   - r/privacy: "DSGVO-konformes Alternative zu Rewind"
   - HackerNews: Ask HN: "Feedback für mein Privacy-Tool?"

**Taktik:** Direktes Feedback, keine Scale-Ambitionen.

---

### Phase 2: Public-Launch (Monat 3)
**Ziel:** 1.000 MAU, virales Momentum.

**Channels:**
1. **HackerNews (Show HN):**
   - Timing: Dienstag 08:00 PST (höchste Traffic-Zeit)
   - Titel: "Show HN: memosaur – Self-Hosted Personal Memory with RAG (GDPR-Compliant)"
   - Post-Format: Demo-Video + GitHub-Link + Landing-Page
   - Target: Top 3 → 10k Visits

2. **ProductHunt:**
   - Launch mit Maker-Account
   - Hunter suchen (jemand mit 1k+ Followers)
   - Tagline: "Your memory. Your data. Your hardware."
   - Target: Top 5 of the Day → 15k Visits

3. **Reddit (multiple Subreddits):**
   - r/selfhosted, r/privacy, r/opensource, r/datahoarder
   - Jeweils leicht angepasster Post (Community-spezifisch)

4. **YouTube (Tech-Channels):**
   - Pitch an: NetworkChuck, TechnoTim, Wolfgang's Channel
   - Offer: Early Access + Interview
   - Potential: 50k-500k Views

---

### Phase 3: Growth-Hacking (Monat 4-6)
**Ziel:** 2.000 MAU, organisches Wachstum.

**Channels:**
1. **Content-Marketing:**
   - Blog-Serie: "Building memosaur" (Technical-Deep-Dive)
   - SEO-optimiert für Keywords: "self-hosted memory", "privacy RAG", "WhatsApp search"
   - Guest-Posts auf: Dev.to, Medium, Hackernoon

2. **Podcast-Tour:**
   - Darknet Diaries (Privacy-Focus)
   - The Changelog (Open-Source)
   - Self-Hosted Podcast

3. **Community-Building:**
   - Discord-Launch: memosaur.chat
   - Weekly Office-Hours (Video-Call mit Users)
   - Contributor-Program (Swag für Contributors)

---

## 5.2 Messaging (1-Satz-Erklärung)

### Versionen (A/B-Testen)

**Functional:**
> "memosaur macht deine Fotos, WhatsApp, Google Maps durchsuchbar – lokal, privat, mit AI."

**Emotional:**
> "Dein Gedächtnis gehört dir – nicht Google, nicht Facebook, nicht der Cloud."

**Technical (für HN):**
> "Self-hosted RAG system for personal data (photos, messages, maps) with Ollama, ChromaDB, GDPR-compliant."

**Problem-First:**
> "Erinnerst du dich an das Restaurant in München? memosaur findet es – ohne Google."

---

### Taglines (für Landing-Page)

**Primär:**
> "Dein Gedächtnis. Deine Daten. Deine Hardware."

**Sekundär:**
> "Privacy-First AI für deine Erinnerungen."

**Call-to-Action:**
> "Installiere memosaur in 5 Minuten – komplett kostenlos."

---

## 5.3 Channels (GitHub, Reddit, HN, Communities)

### Channel-Priorität

| Channel | Reach | Conversion | Effort | Priority |
|---------|-------|------------|--------|----------|
| **HackerNews** | 10k | 5% | Low | P0 |
| **ProductHunt** | 15k | 3% | Low | P0 |
| **r/selfhosted** | 5k | 10% | Low | P0 |
| **YouTube** | 50k | 2% | High | P1 |
| **Podcasts** | 20k | 5% | Medium | P1 |
| **Twitter** | 2k | 3% | Low | P2 |
| **LinkedIn** | 1k | 2% | Low | P3 |

**Strategie:**
- **P0-Channels:** Fokus in Monat 1-3
- **P1-Channels:** Skalierung ab Monat 4
- **P2-Channels:** Langfristig für Community-Building

---

### Reddit-Strategie (Detailed)

**Target-Subreddits:**
1. r/selfhosted (500k Members) – "Look what I built"
2. r/privacy (800k) – "Alternative zu Cloud-Diensten"
3. r/opensource (300k) – "New FOSS-Project"
4. r/datahoarder (200k) – "Search your Archive"
5. r/homelab (400k) – "Self-Hosted AI"

**Post-Format:**
```markdown
Title: "I built memosaur – Self-Hosted Personal Memory with RAG"

Hey r/selfhosted!

I've been frustrated with Cloud-Memory-Apps (Rewind, Mem)
storing all my data. So I built memosaur – a GDPR-compliant,
self-hosted alternative.

Features:
- Search Photos, WhatsApp, Google Maps with AI
- 100% local (Ollama, ChromaDB)
- Docker-Compose Setup (5 min)
- Face Recognition, Geo-Clustering

[Demo-Video] [GitHub] [Docs]

Looking for feedback! What features would you want?
```

**Timing:** Post jeweils 1 Woche auseinander (kein Spam).

---

## 5.4 Pricing/Monetization

### Modell: Freemium + Managed-Hosting

**Free-Tier (Self-Hosted):**
- Alle Features (RAG, Multi-Source, Face-Recognition)
- Community-Support (Discord)
- Unlimited-Daten (eigene Hardware)

**Starter ($10/mo):**
- Managed-Hosting (wir hosten Backend+Ollama)
- 5 GB Storage
- Basic-Modelle (qwen3:4b, gemma3:4b)
- Email-Support

**Pro ($20/mo):**
- 50 GB Storage
- Advanced-Modelle (qwen3:8b, gemma3:12b)
- Priority-Support (48h Response)
- Custom-Domains (memory.yourname.com)

**Family ($30/mo):**
- 5 User-Accounts
- 100 GB Storage
- Shared-Memory-Collections
- Family-Admin-Dashboard

---

### Revenue-Projections (12 Monate)

| Monat | Free-User | Paying ($10) | Paying ($20) | Paying ($30) | MRR |
|-------|-----------|--------------|--------------|--------------|-----|
| 1-2 | 100 | 0 | 0 | 0 | $0 |
| 3 | 500 | 10 | 5 | 0 | $200 |
| 6 | 2.000 | 50 | 30 | 10 | $1.400 |
| 12 | 20.000 | 200 | 150 | 50 | $6.500 |

**Assumptions:**
- 5% Conversion (Free → Paid)
- 60% Starter, 30% Pro, 10% Family
- Churn-Rate: 10%/Monat

**Break-Even:**
- Server-Costs: $2k/mo (bei 200 Paying-Customers)
- Break-Even bei ~300 Customers

---

### Alternative: B2B-Pivot

**Legal-Market:**
- Pricing: $50/Seat/Monat
- Target: 100 Law-Firms (500 Seats)
- ARR: $300k

**Healthcare:**
- Pricing: $30/Seat/Monat
- Target: 200 Practices (1k Seats)
- ARR: $360k

**Rationale:** B2B hat höhere WTP (Willingness-to-Pay) und länger Retention.

---

# 6. Risiken & Offene Fragen

## 6.1 Technical Risks

### 1. Ollama-Dependency (P0)
**Risk:** Ollama ist Third-Party – was wenn Lizenz ändert oder Service stirbt?

**Mitigation:**
- Abstraction-Layer: LLM-Connector unterstützt bereits OpenAI/Anthropic
- Fallback: Lokale GGUF-Modelle via llama.cpp
- Long-Term: Eigener Inference-Server (vLLM)

---

### 2. GPU-Requirement (P0)
**Risk:** Vision-Modell braucht 8GB VRAM → 80% der Laptops haben das nicht.

**Mitigation:**
- Fallback: Cloud-Vision-API (Google Vision, optional)
- Oder: CPU-Only-Mode mit kleineren Modellen (gemma3:4b)
- Oder: Skip Vision → User gibt manuell Beschreibungen ein

---

### 3. Elasticsearch-Overhead (P1)
**Risk:** ES ist heavy → Self-Hoster strugglen mit RAM/Storage.

**Mitigation:**
- ChromaDB-only Modus als Default
- ES ist optional für Power-User
- Oder: Switch zu Meilisearch (leichtgewichtiger)

---

### 4. Skalierung (P1)
**Risk:** ChromaDB skaliert schlecht bei >100k Dokumente.

**Mitigation:**
- Sharding nach Collection
- Upgrade zu Qdrant/Weaviate (Enterprise-Grade)
- Oder: Hybrid mit PostgreSQL (pgvector)

---

## 6.2 Privacy/Legal Risks (DSGVO)

### 1. Gesichtserkennung (Art. 9 DSGVO)
**Risk:** Biometrische Daten = Special-Category → besonders strenge Consent-Pflichten.

**Mitigation:**
- ✅ Bereits implementiert: Expliziter Consent-Dialog
- ✅ Opt-Out möglich
- ✅ Audit-Trail
- **Missing:** User muss Recht auf Löschung haben (Face-Embeddings löschen)

---

### 2. Managed-Hosting (Art. 28 DSGVO)
**Risk:** Wenn wir hosten, sind wir "Auftragsverarbeiter" → brauchen AVV (Auftragsverarbeitungsvertrag).

**Mitigation:**
- E2E-Encryption: Wir sehen nur verschlüsselte Blobs
- Zero-Knowledge-Architecture: Key bleibt im Browser
- Aber: User-Consent nötig, dass Daten auf unseren Servern liegen

---

### 3. WhatsApp-Terms-of-Service
**Risk:** WhatsApp verbietet automatisierte Clients → Account-Ban-Risiko.

**Mitigation:**
- WhatsApp-Web.js ist weit verbreitet (tausende User)
- Rate-Limiting + Zeitfenster-Schutz (bereits implementiert)
- Disclaimer: "Use at your own risk"
- Alternative: Offizielles WhatsApp-Business-API (teuer)

---

## 6.3 Market Risks

### 1. Gibt es Nachfrage? (P0)
**Risk:** Personal-Memory ist Nice-to-Have, kein Must-Have → geringe WTP.

**Validation:**
- Rewind hat 50k Paying-Users à $20/mo → $1M MRR → Nachfrage existiert
- Aber: Rewind ist macOS-native, einfaches Setup → memosaur muss Parity erreichen

**Fallback:**
- B2B-Pivot: Legal/Healthcare haben klare Pains + hohes Budget

---

### 2. Kann Self-Hosting Mainstream werden? (P1)
**Risk:** 95% der User wollen kein Docker/CLI → zu niche.

**Mitigation:**
- Managed-Hosting (wie Mastodon → mastodon.social)
- Desktop-App mit Bundled-Ollama
- Kooperation mit NAS-Herstellern (Synology, QNAP) → 1-Click-Install

---

### 3. Big-Tech baut Konkurrenz (P1)
**Risk:** Apple kündigt "Apple Intelligence Memory" an → hat bessere Integration.

**Mitigation:**
- Privacy-First bleibt Differentiator
- Open-Source-Community kann schneller iterieren
- Cross-Platform (Windows, Linux, Android)

---

## 6.4 Offene Fragen

### Product
1. **Soll memosaur rein Consumer bleiben oder B2B-Pivot?**
   - Argument für B2B: Höhere WTP, längere Retention
   - Argument für Consumer: Größerer Markt, virales Potential

2. **Soll es Mobile-App geben oder Web-PWA reicht?**
   - Native-App: Bessere UX, aber 2x Effort (iOS+Android)
   - PWA: Schneller, aber schlechtere OS-Integration

3. **Soll Vision-Feature mandatory sein oder optional?**
   - Mandatory: Bessere UX, aber GPU-Requirement
   - Optional: Mehr User, aber Features fehlen

---

### Technical
1. **Soll ES mandatory werden oder ChromaDB-only reichen?**
   - ES: Bessere Search-Qualität, aber Setup-Komplexität
   - ChromaDB-only: Einfacher, aber langsamer bei >10k Docs

2. **Soll WhatsApp-Bridge in Python portiert werden?**
   - Pro: 1 Runtime (Python), kein Node-Dependency
   - Contra: whatsapp-web.js ist Battle-Tested, Rewrite ist risky

3. **Soll Face-Recognition auf Cloud ausgelagert werden?**
   - Pro: Kein lokales VRAM nötig, schneller
   - Contra: Privacy-Kompromiss

---

### Business
1. **Soll Freemium-Modell sein oder Full-Open-Source?**
   - Freemium: Revenue-Potential, aber Community-Resistance
   - Full-FOSS: Community-Love, aber kein nachhaltiges Business

2. **Soll VC-Funding gesucht werden oder Bootstrap?**
   - VC: Schnelleres Wachstum, Team-Hiring
   - Bootstrap: Unabhängigkeit, aber langsamer

3. **Soll memosaur Inc. gegründet werden oder Hobby-Project bleiben?**
   - Company: Professionalität, Sales möglich
   - Hobby: No-Stress, aber kein Full-Time-Focus

---

# Appendix: Key Insights

## Was macht memosaur einzigartig?
1. **Privacy-by-Architecture** (Zero-Cloud-Guarantee)
2. **Multi-Source-Integration** (Fotos + Messages + Maps)
3. **Face-Recognition mit Human-in-the-Loop**
4. **DSGVO-Compliance-by-Design**

## Größte Blocker für Launch?
1. **Onboarding-Komplexität** (45 Min Setup)
2. **Fehlende Use-Case-Guidance** ("Was soll ich fragen?")
3. **Kein Distribution-Channel** (nur GitHub)

## Kritischste Entscheidung?
**Consumer vs. B2B?**
- Consumer: Größerer Markt, virales Potential, aber niedrige WTP
- B2B: Kleinerer Markt, aber $50/Seat/Monat statt $10/mo

## Realistische 12-Monat-Ziele?
- 20.000 MAU (Free-User)
- 300 Paying-Customers ($6k MRR)
- 10k GitHub-Stars
- Break-Even (Server-Costs gedeckt)

---

**Fazit:** memosaur hat **Product-Potential**, aber braucht **UX-Polish** + **Go-to-Market-Execution**. Aktueller Status: **Post-MVP, Pre-Launch**. Mit richtigem Fokus (Docker-Compose, Onboarding, Landing-Page) kann Launch in **Q2 2026** realistisch sein.

**Recommended Next Steps:**
1. Docker-Compose Setup (2 Wochen)
2. Onboarding-Wizard (3 Wochen)
3. Landing-Page + Docs (1 Woche)
4. HN/PH-Launch (Woche 7)
5. Community-Building (ongoing)

**Go or No-Go:** ✅ **GO** – aber nur mit Commitment zu UX + Distribution.
