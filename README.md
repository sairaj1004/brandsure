# BrandSure

Pre-publication brand review. Check a draft against approved guidelines, facts and claims; every finding has a citation, severity, confidence and a suggested fix; humans approve.

## Run
    pip install -r requirements.txt
    python run.py
    # open http://localhost:8000

Demo logins (password `demo1234`): admin@nova.test, manager@nova.test, reviewer@nova.test, creator@nova.test

Options: `ANTHROPIC_API_KEY` (enable AI step), `BRANDSURE_MODEL`, `BRANDSURE_DEMO=0` (start empty), `BRANDSURE_DATA=/path` (data folder), `PORT`, `HOST`.

## Test
    python -m unittest discover -s tests      # 28 API/engine tests
    python run.py &  python tests/e2e.py      # browser walkthrough (needs playwright)

## Deploy on Render (free)
1. Push this folder to a GitHub repository (only after the hackathon build window is open).
2. On render.com: New + -> Blueprint -> pick the repo. Render reads `render.yaml` and creates the web service.
   (Or New + -> Web Service: build `pip install -r requirements.txt`, start `gunicorn wsgi:app --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:$PORT`.)
3. Wait for the deploy, then open the `.onrender.com` link. Demo logins are the same (password `demo1234`).
Notes: the free plan sleeps when idle (first load ~30 s) and its disk is temporary, so data resets on redeploy or restart and the demo data is re-created automatically. Keep it at 1 worker because the database is a SQLite file.
