# ConnectaIACare — Contexto para Sessões Claude

> **LEIA ESTE ARQUIVO INTEIRO antes de executar qualquer modificação.**
> Atualizado: 2026-04-19

---

## 1. O que é o ConnectaIACare

Plataforma de cuidado integrado com IA para **idosos e pacientes crônicos**, focando inicialmente em **geriatria**. É uma **stack nova, isolada** da ConnectaIA produção para evitar risco ao CRM pagante.

**Parceiros:**
- **ConnectaIA** (este projeto) — camada de IA, conversação, orquestração
- **Tecnosenior** — IoT ambiente, SPAs, central humana 24h (parceria existente)
- **MedMonitor** — dispositivos clínicos homologados
- **Amparo** — atenção primária digital, monitoramento crônicos

**Stack**:
- **Backend**: Python 3.12 + Flask + Gunicorn
- **Frontend**: Next.js 14 + TypeScript + Tailwind + shadcn/ui
- **DB**: PostgreSQL 16 + pgvector + pg_trgm
- **Cache**: Redis 7
- **WhatsApp**: Evolution API (instância V6, número 555189592617)
- **STT**: Deepgram nova-2 pt-BR
- **LLM**: Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 via Anthropic SDK
- **Voz (saída)**: Sofia Voz (Grok) via HTTP em `sofia-service:5030`
- **Biometria de voz**: Resemblyzer 256-dim embeddings + pgvector
- **Infra**: Docker Compose em VPS Hostinger (compartilha nó com ConnectaIA)

**Domínios** (ADR-013 — usamos subdomínios do `connectaia.com.br` até formalização JV):
- `demo.connectaia.com.br` → API backend (webhook WhatsApp + REST)
- `care.connectaia.com.br` → frontend dashboard médico
- Futuro (pós-JV): migrar para domínio dedicado via novo par de A-records

---

## 2. Regra de Ouro do Fluxo de Alteração

**Local → Git → VPS. NUNCA direto na VPS.**

```
[Seu Mac]  ──git commit + push──▶  [GitHub main]  ──git pull + rebuild──▶  [VPS]
 (edição)      (canônico)            (fonte de código)                  (runtime)
```

### PROIBIDO
1. Editar arquivo direto na VPS (`vi`, `nano`, `sed -i`, `python -c`)
2. `rsync` ou `scp` Local→VPS
3. Commitar sem compilar/testar sintaxe localmente
4. Sobrescrever arquivo na VPS sem baixar e comparar antes

### OBRIGATÓRIO
1. Antes de editar: `git status && git log --oneline -5`
2. Editar no Local (neste diretório)
3. Testar sintaxe: `python3 -c "import ast; ast.parse(open('file.py').read())"`
4. `git add` específico (não `git add .`)
5. `git commit` com mensagem clara
6. `git push origin main`
7. Na VPS: `cd /root/connectaiacare && bash scripts/deploy.sh`
8. Verificar logs: `docker compose logs --tail 50 api`

**Detalhes completos**: `docs/DEPLOY.md`

---

## 3. Arquitetura do Backend

### Arquivo central
**`backend/app.py`** — Flask app entrypoint. Gunicorn aponta para `app:app`.

### Estrutura de serviços

```
backend/src/
├── services/                          # Lógica de domínio
│   ├── postgres.py                   # Pool de conexão + helpers
│   ├── evolution.py                  # WhatsApp via Evolution API
│   ├── transcription.py              # Deepgram STT
│   ├── llm.py                        # Claude (Haiku/Sonnet/Opus)
│   ├── patient_service.py            # CRUD + fuzzy match paciente
│   ├── report_service.py             # CRUD relatos + histórico
│   ├── analysis_service.py           # Extração entidades + análise clínica
│   ├── session_manager.py            # Estado de conversa WhatsApp
│   ├── sofia_voice_client.py         # HTTP → sofia-service (ligações)
│   ├── voice_biometrics_service.py   # Identificação cuidador (Resemblyzer)
│   └── audio_preprocessing.py        # VAD, normalização, quality scoring
├── handlers/
│   ├── pipeline.py                   # Orquestrador do fluxo áudio→análise
│   └── routes.py                     # Blueprints HTTP (webhook + API)
├── prompts/
│   ├── patient_extraction.py         # Prompt extração de entidades
│   └── clinical_analysis.py          # Prompt análise clínica + classificação
└── utils/
    └── logger.py                      # structlog configurado
```

