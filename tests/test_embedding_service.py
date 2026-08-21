import json
import os
import sqlite3
import sys
import types

from app.services import embedding_service


def test_embedding_model_prefers_local_cache(monkeypatch):
    calls = []
    cached_model = object()

    def fake_sentence_transformer(model_name, **kwargs):
        calls.append((model_name, kwargs, os.environ.get("HF_HUB_OFFLINE")))
        return cached_model

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=fake_sentence_transformer),
    )
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(embedding_service, "_st_model", None)

    assert embedding_service._get_st_model() is cached_model
    assert calls == [
        (
            embedding_service.EMBEDDING_MODEL_NAME,
            {"local_files_only": True},
            "1",
        )
    ]


def test_embedding_model_downloads_only_when_local_cache_is_missing(monkeypatch):
    calls = []
    downloaded_model = object()

    def fake_sentence_transformer(model_name, **kwargs):
        calls.append((model_name, kwargs, os.environ.get("HF_HUB_OFFLINE")))
        if kwargs.get("local_files_only"):
            raise OSError("model is not cached")
        return downloaded_model

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=fake_sentence_transformer),
    )
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(embedding_service, "_st_model", None)

    assert embedding_service._get_st_model() is downloaded_model
    assert calls == [
        (
            embedding_service.EMBEDDING_MODEL_NAME,
            {"local_files_only": True},
            "1",
        ),
        (embedding_service.EMBEDDING_MODEL_NAME, {}, None),
    ]


def test_migrate_chroma_collection_configs_repairs_old_schema_and_is_idempotent(
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

    assert embedding_service._migrate_chroma_collection_configs(database_path) == 1
    assert database_path.with_suffix(".sqlite3.pre-0.6-config.bak").exists()

    with sqlite3.connect(database_path) as connection:
        repaired_json = connection.execute(
            "SELECT config_json_str FROM collections WHERE id = 'old'"
        ).fetchone()[0]
        unchanged_json = connection.execute(
            "SELECT config_json_str FROM collections WHERE id = 'current'"
        ).fetchone()[0]

    repaired = json.loads(repaired_json)
    assert repaired["_type"] == "CollectionConfigurationInternal"
    assert repaired["hnsw_configuration"]["_type"] == "HNSWConfigurationInternal"
    assert repaired["hnsw_configuration"]["space"] == "cosine"
    assert json.loads(unchanged_json) == {
        "_type": "CollectionConfigurationInternal"
    }
    assert embedding_service._migrate_chroma_collection_configs(database_path) == 0
