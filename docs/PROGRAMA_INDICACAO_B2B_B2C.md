# Programa "ConnectaIA Indica" — B2B como canal orgânico de B2C

> Endereça o feedback do Opus Chat 2ª rodada (Ponto 2): "O cliente B2B
> é o canal de aquisição mais natural e barato do B2C — os filhos dos
> idosos assistidos já confiam no serviço".
>
> Preparado: 23/04/2026 · Implementação: Fase 2.A (pós-demo)

---

## 1. Por que é poderoso

O **cuidador profissional** da SPA Tecnosenior que recebe áudios do
ConnectaIACare hoje tem rede social natural:

- Famílias dos 20-50 idosos assistidos pela SPA
- Colegas cuidadores que trabalham em outros lares
- A própria família do cuidador (filhos, pais, avós) que podem querer monitoramento

Dessas 3 redes, a **mais valiosa** é a primeira: famílias dos idosos da
SPA. Por quê?

1. **Prova social forte**: já viram o sistema funcionando na SPA, confiam.
2. **Dor real**: 40% dos filhos de idosos em SPA também cuidam de outro
   ente querido em casa (cônjuge idoso do pai, avó, sogro).
3. **Renda compatível**: filhos que pagam SPA privada (R$3-5k/mês) têm
   poder aquisitivo pra R$49,90-149,90 do B2C.
4. **Tempo disponível zero**: eles querem tecnologia pra cuidar do "outro"
   idoso (que não está na SPA) porque não conseguem estar presencialmente.

CAC estimado: **R$20-40 por conversão** (vs R$150-300 em ads digitais).
LTV: 8-14 meses média setor healthcare, **R$500-2000 por cliente**.

---

## 2. Arquitetura da indicação

### 2.1 Quem pode gerar código

3 origens distintas, cada uma com estrutura de comissão própria:

| Origem | Código exemplo | Comissão | Pagamento |
|--------|----------------|----------|-----------|
| **SPA Tecnosenior** | `SPA-VIDA-PLENA` | 1 mês grátis da mensalidade B2B | Crédito próxima fatura |
| **Cuidador profissional** | `CUIDADOR-MARIA123` | R$50 Pix | 2º mês pago do indicado |
| **Familiar cliente B2C** | `FAMILIA-JOAO456` | 10% off próprios 3 meses | Crédito recorrente |

### 2.2 Fluxo de indicação (3 touchpoints)

**Touchpoint 1 — Portal do B2B (SPA)**
- Banner na dashboard: "Recomende a famílias · ganhe 1 mês grátis"
- QR code + link único da SPA: `https://care.connectaia.com.br/assine?ref=SPA-VIDA-PLENA`
- Material físico: cartão de visita + folder pra distribuir nas visitas

**Touchpoint 2 — Portal do paciente (após teleconsulta)**
Depois da família acessar o portal com PIN, vê banner contextual:
> "Cuida de outros entes queridos em casa?  
> Famílias que assinam o Essencial (R$49,90/mês) têm monitoramento 24h
> com WhatsApp + central humana. [Saiba mais]"

Click abre landing page B2C com código pré-aplicado.

**Touchpoint 3 — Cuidador profissional**
Cuidador da SPA tem seu próprio código + QR (gerado no portal B2B interno).
Pode compartilhar direto via WhatsApp com família ou colegas.

### 2.3 Attribution e anti-fraude

Cada conversão é atribuída via:
- Cookie 30 dias após click no link
- Código aplicado manualmente no checkout
- UTM parameters completos no analytics

Proteções:
- Não pagar comissão até o **2º mês pago** (descarta trial/chargebacks)
- Limite de 1 código por indicado (não empilha)
- SPA não pode indicar a si mesma (cross-check via CNPJ na owner)

---

## 3. Schema (migration 013, Fase 2.A)

```sql
-- Códigos de indicação ativos
CREATE TABLE aia_health_referral_codes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code TEXT UNIQUE NOT NULL,
    
    issuer_type TEXT NOT NULL CHECK (issuer_type IN (
        'spa_partner', 'caregiver', 'family_customer'
    )),
    issuer_id UUID NOT NULL,                  -- polimórfico
    issuer_display_name TEXT,                 -- "SPA Vida Plena"
    
    commission_type TEXT NOT NULL CHECK (commission_type IN (
        'fixed_brl', 'percentage', 'months_free_b2b', 'months_discount_b2c'
    )),
    commission_value NUMERIC(10,2) NOT NULL,  -- 50.00 | 0.10 | 1 | 3
    commission_duration INTEGER,              -- em meses (aplicável)
    
    -- Condições de elegibilidade
    applies_to_plans TEXT[] DEFAULT ARRAY['essencial','familia','premium'],
    min_months_before_payout INTEGER DEFAULT 2,
    max_uses INTEGER,                         -- NULL = ilimitado
    
    active BOOLEAN NOT NULL DEFAULT TRUE,
    active_until TIMESTAMPTZ,
    
    total_uses INTEGER NOT NULL DEFAULT 0,
    total_conversions INTEGER NOT NULL DEFAULT 0,
    total_commission_paid NUMERIC(12,2) NOT NULL DEFAULT 0,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON aia_health_referral_codes(code) WHERE active = TRUE;
CREATE INDEX ON aia_health_referral_codes(issuer_type, issuer_id);

-- Histórico de uso (1 registro por clique/assinatura)
CREATE TABLE aia_health_referral_attributions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    referral_code_id UUID NOT NULL REFERENCES aia_health_referral_codes(id),
    
    -- Tracking
    clicked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_address INET,
    user_agent TEXT,
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    
    -- Atribuição (preenchidos quando converte)
    subscription_id UUID,                     -- FK futura pra aia_health_subscriptions
    converted_at TIMESTAMPTZ,
    
    -- Pagamento da comissão
    commission_due_brl NUMERIC(10,2),
    commission_eligible_after TIMESTAMPTZ,    -- data em que pode pagar
    commission_paid_at TIMESTAMPTZ,
    commission_payment_reference TEXT,        -- Pix/boleto/crédito
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON aia_health_referral_attributions(referral_code_id, converted_at);
CREATE INDEX ON aia_health_referral_attributions(commission_paid_at)
    WHERE converted_at IS NOT NULL AND commission_paid_at IS NULL;
```

