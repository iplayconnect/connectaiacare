# Resposta para Matheus (Tecnosenior) — Limites Custom de Medidas de Saúde

**Contexto:** Matheus propôs endpoint pra expor limites personalizados de medidas (PA, glicose, etc.) por paciente, com tiers "aviso" e "perigo", baseados em diretrizes SBC mas customizáveis por condição.

**Objetivo da resposta:** mostrar que ConnectaIACare opera em ambiente clínico maduro, com bases regulatórias estruturadas e supervisão médica ativa — e que a integração proposta encaixa perfeitamente.

---

## 📩 Mensagem curta pra enviar (WhatsApp/Slack)

> Opa Matheus, beleza! Faz total sentido sim — isso encaixa exatamente no que a gente precisa pra fechar uma camada do safety guardrail da plataforma. Hoje a gente já trabalha com:
>
> • **Cross-validation de condições × medicamentos** (engine própria baseada em diretrizes nacionais e Beers Criteria pra geriatria) com regras curadas e validadas pela nossa equipe clínica antes de irem pra produção
> • **Bases curadas** de CID-10 PT-BR, classes terapêuticas (princípio ativo → ATC), e medicamentos potencialmente inapropriados para idosos
> • **Soft prompts** com severidade calibrada (sugestão → atenção → importante → crítico) — sem bloquear, mas alertar
> • **Audit log imutável** de cada decisão clínica do sistema (LGPD Art. 11)
>
> O que vocês têm — limite por paciente com supervisão médica ativa — é exatamente o **input contextual** que nossa engine precisa pra deixar de usar threshold genérico de literatura e passar a respeitar a individualização clínica que vocês já fazem.
>
> Sobre SBC: nossas referências hoje são **DBHA 2020 (SBC) pra pressão, SBD pra diabetes, SBGG pra geriatria, e Critérios de Beers AGS 2023 pra polifarmácia**. Se vocês tiverem limites que extrapolem essas referências por decisão médica específica, esses prevalecem (médico tem autonomia).
>
> Sobre o endpoint, sugiro um GET retornando os limites do paciente + meta de qual diretriz baseia (pra audit). Algo tipo `/patient/<id>/vital-thresholds` com payload contendo `vital_type`, `warning_min/max`, `danger_min/max`, `source` (sbc_dbha_2020 | medical_individualized | etc.) e `last_reviewed_by`.
>
> Toda decisão que nossa engine tomar baseada nesses limites passa pela revisão da nossa equipe clínica (Henrique + Coordenadora PUC + Geriatra UFRGS — geriatria + farmácia clínica) antes de virar regra ativa. Ou seja: você expõe os limites, a gente consome, mas qualquer alerta novo é validado clinicamente antes de ir pro paciente/familiar.
>
> Posso te mandar a especificação técnica que rascunhei? Fica como base pra você criticar e ajustar antes de implementar.

---

## 📋 Especificação técnica (pra anexar / mandar depois)

### Endpoint proposto

```
GET /api/external/patient/<tecnosenior_patient_id>/vital-thresholds
Authorization: Bearer <tecnosenior_api_token>
```

### Payload de resposta

```json
{
  "patient_id": "12345",
  "thresholds": [
    {
      "vital_type": "blood_pressure_systolic",
      "unit": "mmHg",
      "warning": {"min": 100, "max": 140},
      "danger":  {"min": 80,  "max": 180},
      "source": "sbc_dbha_2020",
      "individualized": false,
      "last_reviewed_by_user_id": "uuid-do-medico-tecnosenior",
      "last_reviewed_at": "2026-04-15T10:30:00Z",
      "review_notes": null
    },
    {
      "vital_type": "blood_glucose",
      "unit": "mg/dL",
      "warning": {"min": 80, "max": 140},
      "danger":  {"min": 60, "max": 250},
      "source": "medical_individualized",
      "individualized": true,
      "last_reviewed_by_user_id": "uuid-do-medico",
      "last_reviewed_at": "2026-04-20T14:00:00Z",
      "review_notes": "Paciente DM2 com nefropatia, alvo glicêmico relaxado conforme ADA/SBD 2024"
    },
    {
      "vital_type": "heart_rate",
      "unit": "bpm",
      "warning": {"min": 55, "max": 95},
      "danger":  {"min": 40, "max": 120},
      "source": "sbc_dbha_2020",
      "individualized": false,
      "last_reviewed_by_user_id": null,
      "last_reviewed_at": null,
      "review_notes": null
    },
    {
      "vital_type": "oxygen_saturation",
      "unit": "%",
      "warning": {"min": 92, "max": 100},
      "danger":  {"min": 88, "max": 100},
      "source": "medical_individualized",
      "individualized": true,
      "last_reviewed_by_user_id": "uuid-pneumologista",
      "last_reviewed_at": "2026-03-10T09:00:00Z",
      "review_notes": "DPOC grave — alvo SpO2 relaxado pra evitar hipercapnia"
    }
  ],
  "fetched_at": "2026-05-11T03:45:00Z"
}
```

