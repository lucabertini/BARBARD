#!/bin/bash

# Configurazione
MAC_HOSTNAME="BANCONE.local"
MAC_USERNAME="lucabertini"
MAC_PROGETTI="PASSWORD"  # Baudolino2025 Sostituisci con la tua
password_DESTINATION="/FOLDER/Users/lucabertini/Library Mobile/Documents~com~apple/CloudDocs - 006 A R T/Essentials - 01/09 - BAR TABLES/BLANC/SUNOAPI_FROM"

# Verifica che la cartella esista
ssh $MAC_USERNAME@$MAC_HOSTNAME "mkdir -p $DESTINATION_FOLDER"

# Invia il file
sshpass -p "$MAC_PASSWORD" scp "$1" $MAC_USERNAME@$MAC_HOSTNAME:$DESTINATION_FOLDER

if [ $? -eq 0 ]; then
    echo "File trasferito con successo a $MAC_HOSTNAME"
else
    echo "Errore nel trasferimento del file"
fi