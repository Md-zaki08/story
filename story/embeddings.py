"""Embedding fallback chain (§7), cached to clusters/embeddings.npz.

Order: model2vec -> fastembed -> sentence-transformers -> TF-IDF+SVD.
On this Android/aarch64 host the first three need platform wheels that do not
exist, so the pure numpy/scipy TF-IDF+SVD path is used and flagged in meta.json.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

from . import io_utils

CACHE = io_utils.ROOT / "clusters" / "embeddings.npz"
META = io_utils.ROOT / "clusters" / "meta.json"

_TOKEN_RE = re.compile(r"[a-z][a-z'-]{2,}")
_STOP = set(
    "the and for are but not you all any can had her was one our out day get has him "
    "his how man new now old see two way who boy did its let put say she too use that "
    "with have this will your from they know want been good much some time very when "
    "come here just like long make many more only over such take than them well were "
    "what where which while would there their about into then these those also its".split()
)


def _tokenize(text: str) -> list[str]:
    words = [w for w in _TOKEN_RE.findall(text.lower()) if w not in _STOP]
    bigrams = [words[i] + "_" + words[i + 1] for i in range(len(words) - 1)]
    return words + bigrams


def _try_model2vec():
    from model2vec import StaticModel

    model = StaticModel.from_pretrained("minishlab/potion-base-8M")
    return (
        "model2vec:minishlab/potion-base-8M",
        lambda texts: np.asarray(model.encode(list(texts)), dtype=np.float32),
    )


def _try_fastembed():
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return (
        "fastembed:BAAI/bge-small-en-v1.5",
        lambda texts: np.asarray(list(model.embed(list(texts))), dtype=np.float32),
    )


def _try_sentence_transformers():
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    return (
        "sentence-transformers:all-MiniLM-L6-v2",
        lambda texts: np.asarray(
            model.encode(list(texts), batch_size=32, show_progress_bar=False),
            dtype=np.float32,
        ),
    )


def _try_tfidf():
    import scipy.sparse as sp
    from scipy.sparse.linalg import svds

    state: dict = {}

    def embed(texts: list[str]) -> np.ndarray:
        texts = list(texts)
        docs = [_tokenize(t) for t in texts]
        if "vocab" not in state:
            n = len(docs)
            df: Counter = Counter()
            for toks in docs:
                df.update(set(toks))
            vocab = [w for w, c in df.items() if 2 <= c <= max(2, int(0.6 * n))]
            vocab.sort(key=lambda w: (-df[w], w))
            vocab = vocab[:30000]
            state["vocab"] = {w: i for i, w in enumerate(vocab)}
            state["idf"] = np.array(
                [math.log((1.0 + n) / (1.0 + df[w])) + 1.0 for w in vocab],
                dtype=np.float64,
            )
        vocab = state["vocab"]
        idf = state["idf"]
        rows, cols, vals = [], [], []
        for r, toks in enumerate(docs):
            for w, c in Counter(toks).items():
                j = vocab.get(w)
                if j is not None:
                    rows.append(r)
                    cols.append(j)
                    vals.append((1.0 + math.log(c)) * idf[j])
        X = sp.csr_matrix((vals, (rows, cols)), shape=(len(docs), len(vocab)), dtype=np.float64)
        norms = np.sqrt(np.asarray(X.multiply(X).sum(axis=1)).ravel())
        norms[norms == 0] = 1.0
        X = sp.diags(1.0 / norms) @ X
        k = min(192, min(X.shape) - 1)
        try:
            u, s, _ = svds(X, k=k, random_state=42)
            order = np.argsort(-s)
            emb = u[:, order] * s[order]
        except Exception:
            gram = (X @ X.T).toarray()
            w, v = np.linalg.eigh(gram)
            order = np.argsort(-w)[:k]
            emb = v[:, order] * np.sqrt(np.maximum(w[order], 0.0))
        emb = emb / np.maximum(np.linalg.norm(emb, axis=1, keepdims=True), 1e-12)
        return emb.astype(np.float32)

    return "tfidf-svd:192", embed


_CHAIN = [
    ("model2vec", _try_model2vec),
    ("fastembed", _try_fastembed),
    ("sentence-transformers", _try_sentence_transformers),
    ("tfidf-svd", _try_tfidf),
]


def get_embedder(verbose: bool = True):
    attempts = []
    for name, factory in _CHAIN:
        try:
            method, embed = factory()
            attempts.append({"method": name, "status": "ok"})
            if verbose:
                print(f"[embeddings] using {method}", flush=True)
            return method, embed, attempts
        except Exception as exc:  # noqa: BLE001 - chain must continue
            attempts.append(
                {"method": name, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            )
            if verbose:
                print(f"[embeddings] {name} unavailable: {type(exc).__name__}: {exc}", flush=True)
    raise RuntimeError("All embedding methods in the fallback chain failed")


_EMBEDDER_CACHE = None


def get_cached_embedder(verbose: bool = False):
    global _EMBEDDER_CACHE
    if _EMBEDDER_CACHE is None:
        method, fn, attempts = get_embedder(verbose=verbose)
        _EMBEDDER_CACHE = (method, fn, attempts)
    return _EMBEDDER_CACHE


def embed_texts(texts: list[str], verbose: bool = False):
    """Embed arbitrary texts in the same space as the atoms.

    For the TF-IDF fallback the vocabulary is fit on this batch, so callers
    that need cross-text comparisons must pass all texts in a single call.
    """
    method, fn, _attempts = get_cached_embedder(verbose=verbose)
    return np.asarray(fn(list(texts)), dtype=np.float32), method


def embed_atoms(atom_ids: list[str], texts: list[str], force: bool = False, verbose: bool = True):
    """Return (matrix, method). Reuses clusters/embeddings.npz when ids match."""
    if CACHE.exists() and not force:
        data = np.load(CACHE, allow_pickle=True)
        cached_ids = [str(x) for x in data["atom_ids"]]
        if cached_ids == list(atom_ids):
            meta = io_utils.load_json(META, {}) or {}
            method = meta.get("embedding_method", "cache")
            if verbose:
                print(f"[embeddings] cache hit ({len(atom_ids)} atoms, {method})", flush=True)
            return data["matrix"].astype(np.float32), method

    method, embed, attempts = get_embedder(verbose=verbose)
    if verbose:
        print(f"[embeddings] embedding {len(texts)} texts", flush=True)
    matrix = np.asarray(embed(texts), dtype=np.float32)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        CACHE,
        atom_ids=np.array(list(atom_ids), dtype=object),
        matrix=matrix,
        method=np.array([method]),
    )
    meta = io_utils.load_json(META, {}) or {}
    meta["embedding_method"] = method
    meta["embedding_attempts"] = attempts
    meta["embedding_dim"] = int(matrix.shape[1])
    meta["embedding_count"] = int(matrix.shape[0])
    io_utils.save_json(META, meta)
    if verbose:
        print(f"[embeddings] wrote {CACHE}", flush=True)
    return matrix, method
