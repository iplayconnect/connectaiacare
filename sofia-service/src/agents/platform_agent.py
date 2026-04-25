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
    MAX_TOKENS = 1000
    # medium: admin precisa respostas certas sobre fluxos de configuração.
    # Errar caminho de UI ou esquecer step custa retrabalho.
    THINKING_LEVEL = "medium"
    GREETING = "Oi {first_name}! Posso te ajudar a navegar, achar pacientes, ver alertas ou explicar como configurar."
