# SEO Title Similarity Ranker

A small web app for SEO research: give it a **keyword**, and it

1. fetches the **first‑page Google results** for that keyword (via [SearchAPI](https://www.searchapi.io/)),
2. scores how **semantically similar** each result title is to your keyword (via [Jina embeddings](https://jina.ai/), model `jina-embeddings-v5-text-small`, cosine similarity),
3. shows the ranked titles with a clean **Material‑Design**, RTL (Persian) UI.

Each result row shows **two ranks**:

- a small circular badge — the **embedding‑similarity rank** (this is the sort order),
- a **`رتبهٔ گوگل #N`** chip — the business's original **Google SERP position**.

Titles are **editable**. When you edit one title, only **that** title is re‑embedded
(thanks to a server‑side embedding cache) — the app does **not** re‑query Jina for every
title. The list re‑sorts by embedding score after each change.

![model](https://img.shields.io/badge/embeddings-jina--v5--small-4f46e5) ![stack](https://img.shields.io/badge/stack-Flask%20%2B%20gunicorn%20%2B%20nginx-1e8e3e)

---

## How it works

```
keyword ──▶ /api/search ──▶ SearchAPI (Google)  ──▶ [ {title, business, domain, position} ... ]
                                                          │
            editable titles  ◀───────────────────────────┘
                │
                ▼
        /api/rank ──▶ Jina embeddings (cached) ──▶ cosine(keyword, title) ──▶ sorted by score
```

- **`/api/search`** (POST) — `{ "keyword": "...", "gl": "us", "hl": "en" }` → list of organic
  results with `title`, `source` (business name), `domain`, `link`, `favicon`, `position`.
- **`/api/rank`** (POST) — `{ "query": "...", "items": [{id,title}, ...] }` → each item scored;
  the response field `embedded` tells you how many texts actually hit Jina this call
  (`0` = fully served from cache). Run with **1 gunicorn worker** so the cache is shared.

## API keys

- **SearchAPI key** — set server‑side via the `SEARCHAPI_KEY` env var (see the systemd unit),
  or entered in the UI settings.
- **Jina key** — entered by the user in the UI settings (stored in the browser), or baked in
  server‑side via `JINA_API_KEY`.

## Run locally

```bash
pip install -r requirements.txt
export SEARCHAPI_KEY=your_searchapi_key      # optional; can also be entered in the UI
python app.py                                # http://localhost:8000
```

## Deploy (Debian/Ubuntu, behind nginx)

```bash
sudo SEARCHAPI_KEY=your_searchapi_key bash deploy/setup.sh
# then, for a browser‑trusted HTTPS cert:
sudo certbot --nginx -d your.domain.com --redirect
```

No domain? You can still get a valid Let's Encrypt cert using a wildcard‑DNS host such as
`<server-ip>.nip.io`, e.g. `certbot --nginx -d 203.0.113.10.nip.io --redirect`.

See [`deploy/`](deploy/) for the systemd unit and nginx config.

## Project layout

```
app.py                      Flask backend (search + cached ranking)
templates/index.html        Material‑Design RTL single‑page UI
requirements.txt
deploy/
  jina-ranker.service       systemd unit (1 worker, SEARCHAPI_KEY env)
  nginx.conf                reverse proxy on :80 (add HTTPS with certbot)
  setup.sh                  one‑shot installer
```

## License

MIT — see [LICENSE](LICENSE).
