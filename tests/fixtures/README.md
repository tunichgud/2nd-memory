# Test Fixtures für Face Recognition

## Verzeichnisstruktur

```
fixtures/
├── faces/                    # Test-Bilder mit Gesichtern
│   ├── person_A/            # Gesichter von Person A
│   ├── person_B/            # Gesichter von Person B
│   └── person_C/            # Gesichter von Person C
├── baseline_metrics.json    # Baseline-Metriken
└── ground_truth.json        # Ground Truth aus Validierungs-UI
```

## Ground Truth Format

```json
{
  "person_A": {
    "entity_id": "PER_1",
    "face_ids": ["photo1_face_0", "photo2_face_1", "photo5_face_0"]
  },
  "person_B": {
    "entity_id": "PER_2",
    "face_ids": ["photo3_face_0", "photo4_face_1"]
  }
}
```

## Hinweise

- **Aktuell**: Tests verwenden synthetische Mock-Daten
- **Sprint 2 Ziel**: Echte Ground Truth aus Validierungs-UI integrieren
- **Test-Bilder**: Können in `faces/` abgelegt werden für reale Tests
- **Privacy**: KEINE echten Fotos committen! `.gitignore` beachten
