"""Sub-agent: Operador da plataforma (admin). Foco em FAQ + status agregado."""
from src.agents.base_agent import BaseAgent


class PlatformAgent(BaseAgent):
    PERSONA = "admin_tenant"
    PROMPT_FILE = "sofia_platform.txt"
    ALLOWED_TOOL_NAMES = [
        "get_alert_status",
        "search_patients",
        "get_patient_summary",
        "read_care_event_history",
    ]
    TEMPERATURE = 0.2       # FAQ exige consistência
    MAX_TOKENS = 1000       # Admin lê listas, passos numerados, etc.
    # Admin é desktop-bound — pode usar modelo Pro pra respostas mais ricas
    # quando o user assinar plano B2B premium. Por enquanto Flash.
    GREETING = "Oi {first_name}! Posso te ajudar a navegar, achar pacientes, ver alertas ou explicar como configurar."