### Fluxo end-to-end (cuidador manda áudio WhatsApp → análise)

```
Evolution webhook (POST /webhook/whatsapp)
    ↓
pipeline.handle_webhook() → _handle_audio()
    ↓
evolution.download_media_base64()                    # baixa áudio do WhatsApp
    ↓
voice_biometrics.identify_caregiver_by_voice()       # identifica cuidador (1:1 por phone + 1:N)
    ↓
transcription.transcribe_bytes()                     # Deepgram pt-BR
    ↓
analysis.extract_entities()                          # Claude Haiku (rápido)
    ↓
patients.best_match()                                # fuzzy match + pg_trgm
    ↓
evolution.send_media() com foto + confirmação        # WhatsApp
    ↓
[aguarda SIM/NÃO em session_manager]
    ↓
analysis.analyze()                                   # Claude Opus com histórico
    ↓
reports.save_analysis()                              # persiste análise + classification
    ↓
evolution.send_text() com resumo estruturado         # WhatsApp resposta
    ↓
[se classification in {urgent, critical}]
    ↓
sofia_voice.place_call()                             # liga para familiar
```

### Injeção de dependência
Serviços usam padrão **singleton lazy** via `get_<service>()`. Não fazer construtores com heavy init. Lazy-load de modelos pesados (Resemblyzer ~50MB só carrega na primeira chamada).

**Regra**: se criar novo serviço, adicionar função `get_<service>()` no módulo.

### Cadeia de dependências (ordem de init importa)
Nosso DI é mais leve que o da ConnectaIA, mas ainda há ordem implícita:
```
get_postgres()              → primeiro (ninguém depende de outro)
get_evolution()             → só precisa de env vars
get_transcription()         → só precisa de env vars
get_llm()                   → só precisa de env vars
get_session_manager()       → depende de get_postgres()
get_patient_service()       → depende de get_postgres()
get_report_service()        → depende de get_postgres()
get_analysis_service()      → depende de get_llm() + get_report_service()
get_voice_biometrics()      → depende de get_postgres() + lazy loads Resemblyzer
get_sofia_voice()           → só precisa de env vars
get_pipeline()              → orquestra todos os acima
```
Se criar novo serviço: (1) seguir padrão `get_<name>()`, (2) injetar deps via `get_*()` internamente, (3) lazy-load qualquer recurso pesado.

### Containers esperados em runtime
```
connectaiacare-api          (backend Flask + Gunicorn, porta 5055)
connectaiacare-frontend     (Next.js, porta 3000)
connectaiacare-postgres     (pgvector/pgvector:pg16, porta 5433 exposta local)
connectaiacare-redis        (Redis 7, porta 6380 exposta local)
```
Verificar: `docker compose ps` — todos devem estar `healthy`.

### Serviços externos consumidos (compartilhados com ConnectaIA)
- `sofia-service:5030` — Sofia Voz (via network Docker — não precisa expor)
- `evolution_v2` — Evolution API (compartilhado com ConnectaIA, instância V6 repontada)
- Anthropic Claude API (HTTPS)
- Deepgram API (HTTPS)

---

## 4. Estrutura do Banco de Dados

PostgreSQL 16 (imagem `pgvector/pgvector:pg16`), database `connectaiacare`, user `postgres`.

**Prefixo**: `aia_health_*` para distinguir de outros sistemas.

### Tabelas

| Tabela | Descrição | FKs críticas |
|--------|-----------|-------------|
| `aia_health_patients` | Pacientes com conditions/medications/allergies em JSONB | — |
| `aia_health_caregivers` | Cuidadores profissionais | — |
| `aia_health_reports` | Relatos (áudio + transcrição + análise + classification) | → patients, caregivers |
| `aia_health_conversation_sessions` | Estado WhatsApp (awaiting_confirmation, etc.) | — |
| `aia_health_audit_chain` | Auditoria imutável (hash-chain) | — |
| `aia_health_alerts` | Alertas gerados por análise | → patients, reports |
| `aia_health_voice_embeddings` | Embeddings 256-dim (pgvector) | → caregivers |
| `aia_health_voice_consent_log` | Consentimentos LGPD + calibration logs | → caregivers |

