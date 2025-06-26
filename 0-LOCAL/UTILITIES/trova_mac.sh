#!/bin/bash

# Configurazione di base
MAC_USERNAME="lucabertini"
LOG_FILE="/home/pi/Desktop/BARBARD/LOGS/mac_discovery.log"

# Funzione per registrare log
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
    echo "$1"
}

log_message "Inizio ricerca del Mac"

# Prova prima con il nome host conosciuto
log_message "Tentativo con il nome host BANCONE.local"
if ping -c 1 BANCONE.local &>/dev/null; then
    log_message "Mac trovato con il nome host BANCONE.local"
    IP=$(ping -c 1 BANCONE.local | grep "PING" | awk -F'[()]' '{print $2}')
    echo "$IP" > /home/pi/mac_ip.txt
    echo "BANCONE.local" > /home/pi/mac_hostname.txt
    exit 0
fi

# Ottieni il tuo indirizzo IP e la subnet
MY_IP=$(hostname -I | awk '{print $1}')
SUBNET=$(echo "$MY_IP" | cut -d. -f1-3)

log_message "Indirizzo IP: $MY_IP, Subnet: $SUBNET"

# Scansiona la rete per trovare dispositivi attivi
for i in $(seq 1 254); do
    TARGET="$SUBNET.$i"
    
    # Salta il proprio IP
    if [ "$TARGET" = "$MY_IP" ]; then
        continue
    fi
    
    # Ping con timeout breve
    if ping -c 1 -W 1 "$TARGET" &>/dev/null; then
        log_message "Dispositivo trovato a $TARGET, verifica se è un Mac..."
        
        # Prova a connettersi via SSH per verificare se è un Mac
        if timeout 3 ssh -o BatchMode=yes -o StrictHostKeyChecking=no "$MAC_USERNAME@$TARGET" "test -d /Applications" 2>/dev/null; then
            log_message "Mac trovato all'indirizzo IP: $TARGET"
            echo "$TARGET" > /home/pi/mac_ip.txt
            exit 0
        fi
    fi
done

log_message "Nessun Mac trovato automaticamente nella rete."

# Richiedi input manuale
echo "Non ho trovato automaticamente il Mac. Per favore, inserisci l'indirizzo IP del Mac:"
read -p "Indirizzo IP: " MANUAL_IP

if ping -c 1 "$MANUAL_IP" &>/dev/null; then
    log_message "Indirizzo IP inserito manualmente: $MANUAL_IP (ping riuscito)"
    echo "$MANUAL_IP" > /home/pi/mac_ip.txt
    exit 0
else
    log_message "Impossibile raggiungere l'indirizzo IP inserito: $MANUAL_IP"
    echo "Impossibile raggiungere l'indirizzo IP fornito. Verifica che il Mac sia acceso e connesso alla stessa rete."
    exit 1
fi
