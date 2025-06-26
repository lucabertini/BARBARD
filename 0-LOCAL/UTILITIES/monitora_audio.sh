#!/bin/bash

# Configurazione
SOURCE_FILE="/home/pi/recorded_audio.wav"
SEND_SCRIPT="/home/pi/invia_audio_al_mac.sh"
LOG_FILE="/home/pi/monitor_audio_log.txt"

# Funzione per registrare log
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log_message "Avvio monitoraggio file audio"

# Installa inotify-tools se non è già installato
if ! command -v inotifywait &> /dev/null; then
    log_message "Installazione di inotify-tools..."
    sudo apt-get update
    sudo apt-get install -y inotify-tools
fi

# Directory che contiene il file
SOURCE_DIR=$(dirname "$SOURCE_FILE")

log_message "Monitoraggio della directory: $SOURCE_DIR"

# Crea il file se non esiste
if [ ! -f "$SOURCE_FILE" ]; then
    log_message "Il file $SOURCE_FILE non esiste. Creazione file vuoto..."
    touch "$SOURCE_FILE"
fi

# Monitora la directory per modifiche al file target
inotifywait -m -e close_write,moved_to --format "%w%f" "$SOURCE_DIR" | 
while read FILE; do
    if [ "$FILE" = "$SOURCE_FILE" ]; then
        log_message "File audio modificato: $FILE"
        
        # Attendi un momento per assicurarsi che il file sia completamente scritto
        sleep 1
        
        # Esegui lo script di invio
        log_message "Avvio script di invio..."
        if "$SEND_SCRIPT"; then
            log_message "Script di invio completato con successo"
        else
            log_message "ERRORE: Script di invio fallito"
        fi
    fi
done
