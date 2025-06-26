import os
import sys
from dotenv import load_dotenv
load_dotenv()

import pyaudio
import wave
import time
import webrtcvad
import numpy as np
from pathlib import Path

# Classe per duplicare l'output su console e file
class Tee:
    def __init__(self, *files):
        self.files = files

    def write(self, data):
        for f in self.files:
            f.write(data)

    def flush(self):
        for f in self.files:
            f.flush()

# Apri il file Consolle.txt in modalità append e reindirizza stdout
log_file = open("Consolle.txt", "a", encoding="utf-8")
sys.stdout = Tee(sys.stdout, log_file)

# Parametri configurabili dal file .env
VAD_MODE = int(os.getenv("VAD_MODE", 3))
SILENCE_THRESHOLD_SECONDS = float(os.getenv("SILENCE_THRESHOLD_SECONDS", 2.0))
MAX_RECORD_SECONDS = int(os.getenv("MAX_RECORD_SECONDS", 3600))
ENERGY_THRESHOLD = int(os.getenv("ENERGY_THRESHOLD", 300))
DURATA_MINIMA = float(os.getenv("DURATA_MINIMA", 2))

# Debug: stampa dei parametri impostati
print(f"  ----- PARAMETRI GENERALI   ")
print(f"  ----- AUDIO IN   ")
print(f"  VAD_MODE: {VAD_MODE}")
print(f"  SILENCE_THRESHOLD_SECONDS: {SILENCE_THRESHOLD_SECONDS}")
print(f"  MAX_RECORD_SECONDS: {MAX_RECORD_SECONDS}")
print(f"  ENERGY_THRESHOLD: {ENERGY_THRESHOLD}")
print(f"  DURATA_MINIMA: {DURATA_MINIMA}")

# Determina la cartella in cui si trova lo script
project_directory = Path(__file__).resolve().parent

# File per salvare l'audio registrato
WAVE_OUTPUT_FILENAME = project_directory / "recorded_audio.wav"

# Parametri per la registrazione audio (non configurabili tramite .env)
CHUNK = 320         # 320 campioni = 20 ms di audio a 16 kHz (valido per il VAD)
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

def is_loud(frame, threshold=ENERGY_THRESHOLD):
    """
    Verifica se il frame audio supera il livello di energia (RMS).
    Restituisce True se il frame è considerato "forte", altrimenti False.
    """
    samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return False
    rms = np.sqrt(np.mean(samples**2))
    return rms > threshold

def record_audio_vad():
    """
    Registra audio utilizzando il Voice Activity Detection (VAD).
    Inizia la registrazione al rilevamento del parlato e termina dopo un periodo di silenzio
    oppure quando viene raggiunto il tempo massimo.
    Salva l'audio in un file WAV e restituisce la durata della registrazione,
    stampando in debug il motivo della chiusura.
    """
    print("DEBUG: Avvio della registrazione con VAD")
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
        print("DEBUG: Errore nell'inizializzazione del dispositivo audio:", e)
        p.terminate()
        return 0

    vad = webrtcvad.Vad(VAD_MODE)
    frames = []
    recording = False
    recording_start_time = None
    last_voice_time = time.time()
    previous_speech_state = None
    previous_loud_state = None
    stop_reason = None

    print("DEBUG: In attesa di parlato...")

    while True:
        try:
            frame = stream.read(CHUNK, exception_on_overflow=False)
        except Exception as e:
            print("DEBUG: Errore durante la lettura del frame:", e)
            continue

        if len(frame) != expected_frame_length:
            print("DEBUG: Frame di lunghezza non valida:", len(frame))
            continue

        is_loud_result = is_loud(frame)
        if is_loud_result != previous_loud_state:
            print("DEBUG: Stato RMS cambiato a:", is_loud_result)
            previous_loud_state = is_loud_result

        is_speech = False
        if is_loud_result:
            try:
                is_speech = vad.is_speech(frame, RATE)
            except Exception as e:
                print("DEBUG: Errore nel VAD:", e)
                continue

        if is_speech != previous_speech_state:
            print("DEBUG: Stato VAD cambiato a:", is_speech)
            previous_speech_state = is_speech

        frames.append(frame)

        if is_speech and not recording:
            recording = True
            recording_start_time = time.time()
            last_voice_time = time.time()
            print("DEBUG: Parlato rilevato, inizio registrazione...")

        if recording:
            if is_speech:
                last_voice_time = time.time()
            elif time.time() - last_voice_time > SILENCE_THRESHOLD_SECONDS:
                silence_duration = time.time() - last_voice_time
                print(f"DEBUG: Silenzio prolungato rilevato ({silence_duration:.1f} secondi), fine registrazione.")
                stop_reason = f"Silenzio prolungato ({silence_duration:.1f} secondi di silenzio)"
                break

        if recording and (time.time() - recording_start_time > MAX_RECORD_SECONDS):
            print("DEBUG: Tempo massimo di registrazione raggiunto.")
            stop_reason = "Tempo massimo di registrazione raggiunto"
            break

    stream.stop_stream()
    stream.close()
    p.terminate()

    if frames:
        wf = wave.open(str(WAVE_OUTPUT_FILENAME), 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(sample_width)
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        recording_duration = time.time() - recording_start_time if recording_start_time else 0
        print(f"DEBUG: Durata registrazione: {recording_duration:.1f} secondi. Motivo di chiusura: {stop_reason}")
        return recording_duration
    else:
        print("DEBUG: Nessun frame registrato.")
        return 0

def main():
    """
    Funzione principale che gestisce solo la registrazione audio.
    """
    print("DEBUG: Avvio del ciclo principale")
    while True:
        duration = record_audio_vad()
        if duration < DURATA_MINIMA:
            print("DEBUG: Registrazione troppo breve o nessuna registrazione effettuata.")
        else:
            print(f"DEBUG: Registrazione audio completata. Durata: {duration:.1f} secondi")
            print(f"DEBUG: File audio salvato in {WAVE_OUTPUT_FILENAME}")
        
        time.sleep(1)

if __name__ == "__main__":
    main()