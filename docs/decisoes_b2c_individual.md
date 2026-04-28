# Decisões — B2C + Individual (estrutura de licença + tom + uso)

**Data**: 2026-04-28
**Origem**: Alexandre confirmou que tem casos de **usuários
individuais** entrando agora. Precisamos fechar 3 pontos:

1. B2C: 1 paciente ou múltiplos por tenant?
2. Tom da Sofia em `individual` (forma de tratamento)
3. Cap de mensagens em planos com mensalidade

Cada decisão traz minha posição + alternativa + schema correspondente.

---

## 1. Estrutura de licença: B2C vs individual

### Cenários reais que vão acontecer

| Cenário | Quem assina | Quem é paciente | Quem reporta |
|---------|-------------|-----------------|--------------|
| Filho cuida da mãe em casa | Filho | Mãe | Filho (família) ou cuidador particular contratado |
| Filho cuida do pai E da mãe juntos | Filho | Pai E mãe | Filho ou 1+ cuidadores |
| Casal idoso, cada um contrata sua Sofia | Cada idoso | Si mesmo | Si mesmo (privacidade) |
| Idoso solo na casa, autônomo | Idoso | Si mesmo | Si mesmo |
| Filho mora longe, paga Sofia + cuidador particular pra mãe | Filho | Mãe | Cuidador particular reporta, filho recebe alertas |

### Posição (recomendação)

**Dois modelos distintos no banco:**

- **`B2C`** = 1 tenant, 1 contratante (familiar), **1-N pacientes**
  - Casos: filho cuidando de pai+mãe, filho contratando cuidador
    particular pra um pai, etc.
  - Cobra **por paciente** (R$ Y/paciente/mês)
  - Cuidadores cadastrados (familiares + cuidador particular se
    houver)
  - Plantões opcionais (se tem cuidador profissional rotativo)

- **`individual`** = 1 tenant, **1 paciente que assina sozinho**
  - Caso: idoso solo, autônomo, fala direto com Sofia
  - Cobra **por conta**
  - 0 cuidadores cadastrados (paciente é o único usuário)
  - Sem plantão (nunca)
  - Sofia trata paciente diretamente

**Casal idoso onde cada um contrata** = 2 contas `individual`
separadas (privacidade total — Sofia da esposa não acessa dados do
marido nem vice-versa).

### Por que assim?

1. **Privacidade**: casal pode ter informações que um não quer
   compartilhar com outro (depressão, dor, dependência alcoólica).
   Tenants separados resolvem.
2. **Simplicidade de licença**: 2 SKUs vs 5. B2C cobra por
   paciente, individual cobra por conta. Fim.
3. **Escala futura**: B2C com filho cuidando de 2 pais não vira
   "individual x2" — mantém família como unidade.

### Alternativa que descarto

