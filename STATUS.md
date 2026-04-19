# ConnectaIACare — STATUS do Sprint

**Última atualização**: 2026-04-19 (Dia 1 — domingo)
**Meta**: reunião sexta 24/04 com Murilo e Vinicius
**Dias restantes**: 5

---

## ✅ O que está pronto (Dia 1 — 100% do dia)

### Backend completo
- [x] Estrutura modular em Python 3.12 + Flask
- [x] Configuração via `.env` + `.env.example` documentado
- [x] `Dockerfile` do backend e `docker-compose.yml` completos
- [x] **Schema PostgreSQL** (`aia_health_*`) com 6 tabelas e triggers
  - pacientes, cuidadores, relatos, sessões, auditoria hash-chain, alertas
- [x] **8 pacientes mock** com perfis clínicos realistas (HAS, IC, Alzheimer, Parkinson, DPOC, AVC, etc.)
- [x] Script `init_db.sh` para bootstrap do banco
- [x] **Serviço Evolution** (WhatsApp): envio texto, mídia, áudio + download base64 + presença
- [x] **Serviço Deepgram** (STT nova-2 pt-BR)
- [x] **Serviço LLM** (Claude Haiku/Sonnet/Opus via Anthropic SDK) com suporte a JSON mode
- [x] **Serviço Patient**: fuzzy matching com pg_trgm + SequenceMatcher
- [x] **Serviço Report**: CRUD completo + histórico por paciente
- [x] **Serviço Analysis**: extração de entidades + análise clínica com classificação
- [x] **Serviço Session Manager**: estado de conversa persistido em DB
- [x] **Sofia Voice Client**: cliente HTTP para ligações proativas
- [x] **Pipeline orquestrador**: fluxo completo áudio → análise → WhatsApp + ligação
- [x] **Rotas HTTP**: `/webhook/whatsapp`, `/api/patients`, `/api/reports`, `/api/dashboard/summary`
- [x] **Prompts separados**: `patient_extraction.py` + `clinical_analysis.py`

### Frontend completo
- [x] Next.js 14 + TypeScript + Tailwind + shadcn/ui primitives
- [x] `package.json`, `tsconfig.json`, `tailwind.config.ts`, `next.config.js`
- [x] `Dockerfile` de produção com multi-stage build
- [x] **Layout global** + Header com navegação
- [x] **API client tipado** (`lib/api.ts`) com TypeScript interfaces
- [x] **Dashboard principal**: KPIs, distribuição de classificações, últimos relatos
- [x] **Página de relatos**: listagem com foto do paciente + classificação + summary
- [x] **Detalhe de relato**: player de áudio + transcrição + análise IA estruturada
- [x] **Lista de pacientes**: grid com foto + perfil
- [x] **Detalhe de paciente**: condições, medicações, alergias, responsável, histórico de relatos
- [x] **ClassificationBadge component**: badges coloridos por nível de urgência
- [x] CSS com cores semânticas e animação em críticos

### Materiais de apresentação
- [x] **PITCH_DECK.md**: 10 slides estruturados (problema → visão → benchmark → equipe → produto → diferenciais → roadmap → modelo → próximos passos)
- [x] **ONE_PAGER.md**: resumo 1 página para deixar na mesa
- [x] **DEMO_SCRIPT.md**: roteiro completo de demo com fases, frases-chave, backup plans
- [x] **SCRIPTS de áudio**: 4 cenários (rotina / atenção / urgente / crítico) para ensaio

### Documentação
- [x] **DEVELOPMENT.md**: guia completo de setup, deploy, troubleshooting
- [x] **README.md**: visão geral do projeto

---

## 🎯 O que falta (próximos 4 dias)

### Segunda (20/04) — manhã
- [ ] **Alexandre**: registrar domínio `connectaiacare.com`
- [ ] **Alexandre**: criar repo `iplayconnect/connectaiacare` no GitHub
- [ ] **Alexandre**: Cloudflare DNS apontando `demo.connectaiacare.com` → VPS Hostinger
- [ ] `git init` local + primeiro commit + push para GitHub
- [ ] `docker compose up -d` em dev local para teste end-to-end

### Segunda (20/04) — tarde
- [ ] Rodar primeiros áudios de teste pelo WhatsApp (V6)
- [ ] Ajustar prompts de análise com base em respostas reais
- [ ] Calibrar threshold de matching de paciente
- [ ] Validar envio de foto + confirmação com cuidador

### Terça (21/04)
- [ ] Deploy em VPS Hostinger (container paralelo ao ConnectaIA)
- [ ] Configurar Traefik para roteamento HTTPS
- [ ] Reconfigurar webhook V6 no Evolution para apontar para `demo.connectaiacare.com`
- [ ] Testes end-to-end em prod
- [ ] Integrar Sofia Voice real (validar credenciais e chamada)
- [ ] Gravar backup em vídeo do fluxo completo

### Quarta (22/04)
- [ ] Polir UX do dashboard (animações, loading states)
- [ ] Adicionar atualização em tempo real via Socket.IO (opcional)
- [ ] Ensaiar demo 3x com cronômetro
- [ ] Converter PITCH_DECK.md para PPTX ou Google Slides

### Quinta (23/04)
- [ ] Ensaio final com setup real (celular, laptop, rede)
- [ ] Imprimir one-pager
- [ ] Preparar rascunho de NDA + Carta de Intenções
- [ ] Revisar mensagens WhatsApp (emojis, tom, estrutura)

### Sexta (24/04) — dia D
- [ ] Check-in técnico 1h antes da reunião
- [ ] Demo
- [ ] Deixar one-pager impresso
- [ ] Enviar PDF do pitch + recording da demo por email depois

---

## 🔑 Credenciais necessárias (preencher `.env`)

| Variável | De onde | Observação |
|----------|---------|-----------|
| `ANTHROPIC_API_KEY` | console.anthropic.com | Já temos conta ativa |
| `DEEPGRAM_API_KEY` | console.deepgram.com | Já temos conta ativa |
| `EVOLUTION_API_KEY` | (já temos) `5C979F27-8AF5-4546-86E5-55197FF72F1D` | Instância V6 ConnectaIA |
| `EVOLUTION_API_URL` | `https://evolution.connectaia.com.br` | Shared infra |
| `EVOLUTION_INSTANCE` | `v6` | Número 555189592617 |
| `SOFIA_VOICE_API_URL` | `http://sofia-service:5030` (rede interna) | Ligar no Docker compose do ConnectaIA |
| `SOFIA_VOICE_API_KEY` | token compartilhado com sofia-service | Precisamos gerar |

---

## 📊 Métricas do sprint

- **Linhas de código Python backend**: ~1.800
- **Linhas de código TypeScript frontend**: ~750
- **Arquivos criados**: 30+
- **Tempo estimado de build**: 90% completo em ~2h de sprint
- **Custo de APIs até agora**: R$ 0 (ainda não rodou em dev)

---

## ⚠️ Riscos identificados

1. **Webhook V6 em produção**: quando repontar, se o CRM precisar de alguma mensagem que chegar no V6 vai pra ConnectaIACare e não pra ConnectaIA. Mitigação: Alexandre confirmou que V6 não está em uso hoje.
2. **Sofia Voice**: depende de credenciais e saber se aceita chamada externa. Testar segunda.
3. **Fotos pravatar**: são avatares genéricos. Para a demo final substituir por fotos de stock Unsplash ou geradas via AI para mais realismo.
4. **Domínio**: se não propagar a tempo, usar `cc-demo.connectaia.com.br` como fallback.
