# ConnectaIACare — Security Best Practices Report

**Data**: 2026-04-19
**Auditor**: Claude (via skill `security-best-practices`)
**Escopo**: `backend/app.py`, `backend/src/handlers/routes.py`, `backend/src/handlers/pipeline.py`, `backend/config/settings.py`, `backend/src/services/audio_preprocessing.py`, `backend/Dockerfile`, `docker-compose.yml`
**References carregadas**: `python-flask-web-server-security.md` (835 linhas), cross-check com `SECURITY.md` deste projeto
**Linguagem/Framework detectado**: Python 3.12 + Flask 3.0.3 + Gunicorn + Next.js 14 (TS). Frontend não auditado neste relatório (fazer em report separado com `javascript-typescript-nextjs-web-server-security.md`)

---

## Resumo Executivo

**Achados totais**: 14 (Critical: 0 · High: 4 · Medium: 5 · Low: 5)

O código em estado MVP está **razoavelmente seguro para ambiente de desenvolvimento e demo interno**, MAS **não está pronto para receber dados reais de paciente**. Os 4 achados High impedem go-live em produção e devem ser corrigidos antes de qualquer conexão com dados de saúde reais.

**Nenhum problema crítico de exploração imediata** (como RCE, SQL injection explorável, debug em prod) foi identificado. A base arquitetural é sólida:
- ✅ SQL 100% parametrizado
- ✅ Subprocess com lista de args, sem `shell=True`
- ✅ Sem `render_template_string` ou SSTI
- ✅ Sem `send_file` com path do usuário
- ✅ Sem open redirects

**Destaque positivo**: o projeto já tem SECURITY.md bem pensado, distinguindo-se de projetos típicos onde segurança é afterthought. Os achados aqui complementam (não contradizem) o que já está documentado.

**Recomendação prioritária**: implementar os 4 High antes de conectar o webhook V6 à produção e receber o primeiro relato real. São ~2-4 horas de trabalho total.

---

## Findings por severidade

### HIGH (4)

---

#### FINDING-001 — SECRET_KEY com default fraco fallback

- **Rule ID**: FLASK-CONFIG-001
- **Severity**: High (Critical em prod)
- **Location**: `backend/config/settings.py:12` + `backend/app.py:15`
- **Evidence**:
  ```python
  # settings.py:12
  secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")

  # app.py:15
  app.config["SECRET_KEY"] = settings.secret_key
  ```
- **Impact**: se `SECRET_KEY` não for setado em produção, silenciosamente usa `"dev-secret-change-in-prod"`. Qualquer atacante que leia este repo público consegue forjar sessions Flask assinadas, tokens de formulário, e qualquer valor cookie-signed.
- **Fix (minimal diff)**:
  ```python
  # settings.py
  secret_key: str = os.getenv("SECRET_KEY", "")

  def __post_init__(self):
      if self.env in ("production", "staging") and (
          not self.secret_key or self.secret_key.startswith("dev-")
      ):
          raise RuntimeError(
              "SECRET_KEY must be set to a strong random value in production"
          )
  ```
- **Mitigation**: até fix, setar `SECRET_KEY` via `openssl rand -hex 32` no `.env` da VPS.
- **False positive notes**: ainda não usamos Flask sessions (sessões estão em Postgres via `session_manager`). Mesmo assim, `SECRET_KEY` é usado internamente pelo Flask para `itsdangerous`, CSRF futuro, etc. Não relaxar.

---

#### FINDING-002 — CORS com wildcard default + credentials=True

- **Rule ID**: FLASK-CORS-001
- **Severity**: High
- **Location**: `backend/app.py:17-18` + `backend/config/settings.py:26`
- **Evidence**:
  ```python
  # settings.py:26
  allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "*")

  # app.py:17-18
  origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
  CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=True)
  ```
- **Impact**: se `ALLOWED_ORIGINS` não for setado, default é `"*"` → processado como `["*"]`. `flask-cors` tecnicamente não envia `Access-Control-Allow-Origin: *` junto com `Access-Control-Allow-Credentials: true` (browser rejeita), mas o resultado é CORS silenciosamente quebrado. Pior: se alguém setar `ALLOWED_ORIGINS=*` pensando ser permissivo, todos os fetches autenticados passam a falhar sem explicação clara. E se uma string maliciosa for injetada via env, CORS pode virar reflexão.
- **Fix**:
  ```python
  # settings.py
  allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "")

  def __post_init__(self):
      if self.env == "production":
          if not self.allowed_origins or "*" in self.allowed_origins:
              raise RuntimeError(
                  "ALLOWED_ORIGINS must be an explicit allowlist in production"
              )
  ```