### Extensões
- `pgcrypto` — hash, UUID generation
- `uuid-ossp` — UUID v4
- `pg_trgm` — fuzzy string matching para nome de paciente
- `vector` (pgvector) — busca por similaridade de embeddings

### Migrations
- `001_initial_schema.sql` — tabelas core
- `002_mock_patients.sql` — 8 pacientes mock + 1 cuidadora (Joana)
- `003_voice_biometrics.sql` — pgvector + tabelas de biometria

Rodar: `bash scripts/init_db.sh` (local) ou `docker compose exec ...` (VPS).

---

## 5. Regras de Ouro para Alterações

### NUNCA
1. Editar direto na VPS (quebra git como fonte canônica)
2. Colocar dados médicos em blockchain (ver SECURITY.md — LGPD conflita)
3. Usar `string concatenation` em queries SQL — sempre `%s` params
4. Passar input do usuário direto para prompt de LLM sem sanitização
5. Logar dados de paciente em plaintext (PII/PHI)
6. Commitar `.env`, chaves, tokens, credenciais
7. Criar nova tabela sem prefixo `aia_health_`
8. Chamar Sofia Voice sem validar destinatário (risco: ligar pro paciente/família errado)

### SEMPRE
1. Testar sintaxe antes de commit (`python3 -c "import ast; ast.parse(...)"`)
2. Queries parametrizadas: `cur.execute("WHERE id = %s", (id,))`
3. Validar input em TODO endpoint público
4. Usar `structlog` ao invés de `print()`
5. Documentar qualquer dependência externa nova em `docs/DEPLOY.md`
6. Atualizar `scripts/verify.sh` quando adicionar arquivos críticos
7. Consultar `SECURITY.md` antes de qualquer endpoint que toque PHI
8. Considerar LGPD Art. 11 (dados sensíveis) em qualquer feature nova

---

## 6. Compliance e Regulação

### LGPD
- Dados médicos são **sensíveis** (Art. 5º II + Art. 11).
- ConnectaIA é **operador**; SPA/clínica é **controlador**; paciente é **titular**.
- DPA obrigatório com cada cliente controlador.
- Direitos do titular expostos via API (`GET/DELETE /api/patients/<id>/data`).
- Auditoria de acesso em `aia_health_audit_chain` (hash-chain).
- Retenção: áudios 90 dias, transcrição + análise tempo indeterminado (parte do prontuário).

### CFM 2.314/2022 (Telemedicina)
- **Médico é responsável final** pela decisão clínica.
- IA apoia, IA **não decide autonomamente** (prompts explicitam isso).
- Qualquer classificação `critical` aciona humano (enfermagem + família via Sofia Voz).
- Prontuário deve ser legível pelo médico (nada escondido em prompts).

### ANVISA (Classe II - SaMD)
- Em pausa para MVP. Quando passar de piloto, iniciar processo de registro.
- Classe II abre cobrança via ANS Rol (R$ 50-150k + consultoria regulatória).

### HL7 FHIR R4
- Padrão adotado como meta (não implementado ainda).
- Migrations futuras vão normalizar tabelas para consumir/exportar FHIR resources.

---

## 6.1. MCP (Model Context Protocol) — futuro

O projeto ainda **não usa** MCP, mas é o caminho planejado para integrações externas:
- **MedMonitor API** → MCP server que expõe tools (`get_vital_signs`, `list_devices`).
- **Tecnosenior API** → MCP server (`get_patient_profile`, `sync_sensor_events`).
- **FHIR gateway** → MCP server padronizado para qualquer hospital (`fhir_patient_get`, `fhir_observation_list`).

Quando implementarmos, seguir padrão usado no ConnectaIA:
- Pasta `mcp-servers/<nome>/` com `server.py` (FastMCP) + `Dockerfile` + `requirements.txt`
- Container dedicado no `docker-compose.yml`
- Config por tenant (YAML) listando quais servers estão habilitados
- Cliente `MCPManager` em `src/services/mcp/` que descobre tools via `tools/list`

Ver `docs/MCP_ROADMAP.md` (a criar quando começarmos) para detalhes.

---

## 7. Como Rodar Localmente

### Primeira vez
```bash
cd "/Users/macnovo/.../Python/ConnectaIACare"

cp backend/.env.example backend/.env
# Editar .env com as chaves: ANTHROPIC_API_KEY, DEEPGRAM_API_KEY, etc.

bash scripts/quickstart.sh
# Sobe postgres+pgvector, redis, api, frontend
# Roda migrations + seed de 8 pacientes mock
# Health check na porta 5055
```

