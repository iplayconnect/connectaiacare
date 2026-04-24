# Gemini 3.1 — Benchmark ConnectaIACare

Executado em: 2026-04-24 03:25:04

## 1. Transcrição — Flash-Lite vs Deepgram nova-2

- **3 áudios testados**
- **Similaridade média**: 73% (Jaccard word overlap)
- **Latência média Gemini**: 1595ms

### Amostras (comparação lado a lado)

#### Amostra 1 — 3s
- Similaridade: **62%**
- Latência Gemini: 1606ms

**Deepgram**: Ok, o caso seu armindo já foi finalizado.

**Gemini**: O caso do Armindo já foi finalizado.

---

#### Amostra 2 — 12s
- Similaridade: **79%**
- Latência Gemini: 1539ms

**Deepgram**: Olá aqui é a cuidadora da do senhor Armindo Trevisan. Só pra informar que foi só 1 susto tá ele está ok ele está muito bem já se levantou está sentado e está tudo bem com o senhor Armindo.

**Gemini**: Olá, aqui é a cuidadora da do senhor Armindo Trevisã. Só para informar que foi só um susto, tá? Ele tá OK, ele tá muito bem, já se levantou, tá sentado e tá tudo bem com o senhor Armindo.

---

#### Amostra 3 — 11s
- Similaridade: **78%**
- Latência Gemini: 1639ms

**Deepgram**: Olá, aqui é Milene, eu sou cuidadora do senhor Armindo Trevisan. Ele acabou de cair da cama e está, está se sentindo muito tonto.

**Gemini**: Olá, aqui é a Milene. Sou cuidadora do senhor Arlindo Trevizan. Ele acabou de cair da cama e está e está se sentindo muito tonto.

---

## 2. TTS com audio tags — Flash TTS

❌ Nenhum TTS gerado — Flash TTS pode exigir Vertex AI API específica.

Abordagem alternativa:
- Testar via Vertex AI SDK (`vertexai.generative_models`)
- Ou aguardar disponibilidade do Flash TTS no Gemini API público

## 3. Conclusão preliminar

⚠️  **Transcrição Gemini: TESTES ADICIONAIS NECESSÁRIOS** (similaridade 73%)
- Pode ter perda em termos médicos críticos
- Validar com amostras maiores (>100 áudios, múltiplos cuidadores)

## 4. Roadmap migração (se aprovado)

- **Q2 2026**: testes A/B em produção (10% tráfego Gemini, shadow mode)
- **Q2 2026**: integração Flash TTS substituindo ElevenLabs (audio tags → tom por classification)
- **Q3 2026**: POC Flash Live substituindo Ultravox na Sofia Voz (bridge Asterisk preserva audit)
