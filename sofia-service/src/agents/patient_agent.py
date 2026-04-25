"""Sub-agent: Paciente B2C independente.

Características críticas:
- Idoso, possivelmente com voz turva, escrita devagar
- Frases ULTRA curtas (1-2 frases) — TTS soa melhor
- Tom calmo, sem perguntar várias coisas de uma vez
- Detecta queixas e escala se urgente
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
    TEMPERATURE = 0.5       # Naturalidade conversacional
    # Importante: TTS gera melhor com texto curto. Mantemos teto baixo
    # pra forçar Sofia a ser direta com o idoso.
    MAX_TOKENS = 400
    GREETING = "Oi {first_name}, sou a Sofia. Tô por aqui pra te ajudar. Como você tá hoje?"
