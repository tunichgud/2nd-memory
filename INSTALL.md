# Installationsanleitung – memosaur v2

## Inhaltsverzeichnis

1. [Voraussetzungen](#voraussetzungen)
2. [Ollama installieren](#schritt-1--ollama-installieren)
3. [Repository klonen](#schritt-2--repository-klonen)
4. [Python-Umgebung](#schritt-3--python-umgebung-einrichten)
5. [Konfiguration](#schritt-4--konfiguration)
6. [Google Takeout exportieren](#schritt-5--google-takeout-exportieren)
7. [Server starten](#schritt-6--server-starten)
8. [Erster Start im Browser](#schritt-7--erster-start-im-browser)
9. [Daten importieren](#schritt-8--daten-importieren)
10. [Messenger-Daten (optional)](#messenger-daten-hinzufügen-optional)
11. [Migration von v1](#migration-von-v1-auf-v2)
12. [Fehlerbehebung](#fehlerbehebung)
13. [Modell-Empfehlungen](#empfohlene-modelle-nach-hardware)

---

## Voraussetzungen

| Anforderung | Mindestversion | Empfohlen |
|---|---|---|
| Python | 3.10 | 3.11+ |
| Ollama | 0.6+ | aktuell |
| RAM | 8 GB | 16 GB |
| VRAM (GPU) | 8 GB | 16 GB |
| Speicherplatz | 5 GB | 20 GB |
| Browser | Chrome 112+ / Firefox 115+ | aktuell |

> **Browser-Anforderung:** memosaur v2 verwendet moderne Web-Technologien wie IndexedDB
> und die Web Crypto API (Sync-Verschlüsselung). Diese Features sind in allen modernen
> Browsern verfügbar, aber nicht in sehr alten Versionen.

---

## Schritt 1 – Ollama installieren

Ollama stellt die LLM-Modelle lokal bereit.

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:** Installer von [https://ollama.com/download](https://ollama.com/download)

**macOS:**
```bash
brew install ollama
```

Nach der Installation Ollama starten:
```bash
ollama serve
```

### Benötigte Modelle laden

```bash
# Text-Modell für RAG-Abfragen und Query-Parsing (v0)
ollama pull qwen3:8b

# Vision-Modell für KI-Bildbeschreibungen
ollama pull gemma3:12b
```

> **Hinweis zu AMD-GPUs (RDNA 4 / RX 9070):** Ollama benötigt ROCm 6.3+.
> Falls `ollama ps` die GPU nicht erkennt, siehe
> [Ollama AMD-Dokumentation](https://ollama.com/blog/amd-preview).

> **VRAM-Hinweis:** `gemma3:12b` benötigt ~8 GB VRAM.
> Auf Systemen mit weniger VRAM: `gemma3:4b` (~3 GB) als Vision-Modell nutzen.
> Die Modelle laufen **nicht gleichzeitig** (Vision nur beim Import, Chat-Modell nur bei Abfragen).

---

## Schritt 2 – Repository klonen

```bash
git clone https://github.com/tunichgud/memosaur.git
cd memosaur
```

---

## Schritt 3 – Python-Umgebung einrichten

```bash
# Virtuelle Umgebung erstellen
python3 -m venv .venv

# Aktivieren
# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Abhängigkeiten installieren
pip install -r requirements.txt
```

> **Beim ersten Start** wird ein Modell automatisch heruntergeladen:
> - Python-Backend: `paraphrase-multilingual-MiniLM-L12-v2` (~470 MB, von HuggingFace)
>
> Das Modell wird lokal gecacht und nur einmalig geladen.

---

## Schritt 4 – Konfiguration

```bash
cp config.yaml.example config.yaml
```

`config.yaml` öffnen und anpassen:

```yaml
llm:
  provider: ollama
  base_url: "http://localhost:11434"  # Ollama-Adresse
  model: "qwen3:8b"                   # Text-Modell
  vision_model: "gemma3:12b"          # Vision-Modell
```

> **Ollama auf einem anderen Rechner** (z.B. Windows-Host, memosaur in WSL2):
> Die IP-Adresse aus WSL2 herausfinden:
> ```bash
> cat /etc/resolv.conf | grep nameserver
> ```
> Dann in `config.yaml` eintragen:
> ```yaml
> base_url: "http://172.x.x.x:11434"
> ```

---

## Schritt 5 – Google Takeout exportieren

1. [https://takeout.google.com](https://takeout.google.com) aufrufen
2. **"Auswahl aufheben"** → dann **nur** auswählen:
   - **Google Fotos** (alle Alben oder ein bestimmtes Jahr)
   - **Maps (Meine Orte)** (enthält Bewertungen und gespeicherte Orte)
3. Format: ZIP, Dateigröße: max. 2 GB pro Datei
4. Export herunterladen (kann einige Stunden dauern, Google schickt eine E-Mail)

### Takeout ablegen

```bash
# ZIP-Archiv(e) in das takeout/-Verzeichnis legen:
mkdir -p takeout

# Option A: Entpacken
unzip 'takeout-*.zip' -d takeout/

# Option B: ZIPs direkt im Ordner lassen
# memosaur liest beide Formate automatisch
cp takeout-*.zip takeout/
```

Erwartete Verzeichnisstruktur nach dem Entpacken:
```
takeout/
└── Takeout/
    ├── Google Fotos/
    │   └── Fotos von 2025/
    │       ├── 20250101_120006.jpg
    │       ├── 20250101_120006.jpg.supplemental-metadata.json
    │       └── ...
    └── Maps (Meine Orte)/
        ├── Bewertungen.json
        └── Gespeicherte Orte.json
```

> Falls das Fotos-Verzeichnis ein anderes Jahr enthält, `paths.photos_dir` in `config.yaml` anpassen:
> ```yaml
> paths:
>   photos_dir: "takeout/Takeout/Google Fotos/Fotos von 2024"
> ```

---

## Schritt 6 – Server starten

```bash
# Mit dem Startskript (richtet venv ein falls nötig):
./start.sh

# Oder manuell:
source .venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --app-dir .
```

Der Server gibt beim Start folgendes aus:
```
Initialisiere SQLite-Datenbank: data/memosaur.db
Default-User 'ManfredMustermann' angelegt (ID: 00000000-...)
memosaur v2 gestartet.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## Schritt 7 – Erster Start im Browser

Browser öffnen: **[http://localhost:8000](http://localhost:8000)**

Beim ersten Besuch läuft folgende Sequenz automatisch ab:

### 1. Initialisierung
Die App lädt notwendige Komponenten aus der lokalen Datenbank.

### 2. DSGVO-Einwilligungsdialog
Beim allerersten Start erscheint ein Dialog für die Einwilligungen nach Art. 9 DSGVO:

| Feature | Was wird verarbeitet |
|---|---|
| **Fotos & KI-Bilderkennung** | Bilder werden an Ollama (lokal) gesendet für die Analyse (GPS, Personen, Beschreibungen). |
| **GPS-Standortdaten** | GPS-Koordinaten gehen an OpenStreetMap/Nominatim für Reverse Geocoding. |
| **Nachrichten** | Chat-Texte werden lokal indexiert, um sie für dich durchsuchbar zu machen. |

Ohne Einwilligung sind die jeweiligen Features deaktiviert. Die Einstellung kann jederzeit im **Einstellungen-Tab** geändert werden.

---

## Schritt 8 – Daten importieren

Im **Import-Tab** die gewünschten Quellen einlesen:

### Google Fotos + Maps (empfohlen als Einstieg)

Klick auf **"Alles einlesen"** startet den Import in drei Phasen:

| Phase | Dauer (ca.) | Hinweis |
|---|---|---|
| Bewertungen (47 Einträge) | ~30 Sek. | Nur Embeddings, kein LLM |
| Gespeicherte Orte (210 Einträge) | ~2 Min. | Nur Embeddings, kein LLM |
| 50 Sample-Fotos | ~15–25 Min. | Vision-LLM + Reverse Geocoding pro Foto |

> **Foto-Ingestion via v2-API (mit Consent):**
> Jedes Foto durchläuft:
> 1. Server ruft Ollama Vision auf → generiert Bildbeschreibung.
> 2. Geocoding-Service ermittelt den Ortsnamen aus den Koordinaten.
> 3. Gesichtserkennungs-Modul erkennt Personen-Cluster.
> 4. Alle Daten werden in der lokalen Vektordatenbank (ChromaDB/Elasticsearch) gespeichert.

Nach dem Import zeigt der **Datenbank-Status**:
```
49 Fotos  ·  47 Bewertungen  ·  210 Gespeicherte Orte
```

### Erste Abfrage

Im **Chat-Tab** eine Frage stellen:
```
Wo war ich im August?
Welche Restaurants habe ich bewertet?
Wo habe ich im September Fotos gemacht?
```

---

## Messenger-Daten hinzufügen (optional)

Messenger-Daten benötigen die Einwilligung **"Nachrichten"** im Consent-Dialog.

### WhatsApp

1. WhatsApp → Einstellungen → Chats → Chat exportieren → **Ohne Medien**
2. Die `.txt`-Datei im **Import-Tab** unter "WhatsApp Export" hochladen
3. Nachrichten werden in 10er-Chunks indexiert, erwähnte Personen erkannt

### Signal

1. Signal Desktop → Einstellungen → Chats → Chats exportieren
2. Die `messages.json` im **Import-Tab** unter "Signal Export" hochladen

---

## WhatsApp Live-Brücke (Experimental)

Memosaur kann live auf WhatsApp-Nachrichten reagieren:

1. Node.js (v18+) auf dem Server installieren.
2. Abhängigkeiten installieren: `npm install`
3. Backend starten: `./start.sh`
4. Brücke starten: `npm run whatsapp`
5. QR-Code im Terminal mit WhatsApp scannen (WhatsApp → Verknüpfte Geräte).
6. Memosaur antwortet nun live auf eingehende Nachrichten!

---

---

## Fehlerbehebung

**Symptom:** `model runner has unexpectedly stopped` im Server-Log

**Ursachen/Lösungen:**
- VRAM zu knapp: kleineres Vision-Modell verwenden
  ```yaml
  # config.yaml
  vision_model: "gemma3:4b"   # statt gemma3:12b
  ```
- AMD GPU: ROCm-Version prüfen (`rocm-smi --version`), mindestens 6.3 nötig
- Bild-Resize ist aktiv (max. 768px), aber bei sehr vielen gleichzeitigen Anfragen trotzdem Timeout → `vision_batch_size: 1` in config.yaml sicherstellen

### Ollama nicht erreichbar

**Symptom:** `Connection refused` oder `404 Not Found` im Log

```bash
# Status prüfen
curl http://localhost:11434/api/tags

# Modelle prüfen
ollama list

# Neu starten
ollama serve
```

### Modell nicht gefunden (404)

```bash
ollama pull qwen3:8b
ollama pull gemma3:12b

# Oder alternatives Modell in config.yaml eintragen
```

### Takeout-Pfade nicht gefunden

```bash
# Tatsächliche Struktur prüfen
find takeout/ -maxdepth 4 -type d

# Pfad in config.yaml anpassen falls nötig
# z.B. bei englischsprachigem Takeout:
#   photos_dir: "takeout/Takeout/Google Photos/Photos from 2025"
```

---

## Empfohlene Modelle nach Hardware

| VRAM | Chat-Modell | Vision-Modell | Qualität |
|---|---|---|---|
| 4 GB | `qwen3:4b` | `gemma3:4b` | Gut |
| 8 GB | `qwen3:8b` | `gemma3:4b` | Sehr gut |
| 16 GB | `qwen3:8b` | `gemma3:12b` | Ausgezeichnet |
| 24 GB+ | `mistral-small3.2:24b` | `gemma3:12b` | Optimal |

> Die Modelle laufen **nie gleichzeitig**: Vision wird nur beim Foto-Import verwendet,
> das Chat-Modell nur bei Abfragen und Query-Parsing (v0). Bei 16 GB VRAM
> (z.B. Radeon RX 9070) läuft `gemma3:12b` + `qwen3:8b` komfortabel abwechselnd.

---

## Konsolendiagnose (Browser)

Nützliche Befehle in der Browser-Konsole (F12):

```javascript
// Consent-Status prüfen
fetch('/api/v1/consent/00000000-0000-0000-0000-000000000001')
  .then(r => r.json()).then(console.log)
```