---

## 4. UI mínima na demo 28/04

Pra mostrar pro Murilo que já pensamos no canal orgânico:

**Mockup banner no portal B2B** (dashboard SPA):
```
┌─────────────────────────────────────────────────────────┐
│  🎯  Indique ConnectaIACare pra família                 │
│                                                         │
│  Famílias já atendidas pela SPA Vida Plena recebem     │
│  monitoramento 24h em casa por R$49,90/mês.            │
│                                                         │
│  A cada conversão, 1 mês grátis na mensalidade da SPA. │
│                                                         │
│  Seu código: [ SPA-VIDA-PLENA ]   [Copiar] [QR code]   │
└─────────────────────────────────────────────────────────┘
```

Mesmo banner mostrado **apenas** visualmente — com `disabled` nos botões,
porque a infra de billing B2C ainda não existe. Basta pro Murilo entender
o caminho.

---

## 5. Modelagem de impacto (pra pitch)

**Premissas conservadoras:**
- 10 SPAs no piloto B2B
- Cada SPA atende 30 idosos em média = 300 idosos cobertos
- Cada idoso tem 2.5 familiares próximos = 750 famílias potenciais
- **Taxa de conversão realista**: 3% em 6 meses = 22 conversões
- Ticket médio B2C: R$69,90 (mistura Essencial+Família)
- **MRR B2C gerado por canal B2B**: R$1.538/mês no 6º mês

**Se 1 SPA converter 10 idosos ao longo do ano**:
- SPA ganha 10 meses grátis × R$3.500 mensalidade B2B = **R$35.000/ano de economia**
- ConnectaIA ganha 10 × R$69,90 × 12 meses = **R$8.388 MRR adicional**
- **Win-win óbvio** — SPA tem incentivo forte, ConnectaIA tem CAC negativo

---

## 6. Roadmap de implementação

| Fase | Escopo | Prazo |
|------|--------|-------|
| MVP banner visual (demo) | Banner HTML no portal B2B, sem backend | ✅ pode ser feito agora |
| Schema + geração de código | Migration 013 + API de CRUD de códigos | Semana 2 pós-demo |
| Tracking de clicks | Landing page com `?ref=` + cookie 30d | Semana 3 |
| Conversão attribution | Integração com billing Stripe + webhook | Semana 4-5 |
| Painel de comissão (SPA) | View "minhas indicações" + histórico | Semana 6 |
| Pagamento automatizado | Integração PagBank/Asaas pra Pix | Semana 7-8 |

---

## 7. Riscos e mitigações

**Risco**: SPA tem receio de "perder cliente" pra B2C.
**Mitigação**: os produtos são complementares — B2C não cuida no local
(só monitora remoto), SPA continua sendo o cuidado presencial.
Comunicação clara: "indique pra famílias que NÃO conseguem ter um idoso
em SPA mas querem monitoramento digital".

**Risco**: Cuidador distribui código sem contexto e gera churn alto.
**Mitigação**: Material curado + vídeo curto de 2 min explicando o produto
que o cuidador compartilha junto com o código.

**Risco**: Fraude (cuidador cria família fake pra ganhar R$50).
**Mitigação**: Payout só no 2º mês pago + CPF validado + cruzamento de
IP/device na conversão.

---

## 8. Métricas-chave

- **Taxa de conversão** de click → trial (meta: 30%)
- **Taxa de trial → paid** (meta: 40%)
- **CAC via canal B2B** (meta: <R$40)
- **MRR atribuído ao canal** (meta: 20% do MRR B2C no 1º ano)
- **NPS do cuidador indicador** (satisfação com programa)

---

## 9. Próximo passo imediato

Pro Opus na próxima sessão:
1. Validar commission_structure proposta (valores estão alinhados ao budget?)
2. Decidir se SPA ganha comissão em crédito (mais simples) ou em Pix (mais atrativo)
3. Design do banner + landing page (pode ser feito pelo Claude Design)
4. Scripts de comunicação pros cuidadores (WhatsApp templates)
