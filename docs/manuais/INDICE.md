# Manuais ConnectaIACare — Índice Geral

**Versão:** 1.0.1
**Data:** 2026-05-18

Bem-vindo. Esta é a porta de entrada da documentação da ConnectaIACare.

Aqui você encontra o **manual certo para cada perfil**. Cada manual é escrito na linguagem de quem vai ler — o cuidador não precisa ler o manual do gestor, o gestor não precisa ler o manual do operador.

Quem precisa de **referência técnica completa**, consulte o `PLATAFORMA.md` (49 seções, 11 partes, ~118KB).

---

## Encontre seu manual

### 👩 Sou cuidadora / cuidador
**→ [CUIDADOR.md](CUIDADOR.md)**

Linguagem do dia a dia. Como usar a Sofia pelo WhatsApp, como reportar sinal vital, como pedir socorro. Inclui frases que funcionam e erros comuns.

**Tempo de leitura:** 20 minutos. Lê uma vez, consulta quando precisa.

---

### 👨‍👩‍👧 Sou familiar / responsável por um idoso
**→ [FAMILIAR.md](FAMILIAR.md)**

Como ativar a plataforma para sua mãe/pai. O que você verá. Quando vai receber alerta. Como conversar com a Sofia. Quem cuida de quê.

**Tempo de leitura:** 25 minutos. Tem checklist de primeiros passos.

---

### 👴 Sou idoso e vou usar diretamente
**→ [IDOSO_B2C.md](IDOSO_B2C.md)**

Linguagem bem simples, letra confortável. A Sofia é uma assistente que conversa com você pelo WhatsApp. Aqui está como.

**Tempo de leitura:** 15 minutos. Família ou cuidador pode ler junto.

---

### 👩‍⚕️ Sou médica, médico, enfermeira ou enfermeiro
**→ [MEDICO_ENFERMEIRO.md](MEDICO_ENFERMEIRO.md)**

Tom clínico-técnico. Como funciona a triagem da Sofia, validação farmacológica, cross-validation, drug safety review, prontuário 360°, teleconsulta com SOAP estruturado, governança Sofia (Conselho Científico), compliance LGPD.

**Tempo de leitura:** 45 minutos. Inclui FAQ clínico e sinais de qualidade.

---

### 🏥 Sou gestora ou gestor (clínica, ILPI, home care, operadora)
**→ [GESTOR.md](GESTOR.md)**

Onboarding do tenant (7 dias). Cadastro de equipe. Configuração da Sofia. Importação de pacientes em escala. Plantão P1/P2/P3. Dashboards. Saúde do plantão. Métricas de SLA. Audit log e LGPD. Faturamento. Integrações (Tecnosenior CareNote, FHIR). Playbook quando algo dá errado.

**Tempo de leitura:** 60 minutos. Tem checklist mensal e contatos.

---

### 🎧 Sou operador da Central 24/7
**→ [OPERADOR_CENTRAL.md](OPERADOR_CENTRAL.md)**

Como ler a fila priorizada. Como reivindicar e atender. Quando escalonar para L2/L3/L4. Outcomes possíveis. SLA pessoal. Como pausar plantão. Métricas de avaliação. Playbook de casos típicos (peito, glicemia, família ansiosa, falso alarme, recusa). Frases prontas por tipo de interlocutor.

**Tempo de leitura:** 50 minutos. Tem 5 casos práticos comentados.

---

### 🔧 Sou implementador, dev ou auditor técnico
**→ [PLATAFORMA.md](PLATAFORMA.md)**

Referência completa: arquitetura multi-tenant, Sofia Phase C v2, safety guardrail, cross-validation engine, provenance, voice biometrics, identity resolver, care events state machine, handoff queue, plantão multi-camada, integrações, deploy, observabilidade.

**Tempo de leitura:** 4 horas (leitura completa) ou consulta dirigida.

---

## Por onde começar (caminho sugerido)

### Se você acabou de assinar a plataforma (gestor)

1. Leia o **GESTOR** completo
2. Distribua **CUIDADOR** para sua equipe de cuidadores
3. Distribua **FAMILIAR** para famílias dos pacientes
4. Distribua **MEDICO_ENFERMEIRO** para sua equipe clínica
5. Se contratou Central 24/7, mande **OPERADOR_CENTRAL** para a operação
6. Mantenha **PLATAFORMA** como referência para questões técnicas

### Se você é cuidador iniciante

