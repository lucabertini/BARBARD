#!/bin/bash

# ==========================================================
#      SCRIPT DI TRASFERIMENTO PER RASPBERRY PI
#   Usa SCP per inviare file a un computer remoto (Mac)
# ==========================================================

# --- IMPOSTAZIONI UTENTE ---

# L'indirizzo IP del mio Mac sulla rete locale.
# Impostazioni di Sistema > Wi-Fi > Dettagli.
TARGET_MAC_IP="172.20.10.5"  # <--- cambiare se necessario

# Il nome utente con cui accedi al tuo Mac.
TARGET_MAC_USER="lucabertini" 

# Il percorso completo della cartella di destinazione SUL MAC.
# Usa il percorso corretto che abbiamo trovato prima.
TARGET_MAC_PATH_ON_REMOTE="/Users/lucabertini/Library/Mobile Documents/com~apple~CloudDocs/006 - A R T Essentials/01 - PROGETTI/09 - BARBARD/RT/FROM_TABLES/"
# Una cartella di fallback LOCALE sul Raspberry Pi, in caso il trasferimento fallisca.
FALLBACK_PATH_LOCAL="/home/pi/audio_fallback_pi/"

# --- LOGICA DELLO SCRIPT ---
SOURCE_FILE="$1"
if [ -z "$SOURCE_FILE" ]; then
    echo "ERRORE: Nessun file sorgente fornito allo script."
    exit 1
fi

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
DEST_FILENAME="${POSTAZIONE_PREFIX}-${TIMESTAMP}.wav"

# Assicura che la cartella di fallback locale esista
mkdir -p "$FALLBACK_PATH_LOCAL"

# Tentativo di trasferimento primario via SCP
# -o ConnectTimeout=10 imposta un timeout di 10 secondi per la connessione.
echo "INFO (RPi Script): Tentativo di invio a ${TARGET_MAC_USER}@${TARGET_MAC_IP}"
echo "Destinazione remota: '${TARGET_MAC_PATH_ON_REMOTE}${DEST_FILENAME}'"

# NOTA: È fondamentale che si abbia configurato l'accesso SSH senza password dal Pi al Mac.

scp -o ConnectTimeout=10 "$SOURCE_FILE" "${TARGET_MAC_USER}@${TARGET_MAC_IP}:'${TARGET_MAC_PATH_ON_REMOTE}${DEST_FILENAME}'"
if [ $? -eq 0 ]; then
    echo "SUCCESSO (RPi Script): File trasferito correttamente."
    rm "$SOURCE_FILE"
    exit 0
else
    echo "ERRORE (RPi Script): Trasferimento via SCP fallito."
    echo "Salvataggio nel percorso di fallback locale: '${FALLBACK_PATH_LOCAL}${DEST_FILENAME}'"
    cp "$SOURCE_FILE" "${FALLBACK_PATH_LOCAL}${DEST_FILENAME}"
    exit 1
fi		