- **Mitigation**: até fix, NÃO setar `ALLOWED_ORIGINS=*` em nenhum ambiente com auth. Usar lista explícita.
- **False positive notes**: atualmente NÃO usamos cookies para auth (planejado JWT via Authorization header no P1). Enquanto for só Authorization, `supports_credentials=True` é desnecessário — considerar desabilitar até implementar cookies.

---

#### FINDING-003 — `request.remote_addr` usado para audit LGPD sem ProxyFix

- **Rule ID**: FLASK-PROXY-001
- **Severity**: High (contexto LGPD)
- **Location**: `backend/src/handlers/routes.py:107` e `:128`
- **Evidence**:
  ```python
  # routes.py:107 (enroll)
  consent_ip=request.remote_addr or "",

  # routes.py:128 (delete)
  result = svc.delete_enrollment(caregiver_id, settings.tenant_id, ip=request.remote_addr or "")
  ```
- **Impact**: Flask está atrás do Traefik em produção. `request.remote_addr` retornará o IP do Traefik, não do cliente real. Isso significa que **todos os logs de consentimento LGPD ficarão com o mesmo IP** (do proxy), inutilizando o audit trail. Impacto regulatório direto: LGPD Art. 37 exige registro granular de atividades de tratamento — IP idêntico em todos os registros é evidência de rastreabilidade quebrada.
- **Fix**:
  ```python
  # app.py (adicionar após app = Flask(__name__))
  from werkzeug.middleware.proxy_fix import ProxyFix

  if settings.env != "development":
      app.wsgi_app = ProxyFix(
          app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
      )
  ```
  Obs: `x_for=1` assume Traefik é o único proxy. Se houver Cloudflare + Traefik, usar `x_for=2`. **Confirmar setup real antes de ajustar**.
- **Mitigation**: verificar se Traefik já injeta cabeçalho `X-Real-IP` e ler manualmente enquanto ProxyFix não está configurado.
- **False positive notes**: em dev local sem proxy, `request.remote_addr` está correto. Só falha em prod.

---

#### FINDING-004 — Exception leakage via `str(exc)` em resposta HTTP

- **Rule ID**: (não mapeada diretamente no Flask spec — princípio geral de error handling)
- **Severity**: High
- **Location**: `backend/src/handlers/routes.py:34-35`
- **Evidence**:
  ```python
  except Exception as exc:
      logger.exception("webhook_processing_failed", error=str(exc))
      return jsonify({"status": "error", "reason": str(exc)}), 200  # Evolution spera 200
  ```
- **Impact**: `str(exc)` pode conter stack trace parcial, caminhos de arquivo do servidor, mensagens de erro de libs com detalhes internos (ex: `psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "aia_health_patients_pkey"`). Atacante mandando payload manipulado consegue aprender estrutura do backend. Em contexto LGPD+saúde, pode vazar também dados sensíveis (ex: erro de validação que devolve "paciente Maria já existe").
- **Fix**:
  ```python
  import uuid

  except Exception as exc:
      trace_id = str(uuid.uuid4())
      logger.exception("webhook_processing_failed", trace_id=trace_id, error=str(exc))
      return jsonify({
          "status": "error",
          "reason": "internal_error",
          "trace_id": trace_id,  # opcional — permite correlacionar via log interno
      }), 200
  ```
- **Mitigation**: configurar Flask error handlers globalmente para capturar qualquer exception não tratada.
- **False positive notes**: em alguns webhooks é útil retornar detalhes ao operador para debugar. Neste caso (Evolution), o operador não é o atacante, mas o cliente webhook. O custo do trace_id mapped é baixo.

---

### MEDIUM (5)

---

#### FINDING-005 — Sem `MAX_CONTENT_LENGTH` — webhook aceita payloads gigantes

