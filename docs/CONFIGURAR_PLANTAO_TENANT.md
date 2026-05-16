# Configurar contato de plantão (P1 push) por tenant

**Quando usar:** após deploy da migration 080, cadastrar plantonistas que recebem WhatsApp quando entra handoff P1 clínico.

**Substituiu:** env var `P1_ESCALATION_PHONES` (anti-pattern global, agora vira fallback durante transição).

---

## Opção A — via SQL direto (mais rápido pra hoje)

SSH na VPS:

```bash
ssh root@72.60.242.245

docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c "
INSERT INTO aia_health_tenant_escalation_contacts (
    tenant_id, phone, contact_name, role, priorities
) VALUES (
    'connectaiacare_demo',
    'SEU_PHONE_AQUI',          -- ex: 5551992345678 (DDI+DDD+numero, só dígitos)
    'Alexandre Henrique',
    'admin_tenant',
    ARRAY['P1']
);"
```

Restart NÃO é necessário — a função consulta DB a cada P1 (não cacheia).

---

## Opção B — via API (quando UI estiver pronta, e pra audit)

```bash
# 1. Autenticar (pegar token):
TOKEN=$(curl -s -X POST https://care.connectaia.com.br/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alexandre@connectaiacare.com.br","password":"SUA_SENHA"}' \
  | jq -r '.token')

# 2. Cadastrar:
curl -X POST https://care.connectaia.com.br/api/admin/tenants/connectaiacare_demo/escalation-contacts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "5551992345678",
    "contact_name": "Alexandre",
    "role": "admin_tenant",
    "priorities": ["P1"]
  }'

# 3. Verificar:
curl -H "Authorization: Bearer $TOKEN" \
  https://care.connectaia.com.br/api/admin/tenants/connectaiacare_demo/escalation-contacts
```

---

## Opções de configuração

### Roles válidos
```
plantonista_l1       — triagem técnica (você inicialmente)
plantonista_l2       — clínico (Henrique futuro)
medico_responsavel   — geriatra (Coordenadora PUC / UFRGS)
enfermeiro_chefe     — supervisor turno enfermagem
gestor_unidade       — coordenador ILPI
admin_tenant         — papel super-admin do tenant
outro
```

### Prioridades
```
ARRAY['P1']                    — só emergência crítica (recomendado pra começar)
ARRAY['P1','P2']               — inclui drug_safety high (atenção: + ruído)
ARRAY['P1','P2','P3']          — todos os handoffs (só operacional dedicado)
```

### Schedule por turno (opcional, fase 2)
```sql
-- Plantão segunda a sexta, 8h às 18h:
UPDATE aia_health_tenant_escalation_contacts
   SET schedule_weekdays = ARRAY[1,2,3,4,5],
       schedule_start = '08:00',
       schedule_end = '18:00'
 WHERE phone = 'SEU_PHONE';

-- Plantão noturno (18h às 8h do dia seguinte) — não suportado ainda
-- (precisa lógica de wrap-around). Por enquanto: 2 contatos separados
-- ou deixa schedule NULL = 24/7.

-- Voltar pra 24/7:
UPDATE aia_health_tenant_escalation_contacts
   SET schedule_weekdays = NULL,
       schedule_start = NULL,
       schedule_end = NULL
 WHERE phone = 'SEU_PHONE';
```

### Rotação de plantonista
```sql
-- Desativar plantonista antigo:
UPDATE aia_health_tenant_escalation_contacts
   SET active = FALSE,
       deactivated_at = NOW()
 WHERE phone = 'PHONE_ANTIGO' AND active = TRUE;

-- Cadastrar novo (UNIQUE permite porque o antigo agora é inactive):
INSERT INTO aia_health_tenant_escalation_contacts (
    tenant_id, phone, contact_name, role, priorities
) VALUES (
    'connectaiacare_demo', 'PHONE_NOVO', 'Nome', 'plantonista_l1', ARRAY['P1']
);
```

---

## Testar que funcionou

1. **Confirmar cadastro:**
   ```bash
   ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c \"SELECT id, phone, contact_name, role, priorities, active FROM aia_health_tenant_escalation_contacts WHERE tenant_id='connectaiacare_demo';\""
   ```

2. **Disparar P1 de teste:** mandar "dor no peito" via WhatsApp pro chip ConnectaIACare (`+55 51 99454-8043`).

3. **Esperar < 5 segundos**, deve chegar no seu phone:
   ```
   🚨 P1 CLÍNICO
   Cuidador 555199XXXXXXX
   Motivo: acute_symptom_detected:dor no peito
   SLA: 5min. Atender em:
   app.connectaiacare.com.br/admin/system/operations/handoff
   (handoff_id=abc12345...)
   ```

4. **Validar auditoria:**
   ```bash
   ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c \"SELECT created_at, action, payload->>'reason' FROM aia_health_audit_log WHERE action IN ('clinical_handoff_initiated', 'escalation_contact_created') ORDER BY created_at DESC LIMIT 5;\""
   ```

---

## Próximos passos

- **UI admin** pra gerenciar contatos sem terminal — fase 2
- **Schedule overnight** (turno noite que cruza meia-noite) — fase 2
- **Notificação push mobile** (PWA) além de WhatsApp — fase 3
- **Rotação automática por escala** (gerar contatos efêmeros baseado em planilha de escala) — fase 3
