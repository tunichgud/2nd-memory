# Installationsanleitung – memosaur

## Voraussetzungen

| Anforderung | Mindestversion | Empfohlen |
|---|---|---|
| Python | 3.10 | 3.11+ |
| Ollama | 0.6+ | aktuell |
| RAM | 8 GB | 16 GB |
| VRAM (GPU) | 8 GB | 16 GB |
| Speicherplatz | 5 GB | 20 GB |

> memosaur läuft vollständig lokal. Eine Internetverbindung wird nur für das
> erstmalige Herunterladen der Sprachmodelle und des Embedding-Modells benötigt.

---

## Schritt 1 – Ollama installieren

Ollama stellt die LLM-Modelle bereit.

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
# Text-Modell für Abfragen und Query-Parsing
ollama pull qwen3:8b

# Vision-Modell für Bildbeschreibungen
ollama pull gemma3:12b
```

> **Hinweis zu AMD-GPUs (RDNA 4):** Ollama benötigt ROCm 6.3+.
> Falls `ollama ps` die GPU nicht anzeigt, siehe
> [Ollama AMD-Dokumentation](https://ollama.com/blog/amd-preview).

> **VRAM-Hinweis:** `gemma3:12b` benötigt ~8 GB VRAM. Auf Systemen mit weniger
> VRAM empfiehlt sich `gemma3:4b` (~3 GB) als Vision-Modell.

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
# Windows:
.venv\Scripts\activate

# Abhängigkeiten installieren
pip install -r requirements.txt
```

> Das Embedding-Modell (`paraphrase-multilingual-MiniLM-L12-v2`, ~470 MB) wird
> beim ersten Start automatisch von HuggingFace heruntergeladen.

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
  model: "qwen3:8b"                   # Muss in Ollama installiert sein
  vision_model: "gemma3:12b"          # Muss in Ollama installiert sein
```

> Falls Ollama auf einem anderen Rechner läuft (z.B. Windows-Host, memosaur
> in WSL2), die IP-Adresse entsprechend anpassen.

---

## Schritt 5 – Google Takeout exportieren

1. [https://takeout.google.com](https://takeout.google.com) aufrufen
2. **Auswahl aufheben** → dann nur auswählen:
   - **Google Fotos** (alle Alben oder nur das gewünschte)
   - **Maps (Meine Orte)** (enthält Bewertungen und gespeicherte Orte)
3. Format: ZIP, Dateigröße: max. 2 GB
4. Export herunterladen

### Takeout entpacken

```bash
# ZIP-Archiv(e) in das takeout/-Verzeichnis legen:
mkdir -p takeout
# Entweder entpacken:
unzip 'takeout-*.zip' -d takeout/
# Oder ZIPs direkt im Ordner belassen – memosaur liest beide Formate
```

Die Struktur sollte so aussehen:
```
takeout/
├── Takeout/
│   ├── Google Fotos/
│   │   └── Fotos von 2025/
│   │       ├── 20250101_120006.jpg
│   │       ├── 20250101_120006.jpg.supplemental-metadata.json
│   │       └── ...
│   └── Maps (Meine Orte)/
│       ├── Bewertungen.json
│       └── Gespeicherte Orte.json
```

> Falls das Fotos-Jahr abweicht, `paths.photos_dir` in `config.yaml` anpassen.

---

## Schritt 6 – Server starten

```bash
# Mit dem Startskript (aktiviert venv automatisch):
./start.sh

