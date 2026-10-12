from docuquery.repository import Repository, UserExistsError

import pytest


def test_local_repository_scopes_and_ranks_chunks(tmp_path):
    repository = Repository({
        "SUPABASE_URL": "",
        "SUPABASE_SERVICE_ROLE_KEY": "",
        "LOCAL_DB_PATH": str(tmp_path / "docuquery.sqlite3"),
        "EMBEDDING_DIMENSION": 3,
    })
    repository.save_paper({
        "id": "paper-1", "session_id": "session-a", "title": "Study",
        "filename": "study.pdf", "page_count": 2, "summary": {},
    })
    repository.save_chunks([
        {"id": "c1", "paper_id": "paper-1", "session_id": "session-a", "page_number": 1,
         "section": "Abstract", "content": "retrieval evidence", "embedding": [1.0, 0.0, 0.0]},
        {"id": "c2", "paper_id": "paper-1", "session_id": "session-a", "page_number": 2,
         "section": "Methods", "content": "methods evidence", "embedding": [0.0, 1.0, 0.0]},
    ])
    matches = repository.search_chunks("session-a", "paper-1", [0.9, 0.1, 0.0], limit=2)
    assert matches[0]["id"] == "c1"
    assert matches[0]["page_number"] == 1
    assert repository.get_paper("session-b", "paper-1") is None


def test_local_repository_user_roundtrip(tmp_path):
    repository = Repository({
        "SUPABASE_URL": "",
        "SUPABASE_SERVICE_ROLE_KEY": "",
        "LOCAL_DB_PATH": str(tmp_path / "users.sqlite3"),
        "EMBEDDING_DIMENSION": 3,
    })
    saved = repository.save_user({
        "id": "user-1", "name": "Aditi", "email": "aditi@example.com",
        "password_hash": "hashed-value",
    })
    assert saved["id"] == "user-1"
    found = repository.get_user_by_email("aditi@example.com")
    assert found["name"] == "Aditi"
    assert found["password_hash"] == "hashed-value"
    assert repository.get_user("user-1")["email"] == "aditi@example.com"
    assert repository.get_user_by_email("ghost@example.com") is None

    with pytest.raises(UserExistsError):
        repository.save_user({
            "id": "user-2", "name": "Aditi Two", "email": "aditi@example.com",
            "password_hash": "other-hash",
        })
