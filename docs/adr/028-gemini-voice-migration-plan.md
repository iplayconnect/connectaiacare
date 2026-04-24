# ADR-028 — Avaliação e plano de migração pra Gemini 3.1 (família de voz)

> Status: **Draft — pós-benchmark preliminar 2026-04-24**
> Autores: Alexandre + Coder (pós-análise Opus Chat)
> Contexto: pitch 28/04 com Tecnosenior + roadmap Q2-Q3 otimização custos voz

---

## 1. Contexto

Stack atual de voz do ConnectaIACare:

| Componente | Fornecedor atual | Custo ~ | Uso |
|------------|------------------|---------|-----|
| STT (transcrição WhatsApp) | **Deepgram nova-2** | ~$0.043/min | Cuidador manda áudio → transcreve |
| TTS (fala Sofia Voz) | **ElevenLabs** | ~$0.30/1K chars | Sofia responde por voz em chamadas |
| Voice Agent (Sofia Voz) | **Ultravox** via sofia-service:5030 | ~$0.05/min | Conversação bidirecional real-time |

Em abril 2026 o Google lançou 3 modelos Gemini 3.1 de voz:
- **Flash-Lite** (mar/26): transcrição + multimodal geral, ~$0.25/$1.50 per 1M tokens
- **Flash TTS** (16/04/26): TTS com audio tags `[warm] [urgent] [serious]`, 70+ idiomas
- **Flash Live** (26/03/26): conversação bidirecional real-time via WebSocket

Este ADR avalia viabilidade de migração dos 3 componentes atuais pros correspondentes Gemini.

## 2. Decisão (preliminar)

**Migração faseada em 3 sprints**, condicionada a resultados de A/B test. **Nada muda em produção antes do pitch 28/04**.

### Fase 1 — Transcrição (testar Q2)
- **NÃO migrar agora** apesar do custo atraente (~80% menos).
- **Problema identificado em teste real**: Gemini Flash-Lite **erra nomes próprios** em contexto clínico. Ex:
  - "Armindo Trevisan" → "Arlindo Trevizan" (nome+sobrenome trocados)
  - "Armindo Trevisan" → "Armindo Trevisã" (sobrenome truncado)
- Em contexto médico, nome do paciente **errado** é grave — pode virar prescrição em prontuário errado.
- **Qualidade geral do texto é melhor que Deepgram** (pontuação, concordância, fluência pt-BR).

**Plano**: testar com amostra maior (>50 áudios) + prompt engineering incluindo **glossário de nomes** pacientes/cuidadores (context injection) antes de decidir.

### Fase 2 — TTS com audio tags (testar Q2)
- **Aguardar SDK estável**. Teste inicial falhou: `google-generativeai` Python client não suporta `response_modalities=["AUDIO"]`. Requer Vertex AI SDK ou endpoint REST direto (`:generateContent` com preview flag).
- **Valor estratégico alto se funcionar**: audio tags mapeiam 1:1 com nossa classificação clínica.

Mapeamento proposto:
| Classificação ConnectaIACare | Audio tag Gemini TTS |
|-----------------------------|---------------------|
| `routine` | `[warm] [gentle]` |
| `attention` | `[neutral] [serious]` |
| `urgent` | `[firm] [direct]` |
| `critical` | `[urgent]` |
| Reassurance | `[gentle] [reassuring]` |

Integra com a Constituição Sofia (ADR-027): quando safety detecta `medical_emergency`, Sofia automaticamente passa pra tom `[urgent]` sem configuração humana.

### Fase 3 — Flash Live substituindo Ultravox (POC Q3)
- Ultravox ($0.05/min) é bom mas fechado.
- Flash Live promete integração nativa com **LiveKit** (nossa stack de WebRTC pra teleconsulta).
- **Catch crítico**: Flash Live é server-managed session — pra compliance LGPD Art. 37 (audit trail) precisa de **bridge Asterisk** pra gravar localmente. Isso não é trivial.

Arquitetura POC:
```
Paciente/família → SIP trunk → Asterisk (grava + compliance)
                                      ↓
                                  RTP bridge → Flash Live (WebSocket duplex)
                                      ↓
                                  Áudio processado → Asterisk → canal origem
```

## 3. Resultados do benchmark preliminar (2026-04-24)

Script: `backend/scripts/test_gemini_voice.py`
Relatório completo: `docs/testes/gemini/report.md`

### Transcrição (3 áudios reais de cuidadora Milene sobre Sr. Armindo)

| Métrica | Valor |
|---------|-------|
| Modelo Gemini | `gemini-3.1-flash-lite-preview` |
| Similaridade Jaccard (média) | 73% |
| Latência Gemini | ~1600ms |
| Latência Deepgram (ref) | ~800ms |

**Análise qualitativa** (mais importante que similaridade bruta):
- Gemini é **mais natural** em pontuação, concordância, separação de sentenças
- Gemini **falha em nomes próprios não-comuns** (sobrenomes regionais, nomes menos frequentes)
- Deepgram **mais fiel ao áudio literal** (inclui repetições, hesitações — útil em contexto forense)
- Para análise clínica por IA (GPT/Claude depois): Gemini funciona melhor
- Para prontuário textual onde nome precisa bater exato: Deepgram vence

**Exemplo**:
- Cuidadora diz: "Olá, aqui é Milene, eu sou cuidadora do senhor Armindo Trevisan"
- Deepgram: "Olá, aqui é Milene, eu sou cuidadora do senhor Armindo Trevisan." ✅
- Gemini: "Olá, aqui é a Milene. Sou cuidadora do senhor **Arlindo Trevizan**." ❌ (2 nomes errados)