- **Rule ID**: FLASK-LIMITS-001
- **Severity**: Medium
- **Location**: `backend/app.py` (ausência de config)
- **Evidence**: `app.config["SECRET_KEY"]` é setado, mas não `app.config["MAX_CONTENT_LENGTH"]`. O webhook em `routes.py:22-35` chama `request.get_json(silent=True)` sem limite.
- **Impact**: atacante (ou bug no Evolution) pode mandar JSON de 100MB+ que será parseado em memória. DoS por exaustão de RAM nos workers Gunicorn. Com 2 workers configurados, 2 requisições de 500MB derrubam o serviço.
- **Fix**:
  ```python
  # app.py, dentro de create_app()
  app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB
  app.config["MAX_FORM_MEMORY_SIZE"] = 5 * 1024 * 1024  # 5 MB por campo
  app.config["MAX_FORM_PARTS"] = 100
  ```
  Áudio WhatsApp típico é < 1MB. 20MB dá bastante margem mesmo para áudio longo.
- **Mitigation**: adicionar limit também no Traefik (`buffering.maxRequestBodyBytes`).

---

#### FINDING-006 — Sem security headers nas respostas do backend

- **Rule ID**: FLASK-HEADERS-001
- **Severity**: Medium
- **Location**: `backend/app.py` (ausência)
- **Evidence**: nenhum `after_request` hook. Nenhum middleware de headers. Respostas JSON saem nuas.
- **Impact**: mesmo sendo API JSON (sem risco de XSS direto), headers como `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Strict-Transport-Security` protegem contra exploits em browsers modernos (clickjacking de API responses, sniffing, etc.). Especialmente importante se alguma resposta alguma dia vazar PHI via browser.
- **Fix** (opção 1 — Flask):
  ```python
  @app.after_request
  def add_security_headers(resp):
      resp.headers["X-Content-Type-Options"] = "nosniff"
      resp.headers["Referrer-Policy"] = "no-referrer"
      resp.headers["X-Frame-Options"] = "DENY"
      if settings.env == "production":
          resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
      return resp
  ```
  Opção 2 — configurar no Traefik (middleware `secureHeaders`).
- **Mitigation**: já planejado no SECURITY.md §3.1. Implementar antes de prod.
- **False positive notes**: skill "security-best-practices" avisa cautela com HSTS. Em nosso contexto (saúde, LGPD, TLS obrigatório em prod), HSTS É recomendado. Ver CLAUDE.md §"Overrides de skills externas" (criar essa seção).

---

#### FINDING-007 — Webhook retorna 200 em erros de aplicação, não só de parse

- **Rule ID**: (princípio geral de API design)
- **Severity**: Medium
- **Location**: `backend/src/handlers/routes.py:30-35`
- **Evidence**:
  ```python
  try:
      result = get_pipeline().handle_webhook(event)
      return jsonify(result), 200
  except Exception as exc:
      logger.exception("webhook_processing_failed", error=str(exc))
      return jsonify({"status": "error", "reason": str(exc)}), 200  # Evolution spera 200
  ```
- **Impact**: Evolution espera 200 para confirmar entrega, correto. Mas retornar 200 em QUALQUER erro significa que se nosso backend quebrar internamente (ex: DB offline, LLM quota excedida), **o evento é perdido**. Evolution não re-tenta. Em cenário crítico (paciente com dispneia crítica e LLM falhou), silenciosamente perdemos um alerta.
- **Fix**:
  ```python
  # Distingue erros "aceitáveis" (já processado, não adianta retry) de erros transitórios
  try:
      result = get_pipeline().handle_webhook(event)
      return jsonify(result), 200
  except TransientError as exc:  # custom class para DB timeout, LLM rate limit, etc.
      logger.warning("webhook_transient_error", error=str(exc))
      return jsonify({"status": "retry"}), 503  # Evolution vai retentar
  except Exception as exc:
      trace_id = str(uuid.uuid4())
      logger.exception("webhook_permanent_error", trace_id=trace_id)
      # Logar em fila de dead-letter para revisão manual
      return jsonify({"status": "error", "trace_id": trace_id}), 200
  ```
- **Mitigation**: monitorar logs por `webhook_processing_failed` e reprocessar manualmente.
- **False positive notes**: precisa confirmar comportamento de retry do Evolution (5xx retenta? quantas vezes?). Se Evolution desabilita webhook após N 5xx, ajustar estratégia.

---

#### FINDING-008 — `DEBUG=settings.debug` exposto via `app.run` sem fail-closed

