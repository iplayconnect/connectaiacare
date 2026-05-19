# Manual do Familiar — ConnectaIACare

**Pra quem é este manual:** filho(a), cônjuge, neto(a) ou outra pessoa próxima que é responsável pelo cuidado de uma pessoa idosa. Você pode estar morando junto, longe, ou tendo cuidador profissional cuidando do dia-a-dia.

**O que você vai conseguir:** saber **na hora** como seu parente está, receber alertas se algo importante acontecer, ver histórico completo do prontuário pelo celular ou computador.

**Tempo de leitura:** 15 minutos.

---

## 📑 O que tem aqui

1. [Bem-vindo(a) — o que você ganha aqui](#1-bem-vindoa)
2. [Como começar (cadastro do paciente)](#2-como-começar)
3. [Wizard de cadastro completo (5 passos)](#3-wizard-de-cadastro-completo)
4. [O que é a Sofia (sem tecniquês)](#4-o-que-é-a-sofia)
5. [Onde ver como seu parente está](#5-onde-ver-como-seu-parente-está)
6. [Quando você vai receber alerta](#6-quando-você-vai-receber-alerta)
7. [Conversar com a Sofia (perguntar sobre paciente)](#7-conversar-com-a-sofia)
8. [Falar com o cuidador via Sofia](#8-falar-com-o-cuidador-via-sofia)
9. [Quando você se preocupar (e quando não)](#9-quando-se-preocupar)
10. [Múltiplos familiares acompanhando](#10-múltiplos-familiares)
11. [Privacidade e LGPD](#11-privacidade-e-lgpd)
12. [Custo e plano](#12-custo-e-plano)
13. [FAQ](#13-faq)
14. [Pra emergências](#14-pra-emergências)

---

## 1. Bem-vindo(a)

Cuidar de pai/mãe/avô idoso à distância (ou mesmo morando junto) gera **ansiedade constante**:

- "Será que ele tomou o remédio hoje?"
- "Será que ela passou bem essa noite?"
- "E se acontecer alguma coisa e ninguém me avisa?"
- "Como saber se o cuidador está fazendo um bom trabalho?"

A **ConnectaIACare** existe pra resolver isso. Você vai ter:

✅ **Transparência total** — vê tudo que está acontecendo, em tempo real ou histórico
✅ **Alerta na hora** — se algo importante acontecer, você é avisado(a) imediatamente
✅ **Ponte com a equipe** — médicos, enfermeiros, cuidador, todos no mesmo fluxo
✅ **Sofia ao seu lado** — pode perguntar a qualquer hora "como minha mãe está?"
✅ **Histórico organizado** — quando o médico te perguntar, você sabe responder

---

## 2. Como começar

### Cenário A — Sua casa/clínica já usa ConnectaIACare

Você recebe convite por WhatsApp ou email:

> "Oi! Você foi cadastrado(a) como responsável familiar pela [Nome do paciente]. Pra começar a acompanhar, clica aqui: [link]"

Click no link → senha você define → **pronto**, você tem acesso ao portal.

### Cenário B — Você quer começar a usar (B2C)

Você acessa `connectaiacare.com.br/cadastro` e:

1. Cadastra você mesmo(a) como responsável
2. Cadastra a pessoa idosa (paciente)
3. Cadastra cuidador(es) (se houver)
4. Aceita termo LGPD (autorização pra processar dados de saúde)
5. **Pronto**, começa a usar

### Cenário C — Médico/clínica te recomendou

O médico do paciente cria o cadastro com base na avaliação inicial. Você é adicionado(a) como responsável familiar. Recebe link de acesso.

---

## 3. Wizard de cadastro completo (5 passos)

Depois que o paciente existe na plataforma (mesmo que com nome só), você pode preencher o **cadastro completo** via wizard guiado. Demora 10-15 minutos.

### Passo 1 — "Quem está informando?"

Sofia precisa saber quem está preenchendo, pra registrar a origem dos dados (importante pra equipe médica).

Você escolhe seu papel:
- **Paciente B2C** (auto-declarado) — se é o próprio idoso preenchendo
- **Familiar responsável** — você
- **Procurador legal** — se tem procuração
- **Gestor da unidade** — pra ILPI
- **Enfermeiro / Médico** — pra equipe clínica

Se você marca "familiar" ou "paciente B2C", precisa **aceitar termo LGPD** (lei brasileira de dados sensíveis de saúde). É 1 caixa de seleção.

### Passo 2 — Identificação

Campos:
- Nome completo
- Apelido / como é chamado(a) ("Dona Maria", "Seu Antônio")
- CPF (opcional — mas **importante** se quiser integração com parceiro integrador ou outros)
- Data de nascimento
- Gênero
- Forma de tratamento que Sofia vai usar
- "Paciente reporta sobre si mesmo?" — marque se for idoso autônomo
- Acomodação (unidade, quarto, nível de cuidado I-IV se for ILPI)

### Passo 3 — Condições de saúde

Aqui você lista o que o paciente tem. **Não precisa decorar CID** — basta digitar:

- "Hipertensão"
- "Diabetes"
- "Alzheimer leve"
- "Insuficiência cardíaca"

A Sofia te ajuda a achar o código CID-10 oficial (autocomplete). Se ela não achar, você pode digitar livre.

Pra cada condição, marca opcional:
- **Severidade**: leve / moderada / severa
- **Controlada?**: sim / não
- **Notas**: ex: "diagnóstico em 2018"

### Passo 4 — Medicamentos em uso

Lista de medicações:

- "Losartana 50mg, 1x dia manhã"
- "Metformina 850mg, 2x dia"
- "Donepezila 10mg, 1x noite"

Sofia identifica automaticamente:
- **Classe terapêutica** (BRA, biguanida, anticolinesterásico)
- **Marcas comerciais** equivalentes

Pra cada medicamento:
- Dose
- Posologia (frequência)
- Notas (ex: "tomou efeito colateral X, mudou da metformina 500 pra 850")

### Passo 5 — Revisão final

Sofia mostra um resumo + roda **cross-validation automática**:

| Condição | Esperado | Encontrado | Alerta? |
|---|---|---|---|
| Hipertensão | Anti-hipertensivo | Losartana ✓ | OK |
| Diabetes | Antidiabético | Metformina ✓ | OK |
| **Fibrilação Atrial** | **Anticoagulante** | **AUSENTE** | 🔴 **CRÍTICO** |

Se Sofia detecta gap, ela **alerta você** — mas **não bloqueia** a finalização. O alerta vai pro médico revisar.

Você também adiciona:
- **Alergias** (penicilina, AAS, frutos do mar, etc.)
- **Responsável familiar principal** (com phone WhatsApp — pra receber alertas)

Click "Finalizar" → cadastro completo + Sofia já tem contexto pra cuidar do paciente.

---

## 4. O que é a Sofia (sem tecniquês)

Pensa na Sofia como uma **enfermeira virtual disponível 24/7**, mas que:

- **Não substitui** médico ou enfermeira de verdade
- **Organiza** tudo que cuidador relata
- **Avisa** equipe e família quando algo importante acontece
- **Responde** suas dúvidas sobre o paciente
- **Lembra** medicações, consultas, sinais vitais

Ela existe no **WhatsApp do paciente** (ou cuidador, ou casa) e no **portal web** que você acessa.

### O que ela faz

✅ Recebe áudios e textos dos cuidadores ("dei o remédio", "PA tá alta", "ele caiu")
✅ Organiza tudo no prontuário do paciente
✅ Classifica por gravidade (rotina, atenção, urgente, crítico)
✅ Alerta família e equipe se for grave
✅ Lembra medicações
✅ Responde dúvidas suas sobre o paciente
✅ Conecta com SAMU em emergência

### O que ela NÃO faz

❌ Decidir tratamento (médico decide)
❌ Receitar medicamento (médico receita)
❌ Substituir consulta presencial
❌ Diagnosticar doença nova

---

## 5. Onde ver como seu parente está

### Opção A — Portal web (computador ou celular)

Você acessa `care.connectaia.com.br/login` e vê:

**Prontuário 360°** — abre tudo do paciente:
- Foto, idade, dados básicos
- **Score ACG** (0-100) — risco clínico atual
- **Condições** com badge colorido (controlada/descontrolada)
- **Alergias** em destaque
- **Sinais vitais** últimos 7 dias (gráficos)
- **Timeline 30 dias** — todos os eventos (medicação, sintomas, consultas)
- **Sofia Insights** — resumos automáticos
- **Medicação Timeline + Adesão %** — adesão real de medicação

### Opção B — WhatsApp (rápido)

Você manda mensagem direto pra Sofia:

> "Sofia, como a mãe passou hoje?"

Sofia responde em segundos:
> "Dona Maria passou bem hoje. Tomou todos os 4 medicamentos no horário (cuidador confirmou às 7h, 12h, 18h e 22h). PA medida 2x: 138x82 (12h) e 135x80 (20h) — dentro do alvo. Sem queixas. Próxima medição de PA programada amanhã 8h. Algo específico que você queria saber?"

### Opção C — Relatório semanal automático

Toda segunda-feira de manhã você recebe um WhatsApp com resumo da semana:

> "Resumo da semana — Dona Maria (10-16/maio)
>
> ✅ Adesão medicação: 97% (1 dose esquecida — losartana terça)
> ⚠️ PA média: 142x88 (acima do alvo 130x80) — equipe avaliando
> ✅ Sinais vitais ok (glicose, sat, temp)
> ✅ Sem intercorrências graves
> 📅 Próxima consulta: 22/maio com Dra. Joana
>
> Detalhes completos no portal."

---

## 6. Quando você vai receber alerta

Você é **avisado(a) imediatamente** quando:

### 🔴 Crítico (P1)

- Cuidador relata sintoma agudo (dor no peito, queda, perda de consciência, etc.)
- Detectada **interação medicamentosa grave**
- Equipe abriu pedido de internação

**Como:** push no WhatsApp + (opcional) email.

**Em quanto tempo:** **menos de 1 minuto** depois que Sofia recebeu o relato do cuidador.

### 🟠 Urgente (P2)

- Sinal vital fora do alvo (PA muito alta, glicose muito baixa)
- Medicação esquecida 2x seguidas
- Sintoma novo importante (febre, vômito persistente)

**Como:** WhatsApp.

**Em quanto tempo:** **até 30 minutos**.

### 🟡 Atenção (P3)

- Mudança no comportamento (relato qualitativo)
- Adesão de medicação caiu (< 85%)
- Resultado de exame disponível

**Como:** WhatsApp ou apenas no portal (você decide).

**Em quanto tempo:** **algumas horas** ou no próximo resumo.

### Você configura

No seu perfil (`/perfil`), você escolhe:
- Que prioridades te alertam por WhatsApp (P1 obrigatório, P2 e P3 opcionais)
- Horário de silêncio (ex: não me avisem entre 23h e 7h, exceto P1)
- Email backup
- Múltiplos números (seu + cônjuge)

---

## 7. Conversar com a Sofia

Você pode perguntar **qualquer coisa** sobre o paciente:

### Estado geral
> "Como minha mãe está hoje?"
> "Tem algo me preocupar?"
> "Última PA dela?"

### Medicação
> "Ela tomou a metformina hoje?"
> "Quantos remédios ela tá tomando agora?"
> "Algum efeito colateral relatado?"

### Histórico
> "Quando foi a última vez que ela teve febre?"
> "Ela já caiu no último mês?"
> "Tendência da glicose últimas 2 semanas"

### Comparações
> "Comparado com o mês passado, como ela tá?"
> "Adesão melhorou ou piorou?"

### Próximas ações
> "Próxima consulta dela?"
> "Algum exame agendado?"
> "Quando vem o resultado da glicada?"

### Orientação prática
> "Sofia, o cuidador disse que ela tá meio fraca. É pra eu me preocupar?"
> "Posso dar paracetamol pra ela se reclamar de dor?"
> "Vou viajar 1 semana, alguma coisa que eu deva preparar antes?"

A Sofia consulta o prontuário do paciente, histórico, regras curadas — e responde com base em **dados reais**, não opinião.

---

## 8. Falar com o cuidador via Sofia

Se você quer pedir algo pro cuidador, pode fazer **direto pela Sofia**:

> Você: "Sofia, fala pro Marcos medir a PA dela ainda hoje, por favor."

Sofia entende e:
1. Manda mensagem pro Marcos (cuidador): *"A família da Dona Maria pediu que você meça a PA dela ainda hoje. Pode confirmar quando fizer?"*
2. Marcos faz, manda áudio com resultado pra Sofia
3. Sofia te avisa: *"Marcos mediu agora 14h: PA 138x82, dentro do alvo. Ele anotou."*

**Por que isso é útil:**
- Você não fica enviando WhatsApp direto pro cuidador (privacidade)
- Tudo fica registrado no prontuário (auditoria)
- Você não precisa decorar telefone de cuidador
- Funciona mesmo se o cuidador mudar

---

## 9. Quando se preocupar

### Coisas normais (não se preocupe)

- PA oscilar 10-15 mmHg ao longo do dia
- Glicose variar entre refeições
- 1 dose de medicação esquecida no mês
- Idoso reclamar de dorzinha que passa
- Variação de humor leve
- Resfriado simples

A Sofia já avalia e te diz se algo merece atenção.

### Coisas pra prestar atenção (vai aparecer como atenção/urgente)

- PA persistentemente acima do alvo (3+ medições seguidas)
- Glicose descontrolada (jejum > 180 ou queda < 70)
- Adesão de medicação caindo
- Mudança de comportamento (mais sonolento, mais agitado)
- Recusa repetida de alimentação
- Edema novo (pernas inchadas)
- Tosse persistente (> 3 dias)

### Coisas graves (vai aparecer como crítico — você é avisado)

- Dor no peito, falta de ar
- Queda
- Confusão mental aguda
- Sangramento
- Febre alta persistente
- Suspeita de AVC (boca torta, fala enrolada, fraqueza um lado)
- Reação alérgica

---

## 10. Múltiplos familiares

### Por que cadastrar mais de 1 responsável

- Você pode estar viajando, ocupado(a), dormindo
- Cônjuge / irmão / filhos podem acompanhar
- Redundância pra emergência

### Como cadastrar

No prontuário do paciente:
1. Aba "Responsável familiar"
2. Click "Adicionar familiar"
3. Preencha: nome, parentesco, WhatsApp, email
4. Marque quais prioridades cada um recebe (todos P1 obrigatório, P2/P3 opcional)
5. **Familiar novo precisa aceitar convite** + termo LGPD pra começar a receber

### Hierarquia

- **Responsável primário** — recebe tudo, pode fazer mudanças no cadastro
- **Responsáveis secundários** — recebem alertas conforme configurado, **só leitura** no prontuário
- **Visitantes** (família estendida) — só leitura, sem alertas

---

## 11. Privacidade e LGPD

### Você está aceitando que

✅ ConnectaIACare processa **dados sensíveis de saúde** do paciente (LGPD Art. 11)
✅ Cuidadores, equipe clínica e família autorizada vejam o prontuário
✅ Sofia analise relatos com IA pra estruturar
✅ Audit log mantém histórico de tudo (compliance)

### O que NÃO acontece

❌ Dados vendidos pra terceiros
❌ Marketing pra fora da plataforma
❌ Empresas de seguro/análise de risco recebendo dados
❌ Foto/vídeo divulgados publicamente

### Seus direitos

- **Acesso completo** — vê tudo registrado, exporta em JSON
- **Retificação** — corrige dados errados
- **Eliminação** — pede apagar dados (com cuidados pra integridade histórica)
- **Portabilidade** — leva os dados pra outra plataforma
- **Revogação de consentimento** — para de usar

Pra exercer: `/perfil` → Direitos LGPD → escolha a ação.

### Como dados do paciente sensíveis são tratados

- **Encriptação** em trânsito (HTTPS) e em repouso (banco)
- **Audit imutável** — toda decisão registrada com IP, hora, usuário
- **Acesso limitado** — só quem tem permissão vê
- **DPO designado** (Encarregado de Proteção de Dados) — contato em [/legal/dpo]

---

## 12. Custo e plano

### Modelo B2B (sua casa/clínica usa)

Você não paga nada — a casa contratou a plataforma e custos estão incluídos.

### Modelo B2C (você contratou direto)

Planos típicos (sujeitos a mudança, ver site):

| Plano | Inclui | Faixa |
|---|---|---|
| **Família Essencial** | 1 paciente + 2 familiares + Sofia 24/7 + portal | R$ X/mês |
| **Família Plus** | 1 paciente + 5 familiares + teleconsulta 2x/mês + dispositivos opcionais | R$ Y/mês |
| **Múltiplos pacientes** | Vários idosos sob mesmo grupo familiar | Consultar |

**Importante:** plantão clínico 24/7 NÃO está incluso (ou está em planos mais altos). É serviço separado — você pode contratar via ConnectaIACare ou trazer médico próprio.

### O que você ganha além do custo

- Histórico organizado = menos retrabalho em consulta médica
- Detecção precoce de problemas = menos internação
- Menos ansiedade (vê em tempo real)
- Cuidador melhor avaliado (transparência)

---

## 13. FAQ

### "Tenho que cadastrar todos os medicamentos? Mesmo vitaminas?"
Idealmente sim. Vitaminas e suplementos podem interagir com medicamentos sérios (vitamina K vs anticoagulante, por exemplo). Pelo menos os de uso regular.

### "E se o paciente não tem CPF (estrangeiro, sem documentação)?"
Sistema funciona sem CPF. Só limita algumas integrações externas (parceiro integrador, etc.).

### "Posso compartilhar prontuário com médico fora da plataforma?"
Sim — você exporta (PDF ou JSON) e manda. Médico não precisa ter acesso à plataforma.

### "Cuidador tá relatando algo que eu suspeito ser falso. O que fazo?"
Levanta com gestor da casa. Audit log mostra exatamente o que foi relatado, quando, com que mídia (áudio). Tem como verificar.

### "Sofia detectou interação medicamentosa, isso é grave?"
Depende. Alerta amarelo (atenção) = informativo. Alerta vermelho (crítico) = peça revisão médica urgente.

### "Vou viajar pro exterior, ainda recebo alertas?"
Sim. Sofia manda mensagem pelo WhatsApp normal (que funciona mundialmente com internet).

### "E se eu não responder o alerta crítico? O paciente fica sem cuidado?"
Não. O alerta crítico vai **em paralelo** pra equipe clínica e plantão. Você ser avisado é pra você **saber**, não pra você ser o único respondente. Equipe age independente da sua resposta.

### "Quero que o cuidador NÃO veja certo dado sensível (ex: diagnóstico psiquiátrico estigmatizante)"
Conversa com a equipe clínica — eles podem marcar campo como "restrito" e cuidador não vê. Mas pra cuidado eficaz, equipe recomenda transparência total entre cuidador e cuidado.

### "Posso ver onde o cuidador está? (GPS)"
Não. Sofia não rastreia localização. Privacidade do cuidador.

### "Sofia escuta conversas no celular do paciente sem permissão?"
NÃO. Sofia só processa o que **foi enviado pra ela** (mensagens explícitas via WhatsApp/portal). Não escuta microfone passivamente. Não acessa fotos/vídeos sem você compartilhar.

### "Idoso tem medo de tecnologia. Vai funcionar?"
Sim. A interface principal é o **WhatsApp** (que ele já usa). E **outras pessoas** (você, cuidador) podem operar o sistema **pelo idoso**. Idoso não precisa abrir nenhum app diferente do WhatsApp.

### "Posso instalar app no celular?"
PWA (em desenvolvimento) — vai dar pra "instalar" no celular como ícone próprio, com notificações push. Hoje funciona via navegador.

### "O que acontece se eu cancelar a plataforma?"
Você baixa todos os dados antes (exportação completa). Após cancelamento, plataforma anonimiza dados pessoais mas mantém audit log (LGPD permite pra compliance). Pode reativar dentro de X meses sem perder histórico.

---

## 14. Pra emergências

### 🚨 SE FOR EMERGÊNCIA AGORA

1. **Ligue 192 (SAMU)** primeiro
2. **Avise alguém pertinente** (cuidador, gestor da casa, médico responsável)
3. A Sofia vai te alertar se um cuidador relatou algo crítico — você pode ligar pro cuidador também

### Plantão 24/7

Se sua casa/clínica contratou plantão clínico da ConnectaIACare:
- Em P1, alguém do plantão chama no WhatsApp em até 5min
- Em P2, em até 30min
- Você sempre é copiado(a) nos alertas

### SAMU 192 funciona em qualquer celular

Mesmo celular sem chip, sem internet, sem créditos. **Discagem direta funciona.**

### Lista de contatos críticos pra ter sempre

Salve no celular como favoritos:
- 📞 **192** — SAMU
- 📞 **193** — Bombeiros
- 📞 Cuidador principal (se contratado)
- 📞 Gestor da casa (se ILPI)
- 📞 Médico responsável
- 📞 Plantão ConnectaIACare (se contratado)

---

## ✨ Sua tranquilidade é o objetivo

Você não tá sozinho(a) cuidando do seu parente. **Time inteiro está com você.**

Qualquer dúvida, fale com a Sofia. Ela tá ali pra isso.
