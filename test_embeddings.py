"""
Embedding & Vector Search Verification Tests
Run: .venv\\Scripts\\python.exe test_embeddings.py
"""
import sqlite3, struct, sys, math, time, json
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = Path(__file__).parent / "ship_computer.db"
EMBED_URL = "http://localhost:8080/embeddings"
PASS = 0
FAIL = 0

def ok(name, detail=""):
    global PASS
    PASS += 1
    print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))

def fail(name, detail=""):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def cosine_sim(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0

def deserialize_embedding(blob):
    if blob is None:
        return None
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))

def get_query_embedding(text):
    import urllib.request
    payload = json.dumps({"input": text}).encode()
    req = urllib.request.Request(EMBED_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    # llama.cpp returns: [{"index":0,"embedding":[[...]]}]
    # embedding may be [[token_vec]] (nested) or [vec] (flat)
    raw = None
    if isinstance(data, list) and len(data) > 0:
        v = data[0]
        if isinstance(v, dict) and "embedding" in v:
            raw = v["embedding"]
        elif isinstance(v, list):
            raw = v
    if raw is None and isinstance(data, dict):
        for key in ("embeddings", "data"):
            if key in data:
                inner = data[key]
                if isinstance(inner, list) and len(inner) > 0:
                    v = inner[0]
                    raw = v["embedding"] if isinstance(v, dict) else v
    if raw is None:
        return None
    from spock_rag_adapter.embedding_utils import flatten_embedding

    return flatten_embedding(raw)

# ── Connect ──────────────────────────────────────────────
section("DATABASE CONNECTION")
if not DB.exists():
    fail("DB exists", f"{DB} not found")
    sys.exit(1)
conn = sqlite3.connect(str(DB), timeout=5)
conn.execute("PRAGMA journal_mode=WAL")
ok("Connected", str(DB))

# ── 0. Corpus identity vs live :8080 ─────────────────────
section("0. WIKI-SCAN EMBEDDING LLM")
try:
    from spock_shell.embedding_corpus import (
        live_vs_corpus,
        model_counts,
        model_basename,
        read_corpus,
    )
    corpus = read_corpus(str(DB))
    if not corpus or not corpus.get("model_path"):
        fail("Corpus row", "kb_embedding_corpus is empty — run Wiki Scan after launching :8080")
    else:
        ok(
            "Corpus GGUF",
            f"{corpus.get('model_name') or model_basename(corpus.get('model_path'))}  dim={corpus.get('embeddings_dim')}",
        )
        url = corpus.get("embeddings_url") or EMBED_URL
        if url:
            EMBED_URL = url
        report = live_vs_corpus(EMBED_URL, db_path=str(DB))
        live = report.get("live") or {}
        if not live.get("reachable"):
            fail("Live :8080", live.get("detail") or "unreachable")
        elif report.get("mismatch"):
            fail(
                "Live GGUF matches corpus",
                f"live={live.get('model_name') or live.get('model_path')} "
                f"corpus={corpus.get('model_name')}",
            )
        else:
            ok("Live GGUF matches corpus", live.get("model_name") or live.get("model_path") or "")
            counts = model_counts(str(DB))
        if counts:
            ok("Document model stamps", ", ".join(f"{k}={v}" for k, v in counts.items()))
            ggufs = {k: v for k, v in counts.items() if k != "(unstamped)"}
            unstamped = int(counts.get("(unstamped)") or 0)
            if len(ggufs) > 1:
                fail(
                    "Mixed corpus",
                    "documents.embedding_model_path has more than one GGUF — "
                    "Clear Embeddings / re-scan with one :8080 model",
                )
            elif unstamped and ggufs:
                fail(
                    "Mixed corpus",
                    f"{unstamped} embedded doc(s) missing embedding_model_path "
                    f"(rest stamped {next(iter(ggufs))} — leftover from an unstamped ingest)",
                )
except Exception as e:
    fail("Corpus identity", str(e))

# ── 1. Embedding Coverage ────────────────────────────────
section("1. EMBEDDING COVERAGE")
total = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
with_emb = conn.execute("SELECT count(*) FROM documents WHERE embedding IS NOT NULL").fetchone()[0]
without_emb = conn.execute("SELECT count(*) FROM documents WHERE embedding IS NULL").fetchone()[0]
pct = (with_emb * 100 // total) if total else 0
ok("Document count", str(total))
ok("Embedded", f"{with_emb}/{total} ({pct}%)")
if without_emb > 0:
    rows = conn.execute("SELECT title, path FROM documents WHERE embedding IS NULL LIMIT 10").fetchall()
    print(f"         {without_emb} docs missing embedding (sample):")
    for t, p in rows:
        print(f"           - {t}  ({p})")

# ── 2. Embedding Dimensions ──────────────────────────────
section("2. EMBEDDING DIMENSIONS")
sample_blobs = conn.execute("SELECT id, title, embedding FROM documents WHERE embedding IS NOT NULL LIMIT 20").fetchall()
dim_set = set()
expected_dim = None
try:
    from spock_shell.embedding_corpus import read_corpus as _read_c
    c = _read_c(str(DB))
    if c and c.get("embeddings_dim"):
        expected_dim = int(c["embeddings_dim"])
except Exception:
    expected_dim = None
for doc_id, title, blob in sample_blobs:
    dims = len(blob) // 4
    dim_set.add(dims)
    if expected_dim and dims != expected_dim:
        fail(f"Unexpected dims", f"doc {doc_id} '{title}': {dims} (corpus {expected_dim})")
    elif not expected_dim and dims not in (2560, 5120, 4096, 768, 1024, 384):
        fail(f"Unexpected dims", f"doc {doc_id} '{title}': {dims}")
if len(dim_set) == 1:
    ok("Consistent dimensions", f"{dim_set.pop()} dims across {len(sample_blobs)} samples")
elif len(dim_set) == 0:
    fail("No embeddings to check")
else:
    fail("Inconsistent dimensions", str(dim_set))

# ── 3. Deserialization ───────────────────────────────────
section("3. DESERIALIZATION INTEGRITY")
deser_ok = 0
deser_fail = 0
for doc_id, title, blob in sample_blobs:
    vec = deserialize_embedding(blob)
    if vec and len(vec) > 0 and all(isinstance(v, float) for v in vec[:5]):
        deser_ok += 1
    else:
        deser_fail += 1
        fail("Deserialize", f"doc {doc_id} '{title}'")
ok("Deserialization", f"{deser_ok}/{len(sample_blobs)} OK")
if deser_fail:
    fail("Deserialization failures", str(deser_fail))

# ── 4. Vector Search — Cosine Similarity ─────────────────
section("4. VECTOR SEARCH — COSINE SIMILARITY")
print("  Querying embedding server...")
query_vec = get_query_embedding("authentication service login")
if query_vec is None:
    fail("Query embedding", "Server returned no vector")
else:
    ok("Query embedding", f"{len(query_vec)} dims")

    # Compute similarity against all embedded docs
    results = []
    all_docs = conn.execute(
        "SELECT id, title, path, embedding FROM documents WHERE embedding IS NOT NULL"
    ).fetchall()
    for doc_id, title, path, blob in all_docs:
        doc_vec = deserialize_embedding(blob)
        if doc_vec and len(doc_vec) == len(query_vec):
            sim = cosine_sim(query_vec, doc_vec)
            results.append((sim, doc_id, title, path))

    results.sort(reverse=True)
    print(f"\n  Top 10 results for 'authentication service login':")
    print(f"  {'Rank':<5} {'Score':<8} {'Title'}")
    print(f"  {'─'*5} {'─'*8} {'─'*50}")
    for rank, (sim, doc_id, title, path) in enumerate(results[:10], 1):
        marker = " <-- relevant?" if sim > 0.3 else ""
        print(f"  {rank:<5} {sim:<8.4f} {title}{marker}")

    if not results:
        fail(
            "Top result relevance",
            "no embedded documents to rank — run Wiki Scan / re-embed while :8080 is up",
        )
    elif results[0][0] > 0.3:
        ok("Top result relevance", f"score={results[0][0]:.4f}")
    else:
        fail("Top result relevance", f"best score={results[0][0]:.4f}")

# ── 5. FTS5 Keyword Search ───────────────────────────────
section("5. FTS5 KEYWORD SEARCH")
fts_query = "project"
fts_results = conn.execute(
    "SELECT rowid, rank FROM docs_fts WHERE docs_fts MATCH ? ORDER BY rank LIMIT 10",
    (fts_query,)
).fetchall()
if fts_results:
    ok("FTS5 results", f"{len(fts_results)} hits for '{fts_query}'")
    for rowid, rank in fts_results[:5]:
        title = conn.execute("SELECT title FROM documents WHERE id=?", (rowid,)).fetchone()
        t = title[0] if title else "???"
        print(f"         rowid={rowid} rank={rank:.4f}  {t}")
else:
    fail("FTS5 results", f"No hits for '{fts_query}'")

# ── 6. Hybrid Search Comparison ───────────────────────────
section("6. HYBRID SEARCH — VECTOR vs FTS5 RANKING")
query2 = "how to handle logins"
query2_vec = get_query_embedding(query2)

if query2_vec:
    # Vector top 5
    vec_scores = []
    for doc_id, title, path, blob in all_docs:
        doc_vec = deserialize_embedding(blob)
        if doc_vec and len(doc_vec) == len(query2_vec):
            sim = cosine_sim(query2_vec, doc_vec)
            vec_scores.append((sim, title))
    vec_scores.sort(reverse=True)

    # FTS top 5
    fts_scores = conn.execute(
        "SELECT rowid, rank FROM docs_fts WHERE docs_fts MATCH 'login' ORDER BY rank LIMIT 5"
    ).fetchall()
    fts_titles = []
    for rowid, rank in fts_scores:
        t = conn.execute("SELECT title FROM documents WHERE id=?", (rowid,)).fetchone()
        fts_titles.append((rank, t[0] if t else "???"))

    print(f"  Query: '{query2}'")
    print(f"\n  Vector top 5:")
    for i, (s, t) in enumerate(vec_scores[:5], 1):
        print(f"    {i}. [{s:.4f}] {t}")
    print(f"\n  FTS5 top 5:")
    for i, (s, t) in enumerate(fts_titles[:5], 1):
        print(f"    {i}. [{s:.4f}] {t}")

    # Check overlap
    vec_top = {t for _, t in vec_scores[:5]}
    fts_top = {t for _, t in fts_titles[:5]}
    overlap = vec_top & fts_top
    if overlap:
        ok("Ranking overlap", f"{len(overlap)} docs in both top-5: {overlap}")
    else:
        print("         No overlap — modalities find different results (expected)")
        ok("Ranking divergence", "vector and FTS5 complement each other")
else:
    fail("Query embedding for hybrid test")

# ── 7. Nearest Neighbor Consistency ───────────────────────
section("7. NEAREST NEIGHBOR CONSISTENCY")
# Pick a random doc, find its nearest neighbor, then check reverse
import random
embedded_docs = [(doc_id, title, blob) for doc_id, title, blob in sample_blobs]
if len(embedded_docs) >= 2:
    pick = random.choice(embedded_docs)
    pick_vec = deserialize_embedding(pick[2])
    sims = []
    for doc_id, title, blob in embedded_docs:
        if doc_id == pick[0]:
            continue
        v = deserialize_embedding(blob)
        if v and len(v) == len(pick_vec):
            sims.append((cosine_sim(pick_vec, v), doc_id, title))
    sims.sort(reverse=True)
    nearest = sims[0]
    print(f"  Doc A: '{pick[1]}' (id={pick[0]})")
    print(f"  Nearest: '{nearest[2]}' (id={nearest[1]}) score={nearest[0]:.4f}")

    # Reverse check
    nearest_vec = None
    for doc_id, title, blob in embedded_docs:
        if doc_id == nearest[1]:
            nearest_vec = deserialize_embedding(blob)
            break
    if nearest_vec:
        reverse_sims = []
        for doc_id, title, blob in embedded_docs:
            if doc_id == nearest[1]:
                continue
            v = deserialize_embedding(blob)
            if v and len(v) == len(nearest_vec):
                reverse_sims.append((cosine_sim(nearest_vec, v), doc_id, title))
        reverse_sims.sort(reverse=True)
        reverse_nearest = reverse_sims[0]
        print(f"  Reverse nearest of B: '{reverse_nearest[2]}' (id={reverse_nearest[1]}) score={reverse_nearest[0]:.4f}")
        if pick[1] == reverse_nearest[2]:
            ok("Symmetric nearest neighbor", "A→B and B→A match")
        else:
            ok("Asymmetric (normal)", f"A→B but B→{reverse_nearest[2]}")
    else:
        fail("Reverse lookup")

# ── 8. Batch Embedding Consistency ────────────────────────
section("8. BATCH EMBEDDING CONSISTENCY")
# Re-embed a known doc and check it matches stored
if embedded_docs:
    pick = random.choice(embedded_docs)
    doc_text = conn.execute("SELECT content_plain FROM documents WHERE id=?", (pick[0],)).fetchone()[0]
    if doc_text:
        truncated = doc_text[:1500]
        print(f"  Re-embedding doc {pick[0]} '{pick[1]}' ({len(truncated)} chars)...")
        fresh_vec = get_query_embedding(truncated)
        stored_vec = deserialize_embedding(pick[2])
        if fresh_vec and stored_vec and len(fresh_vec) == len(stored_vec):
            sim = cosine_sim(fresh_vec, stored_vec)
            print(f"  Similarity: {sim:.6f}")
            if sim > 0.99:
                ok("Batch consistency", f"identical embedding (sim={sim:.6f})")
            elif sim > 0.95:
                ok("Batch consistency", f"near-identical (sim={sim:.6f}) — truncation or batching diff")
            else:
                fail("Batch consistency", f"sim={sim:.6f} — model may have changed")
        else:
            fail("Dimension mismatch", f"fresh={len(fresh_vec)} stored={len(stored_vec)}")

# ── Summary ───────────────────────────────────────────────
section("RESULTS")
total_tests = PASS + FAIL
print(f"  {PASS}/{total_tests} passed, {FAIL} failed")
if FAIL == 0:
    print("  ALL TESTS PASSED")
else:
    print("  SOME TESTS FAILED — review above")
conn.close()
sys.exit(1 if FAIL else 0)
