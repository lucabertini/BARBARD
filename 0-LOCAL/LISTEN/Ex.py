#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import pyaudio
import wave
import time
import webrtcvad
import numpy as np
from pathlib import Path
import subprocess
import datetime
from dotenv import load_dotenv

# Reindirizza stderr a /dev/null per sopprimere gli errori ALSA
stderr_fd = os.dup(sys.stderr.fileno())
devnull = os.open(os.devnull, os.O_WRONLY)
os.dup2(devnull, sys.stderr.fileno())

# Imposta l'output come unbuffered
os.environ['PYTHONUNBUFFERED'] = '1'

# Caricamento configurazione
load_dotenv()

# Codici colore ANSI
GRAY = '\033[90m'
GREEN = '\033[92m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'

# Apri il file di log separato
log_file = open("Consolle.txt", "a", encoding="utf-8")

# Funzione per stampare messaggi con colori
def print_colored(message, color=GRAY, is_battery_timestamp=False):
    timestamp = datetime.datetime.now()
    time_str = timestamp.strftime("%H:%M:%S")
    
    if is_battery_timestamp:
        # Formato speciale per il timestamp batteria
        formatted_msg = f"{color}VIVO!: {time_str}{RESET}"
        log_msg = f"VIVO!: {time_str}"
    else:
        # Formato semplificato con solo l'orario per tutti gli altri messaggi
        formatted_msg = f"{color}{time_str} {message}{RESET}"
        log_msg = f"{time_str} {message}"
    
    # Stampa colorata sul terminale
    sys.stdout.write(formatted_msg + "\n")
    sys.stdout.flush()
    
    # Versione per il file di log
    log_file.write(log_msg + "\n")
    log_file.flush()

# Inizializza PyAudio in silenzio (con stderr reindirizzato)
p_temp = pyaudio.PyAudio()
p_temp.terminate()

# Ripristina stderr dopo l'inizializzazione di PyAudio
os.dup2(stderr_fd, sys.stderr.fileno())
os.close(stderr_fd)
os.close(devnull)

# Parametri configurabili dal file .env
VAD_MODE = int(os.getenv("VAD_MODE", 3))
SILENCE_THRESHOLD_SECONDS = float(os.getenv("SILENCE_THRESHOLD_SECONDS", 2.0))
MAX_RECORD_SECONDS = int(os.getenv("MAX_RECORD_SECONDS", 3600))
ENERGY_THRESHOLD = int(os.getenv("ENERGY_THRESHOLD", 300))
DURATA_MINIMA = float(os.getenv("DURATA_MINIMA", 2))

# Log dell'avvio con timestamp
start_time = datetime.datetime.now()
print_colored(f"AVVIO SISTEMA - MONITORAGGIO BATTERIA")
print_colored(f"Parametri: VAD_MODE={VAD_MODE}, SILENCE_THRESHOLD={SILENCE_THRESHOLD_SECONDS}s, MAX_RECORD={MAX_RECORD_SECONDS}s, ENERGY_THRESHOLD={ENERGY_THRESHOLD}, DURATA_MINIMA={DURATA_MINIMA}s")

# Determina la cartella in cui si trova lo script
project_directory = Path(__file__).resolve().parent

# File per salvare l'audio registrato
WAVE_OUTPUT_FILENAME = project_directory / "recorded_audio.wav"

# Parametri per la registrazione audio
CHUNK = 320         # 320 campioni = 20 ms di audio a 16 kHz (valido per il VAD)
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

# Variabile per il timestamp periodico
last_timestamp = time.time()

# Percorso dello script bash per l'invio
SCRIPT_PATH = "/home/pi/Desktop/BARBARD/invia_audio_al_mac.sh"

