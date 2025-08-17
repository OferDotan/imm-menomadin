import os, csv
import src.main as main
import sys
sys.path.insert(0, 'src')
import main as main

def test_run_pipeline_creates_csv(monkeypatch, tmp_path):
    dummy_data = [{
        "source": "TestSource",
        "title": "Suivi et évaluation d’un programme régional (baseline)",
        "issuer": "Example Consulting SARL",
        "country": "Côte d’Ivoire",
        "deadline": "2025-12-31",
        "budget_value": 15000,
        "budget_currency": "EUR",
        "budget_ils": 60000,
        "budget_confidence": "high",
        "summary": "Appel d'offres pour suivi et évaluation, cadre logique, théorie du changement. Baseline et endline."
    }]

    def dummy_fetcher():
        return dummy_data

    monkeypatch.setattr(main, "FETCHERS", [dummy_fetcher])

    original = os.getcwd()
    os.chdir(tmp_path)
    try:
        main.run_pipeline()
        files = [f for f in os.listdir(tmp_path) if f.startswith("opportunities_") and f.endswith(".csv")]
        assert files, "No CSV file generated"
        import csv
        with open(files[0], newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert rows, "CSV is empty"
            assert "source" in reader.fieldnames
            assert "fit_score" in reader.fieldnames
            assert rows[0]["issuer"].lower().find("sarl") != -1
    finally:
        os.chdir(original)