### TTS — testado via REST (sucesso)

**Descoberta**: SDK `google-generativeai` Python não expõe `responseModalities: ["AUDIO"]`. Solução: chamar endpoint REST `v1beta/models/gemini-3.1-flash-tts-preview:generateContent` direto via `httpx`.

**Importante**: o modelo **NÃO aceita** tags inline `[warm] [urgent]` como a análise original do Opus Chat sugeriu. Controle de estilo é via **prefixos em inglês** no início do texto:

| Classification | Prefixo TTS |
|---------------|-------------|
| `routine` | `Say warmly and gently:` |
| `attention` | `Say in a calm but serious tone:` |
| `urgent` | `Say firmly and directly:` |
| `critical` | `Say urgently with clear authority:` |
| Reassurance | `Say gently and reassuringly:` |

**4 samples pt-BR gerados** (commit deste ADR) — `docs/testes/gemini/audios/`:
- `tts_checkin_warm.mp3` (80KB)
- `tts_attention_change.mp3` (108KB)
- `tts_urgent_fall.mp3` (85KB)
- `tts_reassurance.mp3` (116KB)

**Métricas técnicas**:
- Formato retornado: PCM raw L16 mono 24kHz (envolvi em WAV RIFF manualmente)
- Voz: `Kore` (feminina pt-BR padrão; Gemini oferece 30+ vozes)
- Latência geração: 5-11s (preview endpoint, pode variar)
- Tamanho MP3 96kbps: 80-120KB por trecho de ~7-10s falados

**Validação qualitativa pendente**: Alexandre + Murilo escutam e julgam naturalidade pt-BR geriátrico antes de aprovar migração vs manter ElevenLabs.

### Flash Live

Não testado (POC complexo, adiado pra Q3).

## 4. Roadmap de implementação

### Q2/2026 — Transcrição híbrida
1. Script `compare_stt_quality.py` processa 50+ áudios mensais em modo shadow (Gemini + Deepgram em paralelo, só loga)
2. Se Gemini ≥90% similaridade **E** zero erro de nome em amostra rotulada manualmente → migrar
3. Se nomes continuam falhando → Gemini primário + Deepgram só em trechos com entity detection

### Q2/2026 — TTS via Vertex AI
1. Migrar para `vertexai` SDK em vez de `google.generativeai` client direto
2. Implementar wrapper em `backend/src/services/gemini_tts_service.py`
3. A/B test com ElevenLabs em 10% do tráfego de Sofia Voz (shadow)
4. Integrar audio tags com classification layer (ADR-027)

### Q3/2026 — Flash Live POC
1. Estudar integração voip-service (Asterisk + PJSIP) com WebSocket Live API
2. POC em dev com 1 chamada real de teste
3. Avaliar gravação + transcrição pós-call pra audit LGPD
4. Se satisfatório → migração gradual Ultravox → Flash Live no container sofia-service

## 5. Custos estimados (se tudo migrar)

| Item | Atual | Gemini 3.1 | Economia |
|------|-------|-----------|----------|
| STT (Deepgram) | ~$0.043/min | ~$0.008/min | **-81%** |
| TTS (ElevenLabs) | ~$0.30/1K chars | ~$0.12/1K chars | **-60%** |
| Voice Agent (Ultravox) | ~$0.05/min | TBD | ? |

**Ordem de grandeza**: se ConnectaIACare escala pra 10k usuários B2C ativos com 30 msgs/dia de áudio, custo atual STT seria ~$387k/ano; com Flash-Lite cairia pra ~$74k/ano. **Economia anual: $313k.**

## 6. Riscos e mitigação

| Risco | Mitigação |
|-------|-----------|
| Erros de nome em transcrição | Context injection de glossário + manter Deepgram como backup via router (ADR-025) |
| Flash TTS voz robotizada em pt-BR | A/B test com amostra de 100 assinantes reais antes de migrar 100% |
| Latência Gemini maior que Deepgram (1.6s vs 0.8s) | Aceitável pra relato de cuidador (não é real-time); problemático pra Flash Live real-time |
| Dependência de 1 fornecedor (Google) | Router por tarefa já mitiga — fallback cascade pra outros providers configurado em `llm_routing.yaml` |
| SDK Python instável em preview | Isolar em serviço próprio (`gemini_voice_service.py`) com interface estável; trocar impl sem afetar callers |

## 7. O que NÃO faremos

- **Não migrar antes do pitch 28/04** — zero risco de quebrar demo
- **Não migrar sem A/B shadow mode primeiro** — dados de produção, não opinião
- **Não comprometer audit trail LGPD** em Flash Live — bridge Asterisk obrigatório

## 8. Referências

- Script benchmark: `backend/scripts/test_gemini_voice.py`
- Relatório de teste: `docs/testes/gemini/report.md`
- Transcrições comparadas: `docs/testes/gemini/transcription_*.txt`
- ADR-007: Sofia Voz como serviço externo (Grok/Ultravox)
- ADR-021: Íris Framework Agêntico (sofia_voice_ultravox provider)
- ADR-025: LLM Router por tarefa (base pra trocar provider por tarefa)
- ADR-027: Memória + Safety + Canais (classificação clínica usada pra audio tags)

---

**Última atualização**: 2026-04-24 · análise preliminar + benchmark em 3 áudios reais
