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
    TEMPERATURE = 0.3       # Mais determinístico — registro clínico
    MAX_TOKENS = 700        # Cuidador quer respostas curtas
    GREETING = "Oi {first_name}! Pode mandar relato, dúvida sobre medicação ou pedir o status de um paciente."
