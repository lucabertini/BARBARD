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
import shutil

# ---------------------------------------------------
# FUNZIONE DI RILEVAMENTO SISTEMA
# ---------------------------------------------------
def detect_system():
    """Rileva se lo script sta girando su Mac, Raspberry Pi, o altro."""
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("linux"):
        pi_model_file = "/sys/firmware/devicetree/base/model"
        if os.path.exists(pi_model_file):
            try:
                with open(pi_model_file, "r") as f:
                    if "raspberry pi" in f.read().lower():
                        return "raspberry"
            except Exception:
                pass
        return "linux_pc"
    return "unknown"

# ---------------------------------------------------
# CONFIGURAZIONE INIZIALE E CARICAMENTO .ENV
# ---------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(CURRENT_DIR, ".env")
if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE)
    print(f"INFO: File .env caricato da: {ENV_FILE}")
else:
    print(f"ATTENZIONE: File .env non trovato in {CURRENT_DIR}. Si useranno i valori di default.")

# ---------------------------------------------------
# SEZIONE HELPER PER DEVICE INPUT PYAudio
# ---------------------------------------------------
def find_input_device(p_audio, min_input_channels=1, name_keyword=None):
    """
    Cerca tra i device PyAudio quello con almeno `min_input_channels`.
    Se `name_keyword` è fornito, preferisce i device che contengono quella stringa nel nome.
    Ritorna l'indice del primo matching, altrimenti None.
    """
    candidates = []
    for idx in range(p_audio.get_device_count()):
        info = p_audio.get_device_info_by_index(idx)
        if info.get('maxInputChannels', 0) >= min_input_channels:
            candidates.append((idx, info['name']))
    if not candidates:
        return None
    if name_keyword:
        for idx, name in candidates:
            if name_keyword.lower() in name.lower():
                return idx
    return candidates[0][0]

# ---------------------------------------------------
# CARICAMENTO VARIABILI E RILEVAMENTO SISTEMA
# ---------------------------------------------------
DETECTED_SYSTEM = detect_system()
IS_RASPBERRY = (DETECTED_SYSTEM == 'raspberry')
IS_MAC = (DETECTED_SYSTEM == 'mac')

MAC_DEFAULT_DEST_DIR = "/Users/lucabertini/Library/Mobile Documents/com~apple~CloudDocs/006 - A R T Essentials/01 - PROGETTI/09 - BARBARD/RT/FROM_TABLES"
MAC_DESTINATION_DIR = None

if IS_RASPBERRY:
    PROJECT_DIRECTORY = os.getenv("IF_RASPIE_PROJECT_DIRECTORY", CURRENT_DIR)
    POSTAZIONE_PREFIX = os.getenv("POSTAZIONE_PREFIX", "0") # <-- Caricamento per RPi
elif IS_MAC:
    PROJECT_DIRECTORY = os.getenv("IF_MAC_PROJECT_DIRECTORY", CURRENT_DIR)
    POSTAZIONE_PREFIX = os.getenv("POSTAZIONE_PREFIX", "99") # <-- Caricamento per Mac
    MAC_DESTINATION_DIR = os.getenv("MAC_DESTINATION_DIR", MAC_DEFAULT_DEST_DIR)
else:
    PROJECT_DIRECTORY = CURRENT_DIR
    POSTAZIONE_PREFIX = "0" # <-- Default per altri sistemi

LOG_FILE_BASE = os.getenv("LOG_FILE", "Consolle.txt")
SCRIPT_PATH_BASE = os.getenv("SCRIPT_PATH", "sposta_file.sh")
SCRIPT_EXECUTOR = os.getenv("SCRIPT_EXECUTOR", "/bin/bash")

try:
    VAD_MODE = int(os.getenv("VAD_MODE", 3))
    SILENCE_THRESHOLD_SECONDS = float(os.getenv("SILENCE_THRESHOLD_SECONDS", 15.0))
    MAX_RECORD_SECONDS = int(os.getenv("MAX_RECORD_SECONDS", 30))
    ENERGY_THRESHOLD = int(os.getenv("ENERGY_THRESHOLD", 400))
    DURATA_MINIMA = float(os.getenv("DURATA_MINIMA", 10.0))
    CHUNK = int(os.getenv("CHUNK", 320))
    CHANNELS = int(os.getenv("CHANNELS", 1))
    RATE = int(os.getenv("RATE", 16000))
except (ValueError, TypeError) as e:
    print(f"ERRORE: Valore non valido nel .env per un parametro numerico: {e}. Uso i default.")
    VAD_MODE, SILENCE_THRESHOLD_SECONDS, MAX_RECORD_SECONDS, ENERGY_THRESHOLD, DURATA_MINIMA, CHUNK, CHANNELS, RATE = 3, 15.0, 30, 400, 10.0, 320, 1, 16000

try:
    os.makedirs(PROJECT_DIRECTORY, exist_ok=True)
except OSError as e:
    print(f"ERRORE CRITICO: Impossibile creare PROJECT_DIRECTORY '{PROJECT_DIRECTORY}': {e}. Uso la directory corrente.")
    PROJECT_DIRECTORY = CURRENT_DIR
    os.makedirs(PROJECT_DIRECTORY, exist_ok=True)

