const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
const express = require('express');
const cors = require('cors');

// Backend URL (Docker-aware: nutzt backend:8000 im Container, localhost:8000 lokal)
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// Startet den Client mit lokaler Session-Speicherung
// Nutzt den systemweiten Chrome-Browser falls vorhanden (oder Chromium in Docker)
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || '/usr/bin/google-chrome',
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    }
});

// Zeigt den QR-Code beim ersten Start im Terminal an
client.on('qr', (qr) => {
    qrcode.generate(qr, { small: true });
});

// Config aus Backend (wird beim Start geladen)
let BOT_CONFIG = {
    user_chat_id: null,  // Die WhatsApp-ID des Users
    bot_enabled: true,
    test_mode: false
};

// Lädt Bot-Config aus dem Backend (ChromaDB)
async function loadBotConfig() {
    try {
        const response = await axios.get(`${BACKEND_URL}/api/whatsapp/config`);
        BOT_CONFIG = response.data;
        console.log('[WhatsApp] Bot-Config geladen:', BOT_CONFIG);

        if (BOT_CONFIG.user_chat_id) {
            console.log(`[WhatsApp] ✅ User-Chat-ID: ${BOT_CONFIG.user_chat_id}`);
            console.log(`[WhatsApp] 💡 Bot antwortet nur auf Nachrichten AN diesen User`);
        } else {
            console.log('[WhatsApp] ⚠️  Keine User-Chat-ID konfiguriert!');
            console.log('[WhatsApp] 💡 Setze die User-Chat-ID in den Einstellungen');
        }
    } catch (err) {
        console.error('[WhatsApp] Fehler beim Laden der Config:', err.message);
        console.log('[WhatsApp] Verwende Default-Config');
    }
}

client.on('ready', async () => {
    console.log('WhatsApp-Brücke ist online!');

    // Lade Config aus Backend
    await loadBotConfig();

    // Auto-Konfiguration: Wenn keine User-Chat-ID gesetzt ist,
    // verwende automatisch die ID des verbundenen WhatsApp-Accounts
    if (!BOT_CONFIG.user_chat_id && client.info && client.info.wid) {
        const autoUserChatId = client.info.wid.user + '@c.us';
        console.log(`[WhatsApp] 🔍 Keine User-Chat-ID konfiguriert`);
        console.log(`[WhatsApp] ✨ Auto-Konfiguration: Erkenne User-ID aus verbundenem Account`);
        console.log(`[WhatsApp] 📱 Telefon: ${client.info.wid.user}`);
        console.log(`[WhatsApp] 👤 User-Chat-ID: ${autoUserChatId}`);

        try {
            // Speichere in Backend/ChromaDB
            await axios.post(`${BACKEND_URL}/api/whatsapp/config/user-chat`, {
                chat_id: autoUserChatId
            });
            console.log(`[WhatsApp] ✅ User-Chat-ID automatisch gespeichert!`);

            // Reload Config
            await loadBotConfig();
        } catch (err) {
            console.error(`[WhatsApp] ❌ Fehler beim Speichern der Auto-Config:`, err.message);
        }
    }
});

// Speichert eine Nachricht im Backend (ChromaDB)
async function saveMessageToBackend(msg, chatName = null) {
    try {
        const contact = await msg.getContact();
        const chat = await msg.getChat();

        const messageData = {
            message_id: msg.id._serialized,
            chat_id: msg.from,
            chat_name: chatName || chat.name || msg.from,
            sender: msg.fromMe ? 'Ich' : (contact.pushname || contact.name || msg.from),
            text: msg.body,
            timestamp: msg.timestamp,
            is_from_me: msg.fromMe,
            has_media: msg.hasMedia,
            type: msg.type
        };

        await axios.post(`${BACKEND_URL}/api/whatsapp/message`, messageData);
        console.log(`[WhatsApp] 💾 Nachricht gespeichert: ${msg.from}`);
    } catch (err) {
        console.error(`[WhatsApp] Fehler beim Speichern der Nachricht:`, err.message);
    }
}

