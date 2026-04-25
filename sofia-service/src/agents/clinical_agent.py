"""Sub-agent: Médico/Enfermeiro. Foco em apoio à decisão clínica.

Precisão > brevidade. Pode usar modelo Pro quando configurado.
"""
import os

from src.agents.base_agent import BaseAgent


class ClinicalAgent(BaseAgent):
    PERSONA = "medico"
    PROMPT_FILE = "sofia_clinical.txt"
    ALLOWED_TOOL_NAMES = [
        "get_patient_summary",
        "get_patient_vitals",
        "read_care_event_history",
        "list_medication_schedules",
        "query_clinical_guidelines",
        "get_alert_status",
        "search_patients",
        "send_check_in",
        "create_care_event",
    ]
    # Respostas detalhadas com referências (Beers, drug interactions)
    MAX_TOKENS = 1500
    # high: raciocínio clínico profundo (na família 3 ativa thinking interno)
    THINKING_LEVEL = "high"
    # Default Pro pra apoio à decisão clínica — janela 1M, raciocínio
    # profundo, suporta thinking high. Pode trocar via SOFIA_CLINICAL_MODEL
    # (ex: gemini-3-flash-preview pra economia em tenant menor).
    MODEL = os.getenv("SOFIA_CLINICAL_MODEL") or "gemini-3.1-pro-preview"
    GREETING = "Olá {first_name}. Sofia aqui. Posso buscar dados de paciente, diretrizes clínicas ou status de alertas."
