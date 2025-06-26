#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AudioWatchdog.py: Sorveglia una cartella per nuovi file audio,
li trascrive tramite l'API di OpenAI e li organizza per la produzione.
(Versione con percorsi dinamici e portabili)
"""

# --- INIZIO BLOCCO UNIVERSALE DI GESTIONE PERCORSI ---
import os
import sys
from pathlib import Path

# Trova il percorso assoluto della directory in cui si trova questo script.
# Questo rende il progetto portabile e indipendente dalla directory di lavoro corrente.
try:
    PROJECT_ROOT = Path(__file__).parent.resolve()
except NameError:
    # Fallback per ambienti (es. notebook interattivi) dove __file__ non è definito
    PROJECT_ROOT = Path('.').resolve()

# Imposta la directory di lavoro sulla radice del progetto per coerenza.
# Questo garantisce che percorsi relativi come "SONGS" o "WORK_IN_PROGRESS"
# vengano sempre risolti correttamente.
os.chdir(PROJECT_ROOT)
# --- FINE BLOCCO UNIVERSALE ---

import time
import shutil
from datetime import datetime

try:
    import openai
    from dotenv import load_dotenv
    from colorama import init, Fore, Style
except ImportError:
    print("ERRORE: Assicurati di aver installato le librerie necessarie: pip install openai python-dotenv colorama")
    sys.exit(1)

# --- INIZIALIZZAZIONE E COLORI ---
init(autoreset=True)
SEPARATOR = "-----------------------------------------"
TAVOLO_COLOR = Fore.YELLOW + Style.BRIGHT
INFO_COLOR = Fore.CYAN
SUCCESS_COLOR = Fore.GREEN
ERROR_COLOR = Fore.RED
PATH_COLOR = Fore.WHITE
WARNING_COLOR = Fore.YELLOW
TEXT_PREVIEW_COLOR = Style.DIM + Fore.WHITE

def get_timestamp():
    """Restituisce un timestamp formattato per i log."""
    return datetime.now().strftime('%H:%M:%S')

# --- CONFIGURAZIONE ---
try:
    # Carica il file .env dalla radice del progetto
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
except Exception:
    print(f"{TAVOLO_COLOR}AVVISO:{Style.RESET_ALL} Libreria python-dotenv non trovata o .env non presente. Continuo con le variabili di sistema.")

# I percorsi ora sono costruiti a partire dalla radice del progetto per essere portabili
FOLDER_TO_WATCH = PROJECT_ROOT / "FROM_TABLES"
WORK_IN_PROGRESS_DIR = PROJECT_ROOT / "WORK_IN_PROGRESS"
ARCHIVE_DIR = FOLDER_TO_WATCH / "Archive"
TRANSCRIPTION_ERROR_DIR = ARCHIVE_DIR / "transcription_errors"
CHECK_INTERVAL_SECONDS = 5

MIN_CHARS_TRANSCRIPTION = int(os.getenv("CARATTERI_MINIMI", "0"))

# --- CONFIGURAZIONE OPENAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print(f"{ERROR_COLOR}{get_timestamp()} ERRORE CRITICO: OPENAI_API_KEY non trovata. Lo script non può funzionare.")
    sys.exit(1)

try:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    print(f"{ERROR_COLOR}{get_timestamp()} ERRORE CRITICO: Impossibile inizializzare il client OpenAI: {e}")
    sys.exit(1)


def process_audio_files():
    """
    Scansiona la cartella, trova tutti i file .wav e li processa uno per uno
    con un output formattato.
    """
    try:
        # Usiamo glob direttamente sulla Path object che è già un percorso assoluto
        wav_files = sorted(list(FOLDER_TO_WATCH.glob("*.wav")))
    except FileNotFoundError:
        print(f"{ERROR_COLOR}{get_timestamp()} La cartella '{FOLDER_TO_WATCH}' non è stata trovata. La creo.")
        FOLDER_TO_WATCH.mkdir(parents=True, exist_ok=True)
        return

    if not wav_files:
        return

    for audio_path in wav_files:
        try:
            last_size = -1
            while last_size != audio_path.stat().st_size:
                last_size = audio_path.stat().st_size
                time.sleep(1)
        except FileNotFoundError:
            print(f"{WARNING_COLOR}{get_timestamp()} AVVISO:{Style.RESET_ALL} Il file {audio_path.name} è scomparso durante il controllo stabilità. Lo ignoro.")
            continue

        filename = audio_path.name
        print(SEPARATOR)

        try:
            prefix = filename.split('-')[0]
            if not prefix.isdigit():
                print(f"{ERROR_COLOR}{get_timestamp()} Formato file non valido, prefisso non numerico: {filename}")
                print(SEPARATOR + "\n")
                continue
            filename_base = audio_path.stem
            print(f"{get_timestamp()} {TAVOLO_COLOR}TAVOLO-{prefix} > Rilevato file stabile: {Style.NORMAL}{filename}")
        except IndexError:
            print(f"{ERROR_COLOR}{get_timestamp()} Formato file non valido, manca il '-': {filename}")
            print(SEPARATOR + "\n")
            continue

        transcribed_text = ""
        print(f"{get_timestamp()} {INFO_COLOR}Mando a Whisper...", end="", flush=True)
        try:
            with open(audio_path, "rb") as audio_file:
                transcript_result = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="it"
                )
            transcribed_text = transcript_result.text.strip()
            print(f" {SUCCESS_COLOR}Trascritto!")
        except Exception as e:
            print(f" {ERROR_COLOR}FALLITO!")
            print(f"{ERROR_COLOR}{get_timestamp()} Errore OpenAI: {e}")
            error_archive_path = TRANSCRIPTION_ERROR_DIR / prefix
            error_archive_path.mkdir(parents=True, exist_ok=True)
            shutil.move(str(audio_path), str(error_archive_path / filename))
            print(f"{ERROR_COLOR}{get_timestamp()} File spostato in quarantena: {PATH_COLOR}{error_archive_path / filename}")
            print(SEPARATOR + "\n")
            continue

        if MIN_CHARS_TRANSCRIPTION > 0 and len(transcribed_text) < MIN_CHARS_TRANSCRIPTION:
            print(f"{WARNING_COLOR}{get_timestamp()} AVVISO: Trascrizione troppo corta ({len(transcribed_text)}/{MIN_CHARS_TRANSCRIPTION} caratteri). File ignorato.")
            print(f"{TEXT_PREVIEW_COLOR}Contenuto: \"{transcribed_text}\"")
            print(SEPARATOR + "\n")
            continue

        if not transcribed_text:
            print(f"{ERROR_COLOR}{get_timestamp()} Whisper ha restituito una trascrizione vuota.")
            print(SEPARATOR + "\n")
            continue

        try:
            table_work_dir = WORK_IN_PROGRESS_DIR / prefix
            table_work_dir.mkdir(parents=True, exist_ok=True)
            transcription_file_path = table_work_dir / f"{filename_base}.txt"
            transcription_file_path.write_text(transcribed_text, encoding="utf-8")
            print(f"{get_timestamp()} SALVATO IN: {PATH_COLOR}{transcription_file_path}")

            audio_archive_dir = ARCHIVE_DIR / prefix / "Recordings"
            audio_archive_dir.mkdir(parents=True, exist_ok=True)
            final_archive_path = audio_archive_dir / filename
            shutil.move(str(audio_path), str(final_archive_path))
            print(f"{get_timestamp()} ARCHIVIATO IN: {PATH_COLOR}{final_archive_path}")

        except Exception as e:
            print(f"{ERROR_COLOR}{get_timestamp()} ERRORE SALVATAGGIO/ARCHIVIAZIONE: {e}")
        
        print(SEPARATOR + "\n")


def main():
    """Funzione principale di avvio."""
    # Le directory vengono create usando i percorsi assoluti
    FOLDER_TO_WATCH.mkdir(exist_ok=True)
    WORK_IN_PROGRESS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    TRANSCRIPTION_ERROR_DIR.mkdir(parents=True, exist_ok=True)

    print(f"{SUCCESS_COLOR}-----------------------------------------")
    print(f"{SUCCESS_COLOR} Audio Watchdog Avviato")
    print(f"{INFO_COLOR}Controllo la cartella '{PATH_COLOR}{FOLDER_TO_WATCH}{INFO_COLOR}' ogni {CHECK_INTERVAL_SECONDS} secondi.")
    if MIN_CHARS_TRANSCRIPTION > 0:
        print(f"{INFO_COLOR}Trascrizioni con meno di {MIN_CHARS_TRANSCRIPTION} caratteri verranno ignorate.")
    print(f"{TAVOLO_COLOR}Premi CTRL+C per terminare.")
    print(f"{SUCCESS_COLOR}-----------------------------------------")

    try:
        while True:
            process_audio_files()
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print(f"\n{TAVOLO_COLOR}{get_timestamp()} Audio Watchdog terminato dall'utente.")
        sys.exit(0)
    except Exception as e:
        print(f"{ERROR_COLOR}{get_timestamp()} ERRORE FATALE: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()