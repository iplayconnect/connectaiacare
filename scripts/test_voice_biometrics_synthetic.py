"""Test biometria de voz com áudios sintéticos (TTS Google).

Valida pipeline Resemblyzer:
  - Enroll com voiceprint_A (voz feminina jovem, pt-BR-Wavenet-A)
  - Enroll com voiceprint_B (voz masculina, pt-BR-Wavenet-D)
  - Verify_1to1(A_id, voice_A_test)  → esperado MATCH
  - Verify_1to1(A_id, voice_B_test)  → esperado MISMATCH
  - Identify_1toN(voice_A_test)      → esperado retornar A_id
  - Identify_1toN(voice_B_test)      → esperado retornar B_id

Cleanup: deleta os 2 caregivers fakes + voice embeddings após teste.

Usa caregivers em tenant_id='_test_synthetic' pra não poluir tenant prod.

Uso:
    docker exec connectaiacare-api python /app/scripts/test_voice_biometrics_synthetic.py
"""
from __future__ import annotations

import base64
import json
import sys
import uuid
from typing import Any

sys.path.insert(0, "/app")


# ─── Textos longos pra qualidade de enrollment Resemblyzer ──────
TEXT_ENROLL_1 = (
    "Olá Sofia, gostaria de relatar que hoje pela manhã a paciente acordou "
    "bem disposta, tomou o café da manhã sem dificuldade, conversou comigo "
    "sobre os filhos. Ela mediu a pressão arterial às nove horas, deu doze "
    "por oito, dentro do esperado. Continuamos com a medicação prescrita "
    "pelo doutor. À tarde ela cochilou um pouco depois do almoço como de "
    "costume. Sem queixas significativas hoje, dia tranquilo na rotina."
)

TEXT_ENROLL_2 = (
    "Bom dia, hoje quero registrar a evolução da paciente. Acordou às sete "
    "horas, tomou banho com auxílio, almoçou bem comendo arroz com frango "
    "grelhado e legumes. A glicemia capilar de hoje foi de cento e vinte, "
    "dentro do alvo. Continua usando as medicações conforme prescrição "
    "médica. Não houve nenhuma intercorrência clínica significativa "
    "durante todo o turno desta manhã, ela está se sentindo bem disposta."
)

TEXT_VERIFY = (
    "Sofia, hoje à noite a dona Maria reclamou de uma dor leve na perna "
    "esquerda mas conseguiu dormir bem após o jantar. Pressão estável."
)

# 2 vozes BEM diferentes pra ter contraste nítido
VOICE_A = "pt-BR-Wavenet-A"  # feminina jovem
VOICE_B = "pt-BR-Wavenet-D"  # masculina


