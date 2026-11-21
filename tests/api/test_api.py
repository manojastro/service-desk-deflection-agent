from fastapi.testclient import TestClient

from apps.api.app import auth, main


def client_for(database, monkeypatch):
    monkeypatch.setattr(main, "db", database)
    monkeypatch.setattr(auth, "Database", lambda: database)
    return TestClient(main.app)


def login(client, username="employee01", password="demo123"):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_health_readiness_and_auth(database, monkeypatch):
    with client_for(database, monkeypatch) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").json()["status"] == "ready"
        assert client.post("/api/auth/login", json={"username": "employee01", "password": "bad"}).status_code == 401


def test_chat_confirmation_trace_and_dashboard(database, monkeypatch):
    with client_for(database, monkeypatch) as client:
        employee_token = login(client)
        headers = {"Authorization": f"Bearer {employee_token}"}
        first = client.post("/api/chat", headers=headers, json={"message": "Reset my password"})
        assert first.status_code == 200
        assert first.json()["requires_confirmation"]
        session_id = first.json()["session_id"]
        confirmed = client.post(f"/api/chat/{session_id}/confirm", headers=headers, json={"approved": True})
        assert confirmed.json()["deflected"]
        trace = client.get(f"/api/sessions/{session_id}/trace", headers=headers)
        assert trace.status_code == 200
        assert trace.json()["tool_calls"][0]["tool_name"] == "reset_password"
        assert client.get("/api/dashboard", headers=headers).status_code == 403
        ops = login(client, "support", "support123")
        dashboard = client.get("/api/dashboard", headers={"Authorization": f"Bearer {ops}"})
        assert dashboard.status_code == 200
        assert dashboard.json()["summary"]["total_conversations"] >= 19


def test_unknown_chat_creates_ticket(database, monkeypatch):
    with client_for(database, monkeypatch) as client:
        token = login(client)
        response = client.post("/api/chat", headers={"Authorization": f"Bearer {token}"}, json={"message": "My quantum toaster is smoking"})
        assert response.status_code == 200
        assert response.json()["status"] == "escalated"
        assert response.json()["ticket_id"].startswith("TKT-")

