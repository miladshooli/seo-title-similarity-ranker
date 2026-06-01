import os
import math
import threading

import requests
from flask import Flask, request, jsonify, render_template

JINA_API_URL = "https://api.jina.ai/v1/embeddings"
SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"
MODEL = "jina-embeddings-v5-text-small"

app = Flask(__name__)

# In-memory embedding cache: text -> embedding vector.
# Lets us re-score after a single title edit without re-embedding every title.
_EMB_CACHE = {}
_CACHE_LOCK = threading.Lock()


def get_embeddings(texts, api_key):
    """Return embeddings for `texts`, in order. Only cache-missing texts hit Jina."""
    with _CACHE_LOCK:
        missing = [t for t in dict.fromkeys(texts) if t not in _EMB_CACHE]

    if missing:
        resp = requests.post(
            JINA_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": MODEL,
                "task": "text-matching",
                "normalized": True,
                "input": missing,
            },
            timeout=60,
        )
        if not resp.ok:
            raise RuntimeError(f"Jina API error {resp.status_code}: {resp.text}")
        data = resp.json()
        fresh = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
        with _CACHE_LOCK:
            for text, emb in zip(missing, fresh):
                _EMB_CACHE[text] = emb

    with _CACHE_LOCK:
        return [_EMB_CACHE[t] for t in texts], len(missing)


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def fetch_serp_titles(keyword, api_key, gl="us", hl="en"):
    """Fetch first-page Google organic results for `keyword` via SearchAPI."""
    resp = requests.get(
        SEARCHAPI_URL,
        params={"engine": "google", "q": keyword, "api_key": api_key, "gl": gl, "hl": hl},
        timeout=45,
    )
    if not resp.ok:
        raise RuntimeError(f"SearchAPI error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    results = []
    for item in data.get("organic_results", []):
        title = (item.get("title") or "").strip()
        if not title:
            continue
        results.append({
            "title": title,
            "source": item.get("source") or item.get("domain") or "",
            "domain": item.get("domain") or "",
            "link": item.get("link") or "",
            "favicon": item.get("favicon") or "",
            "position": item.get("position"),
        })
    return results


@app.route("/")
def index():
    return render_template("index.html", model=MODEL,
                           has_searchapi=bool(os.environ.get("SEARCHAPI_KEY")),
                           has_jina=bool(os.environ.get("JINA_API_KEY")))


@app.route("/api/search", methods=["POST"])
def api_search():
    payload = request.get_json(silent=True) or {}
    keyword = (payload.get("keyword") or "").strip()
    api_key = (payload.get("searchapi_key") or "").strip() or os.environ.get("SEARCHAPI_KEY", "")
    gl = (payload.get("gl") or "us").strip()
    hl = (payload.get("hl") or "en").strip()

    if not api_key:
        return jsonify({"error": "کلید SearchAPI لازم است."}), 400
    if not keyword:
        return jsonify({"error": "کیورد نمی‌تواند خالی باشد."}), 400

    try:
        results = fetch_serp_titles(keyword, api_key, gl, hl)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
    except requests.RequestException as e:
        return jsonify({"error": f"خطا در ارتباط با SearchAPI: {e}"}), 502

    if not results:
        return jsonify({"error": "هیچ نتیجه‌ای برای این کیورد پیدا نشد."}), 404

    return jsonify({"keyword": keyword, "count": len(results), "results": results})


@app.route("/api/rank", methods=["POST"])
def api_rank():
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    items = payload.get("items") or []
    api_key = (payload.get("jina_key") or "").strip() or os.environ.get("JINA_API_KEY", "")

    # Normalize items to [{id, title}]
    norm = []
    for it in items:
        if isinstance(it, str):
            t = it.strip()
            if t:
                norm.append({"id": t, "title": t})
        elif isinstance(it, dict):
            t = (it.get("title") or "").strip()
            if t:
                norm.append({"id": it.get("id", t), "title": t})

    if not api_key:
        return jsonify({"error": "کلید Jina API لازم است."}), 400
    if not query:
        return jsonify({"error": "کوئری نمی‌تواند خالی باشد."}), 400
    if not norm:
        return jsonify({"error": "حداقل یک عنوان لازم است."}), 400

    texts = [query] + [n["title"] for n in norm]
    try:
        embeddings, embedded_count = get_embeddings(texts, api_key)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
    except requests.RequestException as e:
        return jsonify({"error": f"خطا در ارتباط با Jina API: {e}"}), 502

    query_vec = embeddings[0]
    scored = [
        {"id": n["id"], "title": n["title"],
         "score": cosine_similarity(query_vec, vec)}
        for n, vec in zip(norm, embeddings[1:])
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(scored, 1):
        item["rank"] = i

    # embedded_count tells the client how many texts actually hit Jina this call.
    return jsonify({"query": query, "model": MODEL,
                    "embedded": embedded_count, "results": scored})


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "cached_embeddings": len(_EMB_CACHE)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
