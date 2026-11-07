from app.core.database import get_db
from app.modules.assistant.tools import ToolContext, run_tool
from app.modules.auth.models import User


def _get_auth_headers(client, email="docu_user@example.com", password="a-strong-password-123"):
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/token", data={"username": email, "password": password})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_docuvault_seeding_and_list(client):
    headers = _get_auth_headers(client, "docu_seed@example.com")
    res = client.get("/api/docuvault/documents", headers=headers)
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) >= 2
    titles = [d["title"] for d in docs]
    assert any("Architecture" in t for t in titles)
    assert any("Python" in t for t in titles)


def test_docuvault_create_and_search(client):
    headers = _get_auth_headers(client, "docu_search@example.com")

    # Create document
    create_res = client.post(
        "/api/docuvault/documents",
        headers=headers,
        json={
            "title": "Quantum Computing 101",
            "filename": "quantum.txt",
            "content_text": "Qubits exhibit superposition and quantum entanglement. Shor's algorithm can factor integers in polynomial time.",
            "content_type": "text/plain",
            "tags": ["physics", "quantum", "notes"],
        },
    )
    assert create_res.status_code == 201
    doc = create_res.json()
    assert doc["title"] == "Quantum Computing 101"
    assert doc["file_size"] > 0
    doc_id = doc["id"]

    # Search document with query matching content
    search_res = client.get("/api/docuvault/documents/search?q=superposition", headers=headers)
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert "citations" in search_data
    citations = search_data["citations"]
    assert len(citations) >= 1
    first_match = citations[0]
    assert first_match["document_id"] == doc_id
    assert "superposition" in first_match["snippet"].lower()

    # Get single document
    get_res = client.get(f"/api/docuvault/documents/{doc_id}", headers=headers)
    assert get_res.status_code == 200
    assert "polynomial time" in get_res.json()["content_text"]


def test_docuvault_delete(client):
    headers = _get_auth_headers(client, "docu_del@example.com")
    docs = client.get("/api/docuvault/documents", headers=headers).json()
    doc_id = docs[0]["id"]

    del_res = client.delete(f"/api/docuvault/documents/{doc_id}", headers=headers)
    assert del_res.status_code == 204

    # Verify not found
    get_res = client.get(f"/api/docuvault/documents/{doc_id}", headers=headers)
    assert get_res.status_code == 404


def test_learnloop_deck_and_flashcards(client):
    headers = _get_auth_headers(client, "learn_deck@example.com")

    # Seeded decks should exist
    decks_res = client.get("/api/learnloop/decks", headers=headers)
    assert decks_res.status_code == 200
    decks = decks_res.json()
    assert len(decks) >= 1

    # Create a custom deck
    create_deck_res = client.post(
        "/api/learnloop/decks",
        headers=headers,
        json={
            "title": "Machine Learning Fundamentals",
            "description": "Key concepts in modern ML and Deep Learning",
            "initial_cards": [
                {
                    "front": "What is overfitting?",
                    "back": "When a model learns training data noise rather than true underlying patterns.",
                }
            ],
        },
    )
    assert create_deck_res.status_code == 201
    deck = create_deck_res.json()
    deck_id = deck["id"]
    assert deck["card_count"] == 1

    # Add card to deck
    add_card_res = client.post(
        f"/api/learnloop/decks/{deck_id}/cards",
        headers=headers,
        json={
            "front": "What is gradient descent?",
            "back": "An optimization algorithm used to minimize a loss function.",
        },
    )
    assert add_card_res.status_code == 201
    card = add_card_res.json()
    assert card["status"] == "new"
    card_id = card["id"]

    # Review card with 'good'
    review_res = client.post(
        f"/api/learnloop/cards/{card_id}/review",
        headers=headers,
        json={"rating": "good"},
    )
    assert review_res.status_code == 200
    updated_card = review_res.json()
    assert updated_card["review_count"] == 1
    assert updated_card["status"] == "review"

    # Review card with 'easy'
    review_easy = client.post(
        f"/api/learnloop/cards/{card_id}/review",
        headers=headers,
        json={"rating": "easy"},
    )
    assert review_easy.status_code == 200
    assert review_easy.json()["review_count"] == 2
    assert review_easy.json()["status"] == "mastered"


def test_learnloop_generate_deck_from_document(client):
    headers = _get_auth_headers(client, "learn_gen@example.com")

    # Create document
    create_doc = client.post(
        "/api/docuvault/documents",
        headers=headers,
        json={
            "title": "System Design Basics",
            "filename": "sysdesign.txt",
            "content_text": "Caching reduces database load. Sharding horizontally partitions databases across multiple servers. Load balancers distribute incoming network traffic.",
            "content_type": "text/plain",
            "tags": ["architecture"],
        },
    )
    doc_id = create_doc.json()["id"]

    # Generate deck from document
    gen_res = client.post(f"/api/learnloop/decks/generate-from-doc/{doc_id}", headers=headers)
    assert gen_res.status_code == 201
    gen_deck = gen_res.json()
    assert "System Design Basics" in gen_deck["title"]
    assert gen_deck["card_count"] >= 2


def test_docuvault_learnloop_user_isolation(client):
    headers_a = _get_auth_headers(client, "user_iso_a@example.com")
    headers_b = _get_auth_headers(client, "user_iso_b@example.com")

    doc_a = client.post(
        "/api/docuvault/documents",
        headers=headers_a,
        json={
            "title": "Confidential Strategy A",
            "filename": "secret_a.txt",
            "content_text": "Secret project code name Apollo 11.",
            "content_type": "text/plain",
            "tags": ["confidential"],
        },
    ).json()

    # User B should not find User A's document
    res_b = client.get(f"/api/docuvault/documents/{doc_a['id']}", headers=headers_b)
    assert res_b.status_code == 404

    search_b = client.get("/api/docuvault/documents/search?q=Apollo", headers=headers_b).json()
    assert len(search_b["citations"]) == 0


def test_assistant_tools_docuvault_and_learnloop(client):
    headers = _get_auth_headers(client, "assistant_docu_tools@example.com")
    db = next(client.app.dependency_overrides[get_db]())
    user = db.query(User).filter(User.email == "assistant_docu_tools@example.com").first()
    context = ToolContext(user=user, db=db)

    # 1. Search documents tool
    search_res = run_tool("search_documents", {"query": "Architecture"}, context=context)
    assert "Architecture" in search_res or "Found" in search_res

    # 2. Get study flashcards tool
    cards_res = run_tool("get_study_flashcards", {}, context=context)
    assert "Flashcards" in cards_res or "Card" in cards_res

    # 3. Create deck from document tool
    # First get document id
    docs_res = client.get("/api/docuvault/documents", headers=headers)
    first_doc_id = docs_res.json()[0]["id"]
    gen_tool_res = run_tool("create_deck_from_document", {"document_id": first_doc_id}, context=context)
    assert "Created LearnLoop study deck" in gen_tool_res