- **Rule ID**: FLASK-DEPLOY-002 (parcial)
- **Severity**: Medium (Critical se acontecer em prod)
- **Location**: `backend/app.py:40`
- **Evidence**:
  ```python
  if __name__ == "__main__":
      app.run(host="0.0.0.0", port=5055, debug=settings.debug)
  ```
- **Impact**: em produção, Gunicorn é usado (não `app.run`), então esse bloco nunca executa → OK. Mas `settings.debug = os.getenv("DEBUG", "false").lower() == "true"` e nada impede `DEBUG=true` em prod. Se algum dia alguém rodar `python app.py` em prod por engano (ou configurar Gunicorn erroneamente), debug=True = RCE imediato via Werkzeug debugger.
- **Fix**:
  ```python
  # settings.py __post_init__:
  if self.env == "production" and self.debug:
      raise RuntimeError("DEBUG cannot be enabled in production")
  ```
- **Mitigation**: garantir no Dockerfile que `ENV=production` e `DEBUG=false` em imagem de prod.

---

#### FINDING-009 — `audio_base64` sem limite de tamanho em enroll

- **Rule ID**: FLASK-LIMITS-001 + FLASK-UPLOAD-001
- **Severity**: Medium
- **Location**: `backend/src/handlers/routes.py:92-97`
- **Evidence**:
  ```python
  body = request.get_json(silent=True) or {}
  caregiver_id = body.get("caregiver_id")
  audio_b64 = body.get("audio_base64")
  # ...
  try:
      audio_bytes = base64.b64decode(audio_b64)
  ```
- **Impact**: mesmo com `MAX_CONTENT_LENGTH` (Finding-005), dentro do limite (20MB) ainda cabe um áudio muito maior que o necessário. Um enrollment típico tem ~30KB. Audio de 10MB é absurdo, e passar pelo pipeline de biometria pode travar o worker por segundos.
- **Fix**:
  ```python
  if len(audio_b64) > 5_000_000:  # ~3.5MB binary, sufficient for 2-min mono 16kHz
      return jsonify({"error": "audio_too_large"}), 413
  ```
  Melhor ainda: migrar para Pydantic com `Field(max_length=5_000_000)`.
- **Mitigation**: biometria tem timeout interno; worker não fica preso indefinidamente.

---

### LOW (5)

---

#### FINDING-010 — `TRUSTED_HOSTS` não configurado

- **Rule ID**: FLASK-HOST-001
- **Severity**: Low
- **Location**: `backend/app.py` (ausência)
- **Evidence**: sem `app.config["TRUSTED_HOSTS"]` ou `TRUSTED_HOSTS`.
- **Impact**: Host header injection em raros casos (ex: `url_for(..., _external=True)` para reset de senha). Não usamos isso ainda → low priority.
- **Fix**:
  ```python
  app.config["TRUSTED_HOSTS"] = [
      "demo.connectaiacare.com",
      "app.connectaiacare.com",
      "localhost",
  ]
  ```
- **Mitigation**: Traefik já faz routing por Host → ataques de Host mismatch são mitigados no edge.

---

#### FINDING-011 — Try/except em `get_json` é dead code

- **Rule ID**: (qualidade de código, não segurança direta)
- **Severity**: Low
- **Location**: `backend/src/handlers/routes.py:24-28`
- **Evidence**:
  ```python
  try:
      event = request.get_json(silent=True) or {}
  except Exception as exc:
      logger.error("webhook_json_parse_failed", error=str(exc))
      return jsonify({"status": "error", "reason": "invalid_json"}), 400
  ```
  `silent=True` FAZ `get_json` retornar None em vez de raise. O except nunca executa.
- **Impact**: código morto confunde leitura. Também significa que JSON malformado passa silenciosamente como `{}`, o que pode mascarar bugs.
- **Fix**:
  ```python
  event = request.get_json(silent=True)
  if event is None:
      logger.warning("webhook_invalid_json")
      return jsonify({"status": "error", "reason": "invalid_json"}), 400
  ```

---

#### FINDING-012 — `int(request.args.get("limit", 50))` sem validação

- **Rule ID**: (validação de input)
- **Severity**: Low
- **Location**: `backend/src/handlers/routes.py:60`
- **Evidence**:
  ```python
  limit = int(request.args.get("limit", 50))
  ```
