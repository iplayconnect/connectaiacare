"""Testes do handshake web → WhatsApp.

Componente: src/handlers/onboarding_web_routes.py
Escopo: validação payload + upsert session + URL wa.me.

Uso Flask test client via fixture `client`.
"""
from __future__ import annotations

import pytest
from flask import Flask

from src.handlers.onboarding_web_routes import bp as onboarding_web_bp


@pytest.fixture
def app(mock_db):
    app = Flask(__name__)
    app.register_blueprint(onboarding_web_bp, url_prefix="/api")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ══════════════════════════════════════════════════════════════════
# Validação
# ══════════════════════════════════════════════════════════════════

class TestValidation:

    def test_missing_name_returns_400(self, client):
        r = client.post("/api/onboarding/start-from-web", json={
            "email": "j@e.com", "phone": "11987654321", "plan_sku": "premium",
        })
        assert r.status_code == 400
        assert r.get_json()["field"] == "full_name"

    def test_single_word_name_fails(self, client):
        r = client.post("/api/onboarding/start-from-web", json={
            "full_name": "Juliana",
            "email": "j@e.com", "phone": "11987654321", "plan_sku": "premium",
        })
        assert r.status_code == 400
        assert r.get_json()["field"] == "full_name"

    def test_invalid_email_fails(self, client):
        r = client.post("/api/onboarding/start-from-web", json={
            "full_name": "Juliana Santos",
            "email": "não-email",
            "phone": "11987654321", "plan_sku": "premium",
        })
        assert r.status_code == 400
        assert r.get_json()["field"] == "email"

    def test_invalid_phone_fails(self, client):
        r = client.post("/api/onboarding/start-from-web", json={
            "full_name": "Juliana Santos",
            "email": "j@e.com",
            "phone": "123",  # curto demais
            "plan_sku": "premium",
        })
        assert r.status_code == 400
        assert r.get_json()["field"] == "phone"

    def test_invalid_plan_fails(self, client):
        r = client.post("/api/onboarding/start-from-web", json={
            "full_name": "Juliana Santos", "email": "j@e.com",
            "phone": "11987654321",
            "plan_sku": "plano_inexistente",
        })
        assert r.status_code == 400
        assert r.get_json()["field"] == "plan_sku"

    def test_empty_payload_fails(self, client):
        r = client.post("/api/onboarding/start-from-web", json={})
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════
# Success path
# ══════════════════════════════════════════════════════════════════

class TestStartFromWebSuccess:

    def test_successful_start_returns_whatsapp_url(self, client, mock_db):
        mock_db.fetch_one_response = None  # nenhuma sessão existente
        mock_db.insert_returning_response = {"id": "sess-123"}
        r = client.post("/api/onboarding/start-from-web", json={
            "full_name": "Juliana Santos Oliveira",
            "email": "juliana@email.com",
            "phone": "5511987654321",
            "plan_sku": "premium",
            "role": "family",
            "utm_source": "google",
            "utm_campaign": "b2c_abril",
        })
        assert r.status_code == 200
        body = r.get_json()
        assert body["status"] == "ok"
        assert body["session_id"] == "sess-123"
        assert body["state"] == "collect_payer_cpf"
        assert body["plan_sku"] == "premium"
        assert body["plan_label"] == "Premium"
        # URL wa.me válida
        assert body["whatsapp_url"].startswith("https://wa.me/")
        assert "Premium" in body["whatsapp_message_preview"]

    def test_persists_collected_data(self, client, mock_db):
        mock_db.fetch_one_response = None
        mock_db.insert_returning_response = {"id": "sess-1"}
        client.post("/api/onboarding/start-from-web", json={
            "full_name": "Juliana Santos", "email": "j@e.com",
            "phone": "11987654321", "plan_sku": "familia",
        })
        inserts = mock_db.queries_matching("aia_health_onboarding_sessions")
        assert any("INSERT" in q[0].upper() for q in inserts)

    def test_normalizes_phone_number(self, client, mock_db):
        """Celular sem 55 recebe prefixo automaticamente."""
        mock_db.fetch_one_response = None
        mock_db.insert_returning_response = {"id": "s1"}
        client.post("/api/onboarding/start-from-web", json={
            "full_name": "Juliana Santos", "email": "j@e.com",
            "phone": "11987654321",  # sem 55
            "plan_sku": "essencial",
        })
        inserts = mock_db.queries_matching("aia_health_onboarding_sessions")
        # Param do phone deve ter vindo com 55 prefix
        found_normalized = False
        for query, params in inserts:
            if "5511987654321" in str(params):
                found_normalized = True
                break
        assert found_normalized

    def test_preserves_utm_params_in_metadata(self, client, mock_db):
        mock_db.fetch_one_response = None
        mock_db.insert_returning_response = {"id": "s1"}
        r = client.post("/api/onboarding/start-from-web", json={
            "full_name": "Juliana Santos", "email": "j@e.com",
            "phone": "11987654321", "plan_sku": "premium",
            "utm_source": "facebook", "utm_campaign": "test",
            "utm_medium": "cpc",
        })
        assert r.status_code == 200
        # A chamada deve ter incluído UTMs no metadata
        inserts = mock_db.queries_matching("aia_health_onboarding_sessions")
        all_params_str = " ".join(str(p) for _, p in inserts)
        assert "facebook" in all_params_str
        assert "test" in all_params_str

    def test_default_role_is_family(self, client, mock_db):
        mock_db.fetch_one_response = None
        mock_db.insert_returning_response = {"id": "s1"}
        r = client.post("/api/onboarding/start-from-web", json={
            "full_name": "Juliana Santos", "email": "j@e.com",
            "phone": "11987654321", "plan_sku": "premium",
        })
        assert r.status_code == 200
        # Sem role no payload, default = "family"
        inserts = mock_db.queries_matching("aia_health_onboarding_sessions")
        all_params = " ".join(str(p) for _, p in inserts)
        assert "family" in all_params


# ══════════════════════════════════════════════════════════════════
# Session status endpoint
# ══════════════════════════════════════════════════════════════════

class TestSessionStatus:

    def test_invalid_uuid_returns_400(self, client):
        r = client.get("/api/onboarding/session/not-a-uuid")
        assert r.status_code == 400

    def test_not_found_returns_404(self, client, mock_db):
        mock_db.fetch_one_response = None
        r = client.get("/api/onboarding/session/550e8400-e29b-41d4-a716-446655440000")
        assert r.status_code == 404

    def test_returns_state(self, client, mock_db):
        mock_db.fetch_one_response = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "state": "collect_payer_cpf",
            "collected_data": {"plan_sku": "premium"},
            "created_at": None,
            "last_message_at": None,
            "completed_at": None,
            "subscription_id": None,
        }
        r = client.get("/api/onboarding/session/550e8400-e29b-41d4-a716-446655440000")
        assert r.status_code == 200
        body = r.get_json()
        assert body["state"] == "collect_payer_cpf"
        assert body["is_completed"] is False
        assert body["plan_sku"] == "premium"
