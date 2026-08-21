import json
import os
import sqlite3
import sys
import types
import time
from concurrent.futures import ThreadPoolExecutor

import huggingface_hub
import pytest

from app.services import embedding_service


def test_embedding_model_initialization_is_single_flight(monkeypatch):
    created_models = []
    cached_model = object()

    def slow_sentence_transformer(_model_name, **_kwargs):
        time.sleep(0.05)
        created_models.append(cached_model)
        return cached_model

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=slow_sentence_transformer),
    )
    monkeypatch.setattr(
        huggingface_hub,
        "snapshot_download",
        lambda **_kwargs: "C:/model-cache/snapshot",
    )
    monkeypatch.setattr(embedding_service, "_st_model", None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        models = list(executor.map(lambda _index: embedding_service._get_st_model(), range(2)))

    assert models == [cached_model, cached_model]
    assert created_models == [cached_model]


def test_embedding_model_prefers_local_cache(monkeypatch):
    calls = []
    snapshot_calls = []
    cached_model = object()
    cached_path = "C:/model-cache/snapshot"

    def fake_sentence_transformer(model_name, **kwargs):
        calls.append((model_name, kwargs, os.environ.get("HF_HUB_OFFLINE")))
        return cached_model

    def fake_snapshot_download(**kwargs):
        snapshot_calls.append((kwargs, os.environ.get("HF_HUB_OFFLINE")))
        return cached_path

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=fake_sentence_transformer),
    )
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot_download)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(embedding_service, "_st_model", None)

    assert embedding_service._get_st_model() is cached_model
    assert calls == [
        (
            cached_path,
            {"local_files_only": True},
            "1",
        )
    ]
    assert snapshot_calls == [
        (
            {
                "repo_id": embedding_service.EMBEDDING_MODEL_REPO_ID,
                "local_files_only": True,
            },
            "1",
        )
    ]


def test_embedding_model_downloads_only_when_local_cache_is_missing(monkeypatch):
    calls = []
    downloaded_model = object()

    def fake_sentence_transformer(model_name, **kwargs):
        calls.append((model_name, kwargs, os.environ.get("HF_HUB_OFFLINE")))
        return downloaded_model

    def fake_snapshot_download(**_kwargs):
        raise FileNotFoundError("model is not cached")

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=fake_sentence_transformer),
    )
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot_download)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(embedding_service, "_st_model", None)

    assert embedding_service._get_st_model() is downloaded_model
    assert calls == [
        (embedding_service.EMBEDDING_MODEL_NAME, {}, None),
    ]


def test_chroma_client_rejects_newer_store_schema_without_mutating_it(
    tmp_path,
):
    database_path = tmp_path / "chroma.sqlite3"
    schema = {
        "keys": {
            "#embedding": {
                "float_list": {
                    "vector_index": {
                        "config": {"space": "cosine"},
                    }
                }
            }
        }
    }

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE collections (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                config_json_str TEXT,
                schema_str TEXT
            )
            """
        )
        connection.executemany(
            "INSERT INTO collections VALUES (?, ?, ?, ?)",
            [
                ("old", "hotlist_topics", "{}", json.dumps(schema)),
                (
                    "current",
                    "user_documents",
                    json.dumps({"_type": "CollectionConfigurationInternal"}),
                    None,
                ),
            ],
        )

    with pytest.raises(
        embedding_service.IncompatibleChromaStoreError,
        match="新版 Chroma",
    ):
        embedding_service._validate_chroma_store_compatibility(database_path)

    with sqlite3.connect(database_path) as connection:
        old_json = connection.execute(
            "SELECT config_json_str FROM collections WHERE id = 'old'"
        ).fetchone()[0]
        unchanged_json = connection.execute(
            "SELECT config_json_str FROM collections WHERE id = 'current'"
        ).fetchone()[0]

    assert json.loads(old_json) == {}
    assert json.loads(unchanged_json) == {
        "_type": "CollectionConfigurationInternal"
    }
    assert not database_path.with_suffix(".sqlite3.pre-0.6-config.bak").exists()