- **Impact**: `?limit=abc` → `ValueError` → 500 Internal Server Error. `?limit=999999999` → query pesada. Nenhum é crítico mas ambos são má prática.
- **Fix**:
  ```python
  try:
      limit = int(request.args.get("limit", 50))
  except ValueError:
      return jsonify({"error": "invalid_limit"}), 400
  limit = max(1, min(limit, 500))  # clamp
  ```

---

#### FINDING-013 — `ffmpeg -i <tempfile>` sem timeout global wrapper

- **Rule ID**: FLASK-INJECT-002 (parcial)
- **Severity**: Low
- **Location**: `backend/src/services/audio_preprocessing.py:66-75`
- **Evidence**:
  ```python
  proc = subprocess.run(
      [
          "ffmpeg", "-v", "error",
          "-i", fin.name,
          "-f", "s16le", "-ar", str(TARGET_SR),
          "-ac", "1",
          "-",
      ],
      capture_output=True,
      timeout=FFMPEG_TIMEOUT_SEC,  # 20s
      check=False,
  )
  ```
  Timeout existe mas `FFMPEG_TIMEOUT_SEC = 20`. Subprocess bem configurado, lista de args, sem shell=True. **Isto aqui é bem feito.** Apontando apenas como lembrança.
- **Impact**: n/a — já está correto.
- **Fix**: nenhum. Mantém 20s como está. Bom exemplo para replicar em outros subprocess futuros.

---

#### FINDING-014 — Sem dependabot / auditoria automatizada de deps

- **Rule ID**: FLASK-SUPPLY-001
- **Severity**: Low
- **Location**: `.github/` (ausência)
- **Evidence**: sem `.github/dependabot.yml`, sem `pip-audit` no CI, sem `npm audit` em CI.
- **Impact**: vulnerabilidades em deps (Flask, Werkzeug, anthropic, deepgram-sdk) passam despercebidas até alguém reparar manualmente.
- **Fix**: criar `.github/dependabot.yml`:
  ```yaml
  version: 2
  updates:
    - package-ecosystem: "pip"
      directory: "/backend"
      schedule: { interval: "weekly" }
    - package-ecosystem: "npm"
      directory: "/frontend"
      schedule: { interval: "weekly" }
    - package-ecosystem: "docker"
      directory: "/backend"
      schedule: { interval: "weekly" }
  ```
- **Mitigation**: rodar `pip-audit` manualmente antes de cada release.

---

## Conclusão e priorização

### Corrigir ANTES de conectar webhook V6 em produção (P0 — 2-4h)
- FINDING-001 (SECRET_KEY fail-closed)
- FINDING-002 (CORS allowlist mandatório)
- FINDING-003 (ProxyFix)
- FINDING-004 (não vazar exception)

### Corrigir antes de 100 pacientes reais (P1 — 1-2h)
- FINDING-005 (MAX_CONTENT_LENGTH)
- FINDING-006 (security headers)
- FINDING-007 (retry correto)
- FINDING-008 (DEBUG fail-closed)
- FINDING-009 (audio size limit)

### Roadmap (P2 — 30min cada)
- FINDING-010 a 014

### O que fizemos bem
- SQL 100% parametrizado — zero SQL injection risk
- Subprocess com args em lista + timeout + sem shell=True
- Arquitetura com SECURITY.md guiando
- Separação clara entre service layer e handler layer
- Type hints + dataclasses + structlog = código legível para auditoria

---

## Próximos passos recomendados

1. **Criar branch `security/p0-hardening`** e implementar Findings 001-004 em commits separados (1 por finding, facilita review)
2. **Atualizar `SECURITY.md`** seção §9 Roadmap marcando estes itens como "em progresso"
3. **Executar skill novamente** em `frontend/src/**/*.tsx` usando `javascript-typescript-nextjs-web-server-security.md` — frontend não foi auditado neste relatório
4. **Criar `CLAUDE.md` seção "Overrides de skills externas"** documentando decisão de sempre HSTS+TLS em prod mesmo que skill genérica seja cautelosa

---

*Relatório gerado seguindo o fluxo da skill `security-best-practices` (tech-leads-club/agent-skills). Referências: `python-flask-web-server-security.md` (v 2026-01-26, 835 linhas).*
