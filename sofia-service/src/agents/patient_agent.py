"""Sub-agent: Paciente B2C independente.

Idoso, possivelmente voz turva. Frases ULTRA curtas (1-2). Tom calmo.
"""
from src.agents.base_agent import BaseAgent


class PatientAgent(BaseAgent):
    PERSONA = "paciente_b2c"
    PROMPT_FILE = "sofia_patient.txt"
    ALLOWED_TOOL_NAMES = [
        "get_my_subscription",
        "list_medication_schedules",
        "confirm_medication_taken",
        "create_care_event",
        "schedule_teleconsulta",
    ]
    # TTS soa melhor com texto curto. Teto agressivo.
    MAX_TOKENS = 400
    # low: idoso precisa de resposta rápida (TTS soa natural), mas
    # interpretar queixa de saúde corretamente é crítico — não usamos
    # minimal. O prompt já força frases ULTRA curtas.
    THINKING_LEVEL = "low"
    GREETING = "Oi {first_name}, sou a Sofia. Tô por aqui pra te ajudar. Como você tá hoje?"