LOG_FILE = os.path.join(PROJECT_DIRECTORY, LOG_FILE_BASE)
SCRIPT_PATH = os.path.join(PROJECT_DIRECTORY, SCRIPT_PATH_BASE)

# NOTA: WAVE_OUTPUT_FILENAME non viene più definito qui perché sarà dinamico.

log_file_handle = None
try:
    log_file_handle = open(LOG_FILE, "a", encoding="utf-8")
except Exception as e:
    print(f"ERRORE CRITICO: Impossibile aprire il file di log '{LOG_FILE}': {e}. Logging su file disabilitato.")

GRAY, GREEN, RED, BLUE, RESET = '\033[90m', '\033[92m', '\033[91m', '\033[94m', '\033[0m'

def print_colored(message, color=GRAY, is_battery_timestamp=False):
    timestamp = datetime.datetime.now()
    time_str = timestamp.strftime("%H:%M:%S")
    if is_battery_timestamp:
        formatted = f"{color}VIVO!: {time_str}{RESET}"
        log_msg = f"VIVO!: {time_str}"
    else:
        formatted = f"{color}{time_str} {message}{RESET}"
        log_msg = f"{time_str} {message}"
    sys.stdout.write(formatted + "\n")
    sys.stdout.flush()
    if log_file_handle:
        log_file_handle.write(log_msg + "\n")
        log_file_handle.flush()

# ---------------------------------------------------
# FUNZIONE DI TRASFERIMENTO FILE
# ---------------------------------------------------
def invia_o_sposta_audio(file_path_to_send):
    if not os.path.exists(file_path_to_send):
        print_colored(f"ERRORE: File sorgente {file_path_to_send} non trovato!", RED)
        return False

    if IS_MAC:
        op_type = "Spostamento (Mac)"
        print_colored(f"Avvio {op_type} per il file: {os.path.basename(file_path_to_send)}", BLUE)
        try:
            os.makedirs(MAC_DESTINATION_DIR, exist_ok=True)
            destination_file = os.path.join(MAC_DESTINATION_DIR, os.path.basename(file_path_to_send))
            shutil.move(file_path_to_send, destination_file)
            print_colored(f"File spostato con successo in: {destination_file}", GRAY)
            return True
        except Exception as e:
            print_colored(f"ERRORE durante lo spostamento locale (Mac): {e}", RED)
            return False
    else:
        op_type = "Invio (RPi/Linux)"
        print_colored(f"Avvio {op_type} per il file: {os.path.basename(file_path_to_send)}", BLUE)
        if not os.path.isfile(SCRIPT_PATH):
            print_colored(f"ERRORE CRITICO: Lo script di trasferimento '{SCRIPT_PATH}' non è stato trovato.", RED)
            return False
        if not os.access(SCRIPT_PATH, os.X_OK):
            print_colored(f"ERRORE CRITICO: Lo script '{SCRIPT_PATH}' non ha i permessi di esecuzione.", RED)
            return False

        cmd = [SCRIPT_EXECUTOR, SCRIPT_PATH, file_path_to_send]
        print_colored(f"Esecuzione comando: {' '.join(cmd)}", GRAY)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=60)
            if result.stdout: print_colored(f"Output script:\n{result.stdout.strip()}", GRAY)
            if result.stderr: print_colored(f"Stderr script:\n{result.stderr.strip()}", GRAY if result.returncode == 0 else RED)

            if result.returncode == 0:
                print_colored(f"{op_type} completato con successo tramite script.", GRAY)
                return True
            else:
                print_colored(f"ERRORE durante l'{op_type} tramite script (codice {result.returncode}).", RED)
                return False
        except Exception as e_subproc:
            print_colored(f"ERRORE inatteso durante l'esecuzione dello script: {e_subproc}", RED)
            return False

# ---------------------------------------------------
# FUNZIONI REGISTRAZIONE AUDIO
# ---------------------------------------------------
def is_audio_loud_enough(audio_frame, energy_thresh):
    samples = np.frombuffer(audio_frame, dtype=np.int16).astype(np.float32)
    if samples.size == 0: return False
    rms = np.sqrt(np.mean(samples**2))
    return rms > energy_thresh

