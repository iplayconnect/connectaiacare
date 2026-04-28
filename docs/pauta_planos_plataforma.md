# Pauta — Planos Comerciais da ConnectaIACare

**Data**: 2026-04-28
**Status**: rascunho — preços e limites a serem definidos por Alexandre
**Objetivo**: estrutura única de planos por segmento, alinhada com
o schema técnico (migrations 052-054) e com o panel LLM.

---

## 1. Princípio de design dos planos

1. **Não vender feature técnica** — vender desfecho clínico ("a Sofia
   identifica alterações antes que virem emergência"), não
   "biometria de voz com 256 dimensões".

2. **Plano se ajusta ao volume real do cliente** — não cobrar pelo
   uso máximo, cobrar pelo uso real médio + buffer.

3. **Picos de emergência nunca limitados** — keywords críticas
   (queda, parada, AVC) sempre passam mesmo com quota zerada
   (decisão registrada em `decisoes_b2c_individual.md`).

4. **Atendimento humano é diferencial** — ConnectaIACare é central
   humana + tech, não só IA. Premium tier inclui prioridade na fila
   humana.

5. **3 segmentos, 3 SKU principais** — não inflar catálogo.

---

## 2. Segmentação (3 famílias de cliente)

| Segmento | Tenant_type | Licensing_model | Característica |
|----------|-------------|-----------------|----------------|
| **Institucional** | ILPI / clinica / hospital | b2b_organization | Multi-paciente, plantão obrigatório, equipe técnica |
| **Família** | B2C | b2c_per_patient | 1+ pacientes domiciliares, cuidador familiar ou particular |
| **Indivíduo** | B2C (`is_self_reporting=TRUE`) | b2c_per_patient | Idoso solo, sem cuidador, fala direto com Sofia |

> **Observação arquitetural**: no schema, "indivíduo" não é tenant
> próprio — é flag por paciente dentro de um tenant B2C. Comercialmente
> é um SKU separado porque o público (idoso autônomo) e o pricing são
> diferentes.

---

## 3. Estrutura proposta dos planos (matriz)

### 3.1 Institucional (B2B)

| Tier | Público alvo | Pacientes | Mensagens/mês | Atendimento humano | Preço |
|------|--------------|-----------|---------------|--------------------|-------|
| **Essencial B2B** | ILPI pequena (até 20 leitos) | até 20 | 1.500 | Comercial (8h-18h) | R$ ___ /tenant + R$ ___ /paciente |
| **Padrão B2B** | ILPI/clínica média (20-80 leitos) | até 80 | 5.000 | Estendido (8h-22h) | R$ ___ /tenant + R$ ___ /paciente |
| **Premium B2B** | Hospital ou rede de ILPIs | ilimitado | ilimitado* | 24/7 prioritário | R$ ___ /tenant + R$ ___ /paciente |

*Premium B2B: teto de uso interno de 50 msg/paciente/dia em média.
Cap rígido só acima de 100/dia/paciente sustentado por 5+ dias
(proteção contra abuso).

### 3.2 Família (B2C)

| Tier | Público alvo | Pacientes | Mensagens/mês | Cuidadores | Preço |
|------|--------------|-----------|---------------|-----------|-------|
| **Essencial Família** | Filho cuidando do pai/mãe | até 1 | 100 | até 1 (familiar) | R$ ___ /mês |
| **Padrão Família** | Filho cuidando do casal de idosos | até 2 | 300 | até 3 | R$ ___ /mês |
| **Premium Família** | Família com cuidador profissional rotativo | até 3 | 2.000 | até 6 (3 turnos x 2 dias úteis) | R$ ___ /mês |

### 3.3 Indivíduo

| Tier | Público alvo | Pacientes | Mensagens/mês | Preço |
|------|--------------|-----------|---------------|-------|
| **Indivíduo Essencial** | Idoso autônomo, lúcido, sem cuidador | 1 (próprio) | 100 | R$ ___ /mês |
| **Indivíduo Premium** | Idoso autônomo + acesso prioritário ao humano | 1 (próprio) | 500 | R$ ___ /mês |

> Indivíduo NÃO tem tier "Padrão" — quem precisa de mais, vira
> Família com cuidador adicional.

---

## 4. Features por tier (matriz transversal)

### 4.1 Features básicas (todos os planos)

- Sofia chat WhatsApp (texto e áudio)
- Pipeline de classificação (8 classes)
- Alertas críticos por keyword
- Dashboard básico do paciente
- Histórico de relatos
- Audit chain LGPD

### 4.2 Features condicionais (a confirmar com Alexandre)

| Feature | Essencial | Padrão | Premium |
|---------|-----------|--------|---------|
| Biometria de voz | ❌ | ✅ | ✅ |
| Plantões (cadastro) | ❌ B2B sim, B2C não | ✅ | ✅ |
| Sofia voz (PJSIP) | ❌ | ✅ | ✅ |
| Teleconsulta (LiveKit) | ❌ | Opcional add-on | ✅ |
| Integração Tecnosenior | ❌ | Opcional add-on | ✅ B2B |
| Atendimento humano prioritário | ❌ | ❌ | ✅ |
| Push proativo (Sofia liga) | ❌ | ❌ | ✅ |
| Risco / Score baseline | ❌ | ✅ | ✅ |
| Cascade detection (12+1 dim) | ✅ | ✅ | ✅ |
| Revisão clínica de regras | ❌ | ❌ B2C, ✅ B2B | ✅ |

> Decidir caso a caso. Tabela acima é hipótese.

### 4.3 Suporte

| | Essencial | Padrão | Premium |
|--|-----------|--------|---------|
| Canal | E-mail | E-mail + WhatsApp comercial | E-mail + WhatsApp + telefone |
| Horário | 8h-18h dias úteis | 8h-22h | 24/7 |
| SLA primeiro contato | 24h | 4h | 1h (urgência clínica) |
| Onboarding | Self-service | Acompanhado por SDR | White-glove (1 sessão dedicada) |

---

## 5. Pricing — variáveis a definir

Os preços ficam a cargo do Alexandre. Variáveis que afetam:

1. **Custo unitário por mensagem** — Deepgram + LLM + storage.
   Estimativa atual:
   - Áudio (5-10s): R$ 0.02-0.04
   - Texto: R$ 0.005-0.015
   - Total mix: ~R$ 0.025/msg
   - Com 60% margem-meta: R$ 0.06/msg como floor de pricing

2. **Custo de atendimento humano** — central com X atendentes
   atende N tenants. Calcular custo/atendente/hora rateado.

3. **Margem-alvo por tier**:
   - Essencial: alta margem (60-70%), volume pequeno, baixa
     atenção
   - Padrão: margem média (40-50%), volume maior
   - Premium: margem mais baixa (30-40%) mas alto valor agregado
     + ticket alto

4. **Comparáveis no mercado**:
   - Sensi.ai US$ 50-200/usuário/mês (mas só voz ambiente)
   - Care.com Premium R$ 99-249/mês (família, sem IA)
   - K Health (US) US$ 9-20/mês (chat + médico)
   - Hippocratic AI: enterprise B2B (pricing não público)

5. **Pricing atual com Murilo de referência**: R$ 15/usuário/mês
   pra atendimento SOS (sem IA estruturada). É o piso histórico
   do mercado dele — qualquer plano nosso deve ficar acima disso
   por agregar IA + integração.

---

## 6. Add-ons (vendas cruzadas)

Independente do tier, oferecer:

- **Teleconsulta agendada**: R$ X por consulta + médico (ConnectaLive)
- **Integração Tecnosenior** (B2B): R$ Y/mês adicional
- **Pacote ampliado de mensagens**: 500 msg adicionais por R$ Z
- **Biometria de voz** (em B2C Essencial onde não inclui): R$ K/mês

---

## 7. Trial / Free tier

**Hipótese**: 14 dias de teste gratuito de Padrão (não Essencial).
Motivo: Essencial é comprado por preço; Padrão é comprado por
valor da Sofia. Trial de Essencial = sem incentivo a comprar.

Fim do trial: downgrade automático pra Essencial (não corta acesso,
só limita).

---

## 8. Métricas de sucesso comercial

Pra acompanhar a saúde dos planos depois do lançamento:

| Métrica | Definição | Alvo Y1 |
|---------|-----------|---------|
| MRR (Monthly Recurring Revenue) | Soma mensal de assinaturas ativas | R$ ___ |
| ARPU (Average Revenue Per User) | MRR / # de pacientes ativos | R$ ___ |
| Churn mensal | % de tenants que cancelaram no mês | < 5% |
| Trial → paid conversion | % que continua após trial | > 30% |
| Net Revenue Retention | (Expansão + renovações - churn) / base inicial | > 100% |
| Tickets de suporte por tenant/mês | Volume de atendimento humano | < 3 |

---

## 9. Próximos passos

1. **Alexandre define pricing** das células ___ acima.
2. **Decide features condicionais** da §4.2 (biometria em
   Essencial B2C? Plantão em Padrão Família?).
3. **Escolhe nomes finais** dos tiers (alguns já têm que mudar do
   "Essencial/Padrão/Premium" pra algo menos genérico se quiser
   diferenciação por segmento).
4. **Valida add-ons** da §6.
5. Implementação técnica (cap de quota + frontend de billing) fica
   pra sprint dedicado depois das decisões.

---

## 10. Decisões abertas pra debate

1. **Plano Indivíduo Premium custa quanto** vs **Família
   Essencial**? Indivíduo é mais barato pra fabricar (1 paciente, 0
   cuidador) mas pode ser caro de adquirir (idoso autônomo é raro).

2. **Cobramos por feature ou por tier**? Tier é simples, feature
   é flexível mas confunde. Recomendo tier + add-ons pontuais.

3. **Anuidade vs mensal**? Anuidade prende cliente mas dificulta
   experimentação. Recomendo mensal com desconto pra anual (ex:
   12% off na anuidade).

4. **Cobrança individual vs família agregada**? Família com 2
   pacientes paga R$ X (família) ou 2 × R$ Y (individual)? Modelo
   atual sugere família agregada (b2c_per_patient cobra por
   paciente, mas tier é família).

5. **Free tier permanente** (chamariz)? 5 mensagens/mês de graça +
   trial dos planos pagos? Risco de não converter mas reduz
   barreira de entrada.

---

Quando você fechar pricing + decisões da §10, eu monto a versão
final que vai pro site / pra apresentação comercial.