Tratar tudo como `B2C` (até paciente solo seria "B2C com 1
paciente"). **Risco**: confunde modelo comercial e cria fluxos
condicionais demais ("se for B2C E só 1 paciente E paciente é o
contratante, comportar como individual").

---

## 2. Tom da Sofia em `individual`

### Considerações

- Idoso brasileiro **frequentemente** prefere "senhor/senhora"
  como sinal de respeito.
- Mas há quem prefira intimidade ("me chama de Maria mesmo, pelo
  amor de Deus").
- Tom da Sofia (calma, acolhedora, lenta) é **separado** da forma
  de tratamento.

### Posição (recomendação)

**Sofia pergunta no onboarding** e grava preferência por paciente:

```
Sofia: "Olá! Eu sou a Sofia, sua assistente.
       Você prefere que eu te chame de Maria ou de Dona Maria?
       Pode escolher o jeito que se sentir mais à vontade."
```

Resposta gravada em **`aia_health_patients.preferred_form_of_address`**:
- `first_name` → "Maria"
- `formal` → "Dona Maria" / "Sr. José"
- `full_first_name` → "Dona Maria Helena" (nome composto)
- `nickname` → "Mariazinha" (apelido carinhoso)

**Default conservador** se paciente não respondeu: `formal`. É
melhor errar pelo respeito.

### Tom independente da forma

Tom da Sofia em `individual` é **sempre acolhedor**, independente
de como chama. Características:

- Frases curtas (idoso processa mais devagar texto longo)
- Pausas naturais em áudio (TTS com SSML)
- Repete pergunta de forma diferente se não entender
- Nunca usa termos técnicos sem explicar
- Pergunta "sim ou não" em situações críticas (Grok insight)

Em B2C com cuidador, Sofia trata **cuidador** pelo primeiro nome
(filho/neto chama pela informalidade) e **paciente** pelo
`preferred_form_of_address` quando se dirige a ele.

---

## 3. Cap de mensagens em B2C/individual

### Problema

Em planos com mensalidade fixa, sem cap o cliente que abusa do uso
fica caro pra gente (custo Deepgram + LLM + storage). Mas
**capping rígido pode cortar quem mais precisa** — paciente em
crise mandando 30 mensagens numa noite é exatamente quando Sofia
deve atender.

### Posição (recomendação)

**Fair use com cap soft + emergency override:**

| Plano | Quota mensal | Comportamento |
|-------|--------------|---------------|
| Essencial | 100 msg/mês | Cobre uso normal (3-4 msg/dia) |
| Padrão | 300 msg/mês | Pra famílias mais ativas |
| Premium | ilimitado | + atendimento humano prioritário |

**Regras:**

1. **Aviso aos 80%** — Sofia menciona uma única vez: "Você usou
   80% do plano deste mês. Se passar de 100% continuo te atendendo,
   mas pra uso pesado o plano X custa mais barato."

2. **Acima de 100% — continua atendendo, com 2 modificações:**
   - Latência levemente maior (modelo mais barato no STT, classifier
     menor). Não cortado, só mais devagar.
   - Não dispara push proativo da Sofia até reset.

3. **Override de emergência — sempre passa**, mesmo se zerou quota:
   - Mensagens com keywords críticas (queda, dor torácica, parada,
     convulsão, sangramento intenso, AVC, suspeita IAM)
   - Detectada pelo regex fast-path (ele roda antes da quota check)
   - Loga em `quota_emergency_overrides` pra futuro audit

4. **Reset no dia 1** do mês via cron.

### Alternativa que descarto

**Cap rígido** (corta no Nº mensagem). **Risco**: dia que cuidador
realmente precisa, sistema falha por motivo financeiro. Imagem
ruim, risco clínico. Quota deve ser sinal econômico, não barreira
clínica.

---

## 4. Schema implementado (migration 053)

```sql
-- Forma de tratamento por paciente
ALTER TABLE aia_health_patients
    ADD COLUMN preferred_form_of_address TEXT
        CHECK (preferred_form_of_address IN (
            'first_name', 'formal', 'full_first_name', 'nickname'
        ))
        DEFAULT 'formal';

-- Modelo de licença + quota por tenant
ALTER TABLE aia_health_tenant_config
    ADD COLUMN licensing_model TEXT
        DEFAULT 'b2b_organization'
        CHECK (licensing_model IN (
            'b2b_organization',  -- ILPI/clínica/hospital — fatura por paciente
            'b2c_family',        -- 1 contratante, 1-N pacientes
            'individual'         -- paciente solo
        )),
    ADD COLUMN message_quota_monthly INT,  -- NULL = unlimited
    ADD COLUMN quota_warning_threshold_pct INT NOT NULL DEFAULT 80;

-- Contador mensal por tenant
CREATE TABLE aia_health_message_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    period_year INT NOT NULL,
    period_month INT NOT NULL,
    message_count INT NOT NULL DEFAULT 0,
    last_warning_sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, period_year, period_month)
);

-- Audit override de emergência
CREATE TABLE aia_health_quota_overrides (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    keyword_matched TEXT,
    report_id UUID,
    reason TEXT
);
```

---

## 5. Não vou implementar agora

A enforcement de quota (verificar no pipeline antes de processar)
fica pra próximo sprint. Hoje:

- ✅ Schema da migration 053 (decisões persistidas no banco)
- ✅ `licensing_model` e `tenant_type` independentes:
  - `tenant_type` afeta comportamento operacional (plantão, biometria)
  - `licensing_model` afeta cobrança e cap de uso
- ❌ Quota check no pipeline (próximo sprint)
- ❌ Cron de reset mensal (próximo sprint)
- ❌ Aviso aos 80% (próximo sprint)
- ❌ Onboarding pergunta forma de tratamento (próximo sprint —
  parte do classifier de inputs)

Por que separar: as decisões precisam estar no banco já pra cadastrar
os primeiros tenants individual sem dívida de schema. A enforcement
pode ser wired quando tivermos os primeiros tenants reais usando.

---

## 6. Pontos sensíveis pra Alexandre validar

1. **B2C cobra por paciente, individual cobra por conta** — confirma
   o modelo? Ou prefere algo mais simples (cobra por conta sempre)?

2. **`preferred_form_of_address` default formal** — concorda? Em ILPI
   pode parecer estranho ("Sr. João" pra cuidador profissional que
   chama todo mundo de "Seu João"). Default por `tenant_type` (formal
   em B2C/individual, first_name em ILPI)?

3. **Quotas dos planos**:
   - Essencial 100 msg/mês — ok pra residente solo?
   - Padrão 300 msg/mês — ok pra família ativa?
   - Premium ilimitado — preciso garantir que eu não me prejudique
     (premium ilimitado + atendimento humano prioritário pode ficar
     caro). Vale ter um teto suave (ex: 2000) e cap rígido só acima?

4. **Emergency override** — confirma que palavras-chave médicas
   (queda, parada, AVC, sangramento) sempre passam mesmo zerada
   quota? Acho não-negociável mas vale validar.
