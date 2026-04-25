"""Sub-agent: Cuidador profissional. Foco em relato + medicação."""
from src.agents.base_agent import BaseAgent


class CaregiverAgent(BaseAgent):
    PERSONA = "cuidador_pro"
    PROMPT_FILE = "sofia_caregiver.txt"
    ALLOWED_TOOL_NAMES = [
        "get_patient_summary",
        "get_patient_vitals",
        "list_medication_schedules",
        "confirm_medication_taken",
        "create_care_event",
        "search_patients",
        "schedule_teleconsulta",
    ]
    # Cuidador quer respostas curtas e diretas
    MAX_TOKENS = 700
    # medium: registro clínico precisa precisão (medicação, sintomas).
    # Errar dose ou interpretar relato errado tem custo clínico real.
    THINKING_LEVEL = "medium"
    GREETING = "Oi {first_name}! Pode mandar relato, dúvida sobre medicação ou pedir o status de um paciente."