def get_access_token() -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(
        "/secrets/vertex-sa.json",
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    creds.refresh(Request())
    return creds.token


def synthesize(text: str, voice: str, token: str) -> bytes:
    """Chama Google TTS, retorna PCM 16kHz LINEAR16 bytes."""
    import requests
    resp = requests.post(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "input": {"text": text},
            "voice": {"languageCode": "pt-BR", "name": voice},
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": 16000,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    audio_b64 = resp.json()["audioContent"]
    return base64.b64decode(audio_b64)


def create_fake_caregiver(name: str, tenant_id: str) -> str:
    """Insere caregiver fake. Retorna UUID."""
    from src.services.postgres import get_postgres
    cg_id = str(uuid.uuid4())
    get_postgres().execute(
        """INSERT INTO aia_health_caregivers (
              id, tenant_id, full_name, phone, phone_type, external_id
           ) VALUES (%s, %s, %s, %s, 'unknown', %s)""",
        (cg_id, tenant_id, name, f"55_test_{cg_id[:8]}", f"test_{cg_id[:8]}"),
    )
    return cg_id


def cleanup_caregiver(cg_id: str):
    """Deleta caregiver + voice embeddings (CASCADE)."""
    from src.services.postgres import get_postgres
    get_postgres().execute(
        "DELETE FROM aia_health_caregivers WHERE id = %s", (cg_id,),
    )


def run():
    import requests as _req  # noqa
    token = get_access_token()
    print(f"  ✓ Google TTS token obtido (len={len(token)})")

    print("  ⏳ gerando 6 áudios sintéticos (2 enrolls + 1 verify por voz)...")
    audio_a_e1 = synthesize(TEXT_ENROLL_1, VOICE_A, token)
    audio_a_e2 = synthesize(TEXT_ENROLL_2, VOICE_A, token)
    audio_a_verify = synthesize(TEXT_VERIFY, VOICE_A, token)
    audio_b_e1 = synthesize(TEXT_ENROLL_1, VOICE_B, token)
    audio_b_e2 = synthesize(TEXT_ENROLL_2, VOICE_B, token)
    audio_b_verify = synthesize(TEXT_VERIFY, VOICE_B, token)
    print(f"  ✓ A: {len(audio_a_e1)}, {len(audio_a_e2)}, verify={len(audio_a_verify)}")
    print(f"  ✓ B: {len(audio_b_e1)}, {len(audio_b_e2)}, verify={len(audio_b_verify)}")

    TENANT = "_test_synthetic"

    cg_a = create_fake_caregiver("Voice Test User A (synthetic)", TENANT)
    cg_b = create_fake_caregiver("Voice Test User B (synthetic)", TENANT)
    print(f"  ✓ caregivers fake criados: A={cg_a[:8]} B={cg_b[:8]}")

    try:
        from src.services.voice_biometrics_service import get_voice_biometrics
        svc = get_voice_biometrics()

        # ─── ENROLL (2 samples por caregiver pra completar enrollment) ───
        print("\n=== ENROLLMENT ===")
        for i, (audio, label) in enumerate([(audio_a_e1, "A_1"), (audio_a_e2, "A_2")], 1):
            r = svc.enroll(cg_a, TENANT, audio, sample_rate=16000)
            print(f"  enroll {label}: success={r.get('success')} samples={r.get('samples_count')}/{r.get('samples_needed')} complete={r.get('enrollment_complete')}")
        for i, (audio, label) in enumerate([(audio_b_e1, "B_1"), (audio_b_e2, "B_2")], 1):
            r = svc.enroll(cg_b, TENANT, audio, sample_rate=16000)
            print(f"  enroll {label}: success={r.get('success')} samples={r.get('samples_count')}/{r.get('samples_needed')} complete={r.get('enrollment_complete')}")

        # ─── VERIFY 1=1 ───
        print("\n=== VERIFY 1=1 ===")
        v_aa = svc.verify_1to1(cg_a, TENANT, audio_a_verify, sample_rate=16000)
        score_aa = v_aa.get("score", 0)
        ok_aa = v_aa.get("verified") == True
        print(f"  A verify A: verified={ok_aa} score={score_aa:.4f} "
              f"{'✓ MATCH (esperado)' if ok_aa else '✗ NÃO BATEU (esperado match)'}")

        v_ab = svc.verify_1to1(cg_a, TENANT, audio_b_verify, sample_rate=16000)
        score_ab = v_ab.get("score", 0)
        ok_ab = v_ab.get("verified") == False
        print(f"  A verify B: verified={v_ab.get('verified')} score={score_ab:.4f} "
              f"{'✓ MISMATCH (esperado)' if ok_ab else '✗ MATCH ERRADO (esperado mismatch)'}")

        # ─── IDENTIFY 1=N ───
        print("\n=== IDENTIFY 1=N (pool: A, B) ===")
        i_a = svc.identify_1toN(TENANT, audio_a_verify, sample_rate=16000)
        match_a = i_a.get("matched_caregiver_id")
        print(f"  identify A: matched={match_a[:8] if match_a else None} "
              f"score={i_a.get('score', 0):.4f} "
              f"{'✓ A correto' if match_a == cg_a else '✗ ERRADO (esperado A)'}")

        i_b = svc.identify_1toN(TENANT, audio_b_verify, sample_rate=16000)
        match_b = i_b.get("matched_caregiver_id")
        print(f"  identify B: matched={match_b[:8] if match_b else None} "
              f"score={i_b.get('score', 0):.4f} "
              f"{'✓ B correto' if match_b == cg_b else '✗ ERRADO (esperado B)'}")

        # ─── DECISÃO ───
        print("\n" + "=" * 60)
        all_pass = (
            ok_aa and ok_ab
            and match_a == cg_a and match_b == cg_b
        )
        if all_pass:
            print("  ✅ TODOS PASSARAM — pipeline biometria OK")
        else:
            print("  ❌ Algum teste falhou — revisar threshold OR Resemblyzer")
        print(f"  scores: A↔A={score_aa:.4f} (esperado alto)")
        print(f"          A↔B={score_ab:.4f} (esperado baixo)")
        print(f"  separação: {abs(score_aa - score_ab):.4f} "
              f"({'boa' if abs(score_aa - score_ab) > 0.15 else 'fraca'})")

    finally:
        # ─── CLEANUP ───
        print("\n=== CLEANUP ===")
        cleanup_caregiver(cg_a)
        cleanup_caregiver(cg_b)
        print(f"  ✓ caregivers fakes deletados")


if __name__ == "__main__":
    run()
