# Demo Script — Reunião ConnectaIACare (sexta 24/04/2026)

> **Contexto**: reunião com Murilo (Tecnosenior+MedMonitor) e Vinicius (Amparo) para discutir parceria em cuidado clínico in-house.
> **Objetivo do Alexandre**: apresentar MVP funcional de surpresa no momento certo.
> **Duração ideal da demo**: 5-7 minutos.

---

## Preparação antes da reunião

### Equipamento
- [ ] Laptop com dashboard aberto em `https://demo.connectaiacare.com` (ou localhost:3030)
- [ ] Celular com WhatsApp instalado enviando para o número **555189592617** (instância V6)
- [ ] Segundo celular (opcional) para receber ligação proativa da Sofia Voz — representando "o familiar"
- [ ] Internet estável; backup: hotspot do celular
- [ ] Áudio do laptop funcionando para demonstração ao vivo

### Pré-demo (30 min antes)
- [ ] Verificar backend rodando: `curl https://demo.connectaiacare.com/health`
- [ ] Limpar relatos antigos se desejar demo limpa: `DELETE FROM aia_health_reports WHERE tenant_id='connectaiacare_demo';`
- [ ] Testar envio de áudio via WhatsApp e fluxo end-to-end 1x
- [ ] Fotos dos 8 pacientes carregando no dashboard

---

## Roteiro sugerido

### Fase 1 — Conversa sobre o problema (20 min)
Durante a conversa sobre cuidado clínico in-house, o Alexandre deixa Murilo e Vinicius falarem das dores. Escuta. Anota. Não menciona o MVP.

### Fase 2 — A surpresa (momento-chave)

**Gatilho**: quando alguém mencionar adesão, registro de cuidador, alertas perdidos, ou comunicação com família, Alexandre puxa o celular.

> *"Sabe o que vocês estão descrevendo? Deixa eu mostrar uma coisa que a gente já construiu."*

### Fase 3 — Demo ao vivo (5 min)

**Passo 1** — Abre o WhatsApp no celular e grava um áudio (já ensaiado):

> *"Aqui é a Joana do plantão da noite. Tô com a Dona Maria da Silva. Ela não quis jantar, tá com falta de ar, o joelho direito inchou bastante desde ontem, e a temperatura tá 37.8. Acho que a gente precisa chamar alguém pra dar uma olhada."*

Envia o áudio para **555189592617**.

**Passo 2** — Enquanto o processamento roda (~15-30s), Alexandre explica:

> *"A IA está baixando o áudio, transcrevendo com Deepgram em português brasileiro, extraindo o nome do paciente com Claude, e buscando na base quem é a Dona Maria da Silva."*

**Passo 3** — WhatsApp responde com foto + nome:

> 📋 *Você está relatando sobre:*
> *Maria da Silva Santos · 87 anos · SPA Vida Plena — Ala B · Quarto 12*
> *Responda SIM para confirmar ou NÃO se for outra pessoa.*

Alexandre responde **SIM**.

**Passo 4** — Em ~20s, WhatsApp responde com análise completa:

> 🚨 *Relato registrado — Maria da Silva Santos*
>
> 📊 *Resumo*: Paciente com IC + HAS relatou recusa alimentar, dispneia, edema de MMII e febrícula. Combinação clássica sugestiva de descompensação cardíaca aguda.
>
> 🏷️ *Classificação: URGENTE*
>   _IC classe II conhecida + 3 sinais de descompensação simultâneos + febre em idosa imunossenescente_
>
> 🔔 *Alertas*: Descompensação cardíaca suspeita (alto) · Possível processo infeccioso (médio)
>
> 💡 *Recomendações para você*: Elevar cabeceira a 45°. Verificar edema com compressão. Não oferecer líquidos em volume. Aguardar enfermagem.
>
> 👩‍⚕️ *Equipe de enfermagem foi notificada.*

**Passo 5** — Alexandre abre o laptop, mostra o dashboard:

> *"Enquanto isso, no painel do médico…"*

No dashboard aparece:
- KPIs no topo: 1 urgente/crítico piscando em laranja
- Relato aparecido em tempo real na lista
- Clica no relato → abre detalhe com player do áudio original, transcrição palavra-por-palavra, análise estruturada em JSON legível, cards de alerta, recomendações, tags, condições do paciente, medicações em uso

