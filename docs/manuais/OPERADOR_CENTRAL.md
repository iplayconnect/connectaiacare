# Manual do Operador Central — ConnectaIACare

**Versão:** 1.0
**Data:** 2026-05-18
**Para quem:** Operadores de plantão 24/7 da Central de Atendimento ConnectaIACare (técnicos, auxiliares de enfermagem, enfermeiros, plantonistas administrativos).

---

## Índice

1. [Bem-vindo à Central](#1-bem-vindo-à-central)
2. [Seu papel em 30 segundos](#2-seu-papel-em-30-segundos)
3. [Primeiro login + heartbeat](#3-primeiro-login--heartbeat)
4. [A tela principal — Handoff Inbox](#4-a-tela-principal--handoff-inbox)
5. [Como ler a fila priorizada](#5-como-ler-a-fila-priorizada)
6. [Reivindicar (claim) um atendimento](#6-reivindicar-claim-um-atendimento)
7. [Atender o paciente / cuidador / familiar](#7-atender-o-paciente--cuidador--familiar)
8. [Quando escalonar para L2, L3, L4](#8-quando-escalonar-para-l2-l3-l4)
9. [Resolver o care_event — outcomes possíveis](#9-resolver-o-care_event--outcomes-possíveis)
10. [SLA — o que você precisa cumprir](#10-sla--o-que-você-precisa-cumprir)
11. [Pausar plantão (banheiro, almoço, troca)](#11-pausar-plantão-banheiro-almoço-troca)
12. [Métricas pessoais — como você é avaliado](#12-métricas-pessoais--como-você-é-avaliado)
13. [Casos típicos — playbook](#13-casos-típicos--playbook)
14. [Frases e tom — como falar com cada perfil](#14-frases-e-tom--como-falar-com-cada-perfil)
15. [Erros comuns no início](#15-erros-comuns-no-início)
16. [Ferramentas auxiliares](#16-ferramentas-auxiliares)
17. [FAQ do Operador](#17-faq-do-operador)
18. [Contatos de emergência](#18-contatos-de-emergência)

---

## 1. Bem-vindo à Central

Você está no **núcleo operacional** da ConnectaIACare. Tudo que a Sofia (a IA) não resolve sozinha chega aqui — e você é a pessoa que coloca **olho humano** em cada caso.

Sua função é simples de descrever e exige muito de quem faz:

> Receber um sinal de risco, **entender em segundos** se é grave, **agir certo** e **registrar tudo**.

A Sofia faz o filtro inteligente. Você toma a decisão final. Cuidador, família e paciente confiam que **alguém competente está olhando**, mesmo às 3h da manhã.

Bem-vindo. Este manual é seu mapa.

---

## 2. Seu papel em 30 segundos

| Você É | Você NÃO É |
|---|---|
| Olho humano sobre a fila de risco | Médico que prescreve |
| Quem decide se vira P1, sobe ou descarta | Substituto do SAMU em emergência grave |
| Quem acolhe família ansiosa em tempo real | Atendente de telemarketing |
| Quem aciona médico/enfermeiro/SAMU corretamente | Quem aguenta sozinho um caso clínico |
| Quem registra outcome auditável | Quem "deixa pra resolver depois" |

**Regra de ouro:** quando em dúvida entre **escalonar** ou **resolver sozinho**, sempre escalone. Custa pouco. Errar pra cima é sempre menos grave do que errar pra baixo.

---

## 3. Primeiro login + heartbeat

### Login

1. Abra `https://app.connectaia.com.br/login`
2. Use o e-mail e senha que recebeu
3. Troque a senha na primeira entrada
4. Habilite 2FA (obrigatório para operador)

### Iniciar plantão (heartbeat)

Sidebar → **Operações** → **Meu Plantão** → botão **Iniciar Plantão**

O que isso faz:
- Marca você como **disponível** na fila
- Inicia heartbeat (sistema verifica a cada 30s se você está online)
- Aplica seu **template de turno** (paciente que cuida, urgência que atende)

Se você não inicia plantão, **a fila não vai chegar pra você**. Mesmo logado, sem heartbeat ativo, você fica em standby.

### Confirmar status

Topo direito da tela:
- 🟢 **Disponível** — pode receber novos casos
- 🟡 **Em atendimento** — você claimed um caso, fila não te empurra novo até resolver
- ⏸️ **Em pausa** — você sinalizou pausa (banheiro, almoço)
- 🔴 **Offline** — heartbeat caiu (mais de 90s sem ping)

---

## 4. A tela principal — Handoff Inbox

Sidebar → **Operações** → **Handoff Inbox**

### Layout

**Topo:**
- Filtros (urgência, paciente, status)
- Indicador de SLA (quantos casos perto de estourar)

**Coluna esquerda — Fila priorizada:**
- Lista de casos abertos
- Cada card mostra: paciente, urgência, motivo resumido, tempo decorrido, SLA restante

**Coluna central — Caso ativo:**
- Quando você claim, abre aqui
- Conversa completa com cuidador/paciente/família
- Contexto clínico (prontuário 360°)
- Ações disponíveis

**Coluna direita — Painel auxiliar:**
- Sinais vitais recentes
- Medicações ativas
- Cross-validation alerts
- Histórico de care_events recentes

### Como a fila chega

1. Sofia analisa mensagem que chegou (WhatsApp/voz)
2. Classifica urgência (P1/P2/P3)
3. Cria `aia_care_event` com status `active`
4. Sistema empurra pra fila do operador disponível
5. Você vê **piscando + som de alerta** se P1

---

## 5. Como ler a fila priorizada

### Cor + urgência

| Cor do card | Urgência | Tempo máximo até claim |
|---|---|---|
| 🔴 Vermelho piscando | P1 | **1 min** pra reivindicar |
| 🟠 Laranja | P2 | 5 min |
| 🟡 Amarelo | P3 | 30 min |

### Informações no card

- **Paciente**: nome + idade + condições principais
- **Urgência**: P1/P2/P3 + label do motivo (ex: "Dor torácica relatada")
- **Origem**: Cuidador / Familiar / Paciente direto
- **Tempo decorrido**: quanto tempo o caso está aberto
- **SLA restante**: countdown até estourar

### Ordenação

A fila ordena por:
1. P1 primeiro (sempre)
2. Dentro do mesmo nível, por SLA mais próximo de estourar
3. Empate → por created_at (mais antigo primeiro)

Não tente "escolher caso fácil" — o sistema empurra o que importa.

### Casos que NÃO aparecem na sua fila

- Casos que **outro operador claimou** (você vê com label "Em atendimento por João")
- Casos **resolvidos** (vão pra histórico, aba separada)
- Casos **fora do seu escopo** (ex: você é P3-only, P1 vai pra outro)
- Casos de **tenants** aos quais você não tem acesso (se for operador multi-tenant restrito)

---

## 6. Reivindicar (claim) um atendimento

### Como funciona

- Clica no card da fila
- Botão grande **Reivindicar Atendimento**
- Sistema marca `claimed_at` (alimenta SLA)
- Caso muda pra status `in_progress`
- Outros operadores veem com seu nome ("Em atendimento por Maria")

### Race condition

Se dois operadores clicarem ao mesmo tempo no mesmo P1:
- Sistema usa **lock pessimista**
- Quem clicou primeiro ganha
- O outro vê mensagem "Caso já reivindicado por X"
- Não trava ninguém — apenas redireciona

### Não consigo claim?

- Verifique seu status (está disponível?)
- Verifique sua conexão (heartbeat caiu?)
- Caso pode ter virado P2→P1 e estar fora do seu escopo
- Em último caso, F5 + tentar de novo

### Devolver caso à fila

Se você claimed mas percebe que **não é o operador certo** (ex: precisa de enfermeiro e você é técnico):

- Botão **Devolver à Fila** (ou **Encaminhar a enfermeiro**)
- Escreva motivo curto (auditado)
- Sistema reposiciona o caso na fila com prioridade aumentada (porque tempo passou)

---

## 7. Atender o paciente / cuidador / familiar

### Estrutura típica de um atendimento

**Passo 1 — Leia o contexto antes de falar (15s)**
- Quem é o paciente?
- O que disseram?
- O que a Sofia já respondeu?
- Tem cross-validation alert?
- Sinais vitais recentes?

**Passo 2 — Cumprimente e se identifique (10s)**
- "Olá, sou [seu nome], da Central da ConnectaIACare."
- Use o nome da pessoa que está do outro lado
- Se for cuidador, trate como colega de trabalho
- Se for familiar, trate com acolhimento
- Se for paciente, trate com respeito + simplicidade

**Passo 3 — Confirme o motivo (20s)**
- "Vi aqui que você relatou [resumo]. Pode me contar mais?"
- Não assuma — confirme o que entendeu
- Se for P1, **pergunte direto**: "Está consciente? Respirando bem? Onde dói exatamente?"

**Passo 4 — Decida ação (variável)**
- Resolve direto (orientação, esclarecimento)?
- Escalona pra L2 (enfermeiro)?
- Escalona pra L3 (médico de plantão)?
- Aciona L4 (SAMU)?
- Aciona família?

**Passo 5 — Comunique decisão**
- "Vou pedir pra enfermeira ligar agora, tudo bem?"
- "Acabei de acionar o SAMU, mantenha [paciente] sentado, eu fico na linha."
- "Pode ficar tranquila, isso é normal nesse remédio, mas vou anotar."

**Passo 6 — Registre outcome**
- Antes de fechar caso, escolha outcome (Seção 9)
- Anote nota livre (o que aconteceu, o que orientou)
- Se escalou, marque para quem
- **Audit log grava tudo**

---

## 8. Quando escalonar para L2, L3, L4

### Camadas de plantão

| Camada | Quem | Quando aciona |
|---|---|---|
| **L1** | Você (operador central) | Primeiro contato, triagem fina, orientação simples |
| **L2** | Enfermeiro de plantão | Sinal clínico que precisa interpretação técnica |
| **L3** | Médico de plantão | Decisão clínica, prescrição, condução de caso |
| **L4** | SAMU / Hospital | Emergência fora do escopo (parada, AVC estabelecido, trauma) |

### Quando subir para L2 (enfermeiro)

- Sinal vital alterado mas estável (FC 120, PA 160/100, glicemia 280)
- Queda sem fratura aparente mas com dor
- Confusão mental nova
- Vômito persistente
- Lesão de pele suspeita
- Dúvida sobre uso de medicação

### Quando subir para L3 (médico)

- Enfermeiro pediu (passa o caso adiante)
- Dor torácica típica (não foi descartada por SAMU)
- Crise hipertensiva (PA >180/110)
- Glicemia >400 ou <50 sintomática
- Sangramento ativo
- Convulsão
- Suspeita de AVC (mesmo sinal sutil)

### Quando acionar L4 (SAMU)

**Sempre** se:
- Parada cardiorrespiratória
- AVC com sinais claros (FAST positivo)
- Inconsciência
- Trauma grave (queda de altura, atropelamento)
- Sangramento que não cessa
- Crise convulsiva prolongada (>5min)
- Engasgo grave

**Não espere autorização do médico para chamar SAMU em P1 real.** Chama o SAMU primeiro, avisa o médico depois. SAMU não tem custo pra família e salva vida.

### Como acionar cada camada

- **L2/L3**: botão no painel → "Escalar para enfermeiro/médico" → sistema empurra para fila deles + WhatsApp push
- **L4**: botão "Acionar SAMU 192" → abre fluxo guiado (anota chamada, número do protocolo, hora) → audit log
- **Família**: botão "Notificar família" → envia WhatsApp para responsáveis cadastrados

### O que NÃO fazer

- Não substitua decisão médica (você não prescreve, não desaconselha hospital)
- Não diga "não é nada" se há dúvida
- Não pause o caso (passe adiante se sair de plantão)
- Não tente "resolver pra economizar escalada" — escalada é o produto

---

## 9. Resolver o care_event — outcomes possíveis

Quando termina o atendimento, você escolhe um **outcome**:

| Outcome | Quando usar |
|---|---|
| `resolved_information` | Era dúvida, você esclareceu, paciente OK |
| `resolved_orientation` | Você deu orientação não-clínica (hidratação, repouso) |
| `escalated_l2_nurse` | Enfermeiro assumiu |
| `escalated_l3_doctor` | Médico assumiu |
| `escalated_l4_samu` | SAMU acionado |
| `notified_family` | Família foi avisada, eles tomam ação |
| `false_alarm` | Era falso positivo (Sofia interpretou mal, sem risco) |
| `patient_refused` | Paciente recusou atendimento (registrar) |
| `unreachable` | Não conseguiu contato (tentativas registradas) |
| `expired` | Caso passou do SLA e ninguém pegou (auditável) |

### Campos obrigatórios

- **Outcome** (escolha acima)
- **Nota livre** (o que aconteceu, em 1-3 frases)
- **Tempo de atendimento** (sistema calcula automático)

### Campos opcionais mas úteis

- **Tag** (ex: "queda", "medicação", "dúvida-família")
- **Próxima ação prevista** (ex: "Médico vai retornar em 2h")
- **Alerta para o próximo turno** (ex: "Atenção: paciente reclamou de tontura novamente")

### Fechar caso

Botão **Resolver Atendimento** → caso muda pra `resolved`, sai da sua fila, fica no histórico.

---

## 10. SLA — o que você precisa cumprir

### Promessas contratuais

| Métrica | Promessa |
|---|---|
| P1: criação → claim | ≤ 1 min em 95% dos casos |
| P1: claim → primeira resposta humana | ≤ 4 min em 95% dos casos |
| P1: total criação → resolução/escalada | ≤ 15 min em 90% dos casos |
| P2: criação → claim | ≤ 5 min em 90% |
| P2: claim → primeira resposta | ≤ 25 min em 90% |
| P3: criação → resposta | ≤ 2h em 80% |

### Você é responsável por

- **Claim rápido** (não deixa P1 esperando)
- **Resposta humana real** (não envia mensagem automática achando que conta)
- **Resolução ou escalada limpa** (não deixa P1 aberto por horas)

### O que conta como "primeira resposta humana"

- Mensagem digitada por você no chat (não conta auto-reply da Sofia)
- Ligação iniciada para o cuidador/família
- Acionamento de L2/L3/L4 (conta como ação humana sobre o caso)

### O que NÃO conta

- Você abrir o caso e ler (sem responder)
- Resposta da Sofia (já estava lá antes)
- Mensagem genérica copy-paste sem contexto

### Onde você vê seu SLA

Sidebar → **Operações** → **Meu Plantão** → **SLA Pessoal**

Mostra:
- Seu SLA P1, P2, P3 do turno
- Comparação com meta
- Comparação com colegas (anonimizado)
- Casos no semáforo amarelo/vermelho

---

## 11. Pausar plantão (banheiro, almoço, troca)

### Por que pausar

- Saúde mental — você precisa de respiro
- Saúde física — banheiro, comer, alongar
- Atendimento bem feito — operador cansado erra

### Como pausar

Topo direito → **Pausar Plantão** → escolha motivo:
- Banheiro (5 min)
- Almoço (30 min)
- Reunião (variável)
- Outros (anote)

### O que acontece

- Status fica 🟡 **Em pausa**
- Fila **não te empurra novos casos**
- Casos que você **já claimed** continuam com você (não devolve automático)
- Heartbeat continua (sistema sabe que você existe, só está ocupado)
- Tempo da pausa fica registrado (gestão usa pra escala/dimensionamento)

### Limites

- Banheiro: ilimitado em frequência, max 10min/vez
- Almoço: 1x por turno, 30min
- Outros: combinar com supervisão

### Retomar

Botão **Retomar Plantão** — volta pra 🟢 **Disponível**.

### Troca de turno

5 min antes do fim:
- Pause novos claims (botão "Encerrar entrada de novos casos")
- Termine os que tem em mãos
- Faça **handover** pro próximo turno (mensagem na sala de operadores + anotação em casos sensíveis)
- Botão **Encerrar Plantão** → status vira 🔴

---

## 12. Métricas pessoais — como você é avaliado

### Avaliação NÃO é

- Quantidade de mensagens enviadas
- Quantidade de casos fechados rápido
- Quantidade de não-escaladas

### Avaliação É

| Métrica | Peso | Como mede |
|---|---|---|
| **SLA pessoal** | 30% | % de casos no SLA do seu turno |
| **Qualidade da nota** | 20% | Revisão sample mensal pelo enfermeiro coordenador |
| **Acurácia da escalada** | 20% | % de escaladas que o L2/L3 considerou correto |
| **Feedback de família/cuidador** | 15% | NPS curto após atendimento |
| **Aderência ao playbook** | 15% | Casos críticos seguem o passo a passo? |

### Avaliação 1x por mês

- Reunião 1:1 com coordenador da Central
- Análise de 3-5 casos seus (positivos e a melhorar)
- Plano de desenvolvimento

### O que destrava bônus / progressão

- 3 meses consecutivos SLA ≥95%
- Curso de capacitação clínica básica completado
- Avaliação positiva de pares
- Iniciativa em sugerir melhoria de playbook

---

## 13. Casos típicos — playbook

### Caso 1 — "Dor no peito"

**Sinal:** Cuidador relata via WhatsApp: "Seu João está com dor no peito."

**Sofia já classificou:** P1, escalou pra você em <30s.

**Sua ação:**
1. Claim em <1min
2. Mensagem imediata: "Oi [cuidador], aqui é [seu nome] da Central. Confirma: Sr. João está consciente? Onde dói? Há quanto tempo? Suando frio? Falta de ar?"
3. Enquanto cuidador responde, abre prontuário, vê: 78 anos, hipertenso, diabético, em uso de AAS + losartana. Já teve IAM em 2024.
4. Resposta cuidador: "Consciente, dói no meio do peito, há 10 min, suando."
5. **Decisão imediata: aciona SAMU + médico de plantão + família**
6. Mensagem: "Vou acionar a ambulância e o médico agora. Mantenha o Sr. João sentado, sem esforço, eu fico em contato."
7. Aciona L4 (SAMU 192) → registra protocolo
8. Aciona L3 (médico de plantão) → via push
9. Notifica família (botão)
10. Permanece em contato com cuidador até SAMU chegar
11. Resolve com outcome `escalated_l4_samu` + nota detalhada

**Tempo esperado:** 4-6 min do claim ao SAMU acionado.

---

### Caso 2 — "Glicemia alta"

**Sinal:** Cuidador reporta glicemia 320 mg/dL em paciente diabético.

**Sofia classificou:** P2.

**Sua ação:**
1. Claim em <3min
2. Vê prontuário: diabético tipo 2, em metformina. Glicemia média recente: 180.
3. Mensagem: "Oi [cuidador], 320 está acima do habitual. Sr. [paciente] está com algum sintoma? Tonto? Vomitando? Mais sonolento?"
4. Resposta: "Está bem, só com sede."
5. Decisão: subir pra L2 (enfermeiro) → pode precisar ajuste de medicação
6. Acionamento L2 via botão
7. Mensagem ao cuidador: "Ok, sem sintoma grave. Vou pedir pra enfermeira ligar pra orientar. Ofereça água, evite doce, e não dê insulina extra sem orientação dela. Em 30 min ela liga."
8. Resolve com outcome `escalated_l2_nurse` + nota

---

### Caso 3 — "Família ansiosa"

**Sinal:** Filha do paciente manda 5 mensagens em 10min querendo saber por que mãe não atende telefone.

**Sofia classificou:** P3 (dúvida administrativa).

**Sua ação:**
1. Claim
2. Vê: paciente tem 82 anos, demência leve, vive em ILPI. Última atividade no sistema: cuidador registrou banho às 14h. Família está ansiosa porque tentou ligar e ninguém atendeu.
3. Mensagem à filha: "Oi [nome], aqui é [seu nome] da Central. Sua mãe está bem — o cuidador registrou banho dela às 14h e ela está descansando. Quer que eu peça pro cuidador ligar pra você daqui 30min?"
4. Filha aceita
5. Você notifica cuidador via Sofia ("Solicitação familiar: ligar pra filha às 15h, ela está preocupada")
6. Resolve com outcome `resolved_orientation`
7. Nota: "Família ansiosa por falta de contato. Cuidador acionado para ligar 15h."

---

### Caso 4 — "Falso alarme"

**Sinal:** Sofia classificou P1 por palavra "morrer" no áudio do cuidador.

**Sua ação:**
1. Claim
2. Lê transcrição completa: "Seu João disse que 'tá morrendo de fome' (rs), vai comer agora."
3. Você ri brevemente, lembra que IA não pega ironia.
4. Resolve com outcome `false_alarm`
5. Nota: "Cuidador usou expressão coloquial. Paciente bem, alimentado."
6. Marca tag `melhoria_classificador` → vai pro corpus review do Henrique

---

### Caso 5 — "Paciente recusou atendimento"

**Sinal:** Sofia detectou sintoma, cuidador pediu apoio, mas paciente recusou ir ao hospital.

**Sua ação:**
1. Claim, acione L3 (médico)
2. Médico orienta vai/não vai
3. Se paciente persiste em recusa: registra com outcome `patient_refused`
4. Documenta no audit log: data, hora, quem ofereceu, quem recusou, quem testemunhou
5. Notifica família (importante pra prestação de contas)
6. Se paciente competente, recusa é direito. Você documenta e segue.

---

## 14. Frases e tom — como falar com cada perfil

### Com cuidador

- Tratamento: profissional, colega de trabalho
- Tom: direto, objetivo, técnico
- Exemplo: "Boa noite Marina, peguei aqui. Vou pedir pra enfermeira retornar agora. Mantém ele em decúbito lateral até ela falar."

### Com familiar

- Tratamento: respeitoso, acolhedor
- Tom: explicativo, sem jargão médico
- Exemplo: "Olá Carla, sou Pedro da Central. Sua mãe está sendo avaliada agora. A enfermeira vai te ligar em até 10 min com mais detalhes, tudo bem? Estou aqui se precisar."

### Com paciente direto

- Tratamento: senhor / senhora + primeiro nome
- Tom: pausado, simples, confortável
- Exemplo: "Seu Antônio, aqui é a Camila da Central. Tudo bem com o senhor agora? Quero entender o que aconteceu pra ajudar."

### Com médico/enfermeiro de plantão

- Tratamento: nome simples
- Tom: passa de caso, objetivo, com dados
- Exemplo: "Dra. Ana, P1 escalado. Paciente João Silva, 78a, HAS+DM+IAM prévio, dor torácica há 10min, suando, AAS+losartana de base. SAMU acionado (protocolo X), família avisada. Você assume?"

### Em emergência

- Mantenha calma na voz (mesmo no texto)
- Frases curtas, instruções claras
- Não use ponto de exclamação demais (assusta)
- Confirme cada ação: "SAMU acionado", "Médico avisado", "Família notificada"

---

## 15. Erros comuns no início

| Erro | Por que evitar | Como fazer certo |
|---|---|---|
| Tentar resolver P1 sozinho | Não é seu papel, gera risco | Sempre escala L3 + SAMU se aplicável |
| Esquecer de notificar família | LGPD + confiança | Sempre tem botão pra notificar — usa |
| Nota vazia ou genérica | Audit fica pobre, próximo turno não entende | 1-3 frases concretas |
| Não pausar quando precisa | Cansaço gera erro | Pausa quando precisa, é direito |
| Pegar fila fora da sua especialidade | Confunde, atrasa | Devolve à fila ou redireciona |
| Conversar com cuidador esquecendo prontuário | Você fala genérico, não acolhe contexto | 15s lendo contexto **antes** de mandar mensagem |
| Não confirmar entendimento | Pode interpretar errado | "Confirma se entendi: [resumo]?" |
| Usar gíria médica com família | Família não entende, fica mais ansiosa | "FC alta" → "coração batendo mais rápido" |

---

## 16. Ferramentas auxiliares

### Painel lateral do caso

Quando você claim, painel direito mostra:
- **Sinais vitais** dos últimos 30 dias (gráfico)
- **Medicações ativas** com horário
- **Condições** crônicas
- **Cross-validation alerts** ativos
- **Care events** recentes (últimos 7d)
- **Anotações** de enfermeiro/médico

Use isso pra ter contexto em <30s.

### Atalhos de teclado

| Tecla | Ação |
|---|---|
| `Enter` | Enviar mensagem |
| `Ctrl+R` | Reivindicar próximo caso da fila |
| `Ctrl+E` | Abrir painel de escalonamento |
| `Ctrl+F` | Fechar caso |
| `Ctrl+P` | Pausar |
| `Ctrl+N` | Adicionar nota rápida |
| `Esc` | Limpar input |

### Templates de resposta

Sidebar → **Operações** → **Templates** — frases prontas pra:
- Cumprimento inicial
- Pedido de confirmação clínica
- Notificação de família
- Encerramento com orientação
- Encerramento com escalada

**Use como ponto de partida, sempre customize com nome do paciente e contexto.** Mensagem genérica frieza.

### Sala dos operadores (chat interno)

Sidebar → **Chat Interno**

Use para:
- Pedir segunda opinião rápida ("posso classificar isso como P2?")
- Avisar que vai pausar ("indo banheiro 5min")
- Compartilhar handover de turno
- Pedir backup em momento de pico

**Não use para:**
- Comentar paciente (fica fora do audit log apropriado)
- Discutir caso clínico (usa o caso, não o chat lateral)
- Bate-papo prolongado (foque)

---

## 17. FAQ do Operador

**Quanto tempo até ficar bom no plantão?**
3-4 semanas pra fluir. 3 meses pra estar realmente confortável. Tudo bem ser lento no início.

**Posso ouvir áudio enquanto atendo?**
Música instrumental baixa, sim. Nada com letra distraindo. Headset bom é investimento.

**Se eu errar uma classificação?**
Não há punição por erro de boa-fé. Erro vai pro corpus review (Henrique analisa) e ajuda a melhorar a Sofia. Só penaliza dolo ou negligência.

**E se um caso me afetar emocionalmente?**
Pausa o plantão, avisa coordenador. Temos apoio psicológico disponível (incluído no plano). Conversamos sem julgamento.

**Posso atender de casa?**
Sim, todos os controles são por interface web + VPN. Requisitos: internet estável, lugar sem ruído, equipamento mínimo (notebook + headset).

**Trabalho fim de semana / madrugada?**
Sim, escala 24/7. Turnos rotativos. Adicional noturno + final de semana conforme CLT/contrato.

**Como denunciar problema interno (assédio, sobrecarga)?**
Canal de denúncia anônimo: denuncia@connectaia.com.br. Resposta em 7 dias úteis.

**Posso opinar em mudanças na plataforma?**
Sim, mensalmente coletamos sugestões. As melhores entram em roadmap. Operador de campo geralmente vê o que dev não vê.

**Sofia vai me substituir?**
Não. Quanto mais a plataforma cresce, mais operador humano precisa. Sofia escala o trabalho, não substitui o julgamento.

**E quando a Sofia "tira sarro" da gente?**
Ela não. Mas se sair resposta estranha, reporta no chat interno — vai pra corpus review.

---

## 18. Contatos de emergência

### SAMU (sempre)
**192** — qualquer suspeita de emergência grave, **chama primeiro** e avisa médico depois.

### Coordenador da Central (24/7)
- **WhatsApp**: número fixo dado no onboarding
- Use para: dúvida operacional imediata, pedido de backup, problema técnico bloqueante

### Suporte técnico da plataforma (24/7)
- **Chat interno**: canal "Suporte Técnico"
- **E-mail emergencial**: emergencia-tech@connectaia.com.br
- Use para: sistema fora do ar, fila não atualiza, login não funciona

### Médico de plantão institucional
- Acionável pela própria interface (botão "Acionar L3")
- Não tente WhatsApp pessoal — sempre via plataforma

### Psicólogo de apoio (você)
- Agendamento via RH
- Confidencial
- Incluído no plano

---

## Última palavra

Você é a **camada humana** da plataforma. A Sofia faz muito, mas quando vira gente do outro lado precisando de gente, é **você**.

Não tem como esse manual cobrir tudo. Com o tempo, você desenvolve faro. Confia no instinto, escala quando duvida, registra tudo, cuida de si.

Bom plantão.

---

**Última revisão:** 2026-05-18
**Próxima revisão prevista:** 2026-08-18
**Responsável editorial:** Coordenação da Central
**Versionamento:** manual em git, mudanças auditadas