### Vital types canônicos (já temos no nosso modelo)

| Vital type | Unit | Referência baseline |
|---|---|---|
| `blood_pressure_systolic` | mmHg | SBC — DBHA 2020 |
| `blood_pressure_diastolic` | mmHg | SBC — DBHA 2020 |
| `heart_rate` | bpm | SBC |
| `respiratory_rate` | rpm | Literatura geriátrica |
| `oxygen_saturation` | % | Literatura — DPOC respeitado |
| `body_temperature` | °C | Literatura — sepsis criteria |
| `blood_glucose` | mg/dL | SBD 2024 / ADA |
| `weight` | kg | (sem thresholds fixos — usar Δ%) |

### Campo `source` — valores esperados

| Valor | Significado |
|---|---|
| `sbc_dbha_2020` | Diretriz Brasileira de Hipertensão Arterial — Sociedade Brasileira de Cardiologia |
| `sbd_2024` | Diretrizes da Sociedade Brasileira de Diabetes |
| `sbgg_polifarmacia` | Sociedade Brasileira de Geriatria e Gerontologia |
| `ags_beers_2023` | American Geriatrics Society — Beers Criteria |
| `medical_individualized` | Limites custom definidos por médico responsável pra esse paciente específico |
| `caregiver_alert_calibrated` | Limites ajustados pela equipe de cuidadores baseado em histórico (menor peso clínico) |

### Como nossa engine consumirá

1. **Pull periódico**: cache local refresh a cada 6h (ou push via webhook se preferirem)
2. **Validação no momento de cada medida recebida**:
   - Sofia recebe medida via WhatsApp → consulta cache de limites do paciente
   - Compara contra `warning`/`danger` → dispara classification routine/attention/urgent/critical
   - Se `individualized=true`, prevalece sobre threshold genérico
3. **Fallback seguro**: se endpoint Tecnosenior offline, usamos limites baseline das diretrizes — nunca deixamos paciente sem cobertura clínica

### Audit trail

Toda decisão da nossa engine baseada em threshold da Tecnosenior fica gravada com:
- `threshold_source` (qual valor usamos)
- `threshold_individualized` (true/false)
- `last_reviewed_by_tecnosenior` (rastreabilidade cruzada)
- `decision_made_at` (timestamp da nossa decisão)

Vocês podem auditar tudo via export quando quiserem.

### Considerações de segurança clínica

- **Médico Tecnosenior tem autonomia total**: se ele define um limite individual, esse é o limite usado. Nossa engine respeita.
- **Limites individualizados expiram**: sugestão de TTL de 90 dias com flag de "revisar". Após expiração, fallback pra diretriz baseline.
- **Mudanças críticas viram alerta**: se vocês alterarem um threshold de `danger`, podemos enviar notificação pra confirmação dupla antes de ativar.

### Próximos passos sugeridos

1. **Vocês**: implementar endpoint conforme spec (ou critica e iteramos)
2. **Nós**: implementar consumer no lado da ConnectaIACare + cache + audit
3. **Validação cruzada**: 1 reunião técnica pra calibrar pra alguns pacientes-piloto antes de generalizar
4. **Time clínico nosso**: revisão das regras de cross-validation que vão usar esses limites — Henrique (farmácia/biomédico) + Coordenadora PUC (geriatria) + Geriatra UFRGS

---

## 📝 Notas pro Alexandre (não enviar pro Matheus)

**O que essa resposta passa:**
- Maturidade clínica (lista de diretrizes citadas — SBC/SBD/SBGG/Beers)
- Arquitetura de safety já estruturada (cross-validation, soft prompts, audit log)
- Equipe clínica ativa supervisionando (3 nomes/instituições)
- Respeito pela autonomia médica deles (individualized prevalece)
- Postura técnica (spec concreta, não vibes)

**O que essa resposta NÃO exagera:**
- Não diz que já estamos "100% integrados com SBC" — diz que **usamos as diretrizes como baseline** (verdade)
- Não promete features que não existem — só descreve a engine que já temos
- Não esconde que a integração custom deles é um upgrade pra nós (honestidade)

**Pontos onde Alexandre pode personalizar antes de enviar:**
- Tom da abertura (mais formal/informal conforme histórico de conversa)
- Mencionar especificamente o piloto Armindo+Matheus (CareNote id=2) se fizer sentido
- Decidir se manda a spec técnica junto OU espera ele pedir
- Confirmar se quer chamar reunião técnica ou prefere ir por mensagem

**Riscos a antecipar:**
- Matheus pode perguntar "vocês têm referências SBC ESPECIFICAMENTE implementadas?" — resposta honesta: hoje usamos como guia conceitual, ainda não temos lookup automático contra a diretriz mais recente. Mas integrar com o que vocês já validaram médica e clinicamente é melhor que reimplementar.
- Matheus pode querer ver código/painel pra confirmar maturidade — convidar pra demo do `/admin/governance/curated-review` resolve.
- Matheus pode perguntar prazo — sugestão: 2 semanas pra consumer no nosso lado após o endpoint dele estar de pé.