**Passo 6 (opcional, WOW factor)** — Segundo celular de Alexandre toca.

> *"E tem mais uma coisa…"* (atende no speaker)

Voz natural da Sofia Voz:

> *"Olá, senhora Ana, aqui é a ConnectaIACare, assistente de cuidado da sua mãe Maria. Precisei te avisar que ela apresentou alguns sinais que merecem atenção — recusou a janta, está com um pouco de falta de ar e inchaço na perna. A equipe de enfermagem já foi acionada e vai atendê-la nos próximos minutos. Você prefere que eu te passe para a enfermeira de plantão agora?"*

### Fase 4 — Fechamento (pausa de silêncio, depois…)

> *"Isso aqui está rodando há [X] dias. Funciona em português nativo. Respeita CFM, LGPD, integra FHIR. Murilo, o MedMonitor entra aqui [apontando pra sinais vitais]. Amparo entra aqui [apontando pra relatos de crônicos em casa]. Tecnosenior entra com sensores aqui [apontando pro ambiente]."*
>
> *"A gente pode escalar isso juntos. Como vocês veem?"*

---

## Áudios pré-gravados para demonstrar 3 classificações

### Áudio A — ROTINA (passou bem)
> *"É a Joana, plantão da noite. A Dona Antonia passou bem a noite, dormiu tranquila. Tomou os remédios no horário. No café ela comeu pouco mas aceitou o chá. Humor estável, sem queixas."*

**Resultado esperado**: classificação ROUTINE, sem alertas, recomendação de observação rotineira.

### Áudio B — ATENÇÃO (algo a observar)
> *"Joana falando. Passando sobre o Seu João. Ele tá mais confuso hoje, não reconheceu a filha no telefone. A alimentação tá bem mas o sono ele acordou várias vezes. Tá pedindo pra ir embora, repetindo o nome da esposa que já faleceu. Quero deixar registrado."*

**Resultado esperado**: classificação ATTENTION, alerta nível médio sobre mudança de padrão cognitivo em paciente com Alzheimer.

### Áudio C — URGENTE/CRÍTICO (para o momento-chave)
Ver passo 1 acima (caso Dona Maria da Silva).

**Resultado esperado**: classificação URGENT ou CRITICAL, ligação proativa para familiar.

---

## Cenários de backup (se algo falhar)

| Falha | Plano B |
|-------|---------|
| WhatsApp não envia áudio | Vídeo pré-gravado do fluxo em 60s rodando no laptop |
| Deepgram falha | Transcrição mockada aparecendo como placeholder |
| Claude demora > 30s | *"Estamos em modelo de raciocínio pesado — em produção usaremos o modelo rápido."* |
| Sofia Voz não liga | *"Esta feature fica para quando passarmos do piloto; hoje focamos no registro e análise."* |
| Internet caindo | Hotspot do celular; se persistir, demo offline com screenshots navegados |

---

## Frases-chave para usar durante a demo

- *"Isso aqui já existe, está funcionando."*
- *"Vocês acabaram de ouvir o que pode virar padrão nacional em 2 anos."*
- *"A tecnologia é a parte fácil. O diferencial é o que vocês três trazem: pacientes reais, dispositivos homologados, expertise clínica."*
- *"Não estamos competindo com Silicon Valley. Estamos fazendo algo que eles não podem: plataforma integrada brasileira, em português clinicamente correto, com LGPD nativa."*
- *"Nossa tese é que o futuro do cuidado é contínuo, domiciliar, assistido por IA e mediado pelo WhatsApp. E estamos a 24 horas de começar a provar isso."*

---

## Depois da reunião

- [ ] Enviar o PITCH_DECK.md em PDF e o ONE_PAGER.md impresso (ou por email) no mesmo dia.
- [ ] Agendar DPIA conjunta (60 min) com jurídicos das 4 empresas nas 2 semanas seguintes.
- [ ] Propor kick-off técnico com times de Tecnosenior e MedMonitor para API integration.
- [ ] NDA + Carta de Intenções rascunhada para assinatura em até 10 dias úteis.