# Oder manuell:
source .venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Browser öffnen: **[http://localhost:8000](http://localhost:8000)**

---

## Schritt 7 – Daten importieren

1. **Import-Tab** öffnen
2. **"Alles einlesen"** klicken

Der Import läuft in drei Phasen:
- **Bewertungen** (47 Einträge): ~30 Sekunden
- **Gespeicherte Orte** (210 Einträge): ~2 Minuten
- **Fotos** (50 Sample): ~15–25 Minuten
  - Pro Foto: Reverse Geocoding + Vision-Beschreibung + Embedding
  - Fortschritt im Server-Log sichtbar

Nach dem Import erscheint im **Datenbank-Status**:
```
49 Fotos · 47 Bewertungen · 210 Gespeicherte Orte
```

---

## Schritt 8 – Erste Abfrage

Im **Chat-Tab** eine Frage stellen:

```
Wo war ich im August?
Was habe ich letztes Jahr in München gegessen?
Welche Restaurants habe ich bewertet?
```

---

## Messenger-Daten hinzufügen (optional)

### WhatsApp

1. WhatsApp öffnen → Einstellungen → Chats → Chat exportieren → **Ohne Medien**
2. Die `.txt`-Datei im Import-Tab unter **"WhatsApp Export"** hochladen
3. Nachrichten werden automatisch in 10er-Chunks indexiert, Personen-Erwähnungen extrahiert

### Signal

1. Signal Desktop öffnen → Einstellungen → Chats → Chats exportieren
2. Die `messages.json` im Import-Tab unter **"Signal Export"** hochladen

---

## Fehlerbehebung

### GPU-Timeout beim Bildimport

**Symptom:** `model runner has unexpectedly stopped` im Log

**Ursachen/Lösungen:**
- VRAM reicht nicht: kleineres Vision-Modell verwenden (`gemma3:4b` statt `gemma3:12b`)
- `config.yaml` anpassen: `vision_model: "gemma3:4b"`
- Falls kein passendes Modell verfügbar: Vision in `photos.py` deaktivieren
  (Zeile `description = describe_image(image_bytes)` auskommentieren)

### Ollama nicht erreichbar

**Symptom:** `Connection refused` oder `404 Not Found`

**Lösung:**
```bash
# Ollama-Status prüfen
curl http://localhost:11434/api/tags

# Installierte Modelle prüfen
ollama list

# Ollama neu starten
ollama serve
```

### Modell nicht gefunden (404)

**Symptom:** `model "xyz" not found`

**Lösung:**
```bash
# Modell installieren
ollama pull qwen3:8b
ollama pull gemma3:12b

# In config.yaml anpassen falls anderes Modell genutzt werden soll
```

### Embedding-Modell wird jedes Mal neu geladen

Das Embedding-Modell wird beim ersten Aufruf von HuggingFace geladen und dann
lokal gecacht (`~/.cache/huggingface/`). Der erste Start dauert deshalb länger.

### Takeout-Pfade falsch

**Symptom:** `0 Fotos gefunden` oder `Bewertungen.json nicht gefunden`

**Lösung:** Pfade in `config.yaml` prüfen. Die exakten Pfadnamen im Takeout
können je nach Sprache und Export-Datum variieren:

```bash
# Tatsächliche Struktur anzeigen
find takeout/ -maxdepth 4 -type d
```

---

## Empfohlene Modelle nach Hardware

| VRAM | Text-Modell | Vision-Modell | Qualität |
|---|---|---|---|
| 4 GB | `qwen3:4b` | `gemma3:4b` | Gut |
| 8 GB | `qwen3:8b` | `gemma3:4b` | Sehr gut |
| 16 GB | `qwen3:8b` | `gemma3:12b` | Ausgezeichnet |
| 24 GB+ | `mistral-small3.2:24b` | `gemma3:12b` | Optimal |

> Die Modelle laufen **nicht gleichzeitig** – Vision wird nur beim Import
> benötigt, Text-LLM nur bei Abfragen.

---

## Systemanforderungen (Windows + WSL2)

Falls memosaur unter Windows in WSL2 läuft und Ollama auf dem Windows-Host:

1. Ollama auf Windows installieren und starten
2. Windows-IP aus WSL2 herausfinden:
   ```bash
   cat /etc/resolv.conf | grep nameserver | awk '{print $2}'
   ```
3. In `config.yaml` eintragen:
   ```yaml
   llm:
     base_url: "http://172.x.x.x:11434"
   ```
