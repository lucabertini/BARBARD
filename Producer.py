#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Producer.py: Orchestratore per la generazione di canzoni.
Monitora le trascrizioni pronte, le assegna a dei worker concorrenti
in modo equo e gestisce il ciclo di vita della produzione musicale.
(Versione con percorsi dinamici e portabili, logging stile-immagine,
spinner, CODA LIMITATA e DEBUG)
"""

# --- INIZIO BLOCCO UNIVERSALE DI GESTIONE PERCORSI ---
import os
import sys
from pathlib import Path
from dotenv import load_dotenv # <-- 1. PRIMA MODIFICA

# Trova il percorso assoluto della directory in cui si trova questo script.
# Questo rende il progetto portabile e indipendente dalla directory di lavoro corrente.
try:
    PROJECT_ROOT = Path(__file__).parent.resolve()
except NameError:
    # Fallback per ambienti (es. notebook interattivi) dove __file__ non è definito
    PROJECT_ROOT = Path('.').resolve()

# Imposta la directory di lavoro sulla radice del progetto per coerenza.
os.chdir(PROJECT_ROOT)
load_dotenv() # <-- 2. SECONDA MODIFICA
# --- FINE BLOCCO UNIVERSALE ---

import time
import json
import shutil
import subprocess
from multiprocessing import Pool
from datetime import datetime
from filelock import FileLock, Timeout
from colorama import init, Fore, Style

# --- INIZIALIZZAZIONE GLOBALE ---
init(autoreset=True)

# --- CONFIGURAZIONE CON PERCORSI PORTABILI ---
# I percorsi sono ora costruiti a partire da PROJECT_ROOT per essere robusti.
WORK_DIR = PROJECT_ROOT / "WORK_IN_PROGRESS"
TRANSCRIPT_ARCHIVE_DIR = PROJECT_ROOT / "FROM_TABLES" / "Archive" / "Trascrizioni"
FAILED_TRANSCRIPTS_DIR = WORK_DIR / "failed_processing"
TMP_DIR = PROJECT_ROOT / ".tmp_player"

PLAYLIST_FILE = TMP_DIR / "playlist.queue"
PLAYLIST_LOCK_FILE = TMP_DIR / "playlist.queue.lock"
PRODUCER_LOCK_FILE = TMP_DIR / "producer_instance.lock"
PRODUCER_STATE_FILE = TMP_DIR / "producer_state.json"

# Il percorso dello script da lanciare deve essere assoluto per evitare errori
SONG_GENERATOR_SCRIPT = PROJECT_ROOT / "GenerateSong.py"

MAX_WORKERS= int(os.getenv("MAX_WORKERS", "2"))
MAX_QUEUE_SIZE= int(os.getenv("MAX_QUEUE_SIZE", "2"))




# --- FUNZIONI DI UTILITÀ ---
def get_timestamp():
    return datetime.now().strftime('%H:%M:%S')

def clear_status_line():
    """ Pulisce la riga di stato corrente per evitare sovrapposizioni di output. """
    sys.stdout.write("\r" + " " * 120 + "\r")
    sys.stdout.flush()

def get_queue_size() -> int:
    """ Controlla in modo sicuro la dimensione attuale della playlist. """
    try:
        with FileLock(PLAYLIST_LOCK_FILE, timeout=1):
            if not PLAYLIST_FILE.exists():
                return 0
            lines = PLAYLIST_FILE.read_text(encoding="utf-8").splitlines()
            # Conta solo le righe non vuote
            return len([line for line in lines if line.strip()])
    except Timeout:
        # Se non riesce a ottenere il lock, assume che la coda sia piena per sicurezza
        return MAX_QUEUE_SIZE
    except FileNotFoundError:
        return 0

# --- LOGICA DEL WORKER ---
def create_song_worker(table_number: int, creations_count: int) -> tuple[int, bool]:
    """
    Funzione eseguita da ogni processo worker.
    Lancia GenerateSong.py come sottoprocesso e gestisce l'output.
    """
    clear_status_line()
    print(f"{Fore.CYAN}{get_timestamp()} [ {table_number} ] Equità: Creazioni Precedenti: {creations_count}. COMPONGO!{Style.RESET_ALL}")
    table_work_dir = WORK_DIR / str(table_number)
    transcript_files = sorted(list(table_work_dir.glob("*.txt")))

    try:
        if not transcript_files:
            clear_status_line()
            print(f"{Fore.RED}{get_timestamp()} [ {table_number} ] ERRORE: Nessun file di trascrizione trovato.{Style.RESET_ALL}")
            return table_number, False

        concatenated_text = "\n---\n".join([p.read_text(encoding="utf-8") for p in transcript_files])
        clear_status_line()
        print(f"{Fore.MAGENTA}{get_timestamp()} [ {table_number} ] Avviato. Trovati [{len(transcript_files)}] file. Genero riassunto & lyrics...{Style.RESET_ALL}")

        # Lancia GenerateSong.py usando il percorso assoluto e passando il testo via stdin
        command = [sys.executable, "-u", str(SONG_GENERATOR_SCRIPT), str(table_number)]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=PROJECT_ROOT  # Imposta esplicitamente la CWD per il sottoprocesso
        )
        process.stdin.write(concatenated_text)
        process.stdin.close()
        
        song_data_json = ""
        # Legge l'output dal sottoprocesso in tempo reale
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if not line: continue
            
            clear_status_line()
            
            if line.startswith("MILESTONE:"):
                message = line.replace("MILESTONE: ", "").strip()
                color = Fore.YELLOW + Style.BRIGHT if "INVIO ALL'API" in message else Style.DIM
                print(f"{color}{get_timestamp()} [ {table_number} ] {message}{Style.RESET_ALL}")
            elif line.startswith("{"): # Cattura la riga JSON finale
                song_data_json = line
            else: # Stampa altre informazioni (es. modello e stile)
                print(f"{Style.DIM}{line}{Style.RESET_ALL}")
        
        stderr_output = process.stderr.read()
        return_code = process.wait()

        if return_code != 0:
            clear_status_line()
            print(f"{Fore.RED}{Style.BRIGHT}{get_timestamp()} [ {table_number} ] ERRORE! '{SONG_GENERATOR_SCRIPT.name}' ha fallito (codice {return_code}).{Style.RESET_ALL}")
            print(f"{Fore.RED}{stderr_output.strip()}", file=sys.stderr)
            error_dir = FAILED_TRANSCRIPTS_DIR / str(table_number)
            error_dir.mkdir(parents=True, exist_ok=True)
            for txt_file in transcript_files:
                shutil.move(str(txt_file), str(error_dir / txt_file.name))
            return table_number, False

        if not song_data_json:
            clear_status_line()
            print(f"{Fore.RED}{Style.BRIGHT}{get_timestamp()} [ {table_number} ] ERRORE! Script terminato senza output JSON.{Style.RESET_ALL}")
            return table_number, False
        
        # Aggiunge la canzone alla playlist in modo sicuro
        with FileLock(PLAYLIST_LOCK_FILE):
            with open(PLAYLIST_FILE, "a", encoding="utf-8") as f:
                f.write(song_data_json + "\n")
        
        # Archivia le trascrizioni usate
        archive_sub_dir = TRANSCRIPT_ARCHIVE_DIR / str(table_number)
        archive_sub_dir.mkdir(parents=True, exist_ok=True)
        for txt_file in transcript_files:
            shutil.move(str(txt_file), str(archive_sub_dir / txt_file.name))
        
        clear_status_line()
        print(f"{Fore.GREEN}{Style.BRIGHT}{get_timestamp()} [ {table_number} ] PRODUZIONE COMPLETATA! Canzone inviata alla playlist.{Style.RESET_ALL}")
        return table_number, True
    
    except Exception as e:
        clear_status_line()
        print(f"{Fore.RED}{Style.BRIGHT}{get_timestamp()} [ {table_number} ] ERRORE CRITICO nel worker: {e}{Style.RESET_ALL}", file=sys.stderr)
        # Tenta di spostare i file in quarantena anche in caso di errore generico
        error_dir = FAILED_TRANSCRIPTS_DIR / str(table_number)
        error_dir.mkdir(parents=True, exist_ok=True)
        for txt_file in transcript_files:
            if txt_file.exists():
                shutil.move(str(txt_file), str(error_dir / txt_file.name))
        return table_number, False

# --- GESTORE PRINCIPALE (MANAGER) ---

class ProducerManager:
    def __init__(self, max_workers: int):
        self.max_workers = max_workers
        self.active_jobs = {}  # Dizionario {job_obj: table_number}
        self.creation_counts = self._load_state()
        self.spinner_chars = ['-', '\\', '|', '/']
        self.spinner_index = 0
        
        clear_status_line()
        print(f"{Fore.CYAN}{get_timestamp()} [PRODUCER] Manager avviato. Workers: {max_workers}, Coda max: {MAX_QUEUE_SIZE}.{Style.RESET_ALL}")

    def _load_state(self) -> dict:
        """Carica il contatore di creazioni per ogni tavolo."""
        default_counts = {str(i): 0 for i in range(1, 6)} # Assumiamo tavoli da 1 a 5
        if not PRODUCER_STATE_FILE.exists():
            return default_counts
        try:
            with PRODUCER_STATE_FILE.open('r') as f:
                counts = json.load(f)
                # Assicura che tutti i tavoli base siano presenti
                for i in range(1, 6):
                    if str(i) not in counts:
                        counts[str(i)] = 0
                return counts
        except (json.JSONDecodeError, IOError):
            clear_status_line()
            print(f"{Fore.RED}{get_timestamp()} [PRODUCER] ERRORE: File di stato corrotto. Ricomincio da zero.{Style.RESET_ALL}", file=sys.stderr)
            return default_counts

    def _save_state(self):
        """Salva lo stato aggiornato dei contatori."""
        with PRODUCER_STATE_FILE.open('w') as f:
            json.dump(self.creation_counts, f, indent=2)

    def run(self):
        """Ciclo principale del manager."""
        for d in [TMP_DIR, WORK_DIR, TRANSCRIPT_ARCHIVE_DIR, FAILED_TRANSCRIPTS_DIR]:
            d.mkdir(parents=True, exist_ok=True)
            
        with Pool(processes=self.max_workers) as pool:
            try:
                while True:
                    self.cleanup_finished_jobs()
                    self.assign_new_jobs_fairly(pool)
                    self.print_status_with_spinner()
                    time.sleep(0.2)
            except KeyboardInterrupt:
                clear_status_line()
                print(f"\n{Fore.YELLOW}{get_timestamp()} [PRODUCER] Terminazione richiesta... Attendo fine lavori...{Style.RESET_ALL}")
                pool.close()
                pool.join()
        
        clear_status_line()
        print(f"{Fore.CYAN}{get_timestamp()} [PRODUCER] Lavori terminati. Uscita pulita.{Style.RESET_ALL}")

    def cleanup_finished_jobs(self):
        """Controlla i job terminati e aggiorna lo stato."""
        completed_jobs = {job for job in self.active_jobs if job.ready()}
        if not completed_jobs: return

        for job in completed_jobs:
            table = self.active_jobs.pop(job)
            try:
                _, success = job.get()
                if success:
                    self.creation_counts[str(table)] += 1
                    self._save_state()
            except Exception as e:
                clear_status_line()
                print(f"{Fore.RED}{Style.BRIGHT}{get_timestamp()} [PRODUCER] ERRORE CRITICO ottenendo risultato per tavolo #{table}: {e}{Style.RESET_ALL}", file=sys.stderr)

    def assign_new_jobs_fairly(self, pool):
        """Assegna nuovi lavori in base alla disponibilità e all'equità."""
        # Non assegnare nuovi lavori se la coda di riproduzione è piena o non ci sono worker liberi
        if get_queue_size() >= MAX_QUEUE_SIZE or len(self.active_jobs) >= self.max_workers:
            return

        # Continua ad assegnare finché ci sono slot liberi e materiale pronto
        while len(self.active_jobs) < self.max_workers:
            processing_tables = set(self.active_jobs.values())
            # Trova directory in WORK_DIR che sono numeriche, non in elaborazione, e non vuote
            ready_dirs = [d for d in WORK_DIR.iterdir() if d.is_dir() and d.name.isdigit() and any(d.iterdir())]
            candidate_tables = [d.name for d in ready_dirs if int(d.name) not in processing_tables]
            
            if not candidate_tables:
                break # Nessun lavoro da assegnare

            # Logica di equità: scegli il tavolo con meno creazioni
            table_to_process = min(candidate_tables, key=lambda t: self.creation_counts.get(t, 0))
            creations = self.creation_counts.get(table_to_process, 0)
            
            job_obj = pool.apply_async(create_song_worker, args=(int(table_to_process), creations))
            self.active_jobs[job_obj] = int(table_to_process)

    def print_status_with_spinner(self):
        """Stampa una riga di stato dinamica."""
        active_list = sorted(list(self.active_jobs.values())) if self.active_jobs else 'Nessuno'
        current_queue_size = get_queue_size()
        
        status_msg = f"Slot liberi: {self.max_workers - len(self.active_jobs)}/{self.max_workers} | Coda: {current_queue_size}/{MAX_QUEUE_SIZE} | In Lavorazione: {active_list}"
        
        if current_queue_size >= MAX_QUEUE_SIZE:
             status_msg += f" {Fore.YELLOW}(IN PAUSA){Style.RESET_ALL}"
        
        spinner_char = self.spinner_chars[self.spinner_index]
        line_with_spinner = f"\r{Fore.WHITE}{Style.BRIGHT}[GENERAZIONE] {status_msg} {spinner_char}{Style.RESET_ALL}   "
        
        sys.stdout.write(line_with_spinner)
        sys.stdout.flush()
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_chars)

# --- PUNTO DI INGRESSO DELLO SCRIPT ---
if __name__ == "__main__":
    # --- INIZIO CAMBIAMENTO ---
    # Stampa i parametri di configurazione letti dal file .env (o i valori di default)
    print(f"{Fore.BLUE}{Style.BRIGHT}--- Parametri di Configurazione Caricati ---{Style.RESET_ALL}")
    print(f"{Fore.BLUE}  - MAX_WORKERS    : {MAX_WORKERS}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}  - MAX_QUEUE_SIZE : {MAX_QUEUE_SIZE}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{Style.BRIGHT}-------------------------------------------{Style.RESET_ALL}\n")
    # --- FINE CAMBIAMENTO ---

    try:
        # Usa un file lock per garantire che solo un'istanza del producer sia in esecuzione
        with FileLock(PRODUCER_LOCK_FILE, timeout=0):
            manager = ProducerManager(max_workers=MAX_WORKERS)
            manager.run()
    except Timeout:
        clear_status_line()
        print(f"{Fore.RED}Un'altra istanza del Producer è già in esecuzione.", file=sys.stderr)
    except Exception as e:
        clear_status_line()
        print(f"\n{Fore.RED}ERRORE FATALE nel Producer Manager: {e}{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)