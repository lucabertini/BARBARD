#!/bin/bash
# Script di trasferimento audio configurabile

# Leggi la variabile di ambiente dal file .env
if [ -f ".env" ]; then
    source .env
fi

# Valori predefiniti se non specificati nel .env
DOVE_VIENE_ESEGUITO=${DOVE_VIENE_ESEGUITO:-"Raspberry"}
MAC_USERNAME="lucabertini"
LOG_FILE="invia_audio_log.txt"

echo "Modalità: $DOVE_VIENE_ESEGUITO"

# Definisci i percorsi e le funzioni in base all'ambiente
if [ "$DOVE_VIENE_ESEGUITO" = "Mac" ]; then
    # Configurazione per esecuzione su Mac
    echo "Esecuzione su Mac - Copia locale del file"
    
    # Percorsi per Mac
    SOURCE_FILE="${1:-recorded_audio.wav}"
    DESTINATION_FOLDER="$HOME/Desktop/Registrazioni"
    
    # Crea la directory se non esiste
    mkdir -p "$DESTINATION_FOLDER"
    
    # Crea un nome file con timestamp
    TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
    DEST_FILENAME="recorded_audio_${TIMESTAMP}.wav"
    
    # Copia il file localmente
    cp "$SOURCE_FILE" "$DESTINATION_FOLDER/$DEST_FILENAME"
    
    # Verifica il risultato
    if [ $? -eq 0 ]; then
        echo "File audio copiato con successo in $DESTINATION_FOLDER/$DEST_FILENAME"
        exit 0
    else
        echo "Errore nella copia del file"
        exit 1
    fi
else
    # Configurazione per esecuzione su Raspberry Pi
    echo "Esecuzione su Raspberry Pi - Invio file al Mac remoto"
    
    # Percorsi per Raspberry Pi
    SOURCE_FILE="${1:-/home/pi/Desktop/BARBARD/LISTEN/recorded_audio.wav}"
    DESTINATION_FOLDER="/Users/lucabertini/Library/Mobile Documents/com~apple~CloudDocs/006 - A R T Essentials/01 - PROGETTI/09 - BAR BLANC/SUNOAPI/FROM_TABLES"
    
    # Verifica che il file esista
    if [ ! -f "$SOURCE_FILE" ]; then
        echo "ERRORE: File $SOURCE_FILE non trovato"
        exit 1
    fi
    
    # Trova il Mac nella rete (se esiste lo script)
    if [ -f "/home/pi/Desktop/BARBARD/trova_mac.sh" ]; then
        echo "Ricerca del Mac nella rete..."
        /home/pi/Desktop/BARBARD/trova_mac.sh
    fi
    
    # Leggi l'IP del Mac dal file
    if [ -f "/home/pi/mac_ip.txt" ]; then
        MAC_IP=$(cat /home/pi/mac_ip.txt)
    else
        MAC_IP="172.20.10.5"  # IP di fallback
    fi
    
    echo "Usando l'IP del Mac: $MAC_IP"