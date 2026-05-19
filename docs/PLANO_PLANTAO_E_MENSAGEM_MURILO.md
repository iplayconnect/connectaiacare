# Plantão Humano + Mensagem pro Murilo

**Contexto:** Murilo testou em 13/05, escreveu "dor no peito", sistema escalou P1 corretamente em 3 segundos — mas ficou 74h sem resposta humana porque não havia plantão configurado.

---

## 📱 Mensagem pra mandar pro Murilo (WhatsApp)

> Oi Murilo, tudo bem? Vi aqui que você fez um teste no dia 13 enviando "dor no peito" — o sistema respondeu corretamente em 3 segundos, escalou como emergência P1 e abriu uma chamada pra equipe clínica. Mas como ainda estamos em ambiente de testes, **não teve retorno do plantão médico** (não tem ninguém de plantão ainda, era teste técnico).
>
> Quando entrarmos em piloto real com parceiro integrador, o plantão fica ativo e a resposta humana acontece em até 5 minutos pro P1. Por enquanto, agradeço muito o teste — me ajudou a identificar exatamente onde o sistema está pronto e onde ainda precisa de gente atrás.
>
> Posso te pedir mais um teste? Manda mais alguns relatos como se você fosse cuidador real do Sr. Armindo — coisas do dia-a-dia ("ele tomou o losartana hoje", "ele dormiu mal", "PA tá 140x90") + algum cenário mais sério. Quero ver se a Sofia conversa bem com você e se as classificações dela batem com o que faria sentido na vida real. Qualquer feedback ajuda.

---

## 🩺 Cronograma de plantão sugerido

### Modelo proposto pra fase de testes (próximas 4-6 semanas)

| Camada | Quem | Responsabilidade | Janela | Notificação |
|---|---|---|---|---|
| **L1 — Triagem técnica** | Alexandre | Confirma se P1 é técnico (bug) ou clínico (real) | 24/7 enquanto piloto | WhatsApp push (configurado agora) |
| **L2 — Resposta clínica** | Henrique | Avalia caso, decide se precisa intervenção urgente | 9h-22h durante piloto | WhatsApp push (configurar quando ele toparmos formal) |
| **L3 — Decisão médica** | Geriatra UFRGS (futura) | Casos que precisam decisão médica formal | Comercial (horário PUC) | Email + WhatsApp |
| **L4 — Emergência absoluta** | SAMU 192 | Risco iminente de vida | 24/7 | Mensagem padrão pro próprio cuidador |

### Como funciona na prática

1. **Cuidador manda algo clinicamente sério** ("dor no peito", queda, sintoma agudo)
2. **Sofia escala P1 + abre handoff + responde cuidador**: "Recebi. Vou acionar equipe clínica AGORA. Se for emergência grave, ligue 192 (SAMU) também."
3. **WhatsApp push imediato** pro phone do plantão L1 (você)
4. **Você decide** em até 5min:
   - É bug técnico? → resolve no painel + ajusta cadastro
   - É clínico real? → encaminha pro L2 (Henrique) via WhatsApp/call
   - É emergência? → liga pro cuidador, confirma SAMU foi acionado
5. **Marca como resolvido** na Central com nota da resolução

### Quando piloto parceiro integrador entrar em produção real

Modelo escala pra:
- parceiro integrador já tem plantão médico próprio → integrar com fila deles
- Equipe ConnectaIACare faz triagem L1 e roteia pra fila parceiro integrador pra P1/P2 clínicos
- L1 cobre 24/7 (turnos: você + Murilo? + 1 contratação operacional?)

### Itens operacionais a definir (decisão sua)

1. **Qual phone do Alexandre vai receber P1 push?** Precisa configurar `P1_ESCALATION_PHONES` no .env da VPS
2. **Henrique aceita receber P1 também na fase de piloto?** (com expectativa de resposta dentro de 1h em horário comercial)
3. **Você quer que P2/P3 também notifique você?** (recomendado NÃO — vira ruído. P2/P3 deixa fluir pela Central 24h só)
4. **Auto-dismiss de casos antigos?** Sugestão: itens que ficam > 7 dias sem ação viram `auto_dismissed` com tag pra retrospectiva mensal. Evita fila acumular.

### Métricas pra acompanhar

| Métrica | Alvo | Como medir |
|---|---|---|
| Tempo até claim P1 | < 5min | painel Central · 24h |
| Tempo até resolved P1 | < 30min | painel Central · 24h |
| % P1 com resposta humana | 100% | export semanal handoff |
| P1 stale > 1h | 0 | alerta dedicado |
| Falsos P1 (foi bug, não clínico) | < 5% | retrospectiva mensal |

---

## ✅ O que JÁ está deployado pra suportar isso

| Mudança | Status |
|---|---|
| Fix do contador "SLA estourado" (calcula dinamicamente, não depende de job) | ⚠️ Pendente merge + deploy |
| Push WhatsApp pra `P1_ESCALATION_PHONES` quando entra P1 clínico | ⚠️ Pendente merge + deploy + config env var |
| Notificação genérica pra Central 24h (5551997354484) | ✅ Já funcionava (só ninguém olhava) |

## 🛠️ Configuração necessária na VPS após o merge

```bash
# Adicionar ao .env do backend (sub valor pelo seu phone WhatsApp):
echo 'P1_ESCALATION_PHONES=5551999XXXXXX' >> /root/connectaiacare/backend/.env

# Restart pra ler env novo:
cd /root/connectaiacare && docker compose -f docker-compose.contabo.yml restart api
```

Se quiser múltiplos numeros: `P1_ESCALATION_PHONES=5551999XXXXXX,5551888XXXXXX`
