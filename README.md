# memosaur 🦕

**Privacy-First Persönliches Gedächtnis-System** – vereint Fotos, Nachrichten und Geodaten zu einer durchsuchbaren Wissensbasis, die du per natürlicher Sprache abfragen kannst. Alle persönlichen Daten werden lokal verarbeitet und verbleiben in deiner eigenen Infrastruktur.

> **🚀 Neu hier?** Starte mit der [SETUP.md](SETUP.md) für eine vollständige Installations- und Konfigurationsanleitung.

---

## Was ist memosaur?

memosaur ist eine lokal laufende KI-Anwendung, die deine persönlichen Daten aus verschiedenen Quellen zusammenführt und durch intelligente Abfragen zugänglich macht.

**Das Besondere:** Alle Daten bleiben lokal. Die gesamte Anwendung – Backend, Vektordatenbank und LLM – läuft auf deiner eigenen Hardware. Personennamen und Orte werden durch integrierte Entity-Resolution erkannt und verknüpft.

**Typische Abfragen:**

- „Wo war ich im August mit Nora?"
- „Welche Restaurants habe ich in München besucht?"
- „Was hat Sarah über Nora geschrieben?"
- „Wo habe ich die Dorade gegessen?"

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

### Privacy-First Entity-Flow
- **Lokale Verarbeitung**: Alle Daten werden lokal auf deiner Hardware verarbeitet – kein Cloud-Server sieht deine Inhalte.
- **Entity-Resolution**: Das Mapping zwischen Gesichtern, Chat-Namen und Orten wird in einer lokalen SQLite-Datenbank gespeichert.
- **Transparenz**: Jede Information wird mit ihrer Originalquelle verknüpft, sodass du immer nachvollziehen kannst, woher ein Gedächtnis-Splitter stammt.

### Intelligente Suche
- **Strukturierte Filter**: Ergebnisse werden direkt nach Personen, Orten oder Zeiträumen gefiltert.
- **Quellenübergreifend**: Eine Frage wird gleichzeitig gegen Fotos, Nachrichten, Bewertungen und gespeicherte Orte gesucht.
- **Adaptive Agenten**: Ein KI-Agent plant die Suche (z.B. erst Ort finden, dann Nachrichten aus dem Zeitraum laden).

### Quellen-Transparenz
- Jede Antwort zeigt die verwendeten Quellen direkt:
  - **Fotos**: Thumbnail, Datum, Ort, Personen, erste Zeilen der KI-Beschreibung – klickbar für Vollbild (Lightbox)
  - **Bewertungen**: Sterne, Adresse, Rezensionstext als Blockquote
  - **Nachrichten**: Chat-Blasen-Ansicht mit Zeitstempeln, scrollbar
  - **Gespeicherte Orte**: Adresse, Google Maps Link

### Kartenansicht
- Alle indexierten GPS-Punkte auf einer interaktiven Karte (Leaflet.js / OpenStreetMap)
- Farbkodiert nach Quellentyp: Fotos (blau), Bewertungen (grün), Gespeicherte Orte (amber)
- Filter nach Quelle und Zeitraum

### Multi-User vorbereitet
- SQLite-Datenbank mit User-Tabelle
- Alle Dokumente sind mit `user_id` versehen
- Aktuell: ein Default-User `ManfredMustermann`, weitere können per API angelegt werden

---

## Architektur (Überblick)

```
        BROWSER                              SERVER
           │                                   │
  Anfrage: "Wo war ich mit Nora?"              │
           │                                   │
           ├──────────────────────────────────►│
           │        POST /api/v1/query         │
           │                                   │
           │                          Agent plant Suche
           │                          (Retriever/Tools)
           │                                   │
           │◄──────────────────────────────────┤
           │           Antwort & Quellen       │
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

**📖 Detaillierte Anleitung**: [SETUP.md](SETUP.md) (Installation, Troubleshooting)

---

## Datenexporte beschaffen

### Google Takeout
1. [https://takeout.google.com](https://takeout.google.com) öffnen
2. Nur auswählen: **Google Fotos**, **Maps (Meine Orte)**
3. Export herunterladen und in `takeout/` entpacken (oder als ZIP belassen)

### WhatsApp
- Android/iOS: Einstellungen → Chats → Chat exportieren → **Ohne Medien**
- Die `.txt`-Datei im **Import**-Tab hochladen (Texte werden lokal indexiert)

### Signal
- Signal Desktop: Einstellungen → Chats → Chats exportieren
- Die `messages.json` im **Import**-Tab hochladen

---

## Technologie

| Schicht | Technologie |
|---|---|
| Backend | Python, FastAPI, uvicorn |
| Vektordatenbank | ChromaDB / Elasticsearch (lokal, persistent) |
| Embeddings | sentence-transformers (lokal, multilingual) |
| LLM | Ollama (`qwen3:8b` Chat, `gemma3:12b` Vision) |
| Relationale DB | SQLite via aiosqlite (User) |
| Karten | Leaflet.js / OpenStreetMap |
| Geodaten | Nominatim/OpenStreetMap (Reverse Geocoding) |
| Frontend | HTML, Tailwind CSS CDN |

Ausführliche technische Dokumentation: [TECHNICAL.md](TECHNICAL.md)

---

## Lizenz

Siehe [LICENSE](LICENSE).