// Fängt alle Nachrichten ab (eingehend & selbst gesendet)
client.on('message_create', async msg => {
    // Kurzes Logging
    const sender = msg.fromMe ? 'Ich' : msg.from;
    console.log(`[WhatsApp] Nachricht von ${sender}: ${msg.body.substring(0, 50)}...`);

    // Message History für Frontend speichern
    messageHistory.unshift({
        id: msg.id._serialized,
        body: msg.body,
        from: msg.from,
        fromMe: msg.fromMe,
        timestamp: msg.timestamp,
        chat: msg.from
    });
    if (messageHistory.length > MAX_HISTORY) {
        messageHistory.pop();
    }

    // WICHTIG: Ignoriere Bot-Antworten (beginnen mit 🦕)
    if (msg.body.startsWith('🦕')) {
        console.log(`[WhatsApp] Ignoriere Bot-Nachricht (Loop Prevention)`);
        return;
    }

    // LIVE INGESTION: Speichere JEDE Nachricht (auch aus anderen Chats)
    // Dies läuft parallel zur Bot-Verarbeitung
    saveMessageToBackend(msg).catch(err => {
        console.error(`[WhatsApp] Fehler bei Live-Ingestion:`, err.message);
    });

    // SICHERHEIT STUFE 1: Bot muss aktiviert sein
    if (!BOT_CONFIG.bot_enabled) {
        console.log(`[WhatsApp] 🔒 Bot ist deaktiviert`);
        return;
    }

    // SICHERHEIT STUFE 2: User-Chat-ID muss konfiguriert sein
    if (!BOT_CONFIG.user_chat_id) {
        console.log(`[WhatsApp] ⚠️  Keine User-Chat-ID konfiguriert - ignoriere Nachricht`);
        return;
    }

    // SICHERHEIT STUFE 3: Nur Nachrichten AN den User (im User-Chat) verarbeiten
    // msg.from ist der Chat, in dem die Nachricht geschrieben wurde
    if (msg.from !== BOT_CONFIG.user_chat_id) {
        console.log(`[WhatsApp] ⏭️  Ignoriere Nachricht aus anderem Chat: ${msg.from}`);
        return;
    }

    // SICHERHEIT STUFE 4: Im Produktiv-Modus nur eingehende Nachrichten
    // (nicht die eigenen Nachrichten des Users)
    if (!BOT_CONFIG.test_mode && msg.fromMe) {
        console.log(`[WhatsApp] ⏭️  Ignoriere eigene Nachricht (kein TEST_MODE)`);
        return;
    }

    // Ab hier: Nachricht ist sicher und darf verarbeitet werden
    console.log(`[WhatsApp] ✅ Verarbeite Nachricht im User-Chat`);


    // Schickt die Nachricht an deine memosaur AI-Engine (WebHook)
    try {
        // Im TEST_MODE behandeln wir eigene Nachrichten als "incoming"
        const isIncoming = BOT_CONFIG.test_mode ? true : !msg.fromMe;

        const response = await axios.post(`${BACKEND_URL}/api/v1/webhook`, {
            sender: sender,
            text: msg.body,
            is_incoming: isIncoming
        });

        // Wenn das Backend eine Antwort generiert hat (nur bei echten eingehenden Prompts),
        // schicken wir sie hier per WhatsApp zurück.
        if (response.data && response.data.answer) {
            console.log(`[WhatsApp] Sende Antwort an ${msg.from}...`);
            await msg.reply("🦕 " + response.data.answer);
        }
    } catch (err) {
        console.error("Fehler bei der Kommunikation mit dem memosaur-Backend:", err.message);
    }
});

client.initialize();

// ==============================================================================
// REST API für Frontend
// ==============================================================================

const app = express();
app.use(cors());
app.use(express.json());

// Message History (für Frontend)
const messageHistory = [];
const MAX_HISTORY = 100;

