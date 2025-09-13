from __future__ import annotations

"""
Embeddings utilities using OpenAI Embeddings API (PyTorch for math).

Primary entry point:
- embed_and_mean(abstracts): returns the L2-normalized mean embedding of all
  abstracts. Averages per-abstract embeddings returned by OpenAI.

If you need per-abstract embeddings, use embed_abstracts.
"""

from typing import Iterable, List, Optional, Sequence

import os
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv


_CLIENT: Optional[OpenAI] = None


def get_client(*, base_url: Optional[str] = None, api_key: Optional[str] = None) -> OpenAI:
    """Create and cache an OpenAI client.

    Credentials are read from environment if not provided explicitly.
    """

    # Attempt to load backend/.env relative to this file for local runs
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(env_path)

    global _CLIENT
    if _CLIENT is None:
        if base_url and api_key:
            _CLIENT = OpenAI(base_url=base_url, api_key=api_key)
        elif base_url:
            _CLIENT = OpenAI(base_url=base_url)
        elif api_key:
            _CLIENT = OpenAI(api_key=api_key)
        else:
            _CLIENT = OpenAI()
    return _CLIENT


def embed_abstracts(
    abstracts: Iterable[str],
    *,
    model_name: str = "text-embedding-3-small",
    device: Optional[str] = None,  # kept for API compatibility; unused
    batch_size: int = 64,
    normalize: bool = True,
    output_dtype: Optional[np.dtype | str] = None,
) -> np.ndarray:
    """Embed a list of abstracts via OpenAI embeddings API.

    - Returns a tensor of shape [N, D].
    - If `normalize` is True, L2-normalizes each embedding for cosine similarity.
    - `device` is ignored (remote API), kept to avoid breaking callers.
    """

    texts: List[str] = [a.strip() for a in abstracts if a and a.strip()]
    if not texts:
        raise ValueError("No non-empty abstracts provided")

    client = get_client()
    all_embs: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=model_name, input=batch)
        # Preserve order: sort by the per-batch index
        ordered = sorted(resp.data, key=lambda d: d.index)
        all_embs.extend([d.embedding for d in ordered])

    embs = np.asarray(all_embs, dtype=np.float32)
    if normalize:
        # L2 normalize rows
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        # avoid division by zero
        norms[norms == 0] = 1.0
        embs = embs / norms
    if output_dtype is not None:
        embs = embs.astype(output_dtype)
    return embs


def mean_embedding(
    embeddings: np.ndarray,
    *,
    weights: Optional[Sequence[float] | np.ndarray] = None,
    normalize: bool = True,
) -> np.ndarray:
    """Compute a mean (or weighted mean) embedding over rows.

    - `embeddings`: Tensor [N, D]
    - `weights`: Optional Tensor [N] (non-negative); if provided, computes
      weighted average. Zeros are allowed; if all zeros, raises ValueError.
    - If `normalize` is True, L2-normalizes the resulting vector.
    """

    if embeddings.ndim != 2:
        raise ValueError(f"Expected embeddings shape [N, D], got {tuple(embeddings.shape)}")

    if weights is None:
        mean = embeddings.mean(axis=0)
    else:
        w = np.asarray(weights, dtype=embeddings.dtype)
        if w.ndim != 1 or w.shape[0] != embeddings.shape[0]:
            raise ValueError("weights must be shape [N] matching embeddings [N, D]")
        wsum = w.sum()
        if np.isclose(wsum, 0.0):
            raise ValueError("weights sum to zero")
        mean = (embeddings * w[:, None]).sum(axis=0) / wsum

    if normalize:
        n = np.linalg.norm(mean)
        if n != 0:
            mean = mean / n
    return mean


def embed_and_mean(
    abstracts: Iterable[str],
    *,
    model_name: str = "text-embedding-3-small",
    device: Optional[str] = None,  # unused; kept for compatibility
    batch_size: int = 64,
    normalize: bool = True,
    weights: Optional[Iterable[float]] = None,
    output_dtype: Optional[np.dtype | str] = None,
) -> np.ndarray:
    """Embed a list of abstracts and return the mean embedding.

    This first computes one embedding per abstract, then averages them
    (optionally weighted) to produce a single profile vector.
    """

    embs = embed_abstracts(
        abstracts,
        model_name=model_name,
        device=device,
        batch_size=batch_size,
        normalize=normalize,
        output_dtype=output_dtype,
    )

    w_list: Optional[List[float]] = None
    if weights is not None:
        w_list = list(weights)
        if len(w_list) != embs.shape[0]:
            raise ValueError("weights length must match number of abstracts")

    return mean_embedding(embs, weights=w_list, normalize=normalize)


if __name__ == "__main__":
    # Simple smoke test with dummy abstracts (requires OPENAI_API_KEY)
    print("[embeddings] Running sample test with dummy abstracts...")
    dummy_abstracts = [
        "We propose a transformer-based approach for efficient document understanding and retrieval.",
        "This study explores reinforcement learning for robotic manipulation in unstructured environments.",
        "We introduce a graph neural network for protein interaction prediction and analysis.",
    ]

    embs = embed_abstracts(dummy_abstracts, batch_size=8)
    print(f"Per-abstract embeddings shape: {embs.shape}, dtype: {embs.dtype}")

    mean_vec = embed_and_mean(dummy_abstracts, output_dtype=np.float32)
    print(np.linalg.norm(mean_vec))
    print(f"Mean embedding shape: {mean_vec.shape}, dtype: {mean_vec.dtype}")
