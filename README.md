# memosaur 🦕

**Privacy-First Persönliches Gedächtnis-System** – vereint Fotos, Nachrichten und Geodaten zu einer durchsuchbaren Wissensbasis, die du per natürlicher Sprache abfragen kannst. Alle persönlichen Namen und Orte werden vor dem Server maskiert und erst im Browser wieder lesbar gemacht.

---

## Was ist memosaur?

memosaur ist eine lokal laufende KI-Anwendung, die deine persönlichen Daten aus verschiedenen Quellen zusammenführt und durch intelligente Abfragen zugänglich macht.

**Das Besondere:** Personennamen und Ortsnamen verlassen deinen Browser nur als anonyme Tokens (`[PER_1]`, `[LOC_2]`). Die eigentliche Zuordnung liegt ausschließlich in deiner lokalen Browser-Datenbank (IndexedDB). Der Server sieht und speichert niemals Klarnamen.

**Typische Abfragen:**

- *„Wo war ich im August mit Nora?"*
- *„Welche Restaurants habe ich in München besucht?"*
- *„Was hat Sarah über Nora geschrieben?"*
- *„Wo habe ich die Dorade gegessen?"*

---

## Unterstützte Datenquellen

| Quelle | Format | Was wird indexiert |
|---|---|---|
| **Google Fotos** | Google Takeout (ZIP/Ordner) | GPS-Koordinaten, Datum, Personen-Tags, KI-Bildbeschreibung |
| **Google Maps Bewertungen** | Google Takeout JSON | Ortsname, Adresse, Sternebewertung, Rezensionstext |
| **Google Maps Gespeicherte Orte** | Google Takeout JSON | Name, Adresse, Koordinaten |
| **WhatsApp** | Chat-Export (.txt) | Nachrichten, Absender, erwähnte Personen |
| **Signal** | Desktop-Export (.json) | Nachrichten, Absender, erwähnte Personen |

---

## Funktionen

### Privacy-First Token-Flow (v2)
- **Client-seitige NER**: Ein KI-Modell (~90 MB) läuft direkt im Browser via WebAssembly. Es erkennt Personen, Orte und Organisationen lokal – ohne Serveranfrage.
- **Automatische Maskierung**: Vor jeder Anfrage an den Server werden Klarnamen durch Tokens ersetzt (`Nora` → `[PER_1]`, `München` → `[LOC_11]`).
- **Lokales Wörterbuch**: Das Token↔Klarname-Mapping wird ausschließlich in der Browser-eigenen IndexedDB gespeichert.
- **Re-Mapping im Browser**: Antworten des Servers enthalten nur Tokens. Das Frontend ersetzt sie vor der Anzeige automatisch durch Klarnamen.

### Intelligente Suche
- **Strukturierte Filter**: NER-Ergebnisse aus der Anfrage werden direkt als ChromaDB-Filter genutzt – `[PER_1]` filtert exakt die Einträge mit diesem Token.
- **Quellenübergreifend**: Eine Frage wird gleichzeitig gegen Fotos, Nachrichten, Bewertungen und gespeicherte Orte gesucht.
- **Adaptive Slot-Vergabe**: Relevante Collections bekommen mehr Ergebnis-Slots als irrelevante.

### DSGVO-Einwilligungen (Art. 9)
- Beim ersten Start erscheint ein Consent-Dialog.
- **Fotos & KI**: Opt-in erforderlich (Bilder werden an Ollama-Vision gesendet, Beschreibungen im Browser maskiert).
- **GPS-Daten**: Separates Opt-in (Koordinaten gehen an Nominatim/OpenStreetMap für Reverse Geocoding).
- **Nachrichten**: Separates Opt-in (Text wird vor dem Upload im Browser maskiert).
- Ohne Einwilligung sind die jeweiligen Features deaktiviert.

### Quellen-Transparenz
- Jede Antwort zeigt die verwendeten Quellen direkt:
  - **Fotos**: Thumbnail, Datum, Ort, Personen, erste Zeilen der KI-Beschreibung – klickbar für Vollbild (Lightbox)
  - **Bewertungen**: Sterne, Adresse, Rezensionstext als Blockquote
  - **Nachrichten**: Chat-Blasen-Ansicht mit Zeitstempeln, scrollbar
  - **Gespeicherte Orte**: Adresse, Google Maps Link