1. Leia **CUIDADOR** uma vez
2. Faça seu **cadastro de voz** (1 minuto)
3. Envie seu **primeiro relato de teste**
4. Releia a seção 9 (frases que funcionam) algumas vezes na primeira semana

### Se você é familiar recém-cadastrado

1. Leia **FAMILIAR** seção 1 a 6 (45 min)
2. Confira que recebeu **alerta de teste** da Sofia
3. Salve o contato da Sofia nos seus favoritos
4. Volte ao manual sempre que tiver dúvida

### Se você é médico ou enfermeiro entrando na operação

1. Leia **MEDICO_ENFERMEIRO** seções 1-8 (45 min)
2. Faça uma **revisão piloto** de prontuário (acompanhado por colega)
3. Familiarize-se com **drug safety review queue** e **cross-validation alerts**
4. Participe da próxima reunião do **Conselho Científico** (se aplicável)

### Se você é operador novo na Central

1. Leia **OPERADOR_CENTRAL** **completo** (50 min)
2. Faça turno **shadowing** (acompanha colega) por 1 turno
3. Faça turno **assistido** (você atende, colega revisa) por 1 turno
4. Vai pra plantão autônomo na 3ª semana

---

## Mapa cruzado por situação

| Situação real | Quem precisa fazer o quê | Manual onde está |
|---|---|---|
| Idoso teve mal-estar | Cuidador relata via WhatsApp | Cuidador §6 |
| Sofia detectou P1 (peito) | Operador central reivindica em <1min | Operador §6-§13 (Caso 1) |
| Família ansiosa quer status | Familiar conversa com Sofia ou Central liga | Familiar §7 + Operador §13 (Caso 3) |
| Médico precisa revisar medicação | Sofia entrega drug safety review queue | Médico/Enf §5 |
| Gestor quer ver SLA do mês | Dashboard Saúde do Plantão | Gestor §10 |
| Auditor LGPD pede relatório | Admin exporta audit log | Gestor §12 |
| Idoso quer revogar consentimento | Direito do titular via Sofia | Idoso/B2C §9 + Gestor §12 |
| Cuidador novo entra na equipe | Onboarding voz + treinamento curto | Gestor §4 + Cuidador §3-§4 |
| Quero entender por que Sofia escalou X | Audit log + corpus review | Médico/Enf §11 |
| Sistema fora do ar | Suporte técnico 24/7 | Gestor §15 + Operador §18 |

---

## Versionamento

Todos os manuais estão **versionados em git** no repositório `ConnectaIACare`:

```
docs/
└── manuais/
    ├── INDICE.md              ← você está aqui
    ├── PLATAFORMA.md          ← referência técnica completa
    ├── CUIDADOR.md
    ├── FAMILIAR.md
    ├── IDOSO_B2C.md
    ├── MEDICO_ENFERMEIRO.md
    ├── GESTOR.md
    └── OPERADOR_CENTRAL.md
```

Toda mudança em manual passa por:
1. Pull request no git
2. Revisão por **Editorial** (clareza, tom, completude)
3. Revisão por **Conselho Científico** (se mudança clínica)
4. Merge e versionamento (manual ganha versão nova)

**Para sugerir mudança:** abra issue no repo ou mande pra docs@connectaia.com.br.

---

## Próximas adições previstas

Versões 1.x dos manuais traz:

- **PARCEIRO_INTEGRADOR** — para empresas que vão integrar via FHIR/API (parceiros como Tecnosenior, MedMonitor, Atente/Vita)
- **DPO** — específico para Encarregado de Dados (LGPD)
- **AUDITOR_EXTERNO** — para acreditadoras (ONA, JCI)
- **VISUAL** (PDF + vídeo) — versão ilustrada para distribuir em ILPIs

---

## Sobre a ConnectaIACare

Plataforma de acompanhamento contínuo de idosos com Sofia (IA conversacional), triagem clínica, validação farmacológica, plantão multi-camada e prontuário 360°.

- **Site institucional:** https://www.connectaia.com.br
- **Aplicação:** https://app.connectaia.com.br
- **Status público:** https://status.connectaia.com.br
- **Documentação técnica:** https://docs.connectaia.com.br
- **Comercial:** comercial@connectaia.com.br
- **Suporte:** suporte@connectaia.com.br

---

**Atualização:** 2026-05-18
**Próxima revisão:** trimestral (cada release de manual)
**Responsável editorial:** Equipe ConnectaIA + Conselho Científico