# Funzione per inviare il file audio al Mac via SSH
def invia_audio_al_mac(file_path):
    """
    Invia il file audio al Mac tramite lo script bash.
    """
    try:
        print_colored(f"Invio file audio al Mac: {file_path}", BLUE)
        
        # Verifica che il file esista
        if not os.path.exists(file_path):
            print_colored(f"ERRORE: File {file_path} non esiste!", RED)
            return False
        
        # Verifica che lo script di invio esista
        if not os.path.exists(SCRIPT_PATH):
            print_colored(f"ERRORE: Script di invio non trovato: {SCRIPT_PATH}", RED)
            
            # Prova a usare lo script nella directory standard
            std_script_path = "/home/pi/invia_audio_al_mac.sh"
            if os.path.exists(std_script_path):
                result = subprocess.run(
                    [std_script_path], 
                    capture_output=True, 
                    text=True, 
                    timeout=60
                )
                
                if result.returncode == 0:
                    print_colored(f"Trasferimento completato con script alternativo", BLUE)
                    return True
                else:
                    print_colored(f"ERRORE: Trasferimento fallito", RED)
            
            # Prova con un comando diretto usando SCP
            try:
                remote_path = "/Users/lucabertini/Library/Mobile\\ Documents/com~apple~CloudDocs/006\\ -\\ A\\ R\\ T\\ Essentials/01\\ -\\ PROGETTI/09\\ -\\ BAR\\ BLANC/SUNOAPI/FROM_TABLES/"
                
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                dest_filename = f"recorded_audio_{timestamp}.wav"
                
                scp_command = f"scp '{file_path}' lucabertini@172.20.10.5:'{remote_path}{dest_filename}'"
                result = subprocess.run(
                    scp_command, 
                    shell=True,
                    capture_output=True, 
                    text=True, 
                    timeout=60
                )
                
                if result.returncode == 0:
                    print_colored(f"Trasferimento SCP completato", BLUE)
                    return True
                else:
                    fallback_path = "/Users/lucabertini/Desktop/"
                    scp_fallback = f"scp '{file_path}' lucabertini@172.20.10.5:'{fallback_path}{dest_filename}'"
                    
                    result = subprocess.run(
                        scp_fallback, 
                        shell=True,
                        capture_output=True, 
                        text=True, 
                        timeout=60
                    )
                    
                    if result.returncode == 0:
                        print_colored(f"Trasferimento fallback completato", BLUE)
                        return True
                    else:
                        print_colored(f"ERRORE: Tutti i tentativi falliti", RED)
                        return False
                    
            except Exception as e:
                print_colored(f"ERRORE: Trasferimento diretto: {str(e)}", RED)
                return False
                
            return False
        
        # Esecuzione dello script standard
        result = subprocess.run(
            [SCRIPT_PATH], 
            capture_output=True, 
            text=True, 
            timeout=60
        )
        
        if result.returncode == 0:
            print_colored(f"File audio inviato con successo al Mac", BLUE)
            return True
        else:
            # Secondo tentativo con il percorso diretto
            result2 = subprocess.run(
                [SCRIPT_PATH, file_path], 
                capture_output=True, 
                text=True, 
                timeout=60
            )
            
            if result2.returncode == 0:
                print_colored(f"Trasferimento completato (secondo tentativo)", BLUE)
                return True
            else:
                print_colored(f"ERRORE: Trasferimento fallito", RED)
                return False
            
    except subprocess.TimeoutExpired:
        print_colored(f"ERRORE: Timeout durante il trasferimento", RED)
        return False
    except Exception as e:
        print_colored(f"ERRORE: Trasferimento: {str(e)}", RED)
        return False

def is_loud(frame, threshold=ENERGY_THRESHOLD):
    """
    Verifica se il frame audio supera il livello di energia (RMS).
    """
    samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return False
    rms = np.sqrt(np.mean(samples**2))
    return rms > threshold