### Multi-Device Sync (v2)
- Das Token-Wörterbuch kann verschlüsselt auf dem Server gespeichert werden.
- Verschlüsselung: `PBKDF2 → AES-256-GCM` direkt im Browser (Web Crypto API).
- Das Passwort verlässt niemals den Browser.
- Auf einem zweiten Gerät: Blob herunterladen, entschlüsseln, Wörterbuch ist sofort verfügbar.

### Kartenansicht
- Alle indexierten GPS-Punkte auf einer interaktiven Karte (Leaflet.js / OpenStreetMap)
- Farbkodiert nach Quellentyp: Fotos (blau), Bewertungen (grün), Gespeicherte Orte (amber)
- Filter nach Quelle und Zeitraum

### Multi-User vorbereitet
- SQLite-Datenbank mit User-Tabelle, Consent-Audit-Trail und Sync-Blob-Versionierung
- Alle ChromaDB-Dokumente sind mit `user_id` versehen
- Aktuell: ein Default-User `ManfredMustermann`, weitere können per API angelegt werden

---

## Architektur (Überblick)

```
        BROWSER                              SERVER
           │                                   │
  Anfrage: "Wo war ich mit Nora?"              │
           │                                   │
    NER lokal (WASM)                           │
    Nora → [PER_1]                             │
           │                                   │
    ──── POST /api/v1/query ──────────────────►│
         {masked_query: "mit [PER_1]",         │
          person_tokens: ["[PER_1]"]}          │
                                               │
                              embed + retrieve │
                              LLM antwortet    │
                              mit Tokens       │
                                               │
    ◄──── {masked_answer: "...mit [PER_1]..."} │
           │                                   │
    IndexedDB: [PER_1] → "Nora"               │
           │                                   │
    Anzeige: "...mit Nora..."                  │
```

---

## Schnellstart

```bash
# 1. Repository klonen
git clone https://github.com/tunichgud/memosaur.git
cd memosaur

# 2. Konfiguration anpassen
cp config.yaml.example config.yaml
# config.yaml öffnen und Ollama-URL eintragen

# 3. Google Takeout exportieren und in takeout/ entpacken

# 4. Server starten
./start.sh

# 5. Browser öffnen – NER-Modell lädt beim ersten Besuch (~90 MB, einmalig)
open http://localhost:8000
```

Detaillierte Anleitung: [INSTALL.md](INSTALL.md)

---

## Datenexporte beschaffen

### Google Takeout
1. [https://takeout.google.com](https://takeout.google.com) öffnen
2. Nur auswählen: **Google Fotos**, **Maps (Meine Orte)**
3. Export herunterladen und in `takeout/` entpacken (oder als ZIP belassen)

### WhatsApp
- Android/iOS: Einstellungen → Chats → Chat exportieren → **Ohne Medien**
- Die `.txt`-Datei im **Import**-Tab hochladen (Text wird vor dem Upload im Browser maskiert)

### Signal
- Signal Desktop: Einstellungen → Chats → Chats exportieren
- Die `messages.json` im **Import**-Tab hochladen

---

## Technologie

| Schicht | Technologie |
|---|---|
| Backend | Python, FastAPI, uvicorn |
| Vektordatenbank | ChromaDB (lokal, persistent) |
| Embeddings | sentence-transformers (lokal, multilingual) |
| LLM | Ollama (`qwen3:8b` Chat, `gemma3:12b` Vision) |
| Relationale DB | SQLite via aiosqlite (User, Consent, Sync) |
| NER im Browser | Transformers.js WASM (`bert-base-multilingual`) |
| Token-Speicher | IndexedDB (Browser-lokal) |
| Verschlüsselung | Web Crypto API (AES-256-GCM, PBKDF2) |
| Geodaten | Nominatim/OpenStreetMap (Reverse Geocoding) |
| Frontend | HTML, Tailwind CSS CDN, Leaflet.js |

Ausführliche technische Dokumentation: [TECHNICAL.md](TECHNICAL.md)

---

## Lizenz

Siehe [LICENSE](LICENSE).