### Depois de mudanças no backend
```bash
docker compose restart api
# ou com rebuild se mexeu em Dockerfile ou requirements:
docker compose up -d --build api
```

### Ver logs
```bash
docker compose logs -f api
docker compose logs --tail 100 api
```

### Acessar DB
```bash
docker compose exec postgres psql -U postgres -d connectaiacare
```

### Testar biometria de voz com áudio real
```bash
python scripts/test_voice_biometrics.py --audio path/to/audio.ogg
python scripts/test_voice_biometrics.py --compare audio1.ogg audio2.ogg
```

---

## 8. Como Fazer Deploy na VPS

**Detalhes completos em `docs/DEPLOY.md`**. Resumo:

```bash
# LOCAL
git add <arquivos>
git commit -m "feat: descrição"
git push origin main

# NA VPS
ssh root@72.60.242.245
cd /root/connectaiacare
bash scripts/deploy.sh         # detecta mudanças e rebuild só do afetado
```

---

## 9. Histórico de Problemas Conhecidos

| Problema | Causa | Solução |
|----------|-------|---------|
| ffmpeg not available | Container sem ffmpeg | Dockerfile já instala; se local, `brew install ffmpeg` ou fallback PCM |
| Resemblyzer OOM | Torch puxou CUDA que não existe | `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| Webhook 500 em produção | LLM timeout ou API key inválida | Verificar logs; todos os erros retornam 200 p/ Evolution não desabilitar |
| pgvector não instalado | Imagem postgres sem extensão | Usar `pgvector/pgvector:pg16`, não `postgres:16-alpine` |
| Quality "audio_silencioso" em preprocess | Áudio vazio ou ruído puro | Cuidador precisa falar claramente ≥ 2s |
| Identificação biometria falsa positiva | Cache desatualizado | `voice_bio.invalidate_cache()` manual |

---

## 10. Checklist para Nova Sessão

Ao iniciar nova sessão Claude Code neste projeto:

1. Ler **CLAUDE.md** (este arquivo)
2. Ler **SECURITY.md** (threat model + checklist)
3. Ler **docs/DEPLOY.md** (se for mexer em deploy)
4. Ler **STATUS.md** (estado atual do sprint)
5. Verificar git: `git status && git log --oneline -5`
6. Se for mexer em backend: `docker compose ps` (containers de pé?)
7. Se for mexer em biometria: consultar `audio_preprocessing.py` + `voice_biometrics_service.py` (thresholds, cache)

### Regras CRÍTICAS
- **Fluxo**: SEMPRE Local → git commit → push → VPS git pull → rebuild
- **Stack isolada**: ConnectaIACare NÃO toca em código ou DB da ConnectaIA
- **V6 WhatsApp**: repontada para ConnectaIACare (reverter comando em DEPLOY.md se precisar)
- **Prompt injection**: inputs do paciente/cuidador para LLM devem ser sanitizados
- **SQL injection**: sempre parameterized queries
- **Nenhum dado de paciente no log em plaintext**
- **`aia_health_audit_chain`**: toda ação sensível deve inserir linha de auditoria

---

## 10.1. Planos e pendências em aberto

| Item | Prazo | Detalhe |
|------|-------|---------|
| **Cloudflare A-records** em `connectaia.com.br` | Seg 20/04 | `demo.` e `care.` → 72.60.242.245 |
| **Criação repo GitHub** `iplayconnect/connectaiacare` | ✅ Feito | Push inicial já aplicado |
| **Preenchimento .env com chaves reais** | Seg 20/04 | ANTHROPIC, DEEPGRAM, EVOLUTION (já temos), SOFIA_VOICE |
| **Setup VPS Hostinger** | Seg-Ter 20-21/04 | `scripts/setup-vps.sh` |
| **Repointamento webhook V6** | Ter-Qua 21-22/04 | Comando em `docs/DEPLOY.md` |
| **Demo sexta 24/04** | Sex 24/04 | Reunião Murilo + Vinicius |
| **ANVISA Classe II** | Pós-demo | Começa em Q3 2026 se MVP provar tração |
| **Staging VPS Contabo** | Roadmap | Quando a equipe aumentar e precisarmos isolar testes |
| **MCP para MedMonitor/Tecnosenior** | Fase 2 | Após Fase 1 (Eldercare) em produção |
| **HL7 FHIR** | Fase 2-3 | Integração bidirecional com hospitais Vita/Amparo |
| **Biometria v3 (pyannote)** | Após validar v2 com volume | Substitui Resemblyzer quando volume justificar GPU |

Atualizar esta tabela ao fechar/adicionar items.

---

## 10.2. Política de Comunicação Externa

> **Regra operacional** estabelecida em 2026-04-19. Válida para qualquer
> material que sai do projeto (pitch, one-pager, site, apresentações,
> comunicados, PRs públicos).

### NUNCA nomear em material externo
Fornecedores específicos de IA/ML/infra: Claude, Anthropic, Claude Opus/Sonnet/Haiku, Deepgram, OpenAI, GPT, Grok, Gemini, Llama, Resemblyzer, pyannote, pgvector, Evolution API, FastMCP.

### SEMPRE usar termos genéricos em material externo

| ❌ Evitar | ✅ Usar |
|-----------|---------|
| Claude Opus / Anthropic API | Modelo de raciocínio clínico de última geração |
| Claude Sonnet/Haiku | LLM vertical em saúde |
| Deepgram | Motor de transcrição neural em pt-BR |
| Sofia Voice (Grok) | Agente de voz conversacional natural |
| Resemblyzer | Biometria de voz de produção (256-dim) |
| pgvector | Busca vetorial em base relacional |
| Evolution API | Integração nativa com WhatsApp |

### PODE citar em material externo
- **Cases de mercado com nome**: Sensi.ai, Hippocratic AI, Current Health, Biofourmis, Abridge, Ada Health, Corti, Tsinghua AI Hospital, Ping An, iFlytek
- **Tendências/anúncios oficiais** como fato público: "Anthropic lançou Claude for Healthcare em jan/2026", "Meta WhatsApp Cloud API", "ANS Normativa 465/2021"
- **Frameworks regulatórios**: LGPD, CFM 2.314/2022, ANVISA Classe II, HIPAA, GDPR, HL7 FHIR R4
- **Parceiros do projeto**: Tecnosenior, MedMonitor, Amparo, Vita

### Onde a regra se APLICA
- ✅ `docs/PITCH_DECK.md` (material investidor/parceiro)
- ✅ `docs/ONE_PAGER.md`
- ✅ `docs/DEMO_SCRIPT.md` (roteiro usado na reunião)
- ✅ Site, landing, blog, LinkedIn, press releases

### Onde a regra NÃO se aplica (usar nomes normalmente)
- ❌ Este `CLAUDE.md` (contexto interno)
- ❌ `SECURITY.md`, `INFRASTRUCTURE.md`, `STATUS.md`
- ❌ ADRs e RFCs em `docs/adr/`, `docs/rfc/`
- ❌ Código, comentários, `requirements.txt`, `package.json`
- ❌ Logs estruturados (structlog em produção)

**Razão**: engenharia precisa de nomes técnicos para funcionar. Política é marketing/narrativa, não técnica.

### Por quê
1. Não dar munição a concorrente sobre stack
2. Liberdade de troca de fornecedor sem refazer marketing
3. Não virar "startup que só usa X" — vendemos resultado clínico, não tecnologia
4. Enterprise prefere neutralidade — "melhor modelo disponível" é mais credível
5. Sensi.ai (nosso benchmark) não menciona modelo e capturou 80% do mercado US

---

## 11. Referências rápidas

| Documento | Para quê |
|-----------|---------|
| `SECURITY.md` | Threat model + checklist de segurança |
| `INFRASTRUCTURE.md` | Arquitetura + decisões de infra |
| `docs/DEPLOY.md` | Fluxo Local → VPS + comandos operacionais |
| `docs/DEVELOPMENT.md` | Setup local detalhado |
| `docs/PITCH_DECK.md` | 10 slides para reunião de sexta |
| `docs/ONE_PAGER.md` | Resumo 1 página |
| `docs/DEMO_SCRIPT.md` | Roteiro de demo minutado |
| `STATUS.md` | Estado do sprint + próximos passos |
| `README.md` | Overview geral |
| `scripts/verify.sh` | 83+ checks de integridade do projeto |
| `scripts/test_voice_biometrics.py` | Calibração de biometria com áudios reais |