def record_audio_vad():
    """
    Registra audio utilizzando il Voice Activity Detection (VAD).
    """
    global last_timestamp
    
    print_colored(f"Avvio registrazione con VAD")
    
    # Reindirizza stderr prima di inizializzare PyAudio
    stderr_fd = os.dup(sys.stderr.fileno())
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, sys.stderr.fileno())
    
    p = pyaudio.PyAudio()
    sample_width = p.get_sample_size(FORMAT)
    expected_frame_length = CHUNK * sample_width

    try:
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)
    except OSError as e:
        # Ripristina stderr prima di stampare l'errore
        os.dup2(stderr_fd, sys.stderr.fileno())
        os.close(stderr_fd)
        os.close(devnull)
        
        print_colored(f"ERRORE: Inizializzazione audio: {e}", RED)
        p.terminate()
        return 0
    
    # Ripristina stderr dopo l'inizializzazione di PyAudio
    os.dup2(stderr_fd, sys.stderr.fileno())
    os.close(stderr_fd)
    os.close(devnull)

    vad = webrtcvad.Vad(VAD_MODE)
    frames = []
    recording = False
    recording_start_time = None
    last_voice_time = time.time()
    previous_speech_state = None
    previous_loud_state = None
    stop_reason = None

    # Attesa del parlato
    print_colored(f"In attesa di voce...")

    while True:
        # Timestamp batteria ogni 10 secondi
        current_time = time.time()
        if current_time - last_timestamp >= 10:
            # Usa il nuovo formato per il timestamp batteria
            print_colored("", GRAY, is_battery_timestamp=True)
            last_timestamp = current_time
            
        try:
            frame = stream.read(CHUNK, exception_on_overflow=False)
        except Exception as e:
            print_colored(f"ERRORE: Lettura frame: {e}", RED)
            continue

        if len(frame) != expected_frame_length:
            continue

        is_loud_result = is_loud(frame)
        
        if is_loud_result != previous_loud_state:
            previous_loud_state = is_loud_result

        is_speech = False
        if is_loud_result:
            try:
                is_speech = vad.is_speech(frame, RATE)
            except Exception as e:
                print_colored(f"ERRORE: VAD: {e}", RED)
                continue

        if is_speech != previous_speech_state:
            previous_speech_state = is_speech

        frames.append(frame)

        if is_speech and not recording:
            recording = True
            recording_start_time = time.time()
            last_voice_time = time.time()
            print_colored(f"Voce rilevata, inizio registrazione", GREEN)

        if recording:
            if is_speech:
                last_voice_time = time.time()
            elif time.time() - last_voice_time > SILENCE_THRESHOLD_SECONDS:
                silence_duration = time.time() - last_voice_time
                print_colored(f"Fine registrazione: silenzio di {silence_duration:.1f}s", RED)
                stop_reason = f"Silenzio prolungato ({silence_duration:.1f}s)"
                break

        if recording and (time.time() - recording_start_time > MAX_RECORD_SECONDS):
            print_colored(f"Fine registrazione: tempo massimo raggiunto", RED)
            stop_reason = "Tempo massimo raggiunto"
            break

    stream.stop_stream()
    stream.close()
    p.terminate()

    if frames:
        # Percorso completo e assoluto del file
        wave_output_absolute = os.path.abspath(str(WAVE_OUTPUT_FILENAME))
        
        wf = wave.open(str(WAVE_OUTPUT_FILENAME), 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(sample_width)
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        recording_duration = time.time() - recording_start_time if recording_start_time else 0
        print_colored(f"Registrazione: {recording_duration:.1f}s. Motivo: {stop_reason}")
        
        # Breve attesa per completare la scrittura
        time.sleep(1)
        
        # Invia il file audio al Mac
        invia_audio_al_mac(wave_output_absolute)
        
        return recording_duration
    else:
        return 0

def main():
    """
    Funzione principale che gestisce solo la registrazione audio.
    """
    global last_timestamp
    
    print_colored(f"Sistema operativo")
    
    # Crea uno script bash di trasferimento se non esiste
    if not os.path.exists(SCRIPT_PATH):
        print_colored(f"Script di invio non trovato, creazione...")
        try:
            with open(SCRIPT_PATH, 'w') as f:
                f.write("""#!/bin/bash
# Script di trasferimento audio automatico
SOURCE_FILE="/home/pi/Desktop/BARBARD/recorded_audio.wav"
# Se viene fornito un argomento, usa quello come percorso del file
if [ -n "$1" ]; then
    SOURCE_FILE="$1"
fi

# Verifica che il file esista
if [ ! -f "$SOURCE_FILE" ]; then
    echo "ERRORE: File $SOURCE_FILE non trovato"
    exit 1
fi

# Crea nome file con timestamp per evitare sovrascritture
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
DEST_FILENAME="recorded_audio_$TIMESTAMP.wav"

# Destinazione sul Mac
MAC_IP="172.20.10.5"
MAC_USER="lucabertini"
DEST_FOLDER="/Users/lucabertini/Desktop/"

# Invia il file
scp "$SOURCE_FILE" "$MAC_USER@$MAC_IP:$DEST_FOLDER$DEST_FILENAME"

# Verifica il risultato
if [ $? -eq 0 ]; then
    echo "File audio trasferito con successo a $MAC_IP:$DEST_FOLDER$DEST_FILENAME"
    exit 0
else
    echo "Errore nel trasferimento del file"
    exit 1
fi
""")
            # Rendi lo script eseguibile
            os.chmod(SCRIPT_PATH, 0o755)
            print_colored(f"Script di invio creato")
        except Exception as e:
            print_colored(f"ERRORE: Creazione script: {e}", RED)
    
    while True:
        # Timestamp batteria
        current_time = time.time()
        if current_time - last_timestamp >= 10:
            # Usa il nuovo formato per il timestamp batteria
            print_colored("", GRAY, is_battery_timestamp=True)
            last_timestamp = current_time
            
        duration = record_audio_vad()
        if duration < DURATA_MINIMA:
            # Non stampiamo nulla per registrazioni troppo brevi
            pass
        else:
            print_colored(f"Registrazione completata: {duration:.1f}s")
        
        time.sleep(1)

if __name__ == "__main__":
    main()