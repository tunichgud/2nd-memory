# 🛠️ 2nd Memory Tools

Wartungs- und Debug-Skripte für 2nd Memory.

## 📁 Übersicht

### **Gesichtserkennung & Validierung**

#### `migrate_ground_truth.py`
**Problem:** Personen erscheinen in Statistiken, aber nicht in der Personen-Liste

**Lösung:** Migriert alte Validierungen aus Ground-Truth-JSON nach ChromaDB/Elasticsearch

**Verwendung:**
```bash
python tools/migrate_ground_truth.py
```

**Was es tut:**
- Liest `data/ground_truth/validated_clusters.json`
- Schreibt `entity_id` in ChromaDB für alle Face-IDs
- Erstellt Elasticsearch-Einträge
- Zeigt Zusammenfassung: "Anna: 123 Gesichter, Marie: 45 Gesichter..."

**Alternative:** Nutze den UI-Button "🔧 Daten reparieren" im Validierungs-Tab

---

#### `check_face_assignments.py`
**Zweck:** Debug-Tool für Gesichtszuordnungen

**Verwendung:**
```bash
# Alle Gesichter prüfen
python tools/check_face_assignments.py

# Nur erste 100 prüfen
python tools/check_face_assignments.py --limit 100

# Mit Details
python tools/check_face_assignments.py --details
```

**Output:**
```
📊 GESICHTSZUORDNUNGEN - ÜBERSICHT
======================================================================
Total Gesichter:     1141
✅ Zugeordnet:       500 (43.8%)
❌ Unzugeordnet:     641 (56.2%)
👥 Verschiedene Personen: 8
======================================================================

🏆 TOP PERSONEN (nach Anzahl Gesichter):
----------------------------------------------------------------------
 1. Anna                   123 Gesichter  ████████████████████████
 2. Marie                   89 Gesichter  ██████████████████
 3. Monika, Leon           67 Gesichter  ██████████████
...
```

---

### **Daten-Ingestion**

#### `ingest_500.py` / `ingest_next_100.py`
Importiert Fotos in Batches

#### `import_whatsapp_cli.py`
WhatsApp-Chat-Import via CLI

#### `sync_to_es.py`
Synchronisiert ChromaDB → Elasticsearch

---

### **Testing & Debugging**

#### `inspect_chroma.py`
Inspiziert ChromaDB Collections

#### `test_agentic_rag.py`
Testet RAG-Agenten

#### `test_embedding_opt.py`
Testet Embedding-Optimierungen

#### `test_stream.py`
Testet Streaming-Funktionalität

---

## 🚀 Häufige Anwendungsfälle

### **Problem: "Anna fehlt in der Personen-Liste"**
```bash
python tools/migrate_ground_truth.py
```

### **Problem: "Wie viele Gesichter sind zugeordnet?"**
```bash
python tools/check_face_assignments.py
```

### **Problem: "Welche Personen habe ich?"**
```bash
python tools/check_face_assignments.py | grep "TOP PERSONEN" -A 20
```

### **Problem: "Cluster zu groß / zu klein"**
1. Editiere `config.yaml`:
   ```yaml
   face_recognition:
     dbscan_eps: 0.28  # Niedriger = strengeres Clustering
   ```
2. Backend neu starten
3. Personen-Tab → "Aktualisieren"

---

## 📝 Hinweise

- **Alle Skripte aus dem Root-Verzeichnis ausführen:**
  ```bash
  cd /path/to/2nd-memory
  python tools/script_name.py
  ```

- **Backup vor Wartung:**
  ```bash
  cp -r data/chroma data/chroma.backup
  cp -r data/ground_truth data/ground_truth.backup
  ```

- **Logs aktivieren:**
  Die meisten Skripte nutzen Python's `logging`. Für mehr Details:
  ```bash
  export LOG_LEVEL=DEBUG
  python tools/script_name.py
  ```

---

## 🐛 Fehlerbehebung

**"ModuleNotFoundError: No module named 'backend'"**
→ Aus dem Root-Verzeichnis ausführen, nicht aus `tools/`

**"Ground Truth Datei nicht gefunden"**
→ Noch keine Validierungen durchgeführt. Gehe zu Validierungs-Tab und validiere Cluster.

**"Elasticsearch nicht erreichbar"**
→ Prüfe ob Elasticsearch läuft: `curl localhost:9200`

---

Für weitere Hilfe: Siehe Hauptdokumentation in `TECHNICAL.md`
