# IMM Opportunity Scanner Agent (Desktop-ready)

Repo structure expected at repo root:
- .github/workflows/imm_scanner.yml  (weekly + manual trigger, runs tests first)
- .github/workflows/tests.yml        (pytest on push/PR)
- src/main.py                        (scanner)
- src/agent.py                       (runner)
- tests/test_pipeline.py             (mocked unit test)
- requirements.txt
- Dockerfile
