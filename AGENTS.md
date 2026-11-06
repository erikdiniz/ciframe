# AGENTS.md

deciframe is a song-discovery tool for musicians: search by title/artist,
genre, chords you already know, or a famous chord sequence, and it finds
similar songs. Full description: [README.md](README.md).

## Stack

- Backend: Python 3.9, Flask 3.1, gunicorn. Single file (`main.py`) that
  loads `data/top/dataset_final.csv` into memory once at startup. Songs and
  genres stay in memory; only the custom chord-sequence catalog lives in
  SQLite (`db/deciframe.sqlite3`, override with `DECIFRAME_DB`).
- Frontend: AngularJS 1.4.9 + jQuery, loaded from CDN in `static/index.html`,
  no build step. Legacy, and there's no plan to modernize the stack itself —
  but touching it is no longer off-limits when a task needs it; see
  [docs/adr/0003-lift-frontend-freeze.md](docs/adr/0003-lift-frontend-freeze.md).
- Deploy: local-only via Docker for now. No cloud target has been chosen.

## Run locally

Docker (matches how the app actually ships):

```
docker build -t ciframe .
docker run -p 8080:8080 -v deciframe-db:/app/db ciframe
```

The named volume keeps the SQLite sequence catalog across container
recreations. Without `-v`, the database lives in an anonymous volume and is not
reused by a new container. `DECIFRAME_DB` can point to another path.

Or a plain virtualenv:

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py        # serves on :5000 instead of :8080
```

## Verify it's up

```
curl http://localhost:8080/generos
curl http://localhost:8080/sequencias
```

`/generos` should return a JSON array of genre names (e.g. `["Rock", "Samba", ...]`) and `/sequencias` should return the seeded catalog (6 sequences on a fresh database), not an error page. If it hangs on startup, it's still parsing the CSV — give it a few seconds.

## Gotchas

- Editing `data/top/*.csv` requires a restart: it's read once at import time, not per-request.
- `db/deciframe.sqlite3` is created on import and seeded with the 6 original sequences. Deleting it recreates the seeds but loses custom sequences; in Docker, mount the `deciframe-db` volume at `/app/db` to keep it across container recreations. `db/` is ignored by git and Docker, so never bake a local database into the image.
- Every endpoint returns `json.dumps(...)` as a plain string, not `jsonify` — responses come back `Content-Type: text/html`. This is intentional legacy behavior; changing it is a real API change, not a cleanup.
- Check `docs/adr/` before changing the deploy setup — it has a documented reason for its current state.
