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
import contextlib

# ... (tutte le sezioni iniziali rimangono identiche) ...
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
# SEZIONE HELPER
# ---------------------------------------------------
def find_input_device(p_audio, min_input_channels=1, name_keyword=None):
    """Cerca e ritorna l'indice del device di input."""
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

def find_supported_rate(p_audio, device_index, channels, rates_to_try=[16000, 48000, 32000, 8000, 44100]):
    """
    Testa una lista di frequenze di campionamento e ritorna la prima supportata dal device.
    Priorità alle frequenze compatibili con WebRTC VAD.
    """
    for rate in rates_to_try:
        try:
            if p_audio.is_format_supported(rate,
                                           input_device=device_index,
                                           input_channels=channels,
                                           input_format=pyaudio.paInt16):
                return rate
        except ValueError:
            continue
    return None

# ---------------------------------------------------
# CARICAMENTO VARIABILI E RILEVAMENTO SISTEMA
# ---------------------------------------------------
DETECTED_SYSTEM = detect_system()
IS_RASPBERRY = (DETECTED_SYSTEM == 'raspberry')
IS_MAC = (DETECTED_SYSTEM == 'mac')
IS_LINUX = (DETECTED_SYSTEM in ['raspberry', 'linux_pc'])

MAC_DEFAULT_DEST_DIR = "/Users/lucabertini/Library/Mobile Documents/com~apple~CloudDocs/006 - A R T Essentials/01 - PROGETTI/09 - BARBARD/RT/FROM_TABLES"
MAC_DESTINATION_DIR = None

if IS_RASPBERRY:
    PROJECT_DIRECTORY = os.getenv("IF_RASPIE_PROJECT_DIRECTORY", CURRENT_DIR)
    POSTAZIONE_PREFIX = os.getenv("POSTAZIONE_PREFIX", "0")
elif IS_MAC:
    PROJECT_DIRECTORY = os.getenv("IF_MAC_PROJECT_DIRECTORY", CURRENT_DIR)
    POSTAZIONE_PREFIX = os.getenv("POSTAZIONE_PREFIX", "99")
    MAC_DESTINATION_DIR = os.getenv("MAC_DESTINATION_DIR", MAC_DEFAULT_DEST_DIR)
else:
    PROJECT_DIRECTORY = CURRENT_DIR
    POSTAZIONE_PREFIX = "0"

LOG_FILE_BASE = os.getenv("LOG_FILE", "Consolle.txt")
SCRIPT_PATH_BASE = os.getenv("SCRIPT_PATH", "sposta_file.sh")
SCRIPT_EXECUTOR = os.getenv("SCRIPT_EXECUTOR", "/bin/bash")

try:
    VAD_MODE = int(os.getenv("VAD_MODE", 3))
    SILENCE_THRESHOLD_SECONDS = float(os.getenv("SILENCE_THRESHOLD_SECONDS", 10.0))
    MAX_RECORD_SECONDS = int(os.getenv("MAX_RECORD_SECONDS", 30))
    ENERGY_THRESHOLD = int(os.getenv("ENERGY_THRESHOLD", 400))
    DURATA_MINIMA = float(os.getenv("DURATA_MINIMA", 10.0))
    # CHUNK non è più una costante fissa, ma un valore di default.
    DEFAULT_CHUNK = int(os.getenv("CHUNK", 320))
    CHANNELS = int(os.getenv("CHANNELS", 1))
    DEFAULT_RATE = int(os.getenv("RATE", 16000))
except (ValueError, TypeError) as e:
    print(f"ERRORE: Valore non valido nel .env per un parametro numerico: {e}. Uso i default.")
    VAD_MODE, SILENCE_THRESHOLD_SECONDS, MAX_RECORD_SECONDS, ENERGY_THRESHOLD, DURATA_MINIMA, DEFAULT_CHUNK, CHANNELS, DEFAULT_RATE = 3, 10.0, 30, 400, 10.0, 320, 1, 16000

try:
    os.makedirs(PROJECT_DIRECTORY, exist_ok=True)
except OSError as e:
    print(f"ERRORE CRITICO: Impossibile creare PROJECT_DIRECTORY '{PROJECT_DIRECTORY}': {e}. Uso la directory corrente.")
    PROJECT_DIRECTORY = CURRENT_DIR
    os.makedirs(PROJECT_DIRECTORY, exist_ok=True)

LOG_FILE = os.path.join(PROJECT_DIRECTORY, LOG_FILE_BASE)
SCRIPT_PATH = os.path.join(PROJECT_DIRECTORY, SCRIPT_PATH_BASE)

log_file_handle = None
try:
    log_file_handle = open(LOG_FILE, "a", encoding="utf-8")
except Exception as e:
    print(f"ERRORE CRITICO: Impossibile aprire il file di log '{LOG_FILE}': {e}. Logging su file disabilitato.")

GRAY, GREEN, RED, BLUE, RESET = '\033[90m', '\033[92m', '\033[91m', '\033[94m', '\033[0m'

