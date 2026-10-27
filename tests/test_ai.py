import os
os.environ["FORCE_SQLITE"] = "1"
os.environ["SECRET_KEY"] = "test-secret-key"

import json
import re
import pytest

import ai_service
import analytics
import app as flask_app
import db


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["name"] = "Admin Staff"
        sess["role"] = "Admin"
        sess["customer_id"] = 1
        sess["customer_name"] = "Demo Customer"
    return client


def test_logged_out_redirects(client):
    """Staff AI routes must require login and redirect logged-out requests."""
    res = client.post("/ai/chat", json={"question": "What is our revenue?"})
    assert res.status_code in (302, 401)
    if res.status_code == 302:
        assert "/login" in res.headers["Location"]


def test_too_long_question_returns_400(auth_client):
    """Questions exceeding MAX_QUESTION_CHARS should be rejected with 400."""
    long_q = "a" * (ai_service.MAX_QUESTION_CHARS + 10)
    res = auth_client.post("/ai/chat", json={"question": long_q})
    assert res.status_code == 400
    data = res.get_json()
    assert data["code"] == "too_long"


def test_missing_api_key_returns_503(auth_client, monkeypatch):
    """When GROQ_API_KEY is missing or empty, return 503 not_configured."""
    monkeypatch.setenv("GROQ_API_KEY", "")
    res = auth_client.post("/ai/chat", json={"question": "How are sales doing?"})
    assert res.status_code == 503
    data = res.get_json()
    assert data["code"] == "not_configured"


def test_chat_success_for_logged_in_staff(auth_client, monkeypatch):
    """Mock Groq call should return 200 with answer and model."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_mock_key_123456789")
    monkeypatch.setattr(ai_service, "_complete", lambda msgs, max_tokens=1200: ("mock answer", "mock-model"))

    res = auth_client.post("/ai/chat", json={"question": "What is our current monthly profit?", "history": []})
    assert res.status_code == 200
    data = res.get_json()
    assert data["answer"] == "mock answer"
    assert data["model"] == "mock-model"
    assert "topics" in data


def test_ai_status_endpoint(auth_client):
    """GET /ai/status should return status dict."""
    res = auth_client.get("/ai/status")
    assert res.status_code == 200
    data = res.get_json()
    assert "configured" in data
    assert "model" in data
    assert "sdk_installed" in data


def test_one_shot_ai_endpoints(auth_client, monkeypatch):
    """Summary, recommendations, and explanations should work when mocked."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_mock_key_123456789")
    monkeypatch.setattr(ai_service, "_complete", lambda msgs, max_tokens=1200: ("mock answer", "mock-model"))

    res_sum = auth_client.post("/ai/summary")
    assert res_sum.status_code == 200
    assert res_sum.get_json()["answer"] == "mock answer"

    res_rec = auth_client.post("/ai/recommendations")
    assert res_rec.status_code == 200
    assert res_rec.get_json()["answer"] == "mock answer"

    res_health = auth_client.post("/ai/explain/health")
    assert res_health.status_code == 200
    assert res_health.get_json()["answer"] == "mock answer"


def test_context_for_running_out_contains_forecast_and_no_emails():
    """Verify built context contains FORECAST_model_estimates and no email addresses."""
    q = "which products are running out"
    ctx = ai_service.build_context(q)
    assert "FORECAST_model_estimates" in ctx
    ctx_str = json.dumps(ctx)
    # Check that no customer or staff emails are leaked in AI context
    email_matches = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", ctx_str)
    assert email_matches == []


def test_all_existing_pages_return_200(auth_client):
    """Ensure all core web pages continue to load with HTTP 200."""
    pages = [
        "/",
        "/profit",
        "/cashflow",
        "/expenses",
        "/anomalies",
        "/inventory",
        "/alerts",
        "/orders",
        "/sales",
        "/forecast",
        "/health-score",
        "/insights",
        "/staff",
        "/shop",
        "/shop/login",
        "/health"
    ]
    for path in pages:
        res = auth_client.get(path)
        assert res.status_code == 200, f"Page {path} returned status {res.status_code}"
