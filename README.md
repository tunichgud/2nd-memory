# memosaur 🦕

**Persönliches Gedächtnis-System** – vereint Fotos, Nachrichten und Geodaten zu einer durchsuchbaren Wissensbasis, die du per natürlicher Sprache abfragen kannst.

---

## Was ist memosaur?

memosaur ist eine lokal laufende KI-Anwendung, die deine persönlichen Daten aus verschiedenen Quellen zusammenführt und durch intelligente Abfragen zugänglich macht. Alle Daten bleiben auf deinem Rechner – keine Cloud, keine Datenweitergabe.

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

### Intelligente Suche
- **Query-Parsing**: Erkennt automatisch Personennamen, Zeiträume und Orte aus natürlichsprachigen Fragen
- **Strukturierte Filter**: Personen-Tags aus Fotos und Nachrichteninhalten werden kombiniert – „mit Nora" filtert nur Fotos, auf denen Nora wirklich zu sehen ist
- **Quellenübergreifend**: Eine Frage wird gleichzeitig gegen alle Datenquellen gesucht

### Quellen-Transparenz
- Jede Antwort zeigt die verwendeten Quellen mit konkretem Beleg:
  - **Fotos**: Thumbnail direkt in der Quellenangabe, Datum, Ort, beteiligte Personen
  - **Nachrichten**: Chat-Verlauf als Blasen-Ansicht, Zeitstempel sichtbar
  - **Bewertungen**: Rezensionstext als Blockquote, Sternebewertung
- Klick auf ein Foto-Thumbnail öffnet die Vollbildansicht (Lightbox)

### Kartenansicht
- Alle indexierten GPS-Punkte auf einer interaktiven Karte (Leaflet.js / OpenStreetMap)
- Farbkodiert nach Quellentyp: Fotos (blau), Bewertungen (grün), Gespeicherte Orte (amber)
- Filter nach Quelle und Zeitraum

### Privatsphäre
- Vollständig lokal: Daten verlassen den Rechner nicht
- Kein Account, keine Cloud-Synchronisation
- Optional: Cloud-LLM (OpenAI/Anthropic) für bessere Antwortqualität

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

# 5. Browser öffnen
open http://localhost:8000
```

Detaillierte Anleitung: [INSTALL.md](INSTALL.md)

---

## Datenexporte beschaffen

### Google Takeout
1. [https://takeout.google.com](https://takeout.google.com) öffnen
2. Nur auswählen: **Google Fotos**, **Maps (Meine Orte)**
3. Export herunterladen und in `takeout/` entpacken

### WhatsApp
- Android/iOS: Einstellungen → Chats → Chat exportieren → Ohne Medien
- Die `.txt`-Datei im **Import**-Tab hochladen

### Signal
- Signal Desktop: Einstellungen → Chats → Chats exportieren
- Die `messages.json` im **Import**-Tab hochladen

---

## Technologie

- **Backend**: Python, FastAPI, ChromaDB, sentence-transformers
- **LLM**: Ollama (lokal) oder OpenAI/Anthropic (optional)
- **Frontend**: HTML, Tailwind CSS, Leaflet.js
- **Geodaten**: Nominatim/OpenStreetMap für Reverse Geocoding

Ausführliche technische Dokumentation: [TECHNICAL.md](TECHNICAL.md)

---

## Lizenz

Siehe [LICENSE](LICENSE).
