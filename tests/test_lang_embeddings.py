import os

import huggingface_hub

from app.lang import embeddings
from app.services.embedding_service import EMBEDDING_MODEL_REPO_ID


def test_langchain_embeddings_use_explicit_cached_snapshot(monkeypatch):
    calls = []
    snapshot_path = "C:/model-cache/snapshot"

    def fake_snapshot_download(**kwargs):
        calls.append(("snapshot", kwargs, os.environ.get("HF_HUB_OFFLINE")))
        return snapshot_path

    def fake_embeddings(**kwargs):
        calls.append(("embeddings", kwargs, os.environ.get("HF_HUB_OFFLINE")))
        return object()

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot_download)
    monkeypatch.setattr(embeddings, "HuggingFaceEmbeddings", fake_embeddings)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    embeddings.get_embeddings.cache_clear()

    embeddings.get_embeddings()

    assert calls == [
        (
            "snapshot",
            {"repo_id": EMBEDDING_MODEL_REPO_ID, "local_files_only": True},
            "1",
        ),
        (
            "embeddings",
            {
                "model_name": snapshot_path,
                "model_kwargs": {"device": "cpu", "local_files_only": True},
                "encode_kwargs": {"normalize_embeddings": True},
            },
            None,
        ),
    ]
