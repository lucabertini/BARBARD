import datetime
import time
import sys

# --- Classe per i colori del terminale ---
class AnsiColors:
    GREEN = '\033[92m'  # Colore verde
    RESET = '\033[0m'   # Resetta il colore al default

# --- Funzione per stampare messaggi con timestamp (formato solo ora) ---
def print_with_timestamp(message, color=""):
    """
    Stampa un messaggio preceduto da un timestamp attuale.
    Format: [HH:MM:SS.ms] messaggio
    """
    # MODIFICA: La stringa di formattazione ora esclude la data (%Y-%m-%d)
    timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
    
    print(f"[{timestamp}] {color}{message}{AnsiColors.RESET}")
    sys.stdout.flush()

# --- Sequenze di messaggi ---
# MODIFICA: La prima riga è stata divisa in due elementi della lista
messages_phase_1 = [
    "Background running …",
    "Style: Old fashioned Crooner Style",
    "Keeping …",
    "Listening…",
    "Analysing …",
    "Reframing …",
    "Extending …"
]

# MODIFICA: Anche qui la prima riga è stata divisa
messages_phase_2 = [
    "Music running …",
    "Style: Old fashioned Crooner Style",
    "Keeping …",
    "Listening…",
    "Analysing …",
    "Reframing …",
    "Extending …"
]

# --- Funzione principale ---
def main():
    """
    Esegue la logica principale dello script.
    """
    end_time = datetime.datetime.now() + datetime.timedelta(minutes=0.8)
    
    print("-" * 50)

    # FASE 1: Loop per il primo minuto
    while datetime.datetime.now() < end_time:
        for message in messages_phase_1:
            if datetime.datetime.now() >= end_time:
                break
            
            print_with_timestamp(message)
            time.sleep(0.3) 

    print("-" * 50)
    
    # TRANSIZIONE: Stampa il messaggio "Playing" in verde
    print_with_timestamp("Extension: Queuing", color=AnsiColors.GREEN)
    print_with_timestamp("Preparing to Merge", color=AnsiColors.GREEN)
    
    print("-" * 50)
    time.sleep(1)

    # FASE 2: Loop infinito
    while True:
        for message in messages_phase_2:
            print_with_timestamp(message)
            time.sleep(0.3)

# --- Blocco di esecuzione ---
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProcesso interrotto dall'utente. Uscita.")
        sys.exit(0)