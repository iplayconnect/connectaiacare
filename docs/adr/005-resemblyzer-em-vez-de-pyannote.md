# ADR-005: Resemblyzer para biometria de voz (em vez de pyannote.audio)

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: biometrics, ml, performance, cost

## Context and Problem Statement

O ConnectaIACare precisa identificar cuidadores por voz (enrollment + verificação 1:1 + identificação 1:N) para lidar com o cenário de "aparelho compartilhado entre plantões" — cenário pré-existente na ConnectaIA com Resemblyzer já em produção. Para o MVP, precisamos decidir se mantemos Resemblyzer (conhecido, já testado) ou adotamos um modelo mais preciso (pyannote.audio).

## Decision Drivers

- **Reuso de código**: ConnectaIA já opera Resemblyzer em produção — 90% do código é copiável
- **Precisão necessária**: cenário é 10-30 cuidadores por tenant, não milhares — EER de 3-5% é aceitável
- **Latência no pipeline**: identificação precisa caber em ~2s para não travar o webhook WhatsApp
- **CPU vs GPU**: Resemblyzer roda CPU-only (~500ms por embedding); pyannote exige GPU para latência aceitável
- **Infraestrutura**: não temos GPU na VPS Hostinger
- **Tamanho do modelo**: Resemblyzer ~50MB (cabe em container padrão); pyannote models ~500MB-2GB
- **Complexidade operacional**: pyannote é pipeline completo (VAD + embedder + clustering); Resemblyzer é só embedder

## Considered Options

- **Option A**: Resemblyzer (escolhida)
- **Option B**: pyannote.audio
- **Option C**: SpeechBrain (ECAPA-TDNN)
- **Option D**: API externa (Azure Speaker Recognition, Google Speaker ID)

## Decision Outcome

Chosen option: **Option A — Resemblyzer 0.1.4 com 256-dim embeddings, rodando CPU-only no container Python**, porque reusa código maduro da ConnectaIA, tem latência compatível com o pipeline WhatsApp, e oferece precisão suficiente para o cenário de 10-30 cuidadores por tenant.

### Positive Consequences

- Time-to-market: ~2h de adaptação em vez de dias de integração nova
- Sem GPU necessária — cabe na VPS Hostinger compartilhada
- Modelo pequeno (~50MB) não impacta tempo de build/deploy
- Código defensivo já resolvido (lazy-load thread-safe, audio preprocessing, timeout)

### Negative Consequences

- Precisão inferior a pyannote (~5% EER vs ~2% EER em benchmarks acadêmicos)
- Resemblyzer treinado em inglês — português tem precisão um pouco pior mas aceitável
- Não suporta diarização nativamente (para futuro de áudios multi-falante)
- Projeto Resemblyzer tem manutenção baixa (último commit significativo ~2021)

## Pros and Cons of the Options

### Option A — Resemblyzer ✅ Chosen

- ✅ Já validado em produção na ConnectaIA
- ✅ CPU-only (~500ms)
- ✅ 50MB footprint
- ✅ API simples
- ❌ Manutenção low
- ❌ Precisão menor que SOTA

### Option B — pyannote.audio

- ✅ SOTA precisão
- ✅ Pipeline completo (VAD + embedder + clustering)
- ✅ Manutenção ativa
- ❌ Exige GPU para latência produção
- ❌ Modelos ~2GB complicam deploy
- ❌ API complexa (config YAML + Hugging Face tokens)

### Option C — SpeechBrain (ECAPA-TDNN)

- ✅ Precisão alta (~2% EER)
- ✅ CPU viável (mais pesado que Resemblyzer)
- ❌ Código ainda não testado em produção ConnectaIA
- ❌ Dependência do PyTorch Lightning

### Option D — API externa (Azure/Google)

- ✅ Zero manutenção
- ❌ Dados médicos (voz) saem do nosso perímetro
- ❌ Custos escalam com volume
- ❌ Latência de rede externa
- ❌ Vendor lock-in + DPA complexidade

## When to Revisit

- Quando volume passar de 10k cuidadores ativos
- Se EER medido em produção exceder 5% (falso-positivo em identificação 1:N)
- Quando precisarmos de diarização (áudios multi-falante: cuidador + idoso simultâneos)
- Se obtivermos GPU no ambiente de produção (justifica upgrade)

## Links

- Código: [voice_biometrics_service.py](../../backend/src/services/voice_biometrics_service.py)
- Pre-processing: [audio_preprocessing.py](../../backend/src/services/audio_preprocessing.py)
- Migration: [003_voice_biometrics.sql](../../backend/migrations/003_voice_biometrics.sql)
- Teste CLI: [test_voice_biometrics.py](../../scripts/test_voice_biometrics.py)
- Relacionado: [ADR-004](004-pgvector-em-vez-de-vector-db-dedicado.md)
