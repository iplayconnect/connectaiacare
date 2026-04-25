"""Sofia Care — fundações multi-persona (Sofia.1).

Módulos:
    persona_detector: resolve persona de uma mensagem (JWT ou phone)
    quota_service:    track de tokens consumidos (sem enforcement nesta fase)
    availability_service: time window de operadores

Sub-pacotes futuros (Sofia.2+):
    orchestrator: classify + dispatch + synthesize
    agents:       sub-agents por persona
    tools:        tool registry com RBAC
"""