def record_audio_vad():
    global last_timestamp
    print_colored(f"Inizio ciclo di ascolto (Energy: {ENERGY_THRESHOLD}, Silence: {SILENCE_THRESHOLD_SECONDS}s, MaxRec: {MAX_RECORD_SECONDS}s, MinDur: {DURATA_MINIMA}s)", GRAY)
    FORMAT = pyaudio.paInt16
    FRAME_DURATION_MS = (CHUNK * 1000) / RATE
    if FRAME_DURATION_MS not in [10, 20, 30]:
        print_colored(f"ATTENZIONE: Durata frame ({FRAME_DURATION_MS:.1f}ms) non ottimale per VAD.", RED)

    p_audio = pyaudio.PyAudio()
    sample_width_bytes = p_audio.get_sample_size(FORMAT)

    device_idx = find_input_device(p_audio, CHANNELS, os.getenv("INPUT_DEVICE_KEYWORD"))
    if device_idx is None:
        print_colored("ERRORE: nessun device di input trovato!", RED)
        p_audio.terminate()
        return 0
    device_info = p_audio.get_device_info_by_index(device_idx)
    print_colored(f"Microfono selezionato: '{device_info['name']}' (index {device_idx})", GRAY)

    try:
        audio_stream = p_audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK, input_device_index=device_idx)
    except Exception as e_audio_init:
        print_colored(f"ERRORE CRITICO: Impossibile aprire lo stream: {e_audio_init}", RED)
        p_audio.terminate()
        return 0

    vad_processor = webrtcvad.Vad(VAD_MODE)
    recorded_frames_buffer = []
    is_currently_recording = False
    recording_start = 0.0
    time_of_last_voice = time.time()
    
    print_colored(f"Ascolto avviato... (VAD Mode: {VAD_MODE})", GRAY)
    try:
        while True:
            now = time.time()
            if now - last_timestamp >= 10:
                print_colored("", GRAY, is_battery_timestamp=True)
                last_timestamp = now
            try:
                frame = audio_stream.read(CHUNK, exception_on_overflow=False)
            except IOError:
                continue

            loud = is_audio_loud_enough(frame, ENERGY_THRESHOLD)
            speech = loud and vad_processor.is_speech(frame, RATE)

            if speech:
                time_of_last_voice = now
                if not is_currently_recording:
                    is_currently_recording = True
                    recorded_frames_buffer = []
                    recording_start = now
                    print_colored("Voce rilevata! Inizio registrazione...", GREEN)
                recorded_frames_buffer.append(frame)
            elif is_currently_recording:
                recorded_frames_buffer.append(frame)
                if now - time_of_last_voice > SILENCE_THRESHOLD_SECONDS:
                    print_colored(f"Fine registrazione: silenzio > {SILENCE_THRESHOLD_SECONDS:.1f}s.", RED)
                    break
            if is_currently_recording and (now - recording_start > MAX_RECORD_SECONDS):
                print_colored(f"Fine registrazione: max {MAX_RECORD_SECONDS}s raggiunti.", RED)
                break
    finally:
        audio_stream.stop_stream()
        audio_stream.close()
        p_audio.terminate()

    if is_currently_recording and recorded_frames_buffer:
        duration = (len(recorded_frames_buffer) * CHUNK) / RATE

        # --- NUOVA MODIFICA: Generazione del nome file dinamico ---
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dynamic_filename_base = f"{POSTAZIONE_PREFIX}-{timestamp_str}.wav"
        output_filepath = os.path.join(PROJECT_DIRECTORY, dynamic_filename_base)
        # --- FINE MODIFICA ---

        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
        try:
            with wave.open(output_filepath, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(sample_width_bytes)
                wf.setframerate(RATE)
                wf.writeframes(b''.join(recorded_frames_buffer))
            
            print_colored(f"File audio salvato: {os.path.basename(output_filepath)} (Durata: {duration:.1f}s).", GRAY)
            time.sleep(0.2)

            if duration >= DURATA_MINIMA:
                print_colored(f"Durata ok ({duration:.1f}s). Avvio invio/spostamento...", GRAY) 
                invia_o_sposta_audio(output_filepath)
            else:
                print_colored(f"Registrazione troppo breve ({duration:.1f}s). Rimozione file.", GRAY)
                try:
                    os.remove(output_filepath)
                except OSError as e:
                    print_colored(f"ATTENZIONE: Impossibile rimuovere il file breve: {e}", RED)
        except Exception as e:
            print_colored(f"ERRORE salvataggio/gestione WAV: {e}", RED)
    return 0

# ---------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------
if __name__ == "__main__":
    try:
        print_colored(f"AVVIO SCRIPT {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", BLUE)
        if IS_MAC: 
            print_colored(f"Sistema rilevato: Mac (Prefisso: {POSTAZIONE_PREFIX}). I file verranno spostati in:", BLUE)
            print_colored(f"'{MAC_DESTINATION_DIR}'", BLUE)
        elif IS_RASPBERRY:
            print_colored(f"Sistema rilevato: Raspberry Pi (Prefisso: {POSTAZIONE_PREFIX}). I file verranno inviati con lo script '{SCRIPT_PATH}'", BLUE)
        else:
             print_colored(f"Sistema rilevato: {DETECTED_SYSTEM} (Prefisso: {POSTAZIONE_PREFIX}). I file verranno inviati con lo script '{SCRIPT_PATH}'", BLUE)

        last_timestamp = time.time()
        while True:
            record_audio_vad()
            time.sleep(1)
    except KeyboardInterrupt:
        print_colored("Programma interrotto dall'utente.", RED)
    except Exception as e:
        print_colored(f"ERRORE CRITICO NON GESTITO: {e}", RED)
        import traceback
        if log_file_handle: traceback.print_exc(file=log_file_handle)
    finally:
        print_colored("Chiusura script...", BLUE)
        if log_file_handle: log_file_handle.close()
        print_colored("Script terminato.", RESET)