from datetime import datetime
from main import run_pipeline

def run():
    print("[agent] Starting IMM opportunity scan…")
    run_pipeline()
    print("[agent] Completed at", datetime.utcnow().isoformat(), "UTC")

if __name__ == "__main__":
    run()
