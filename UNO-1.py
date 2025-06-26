#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Orchestrator.py (Versione Semplificata e Robusta)
Processo unico che gestisce l'intera pipeline di generazione musicale.
Include un caricatore .env manuale per gestire configurazioni complesse.
"""

import os
import sys
import time
import json
import shutil
import random
import re # Importato per la nuova funzione
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

# --- LIBRERIE ESTERNE ---
try:
    import openai
    # Non usiamo più load_dotenv, ma lasciamo la libreria per compatibilità
    from dotenv import load_dotenv
    from colorama import init, Fore, Style
    from filelock import FileLock, Timeout
except ImportError:
    print("ERRORE: Assicurati di aver installato le librerie necessarie: pip install openai python-dotenv colorama filelock requests")
    sys.exit(1)

# --- INIZIALIZZAZIONE GLOBALE ---
init(autoreset=True)

# --- MODIFICA CHIAVE: CARICATORE .ENV MANUALE ---
def manual_load_dotenv(dotenv_path: Path = Path(".env")):
    """
    Carica manualmente le variabili d'ambiente da un file .env,
    gestendo correttamente valori complessi non virgolettati.
    Questo evita gli errori di parsing di python-dotenv.
    """
    if not dotenv_path.is_file():
        return
    
    with open(dotenv_path) as f:
        for line in f:
            # Ignora commenti e righe vuote
            if line.strip().startswith('#') or not line.strip():
                continue
            
            # Cerca il formato CHIAVE=VALORE
            match = re.match(r'^\s*([\w.-]+)\s*=\s*(.*)?\s*$', line)
            if match:
                key, value = match.groups()
                # Se il valore non è già nell'ambiente, impostalo
                if key not in os.environ:
                    os.environ[key] = value or ''

# Chiamiamo la nostra funzione invece di quella standard
manual_load_dotenv()
# --- FINE MODIFICA ---


# (Il resto del codice rimane ESATTAMENTE lo stesso della versione robusta precedente)
# ...
# --- CONFIGURAZIONE ---
# Cartelle
FOLDER_TO_WATCH = Path("FROM_TABLES")
OUTPUT_DIR = Path("SONGS")
ARCHIVE_DIR = FOLDER_TO_WATCH / "Archive"
TRANSCRIPTION_ERROR_DIR = ARCHIVE_DIR / "transcription_errors"
TMP_DIR = Path("./.tmp_player")

# Gestione Coda di Riproduzione
PLAYLIST_FILE = TMP_DIR / "playlist.queue"
PLAYLIST_LOCK_FILE = TMP_DIR / "playlist.queue.lock"
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "2"))
CHECK_INTERVAL_SECONDS = 5

# Configurazione API e Generazione
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
KIEAI_API_KEY = os.getenv("KIEAI_API_KEY")
MIN_CHARS_TRANSCRIPTION = int(os.getenv("CARATTERI_MINIMI", "10"))

# Modelli e Prompt (da GenerateSong.py)
MUSIC_MODEL = os.getenv("MODEL", "V4_5")
LYRICS_MODEL = os.getenv("LYRICS_MODEL", "gpt-4o")
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "gpt-3.5-turbo")
SUMMARY_SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "Riassumi la conversazione seguente in modo conciso, catturandone l'argomento e l'umore.")
LYRICS_MASTER_PROMPT = os.getenv("STILE_LYRICS", "Sei un cantautore. Usa il riassunto seguente per scrivere il testo completo di una canzone, con strofe e ritornello.")

def load_env_list(prefix: str) -> list[str]:
    return [v for k, v in os.environ.items() if k.startswith(prefix) and v.strip()]
STYLE_OPTIONS = load_env_list("DEFAULT_STYLE")

# --- COLORI E LOGGING ---
TITLE_COLOR = Fore.CYAN + Style.BRIGHT
SUCCESS_COLOR = Fore.GREEN
ERROR_COLOR = Fore.RED
WARNING_COLOR = Fore.YELLOW
INFO_COLOR = Fore.BLUE
PATH_COLOR = Fore.WHITE
DIM_COLOR = Style.DIM

def get_timestamp(): return datetime.now().strftime('%H:%M:%S')
def log_milestone(msg: str): print(f"{get_timestamp()} {TITLE_COLOR}>>> {msg}{Style.RESET_ALL}")
def log_info(msg: str): print(f"{get_timestamp()} {INFO_COLOR}{msg}{Style.RESET_ALL}")
def log_error(msg: str, file=sys.stderr): print(f"{get_timestamp()} {ERROR_COLOR}!!! {msg}{Style.RESET_ALL}", file=file)
def log_success(msg: str): print(f"{get_timestamp()} {SUCCESS_COLOR}*** {msg}{Style.RESET_ALL}")

# Inizializzazione Client OpenAI
if not OPENAI_API_KEY or not KIEAI_API_KEY:
    log_error("ERRORE CRITICO: OPENAI_API_KEY e KIEAI_API_KEY devono essere impostati.")
    sys.exit(1)
try:
    openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    log_error(f"Impossibile inizializzare il client OpenAI: {e}")
    sys.exit(1)


class Orchestrator:
    def __init__(self):
        for d in [FOLDER_TO_WATCH, OUTPUT_DIR, ARCHIVE_DIR, TRANSCRIPTION_ERROR_DIR, TMP_DIR]:
            d.mkdir(parents=True, exist_ok=True)
        PLAYLIST_FILE.touch(exist_ok=True)
        log_milestone("Orchestratore avviato. Pipeline pronta.")
        log_info(f"Controllo '{FOLDER_TO_WATCH}' ogni {CHECK_INTERVAL_SECONDS} sec. Coda max: {MAX_QUEUE_SIZE}.")

    def get_queue_size(self) -> int:
        try:
            with FileLock(PLAYLIST_LOCK_FILE, timeout=1):
                lines = PLAYLIST_FILE.read_text(encoding="utf-8").splitlines()
                return len([line for line in lines if line.strip()])
        except (Timeout, FileNotFoundError):
            return 0

    def add_to_playlist(self, song_data: dict):
        with FileLock(PLAYLIST_LOCK_FILE):
            with open(PLAYLIST_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(song_data) + "\n")
        log_success(f"Canzone '{Path(song_data['path']).name}' aggiunta alla playlist!")

    def _transcribe_audio(self, audio_path: Path) -> Optional[str]:
        log_info(f"Rilevato file stabile: {audio_path.name}. Invio a Whisper...")
        try:
            with open(audio_path, "rb") as audio_file:
                transcript_result = openai_client.audio.transcriptions.create(
                    model="whisper-1", file=audio_file, language="it"
                )
            text = transcript_result.text.strip()
            if not text or len(text) < MIN_CHARS_TRANSCRIPTION:
                log_error(f"Trascrizione scartata (troppo corta: {len(text)}/{MIN_CHARS_TRANSCRIPTION} caratteri).")
                return None
            log_success("Trascrizione completata.")
            return text
        except Exception as e:
            log_error(f"Errore durante la trascrizione con OpenAI: {e}")
            return None

    def _generate_lyrics(self, text: str) -> Optional[Tuple[str, str]]:
        log_info("Genero riassunto e testo con GPT...")
        try:
            summary_response = openai_client.chat.completions.create(model=SUMMARY_MODEL, messages=[{"role": "system", "content": SUMMARY_SYSTEM_PROMPT}, {"role": "user", "content": text}])
            summary = summary_response.choices[0].message.content.strip()
            
            lyrics_response = openai_client.chat.completions.create(model=LYRICS_MODEL, messages=[{"role": "user", "content": f"{LYRICS_MASTER_PROMPT}\n\n---\n\n{summary}"}])
            lyrics = lyrics_response.choices[0].message.content.strip()
            log_success("Testo della canzone ricevuto.")
            return lyrics, summary
        except Exception as e:
            log_error(f"Errore durante la generazione del testo: {e}")
            return None

    def _generate_music(self, lyrics: str, style: str) -> Optional[Path]:
        """Chiama l'API musicale, esegue il polling e scarica il file."""
        log_info(f"Richiesta generazione musicale. Stile: {style}")
        log_milestone("INVIO ALLA MUSIC API")
        
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {KIEAI_API_KEY}", "Content-Type": "application/json"})
        payload = {"prompt": lyrics, "customMode": True, "model": MUSIC_MODEL, "style": style, "instrumental": False}

        try:
            resp = session.post("https://kieai.erweima.ai/api/v1/generate", json=payload)
            resp.raise_for_status()
            
            response_json = resp.json()
            
            data_field = response_json.get("data")
            if not data_field:
                log_error(f"API non ha restituito un campo 'data' valido. Risposta completa: {json.dumps(response_json)}")
                return None
            
            task_id = data_field.get("taskId")
            if not task_id:
                log_error(f"API non ha restituito un task_id. Risposta completa: {json.dumps(response_json)}")
                return None

        except requests.exceptions.RequestException as e:
            log_error(f"Errore HTTP richiesta iniziale API musicale: {e}"); return None
        except json.JSONDecodeError:
            log_error(f"La risposta dell'API non era un JSON valido. Risposta: {resp.text}"); return None
        
        log_info(f"Richiesta accettata. Task ID: {task_id}. Inizio polling...")
        
        for attempt in range(80):
            time.sleep(10)
            try:
                r = session.get(f"https://kieai.erweima.ai/api/v1/generate/record-info?taskId={task_id}"); r.raise_for_status()
                data = r.json().get("data", {}); status = data.get("status", "UNKNOWN")
                sys.stdout.write(f"\r{DIM_COLOR}{get_timestamp()} Polling... Stato API: {status}{Style.RESET_ALL}")
                sys.stdout.flush()
                
                if status == "SUCCESS":
                    sys.stdout.write("\r" + " " * 80 + "\r")
                    log_success("API musicale ha completato la generazione!")
                    audio_url = data.get("response", {}).get("sunoData", [{}])[0].get("audioUrl")
                    if not audio_url:
                        log_error("Generazione riuscita ma nessun URL audio trovato."); return None
                    
                    log_info("Download del file audio...")
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    safe_style = "".join(filter(str.isalnum, style.replace(' ','_')))[:20]
                    mp3_filepath = OUTPUT_DIR / f"{timestamp}_{safe_style}.mp3"
                    with requests.get(audio_url, stream=True, timeout=120) as r_download:
                        r_download.raise_for_status()
                        with open(mp3_filepath, "wb") as f:
                            for chunk in r_download.iter_content(chunk_size=8192): f.write(chunk)
                    return mp3_filepath

                elif status in ("FAILURE", "SENSITIVE_WORD_ERROR", "GENERATE_AUDIO_FAILED"):
                    log_error(f"Generazione fallita, stato API: {status}"); return None
            
            except requests.exceptions.RequestException as e:
                log_error(f"Errore durante il polling: {e}. Riprovo...")
        
        log_error("Timeout generazione musica."); return None

    def process_next_audio_file(self) -> Optional[dict]:
        try:
            wav_files = sorted(list(FOLDER_TO_WATCH.glob("*.wav")))
            if not wav_files: return None
        except FileNotFoundError:
            FOLDER_TO_WATCH.mkdir(parents=True, exist_ok=True); return None

        audio_path = wav_files[0]
        
        try:
            last_size = -1
            while last_size != audio_path.stat().st_size:
                last_size = audio_path.stat().st_size; time.sleep(1)
        except FileNotFoundError:
            log_error(f"Il file {audio_path.name} è scomparso durante il controllo. Lo ignoro."); return None
        
        print("\n" + "="*70)
        log_milestone(f"Inizio elaborazione per '{audio_path.name}'")
        
        transcribed_text = self._transcribe_audio(audio_path)
        
        if not transcribed_text:
            error_archive_path = TRANSCRIPTION_ERROR_DIR / "audio_files"
            error_archive_path.mkdir(parents=True, exist_ok=True)
            shutil.move(str(audio_path), str(error_archive_path / audio_path.name))
            log_error(f"File audio spostato in quarantena: {error_archive_path / audio_path.name}")
            return None

        result = self._generate_lyrics(transcribed_text)
        if not result: return None
        lyrics, summary = result

        style = random.choice(STYLE_OPTIONS) if STYLE_OPTIONS else "epic cinematic"
        music_path = self._generate_music(lyrics, style)
        if not music_path: return None

        (ARCHIVE_DIR / "Recordings").mkdir(parents=True, exist_ok=True)
        (ARCHIVE_DIR / "Transcripts").mkdir(parents=True, exist_ok=True)
        shutil.move(str(audio_path), str(ARCHIVE_DIR / "Recordings" / audio_path.name))
        (ARCHIVE_DIR / "Transcripts" / f"{music_path.stem}.txt").write_text(transcribed_text, encoding="utf-8")
        music_path.with_suffix('.lyrics.txt').write_text(lyrics, encoding="utf-8")

        return {"path": str(music_path.resolve()), "style": style}

    def run(self):
        while True:
            try:
                if self.get_queue_size() >= MAX_QUEUE_SIZE:
                    sys.stdout.write(f"\r{WARNING_COLOR}{get_timestamp()} Coda piena ({self.get_queue_size()}/{MAX_QUEUE_SIZE}). In pausa...{Style.RESET_ALL}      ")
                    sys.stdout.flush()
                    time.sleep(10)
                    continue
                
                sys.stdout.write(f"\r{DIM_COLOR}{get_timestamp()} In attesa di nuovi file audio...{Style.RESET_ALL}          ")
                sys.stdout.flush()

                song_data = self.process_next_audio_file()
                
                if song_data:
                    self.add_to_playlist(song_data)
                    print("="*70 + "\n")
                else:
                    time.sleep(CHECK_INTERVAL_SECONDS)

            except Exception as e:
                log_error(f"ERRORE FATALE nel ciclo principale: {e}")
                time.sleep(30)

if __name__ == "__main__":
    try:
        orchestrator = Orchestrator()
        orchestrator.run()
    except KeyboardInterrupt:
        print(f"\n{get_timestamp()} {WARNING_COLOR}Orchestratore terminato dall'utente.")
    except Exception as e:
        log_error(f"ERRORE NON GESTITO: {e}", file=sys.stderr)
        sys.exit(1)