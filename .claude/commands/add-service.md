---
description: Scaffolda novo serviço backend seguindo o padrão do projeto
argument-hint: <service-name>
---

Crie novo serviço backend em `backend/src/services/<service_name>.py` seguindo padrões do ConnectaIACare.

**Argumento `$ARGUMENTS`**: nome do serviço em snake_case (ex: `medication_interactions_service`).

## Processo

1. **Entenda o propósito**: pergunte ao usuário:
   - O que o serviço faz (1 frase)
   - Quais APIs externas usa (Claude? Deepgram? Sofia Voz? Tecnosenior API?)
   - Se lida com PHI (afeta logging + auditoria)
   - Se tem estado ou é stateless

2. **Leia um exemplo existente** para copiar padrões:
   - `backend/src/services/patient_service.py` (CRUD + fuzzy match)
   - `backend/src/services/analysis_service.py` (LLM + orquestração)
   - `backend/src/services/voice_biometrics_service.py` (modelo pesado + cache)

3. **Crie o arquivo** com esqueleto:

```python
"""<Service Description>.

<Detalhes de comportamento, dependências, thresholds.>
"""
from __future__ import annotations

from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


class <ServiceName>Service:
    def __init__(self):
        self.db = get_postgres()
        # ...outras deps via get_<dep>()

    def <main_method>(self, ...) -> dict[str, Any]:
        logger.info("<service>_method_called param=%s", ...)
        # Validação de input
        # Chamada ao DB ou API externa
        # Audit log se tocar PHI
        return {...}


_instance: <ServiceName>Service | None = None


def get_<service_name>() -> <ServiceName>Service:
    global _instance
    if _instance is None:
        _instance = <ServiceName>Service()
    return _instance
```

4. **Padrões obrigatórios**:
   - ✅ Singleton lazy (`_instance` + `get_<name>()`)
   - ✅ Import via `get_*()` interno (não construtor com args)
   - ✅ Logger structlog (`from src.utils.logger import get_logger`)
   - ✅ Type hints em todos os métodos públicos
   - ✅ Docstring no módulo + métodos principais
   - ✅ Queries parameterizadas (NUNCA f-string em SQL)
   - ✅ Validação de input se recebe de request externo
   - ✅ Try/except com log antes de re-raise em operações DB

5. **Se o serviço toca PHI**:
   - Adicionar audit log via `aia_health_audit_chain` (futuro módulo `audit.py`)
   - Não logar PHI em plaintext (só IDs)
   - Consultar SECURITY.md §3.2 para cada tipo de input

6. **Se o serviço chama LLM**:
   - Usar `get_llm()` e `llm.complete()` ou `llm.complete_json()`
   - Prompts ficam em arquivo separado em `src/prompts/<service>.py` com constante `SYSTEM_PROMPT`
   - Proteger contra prompt injection (SECURITY.md §4): tags XML ao redor de input, validação pós-hoc

7. **Se o serviço chama API externa**:
   - Criar classe cliente separada se for complexo (ver `evolution.py`, `sofia_voice_client.py`)
   - Usar `httpx.Client(timeout=...)` e tratar timeouts explicitamente
   - Keys via `settings.*` nunca hardcoded
   - Retry com backoff para erros transitórios (5xx, timeouts)

8. **Se precisar de tabela nova**:
   - Rodar `/add-migration` antes

9. **Se precisar de rota HTTP**:
   - Adicionar ao `backend/src/handlers/routes.py` (ou criar novo blueprint)
   - Seguir padrão REST + validação + audit

10. **Atualize**:
    - `scripts/verify.sh`: adicionar o novo arquivo ao check de sintaxe
    - `CLAUDE.md` §3 (estrutura de serviços) se o serviço é proeminente

11. **Oferecer commit** com:
    - Mensagem: `feat(service): add <service_name> — <short purpose>`