// GET /api/whatsapp/chats - Liste aller Chats (mit Import-Status)
app.get('/api/whatsapp/chats', async (req, res) => {
    try {
        const chats = await client.getChats();

        // Hole Import-Status für alle Chats
        const chatListPromises = chats.map(async (chat) => {
            const chatId = chat.id._serialized;

            // Hole letzten Import-Timestamp vom Backend
            let importStatus = {
                imported: false,
                lastImport: null,
                messagesImported: 0
            };

            try {
                const statusResponse = await axios.get(
                    `${BACKEND_URL}/api/whatsapp/import-plan/chat/${encodeURIComponent(chatId)}/last-import`
                );

                if (statusResponse.data && !statusResponse.data.never_imported) {
                    importStatus = {
                        imported: true,
                        lastImport: new Date(statusResponse.data.last_imported_timestamp * 1000).toISOString(),
                        messagesImported: statusResponse.data.total_messages_imported || 0,
                        importRuns: statusResponse.data.import_runs || 0
                    };
                }
            } catch (err) {
                // Chat wurde noch nie importiert
            }

            // Schätze Nachrichtenanzahl (basierend auf letzten Nachrichten)
            let estimatedMessageCount = 0;
            try {
                const messages = await chat.fetchMessages({ limit: 1 });
                if (messages.length > 0) {
                    // Grobe Schätzung basierend auf Chat-Alter
                    const chatAge = Date.now() / 1000 - (chat.timestamp || 0);
                    const daysOld = chatAge / (24 * 60 * 60);
                    estimatedMessageCount = Math.round(daysOld * 2); // ~2 Nachrichten pro Tag
                }
            } catch (err) {
                // Ignorieren
            }

            return {
                id: chatId,
                name: chat.name || chat.id.user,
                isGroup: chat.isGroup,
                unreadCount: chat.unreadCount,
                timestamp: chat.timestamp,
                lastActivity: chat.lastMessage ? new Date(chat.lastMessage.timestamp * 1000).toISOString() : null,
                estimatedMessageCount: estimatedMessageCount,
                importStatus: importStatus
            };
        });

        const chatList = await Promise.all(chatListPromises);

        // Sortiere nach Aktivität (neueste zuerst)
        chatList.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));

        res.json({ chats: chatList });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// GET /api/whatsapp/messages/:chatId - Nachrichten eines Chats
app.get('/api/whatsapp/messages/:chatId', async (req, res) => {
    try {
        const chat = await client.getChatById(req.params.chatId);
        const messages = await chat.fetchMessages({ limit: Infinity });

        const messageList = messages.map(msg => ({
            id: msg.id._serialized,
            body: msg.body,
            from: msg.from,
            fromMe: msg.fromMe,
            timestamp: msg.timestamp,
            type: msg.type
        }));

        res.json({ messages: messageList });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// POST /api/whatsapp/send - Nachricht senden
app.post('/api/whatsapp/send', async (req, res) => {
    try {
        const { chatId, message } = req.body;

        if (!chatId || !message) {
            return res.status(400).json({ error: 'chatId and message required' });
        }

        const chat = await client.getChatById(chatId);
        await chat.sendMessage(message);

        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// GET /api/whatsapp/status - Status der Verbindung
app.get('/api/whatsapp/status', (req, res) => {
    const state = client.info ? {
        connected: true,
        user: client.info.pushname,
        phone: client.info.wid.user
    } : {
        connected: false
    };

    res.json(state);
});

// Rate Limiting Konstanten
const PAUSE_BETWEEN_CHATS = 3000;  // 3 Sekunden zwischen Chats
const BATCH_SIZE = 10;              // Nach 10 Chats: große Pause
const BATCH_PAUSE = 60000;          // 60 Sekunden Pause nach jedem Batch
const SAFE_HOURS_START = 9;         // Import nur 09:00-22:00
const SAFE_HOURS_END = 22;
const BULK_THRESHOLD = 20;          // Ab 20 Chats = "Bulk" → Zeitfenster aktiv

// Prüft, ob wir im sicheren Zeitfenster sind (09:00-22:00)
function isWithinSafeTimeWindow() {
    const now = new Date();
    const hour = now.getHours();
    return hour >= SAFE_HOURS_START && hour < SAFE_HOURS_END;
}

// Holt letzten Import-Timestamp für einen Chat vom Backend
async function getLastImportTimestamp(chatId) {
    try {
        const response = await axios.get(`${BACKEND_URL}/api/whatsapp/import-plan/chat/${encodeURIComponent(chatId)}/last-import`);
        return response.data.last_imported_timestamp || 0;
    } catch (err) {
        // Chat wurde noch nie importiert
        return 0;
    }
}

// Aktualisiert letzten Import-Timestamp für einen Chat im Backend
async function updateLastImportTimestamp(chatId, timestamp, messageId) {
    try {
        await axios.post(`${BACKEND_URL}/api/whatsapp/import-plan/chat/${encodeURIComponent(chatId)}/update-timestamp`, {
            timestamp: timestamp,
            message_id: messageId
        });
    } catch (err) {
        console.error(`[WhatsApp] Fehler beim Aktualisieren des Timestamps:`, err.message);
    }
}

// Exponential Backoff bei Rate Limit Errors
async function retryWithBackoff(fn, maxRetries = 4) {
    let delay = 5000; // Start mit 5s
    for (let i = 0; i < maxRetries; i++) {
        try {
            return await fn();
        } catch (err) {
            if (err.message.includes('rate limit') || err.message.includes('429')) {
                console.log(`[WhatsApp] Rate Limit erreicht, warte ${delay/1000}s...`);
                await new Promise(resolve => setTimeout(resolve, delay));
                delay *= 2; // Exponential: 5s -> 10s -> 20s -> 40s
            } else {
                throw err; // Anderer Fehler: sofort werfen
            }
        }
    }
    throw new Error('Max retries erreicht');
}

// POST /api/whatsapp/import-all-chats - Importiert alle Chat-Historien
app.post('/api/whatsapp/import-all-chats', async (req, res) => {
    try {
        console.log('[WhatsApp] 📥 Starte intelligenten Bulk-Import...');

        // Prüfe Zeitfenster
        if (!isWithinSafeTimeWindow()) {
            const now = new Date();
            return res.status(400).json({
                error: 'Import nur zwischen 09:00-22:00 Uhr erlaubt',
                current_hour: now.getHours(),
                safe_window: `${SAFE_HOURS_START}:00-${SAFE_HOURS_END}:00`
            });
        }

        const chats = await client.getChats();
        console.log(`[WhatsApp] Gefunden: ${chats.length} Chats`);

        // PHASE 1: Sortiere Chats nach Aktivität (neueste zuerst)
        chats.sort((a, b) => {
            const tsA = a.lastMessage?.timestamp || 0;
            const tsB = b.lastMessage?.timestamp || 0;
            return tsB - tsA; // Neueste zuerst
        });

        console.log('[WhatsApp] ✅ Chats sortiert nach Aktivität (neueste zuerst)');
        console.log(`[WhatsApp] Top 3 aktive Chats:`);
        for (let i = 0; i < Math.min(3, chats.length); i++) {
            const chat = chats[i];
            const lastMsg = chat.lastMessage ? new Date(chat.lastMessage.timestamp * 1000).toISOString() : 'nie';
            console.log(`[WhatsApp]   ${i+1}. ${chat.name || chat.id._serialized} (${lastMsg})`);
        }

        let totalImported = 0;
        let totalNew = 0;
        let totalSkipped = 0;
        let errors = 0;
        let chatIndex = 0;

        // PHASE 2: Importiere jeden Chat mit Rate Limiting & Deduplication
        for (const chat of chats) {
            chatIndex++;

            // Zeitfenster-Check vor jedem Chat
            if (!isWithinSafeTimeWindow()) {
                console.log(`[WhatsApp] ⏰ Außerhalb des Zeitfensters - Import pausiert`);
                console.log(`[WhatsApp] 📊 Zwischenstand: ${totalNew} neue, ${totalSkipped} übersprungen, ${errors} Fehler`);
                return res.json({
                    success: false,
                    paused: true,
                    reason: 'Zeitfenster überschritten',
                    progress: {
                        chats_processed: chatIndex - 1,
                        total_chats: chats.length,
                        new_messages: totalNew,
                        skipped_messages: totalSkipped,
                        errors: errors
                    }
                });
            }

            try {
                const chatId = chat.id._serialized;
                const chatName = chat.name || chatId;
                console.log(`[WhatsApp] [${chatIndex}/${chats.length}] Importiere: ${chatName}`);

                // SMART DEDUPLICATION: Hole letzten Import-Timestamp
                const lastImportTimestamp = await getLastImportTimestamp(chatId);
                if (lastImportTimestamp > 0) {
                    const lastDate = new Date(lastImportTimestamp * 1000).toISOString();
                    console.log(`[WhatsApp]   📌 Letzter Import: ${lastDate}`);
                    console.log(`[WhatsApp]   ⏩ Importiere nur neuere Nachrichten`);
                }

                // Lade ALLE Nachrichten aus diesem Chat
                const allMessages = await retryWithBackoff(async () => {
                    return await chat.fetchMessages({ limit: Infinity });
                });

                console.log(`[WhatsApp]   📦 ${allMessages.length} Nachrichten total`);

                // Filtere: Nur Nachrichten NACH letztem Import
                const newMessages = allMessages.filter(msg => msg.timestamp > lastImportTimestamp);
                console.log(`[WhatsApp]   ✨ ${newMessages.length} neue Nachrichten`);

                if (newMessages.length === 0) {
                    console.log(`[WhatsApp]   ⏭️  Keine neuen Nachrichten - überspringe Chat`);
                    totalSkipped += allMessages.length;
                } else {
                    // Speichere nur neue Nachrichten
                    let latestTimestamp = lastImportTimestamp;
                    let latestMessageId = null;

                    for (const msg of newMessages) {
                        try {
                            await saveMessageToBackend(msg, chatName);
                            totalImported++;
                            totalNew++;

                            // Track neueste Nachricht für Timestamp-Update
                            if (msg.timestamp > latestTimestamp) {
                                latestTimestamp = msg.timestamp;
                                latestMessageId = msg.id._serialized;
                            }
                        } catch (err) {
                            console.error(`[WhatsApp]   ❌ Fehler bei Nachricht ${msg.id._serialized}:`, err.message);
                            errors++;
                        }
                    }

                    // Update letzten Import-Timestamp
                    if (latestMessageId) {
                        await updateLastImportTimestamp(chatId, latestTimestamp, latestMessageId);
                        console.log(`[WhatsApp]   ✅ Timestamp aktualisiert: ${new Date(latestTimestamp * 1000).toISOString()}`);
                    }

                    totalSkipped += (allMessages.length - newMessages.length);
                }

                // RATE LIMITING: Pause zwischen Chats
                console.log(`[WhatsApp]   ⏸️  Pause ${PAUSE_BETWEEN_CHATS/1000}s...`);
                await new Promise(resolve => setTimeout(resolve, PAUSE_BETWEEN_CHATS));

                // BATCH PAUSE: Nach jedem 10. Chat große Pause
                if (chatIndex % BATCH_SIZE === 0) {
                    console.log(`[WhatsApp] 🛑 BATCH PAUSE (${chatIndex} Chats) - warte ${BATCH_PAUSE/1000}s...`);
                    await new Promise(resolve => setTimeout(resolve, BATCH_PAUSE));
                }

            } catch (err) {
                console.error(`[WhatsApp] ❌ Fehler bei Chat ${chat.id._serialized}:`, err.message);
                errors++;
            }
        }

        console.log(`[WhatsApp] 🎉 Import abgeschlossen!`);
        console.log(`[WhatsApp]   ✨ ${totalNew} neue Nachrichten importiert`);
        console.log(`[WhatsApp]   ⏭️  ${totalSkipped} bereits importiert (übersprungen)`);
        console.log(`[WhatsApp]   📊 ${totalImported} total gespeichert`);
        console.log(`[WhatsApp]   ❌ ${errors} Fehler`);

        res.json({
            success: true,
            total_chats: chats.length,
            new_messages: totalNew,
            skipped_messages: totalSkipped,
            total_saved: totalImported,
            errors: errors
        });

    } catch (err) {
        console.error('[WhatsApp] Bulk-Import Fehler:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// POST /api/whatsapp/import-selected-chats - Importiert ausgewählte Chats
app.post('/api/whatsapp/import-selected-chats', async (req, res) => {
    try {
        const { chatIds } = req.body;

        if (!chatIds || !Array.isArray(chatIds) || chatIds.length === 0) {
            return res.status(400).json({ error: 'chatIds array required' });
        }

        console.log(`[WhatsApp] 📥 Starte selektiven Import für ${chatIds.length} Chat(s)...`);

        // Zeitfenster-Check nur bei Bulk-Import (20+ Chats)
        if (chatIds.length >= BULK_THRESHOLD && !isWithinSafeTimeWindow()) {
            const now = new Date();
            console.log(`[WhatsApp] ⏰ Bulk-Import (${chatIds.length} Chats) außerhalb Zeitfenster blockiert`);
            return res.status(400).json({
                error: `Bulk-Import (${BULK_THRESHOLD}+ Chats) nur zwischen 09:00-22:00 Uhr erlaubt`,
                current_hour: now.getHours(),
                safe_window: `${SAFE_HOURS_START}:00-${SAFE_HOURS_END}:00`,
                hint: `Wähle weniger als ${BULK_THRESHOLD} Chats für Import ohne Zeitrestriktion`
            });
        }

        // Lade alle Chats vom Client
        const allChats = await client.getChats();
        console.log(`[WhatsApp] Gefunden: ${allChats.length} Chats total`);

        // Filtere nur die ausgewählten Chats
        const selectedChats = allChats.filter(chat => chatIds.includes(chat.id._serialized));
        console.log(`[WhatsApp] Gefiltert: ${selectedChats.length} ausgewählte Chat(s)`);

        if (selectedChats.length === 0) {
            return res.status(404).json({ error: 'Keine der ausgewählten Chats gefunden' });
        }

        // Sortiere nach Aktivität (neueste zuerst)
        selectedChats.sort((a, b) => {
            const tsA = a.lastMessage?.timestamp || 0;
            const tsB = b.lastMessage?.timestamp || 0;
            return tsB - tsA;
        });

        console.log('[WhatsApp] ✅ Chats sortiert nach Aktivität');

        let totalImported = 0;
        let totalNew = 0;
        let totalSkipped = 0;
        let errors = 0;
        let chatIndex = 0;

        // Importiere jeden ausgewählten Chat
        for (const chat of selectedChats) {
            chatIndex++;

            // Zeitfenster-Check vor jedem Chat (nur bei Bulk-Import)
            if (chatIds.length >= BULK_THRESHOLD && !isWithinSafeTimeWindow()) {
                console.log(`[WhatsApp] ⏰ Bulk-Import außerhalb des Zeitfensters - Import pausiert`);
                return res.json({
                    success: false,
                    paused: true,
                    reason: 'Zeitfenster überschritten (Bulk-Import)',
                    progress: {
                        chats_processed: chatIndex - 1,
                        total_chats: selectedChats.length,
                        new_messages: totalNew,
                        skipped_messages: totalSkipped,
                        errors: errors
                    }
                });
            }

            try {
                const chatId = chat.id._serialized;
                const chatName = chat.name || chatId;
                console.log(`[WhatsApp] [${chatIndex}/${selectedChats.length}] Importiere: ${chatName}`);

                // Smart Deduplication
                const lastImportTimestamp = await getLastImportTimestamp(chatId);
                if (lastImportTimestamp > 0) {
                    const lastDate = new Date(lastImportTimestamp * 1000).toISOString();
                    console.log(`[WhatsApp]   📌 Letzter Import: ${lastDate}`);
                }

                // Lade ALLE Nachrichten
                const allMessages = await retryWithBackoff(async () => {
                    return await chat.fetchMessages({ limit: Infinity });
                });

                console.log(`[WhatsApp]   📦 ${allMessages.length} Nachrichten total`);

                // Filtere neue Nachrichten
                const newMessages = allMessages.filter(msg => msg.timestamp > lastImportTimestamp);
                console.log(`[WhatsApp]   ✨ ${newMessages.length} neue Nachrichten`);

                if (newMessages.length === 0) {
                    console.log(`[WhatsApp]   ⏭️  Keine neuen Nachrichten`);
                    totalSkipped += allMessages.length;
                } else {
                    let latestTimestamp = lastImportTimestamp;
                    let latestMessageId = null;

                    for (const msg of newMessages) {
                        try {
                            await saveMessageToBackend(msg, chatName);
                            totalImported++;
                            totalNew++;

                            if (msg.timestamp > latestTimestamp) {
                                latestTimestamp = msg.timestamp;
                                latestMessageId = msg.id._serialized;
                            }
                        } catch (err) {
                            console.error(`[WhatsApp]   ❌ Fehler bei Nachricht:`, err.message);
                            errors++;
                        }
                    }

                    // Update Timestamp
                    if (latestMessageId) {
                        await updateLastImportTimestamp(chatId, latestTimestamp, latestMessageId);
                        console.log(`[WhatsApp]   ✅ Timestamp aktualisiert`);
                    }

                    totalSkipped += (allMessages.length - newMessages.length);
                }

                // Rate Limiting
                if (chatIndex < selectedChats.length) {
                    console.log(`[WhatsApp]   ⏸️  Pause ${PAUSE_BETWEEN_CHATS/1000}s...`);
                    await new Promise(resolve => setTimeout(resolve, PAUSE_BETWEEN_CHATS));
                }

                // Batch Pause
                if (chatIndex % BATCH_SIZE === 0 && chatIndex < selectedChats.length) {
                    console.log(`[WhatsApp] 🛑 BATCH PAUSE - warte ${BATCH_PAUSE/1000}s...`);
                    await new Promise(resolve => setTimeout(resolve, BATCH_PAUSE));
                }

            } catch (err) {
                console.error(`[WhatsApp] ❌ Fehler bei Chat:`, err.message);
                errors++;
            }
        }

        console.log(`[WhatsApp] 🎉 Selektiver Import abgeschlossen!`);
        console.log(`[WhatsApp]   ✨ ${totalNew} neue Nachrichten`);
        console.log(`[WhatsApp]   ⏭️  ${totalSkipped} übersprungen`);

        res.json({
            success: true,
            total_chats: selectedChats.length,
            new_messages: totalNew,
            skipped_messages: totalSkipped,
            total_saved: totalImported,
            errors: errors
        });

    } catch (err) {
        console.error('[WhatsApp] Selektiver Import Fehler:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// GET /api/whatsapp/history - Message History (last 100)
app.get('/api/whatsapp/history', (req, res) => {
    res.json({ messages: messageHistory });
});

// GET /api/whatsapp/config - Bot-Konfiguration
app.get('/api/whatsapp/config', (req, res) => {
    res.json({
        bot_enabled: BOT_CONFIG.bot_enabled,
        test_mode: BOT_CONFIG.test_mode,
        my_chat_id: BOT_CONFIG.user_chat_id,
        my_chat_configured: BOT_CONFIG.user_chat_id !== null
    });
});

// POST /api/whatsapp/config/my-chat - Setze deine Chat-ID manuell
app.post('/api/whatsapp/config/my-chat', (req, res) => {
    const { chatId } = req.body;

    if (!chatId) {
        return res.status(400).json({ error: 'chatId required' });
    }

    BOT_CONFIG.user_chat_id = chatId;
    console.log(`[WhatsApp] ✅ user_chat_id manuell gesetzt: ${chatId}`);

    res.json({
        bot_enabled: BOT_CONFIG.bot_enabled,
        test_mode: BOT_CONFIG.test_mode,
        my_chat_id: BOT_CONFIG.user_chat_id,
        my_chat_configured: true
    });
});

// DELETE /api/whatsapp/config/my-chat - Entferne Chat-ID (Reset)
app.delete('/api/whatsapp/config/my-chat', (req, res) => {
    const old = BOT_CONFIG.user_chat_id;
    BOT_CONFIG.user_chat_id = null;
    console.log(`[WhatsApp] ❌ user_chat_id zurückgesetzt (war: ${old})`);

    res.json({
        bot_enabled: BOT_CONFIG.bot_enabled,
        test_mode: BOT_CONFIG.test_mode,
        my_chat_id: BOT_CONFIG.user_chat_id,
        my_chat_configured: false
    });
});

const PORT = process.env.WHATSAPP_PORT || 3001;
app.listen(PORT, () => {
    console.log(`WhatsApp API listening on http://localhost:${PORT}`);
});
