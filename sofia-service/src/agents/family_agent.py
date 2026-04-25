"""Sub-agent: Familiar. Foco em status do ente + agendar tele."""
from src.agents.base_agent import BaseAgent


class FamilyAgent(BaseAgent):
    PERSONA = "familia"
    PROMPT_FILE = "sofia_family.txt"
    ALLOWED_TOOL_NAMES = [
        "get_patient_summary",
        "get_patient_vitals",
        "read_care_event_history",
        "list_medication_schedules",
        "schedule_teleconsulta",
        "get_my_subscription",
    ]
    MAX_TOKENS = 800
    # medium: familiar pergunta sobre saúde do ente (mãe/pai). Acertar
    # interpretação clínica + tom emocional importa.
    THINKING_LEVEL = "medium"
    GREETING = "Oi {first_name}, sou a Sofia. Quer ver como tá seu familiar, agendar uma teleconsulta ou ver o histórico?"
