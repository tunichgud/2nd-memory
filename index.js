const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios'); // Für den Request ans Python-Backend

// Startet den Client mit lokaler Session-Speicherung
// Nutzt den systemweiten Chrome-Browser falls vorhanden
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        executablePath: '/usr/bin/google-chrome',
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    }
});

// Zeigt den QR-Code beim ersten Start im Terminal an
client.on('qr', (qr) => {
    qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
    console.log('WhatsApp-Brücke ist online!');
});

// Fängt alle Nachrichten ab (eingehend & selbst gesendet)
client.on('message_create', async msg => {
    // Kurzes Logging
    const sender = msg.fromMe ? 'Ich' : msg.from;
    console.log(`[WhatsApp] Nachricht von ${sender}: ${msg.body.substring(0, 50)}...`);

    // Schickt die Nachricht an deine memosaur AI-Engine (WebHook)
    try {
        const response = await axios.post('http://localhost:8000/api/v1/webhook', {
            sender: sender,
            text: msg.body,
            is_incoming: !msg.fromMe
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
