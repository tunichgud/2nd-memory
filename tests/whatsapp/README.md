# WhatsApp Tests

Dieses Verzeichnis enthält Unit-Tests für die WhatsApp-Integration von Memosaur.

## Tests

### test_chat_routing.js

**Regressionstest für kritischen Chat-Routing Bug-Fix**

**Kontext:**
- **Bug**: Memosaur hat in fremde WhatsApp-Chats geantwortet (z.B. an Sarah), wenn der User dort eine eigene Nachricht geschrieben hat.
- **Root Cause**: Bei `fromMe: true` gibt WhatsApp `msg.from` als eigene Telefonnummer zurück — unabhängig vom Chat. Die alte Sicherheitsprüfung hat daher fälschlicherweise eigene Nachrichten in Fremdchats durchgelassen.
- **Fix**: In `index.js` Zeilen 150–157 wird jetzt `msg.to` für ausgehende und `msg.from` für eingehende Nachrichten verwendet.

**Getestete Szenarien:**
1. Eingehende Nachricht im eigenen Chat → verarbeiten
2. Eingehende Nachricht in Fremd-Chat → ignorieren
3. Eigene Nachricht im eigenen Chat → verarbeiten
4. **Eigene Nachricht im Fremd-Chat → IGNORIEREN** (Kern-Regressionstest)
5. Edge Cases: undefined/null `msg.to`
6. Gruppenchats (verschiedene ID-Formate)
7. Komplexe Szenarien mit gemischten Nachrichten
8. Direkter Vergleich alte vs. neue Logik

**Ausführung:**
```bash
node tests/whatsapp/test_chat_routing.js
```

**Erwartetes Ergebnis:**
```
Ergebnis: 22 Tests bestanden, 0 Tests fehlgeschlagen
✅ ERFOLG: Alle Tests bestanden!
```

### test_send_guard.js

**Acceptance Test für den WhatsApp Send-Guard**

**Kontext:**
- **Bug**: Der `/api/whatsapp/send` Endpoint akzeptierte beliebige `chatId`-Werte — keine Prüfung ob der Empfänger der eigene Chat ist.
- **Fix**: `assertSendAllowed(chatId, config)` wird vor jedem `sendMessage()` aufgerufen und wirft einen `Error` wenn `chatId !== user_chat_id`.
- **HTTP**: Der Endpoint gibt `403` (nicht `500`) zurück bei Safety-Fehlern (erkennbar am `"Safety:"` Prefix).

**Besonderheit:** Der Test importiert `assertSendAllowed` **direkt aus `index.js`** via `module.exports` — keine Logik-Kopie. Wenn jemand den Guard in `index.js` entfernt oder verändert, schlagen diese Tests sofort an.

**Getestete Szenarien:**
1. Eigener Chat → erlaubt
2. **Fremde Person (z.B. Sarah) → blockiert** (Kern-Safety-Test)
3. Gruppenchat → blockiert
4. `user_chat_id` nicht konfiguriert (null) → blockiert
5. `user_chat_id` leer ("") → blockiert
6. Edge Cases: leere / undefined `chatId`
7. Error-Message Prefix `"Safety:"` → Voraussetzung für HTTP 403

**Ausführung:**
```bash
node tests/whatsapp/test_send_guard.js
```

**Erwartetes Ergebnis:**
```
Ergebnis: 10 Tests bestanden, 0 Tests fehlgeschlagen
✅ ERFOLG: Send-Guard schützt zuverlässig vor unberechtigtem Senden.
```

---

## Teststil

Alle Tests in diesem Verzeichnis folgen dem Memosaur-Teststil:
- Plain Node.js (kein Jest, kein Mocha)
- `assert(description, condition)` Hilfsfunktion
- Ausgabe mit `console.log` für Struktur
- `process.exit(1)` bei Fehlern
- Kommentare auf Deutsch
- Kernfunktionen werden via `module.exports` aus `index.js` importiert — keine Logik-Kopien
