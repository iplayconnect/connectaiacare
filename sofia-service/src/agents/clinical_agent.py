"""Sub-agent: Médico/Enfermeiro. Foco em apoio à decisão clínica.

Característica crítica: precisão > brevidade. Pode usar modelo Pro
quando disponível. Tools de query clínica disponíveis exclusivamente.
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
    TEMPERATURE = 0.2       # Precisão clínica > criatividade
    MAX_TOKENS = 1500       # Respostas mais detalhadas com referências
    # Permite override pra Pro quando o tenant assinar plano clínico
    # (env: SOFIA_CLINICAL_MODEL=gemini-2.5-pro). Default = mesma base.
    MODEL = os.getenv("SOFIA_CLINICAL_MODEL") or None
    GREETING = "Olá {first_name}. Sofia aqui. Posso buscar dados de paciente, diretrizes clínicas ou status de alertas."