@contextlib.contextmanager
def silence_alsa_errors():
    if not IS_LINUX:
        yield
        return
    devnull = None
    old_stderr_fd = -1
    try:
        old_stderr_fd = os.dup(sys.stderr.fileno())
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stderr.fileno())
        yield
    finally:
        if old_stderr_fd != -1:
            os.dup2(old_stderr_fd, sys.stderr.fileno())
            os.close(old_stderr_fd)
        if devnull is not None:
            os.close(devnull)

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

# --- VERSIONE FINALE CON ADATTAMENTO DI RATE E CHUNK ---
def record_audio_vad():
    global last_timestamp
    print_colored(f"Inizio ciclo di ascolto (Energy: {ENERGY_THRESHOLD}, Silence: {SILENCE_THRESHOLD_SECONDS}s, MaxRec: {MAX_RECORD_SECONDS}s, MinDur: {DURATA_MINIMA}s)", GRAY)
    FORMAT = pyaudio.paInt16
    
    p_audio = None
    audio_stream = None
    recorded_frames_buffer = []
    is_currently_recording = False
    
    # Valori che verranno determinati dinamicamente
    RATE = 0
    CHUNK = 0
    sample_width_bytes = 0

    with silence_alsa_errors():
        try:
            p_audio = pyaudio.PyAudio()
            sample_width_bytes = p_audio.get_sample_size(FORMAT)

            device_idx = find_input_device(p_audio, CHANNELS, os.getenv("INPUT_DEVICE_KEYWORD"))
            if device_idx is None:
                print_colored("ERRORE: nessun device di input trovato!", RED)
                return 0
            device_info = p_audio.get_device_info_by_index(device_idx)
            print_colored(f"Microfono selezionato: '{device_info['name']}' (index {device_idx})", GRAY)

            # 1. Trova un RATE supportato
            rates_to_try = [DEFAULT_RATE, 16000, 48000, 32000, 8000, 44100]
            unique_rates = sorted(set(rates_to_try), key=rates_to_try.index)
            RATE = find_supported_rate(p_audio, device_idx, CHANNELS, unique_rates)
            
            if not RATE:
                print_colored(f"ERRORE CRITICO: Il microfono non supporta nessuna delle frequenze VAD compatibili.", RED)
                return 0
            
            # 2. Calcola il CHUNK corretto per il RATE trovato, per avere una durata frame valida (es. 20ms)
            VAD_FRAME_DURATION_MS = 20  # Usiamo 20ms come target
            CHUNK = int(RATE * VAD_FRAME_DURATION_MS / 1000)
            
            print_colored(f"Configurazione audio dinamica: RATE={RATE}Hz, CHUNK={CHUNK} (per {VAD_FRAME_DURATION_MS}ms di frame)", BLUE)

            # Apri lo stream con i parametri calcolati
            audio_stream = p_audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK, input_device_index=device_idx)

            vad_processor = webrtcvad.Vad(VAD_MODE)
            recording_start = 0.0
            time_of_last_voice = time.time()

            print_colored(f"Ascolto avviato... (VAD Mode: {VAD_MODE})", GRAY)
            while True:
                now = time.time()
                if now - last_timestamp >= 10:
                    print_colored("", GRAY, is_battery_timestamp=True)
                    last_timestamp = now
                try:
                    frame = audio_stream.read(CHUNK, exception_on_overflow=False)
                except IOError as e:
                    print_colored(f"ATTENZIONE: Errore di I/O dallo stream audio (overflow?): {e}", RED)
                    continue

                # Controllo di sicurezza sulla lunghezza del frame
                if len(frame) != CHUNK * sample_width_bytes:
                    continue

                loud = is_audio_loud_enough(frame, ENERGY_THRESHOLD)
                
                try:
                    speech = loud and vad_processor.is_speech(frame, RATE)
                except Exception as vad_error:
                    print_colored(f"ERRORE VAD: {vad_error}. La registrazione si interrompe.", RED)
                    break
                
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
        
        except Exception as e_audio_init:
            print_colored(f"ERRORE CRITICO NELLA GESTIONE AUDIO: {e_audio_init}", RED)
            import traceback
            if log_file_handle: traceback.print_exc(file=log_file_handle)
            return 0
        finally:
            if audio_stream:
                audio_stream.stop_stream()
                audio_stream.close()
            if p_audio:
                p_audio.terminate()

    if is_currently_recording and recorded_frames_buffer and RATE > 0:
        duration = (len(recorded_frames_buffer) * CHUNK) / RATE

        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dynamic_filename_base = f"{POSTAZIONE_PREFIX}-{timestamp_str}.wav"
        output_filepath = os.path.join(PROJECT_DIRECTORY, dynamic_filename_base)
        
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
# --- FINE FUNZIONE MODIFICATA ---

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
            if IS_LINUX: print_colored("INFO: Gestione errori ALSA per Linux/RPi ATTIVA.", GRAY)
        else:
             print_colored(f"Sistema rilevato: {DETECTED_SYSTEM} (Prefisso: {POSTAZIONE_PREFIX}). I file verranno inviati con lo script '{SCRIPT_PATH}'", BLUE)
             if IS_LINUX: print_colored("INFO: Gestione errori ALSA per Linux/RPi ATTIVA.", GRAY)

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