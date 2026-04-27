# Sofia — Visão Geral

> ConnectaIACare · Material de boas-vindas para o time clínico
> Data: abril/2026

---

## Sobre este documento

Este texto descreve o que a **Sofia** é hoje, como ela atua e para onde estamos caminhando. Foi escrito para alguém entrando no time agora — em linguagem natural, sem detalhes técnicos. O objetivo é dar uma visão completa em 15-20 minutos de leitura, suficiente para entender onde sua expertise clínica e farmacológica vai contribuir.

---

## 1. O que estamos construindo

A **ConnectaIACare** é uma plataforma de cuidado integrado para idosos e pacientes crônicos no Brasil. No centro dela está a **Sofia** — uma assistente de inteligência artificial que conversa com pacientes, familiares, cuidadores e profissionais de saúde.

A diferença da Sofia para outras assistentes virtuais é a **continuidade do cuidado**: ela está presente todo dia, lembra do paciente entre conversas, identifica padrões clínicos preocupantes e organiza a rotina de cuidado sem precisar de equipe humana o tempo todo.

### A visão

> Que cuidado de qualidade pra idoso brasileiro deixe de ser caro porque exige equipe humana 24/7. A Sofia não substitui o humano — ela cobre os 90% das interações que são informativas/rotineiras, e libera o humano (cuidador, enfermagem, médico) pra atuar nos 10% que realmente precisam de decisão clínica.

Nosso cenário-norte é a **Dona Helena**: idosa de 82 anos, mora sozinha em Porto Alegre, filha em Lisboa, sem cuidador presencial. A Sofia liga 8h30 todo dia pra checar como ela passou a noite, lembra dos remédios, capta sintomas novos. Quando algo precisa de atenção (ex: ela relata tontura nova), a Sofia escala pra equipe de atendentes humanos da ConnectaIA — que decide se chama o médico, se conversa com a filha, se aciona o SAMU.

A matemática só fecha porque a Sofia opera com **custo marginal próximo de zero** por paciente. Cuidador humano 24/7 = R$ 5 mil/mês. Plano com Sofia + atendente sob demanda = uma fração disso, e funciona em escala.

### Posicionamento de mercado

A ConnectaIACare **não compete** com:
- **EHR enterprise** (MV, TOTVS, Tasy) — eles são a infra hospitalar pra grandes operadoras
- **Telemedicina pura** (Doctoralia, Conexa) — eles conectam paciente ao médico humano por consulta
- **Healthtech B2B administrativa** (Memed, iClinic) — eles digitalizam o workflow do médico

A ConnectaIACare atua **na ponta**: onde o cuidado vira conversa diária, onde o idoso precisa de presença, onde o cuidador precisa de apoio para decidir. Modelo B2B2C (clínica + paciente final) e B2C (idoso direto).

Existem players globais que validaram a tese: **Hippocratic AI** (EUA) faz check-ins pós-alta hospitalar com não-inferioridade vs enfermagem em 90% dos protocolos. **Sensi.ai** monitora idosos via sensores + IA, com 40% de redução em hospitalização. **Tesla** vende com IA por voz convertendo ~20%. Nenhum player brasileiro tem **arquitetura de ponta integrada** (chat + voz + ligação + motor clínico + memória) — aí está nossa janela.

---

## 2. Como a Sofia atua

A Sofia é **uma só** com vários canais. O paciente não precisa "explicar de novo" quando troca de canal — ela mantém continuidade.

### Os 4 canais

**WhatsApp** (canal primário pra B2C). 90%+ dos brasileiros adultos usam WhatsApp diariamente. Pra idoso 65+, frequentemente é o **único** app digital usado. A Sofia opera via WhatsApp Business API homologada com a Meta, recebe e envia: texto, áudio (paciente que não digita bem, manda áudio de 30s — Sofia transcreve, estrutura clinicamente, registra no prontuário), foto (receita, embalagem de remédio, bula, lesão de pele, display de glicosímetro/oxímetro), botões interativos (lembrete de medicação com [Sim, tomei] [Ainda não]). Em estudo: **chamada de voz outbound via WhatsApp** (Meta liberou em 2024) — toca o WhatsApp que o paciente reconhece, mostra foto verificada da equipe, qualidade superior à PSTN.

**Chat texto web/app** — usado quando há tempo pra escrever, anexar arquivo, conversa lenta. Profissional cadastra paciente, médico consulta dose máxima, família acessa painel completo do paciente. Persona profissional preferida.

**Voz no browser** — botão flutuante no painel. Hands-free pra cuidador com mãos ocupadas, ou pra paciente que tem dificuldade pra digitar. Mesma latência baixa de uma ligação.

**Ligação telefônica direta** — Sofia liga (ou atende, em fase futura) com voz natural. Fallback pra paciente sem WhatsApp e crítico em situações de urgência (chamar família via número fixo). Funciona como uma ligação humana qualquer — ela cumprimenta pelo nome, conversa, escuta.

### Entrada multimodal de relatos (importante pro teu papel clínico)

A entrada via WhatsApp não é "chat tradicional". Pra geriatria brasileira, a forma mais natural de relato é **áudio + foto**:

- **Áudio**: paciente fala 30s "Sofia, hoje minha mãe acordou confusa, não soube onde tava, e ela tá bebendo pouca água". Sofia transcreve, **estrutura clinicamente** (sintomas: confusão mental aguda, baixa ingesta hídrica), confronta com motor (idosa + medicações + baixa ingesta hídrica → suspeita de delirium hipoativo por desidratação), classifica severidade, registra no prontuário e pode escalar. **Tudo a partir de um áudio de WhatsApp.**

- **OCR de receita médica**: paciente fotografa receita ao chegar em casa. Sofia extrai medicamentos/doses/posologias e **confronta com prescrição registrada**. Se farmácia entregou errado, ou paciente está olhando receita anterior misturada, Sofia escala antes da primeira dose. **Esse é um detector de erro de medicação no momento certo.**

- **OCR de bula**: paciente em dúvida sobre efeito colateral, manda foto da bula. Sofia lê, identifica seção relevante, explica em linguagem simples. Não substitui orientação farmacêutica, **estende o alcance dela**.

- **OCR de embalagem**: idoso esqueceu nome do remédio, manda foto da caixa. Sofia identifica princípio ativo, dose, lote, validade. Confronta com o que deveria estar tomando.

- **OCR de exame laboratorial**: paciente recebeu hemograma, fotografa. Sofia extrai estruturado (Hb, leucócitos, creatinina, etc.), arquiva no prontuário, e roda alertas (creatinina subiu? Sofia avisa pra equipe rever ajuste renal das medicações via motor).

- **Visão multimodal de lesão / ferida / edema**: paciente fotografa. Sofia identifica sinais visuais sugestivos (vermelhidão, exsudato, deiscência), **gera observação clínica** pro prontuário — não diagnostica.

- **Foto do display de aparelho** (glicosímetro, oxímetro, aparelho de pressão): Sofia extrai valor, registra com flag "auto-relato via foto" pra diferenciar de equipamento integrado, roda alertas se valor está fora de faixa do paciente.

**Aqui sua expertise é central**: validar quais entradas multimodais são clinicamente confiáveis, calibrar limites onde a Sofia deve recusar interpretar (foto desfocada, papel rasgado, dados ambíguos), e definir quais classes de imagem disparam escalação automática vs apenas registro.

### As personas

A Sofia ajusta o tom e o que pode fazer baseado em quem está conversando com ela:

- **Médico/Enfermagem**: pode usar termos clínicos, acessar histórico longitudinal, validar prescrições contra o motor de cruzamentos, pesquisar interações
- **Cuidador profissional**: tom direto, foco em registrar relatos, escalar quando preciso, atualizar status de eventos
- **Família**: tom acolhedor, transparência clínica, sem dramatizar. Sofia reconhece que pode estar do outro lado uma pessoa em pânico
- **Paciente**: tom calmo, sem mediquês, paciente com silêncios e repetições. Use apelido se souber. "A pressão tá alta" não "você apresenta hipertensão"
- **Comercial**: tom caloroso, conversor mas não televendas, missão de qualificar e agendar próximo passo

### Os 3 propósitos × 3 canais (matriz de uso)

| Propósito | Chat texto | Voz browser | Ligação telefônica |
|-----------|------------|-------------|---------------------|
| **Suporte clínico** | Médico pergunta dose máxima de dabigatrana, Sofia roda validador e responde | Enfermeira em plantão pergunta interação enquanto preenche prontuário | Cuidador profissional liga fora do horário comercial pra tirar dúvida |
| **Relacionamento** | Familiar acessa app, vê resumo do paciente, conversa com Sofia | Paciente B2C usa voz pra check-in informal "Sofia, hoje tá tudo bem?" | Sofia liga 8h30 todo dia pro paciente B2C, valida medicação, capta sintoma |
| **Comercial** | Visitante do site abre chat, Sofia qualifica e agenda demo | Demo ao vivo no site com Sofia explicando proposta | Sofia liga pro lead que se cadastrou na landing |

Cada combinação dessas tem um **playbook editável** no banco — define o tom, as ferramentas que a Sofia pode usar, o que fazer depois da conversa. Admin pode editar sem precisar de release de código.

---

## 3. O motor clínico de cruzamentos

Esta é a **parte do produto onde sua expertise mais entra**. Vou detalhar.

A Sofia tem um motor determinístico (não-LLM, código + regras) que valida toda prescrição em **12 dimensões** simultaneamente:

1. **Dose máxima diária** (ANVISA + FDA por princípio ativo)
2. **Critérios de Beers 2023** (AVOID + Caution em geriatria)
3. **Alergias documentadas** + reações cruzadas (ex: penicilina ↔ todos os β-lactâmicos)
4. **Duplicidade terapêutica** (mesmo princípio ou mesma classe)
5. **Polifarmácia** (carga total ≥ N medicamentos com peso por classe)
6. **Interações medicamento-medicamento** — incluindo interações por absorção que podem ser **mitigadas espaçando os horários** (levotiroxina + carbonato de cálcio = espaçar 4h, não evitar)
7. **Contraindicações por condição clínica** do paciente (ex: Parkinson + risperidona; demência + antipsicótico atípico; sinusoide QT prolongado + azitromicina)
8. **ACB Score** (Anticholinergic Cognitive Burden cumulativo — soma da carga anticolinérgica de TODOS os medicamentos)
9. **Risco de queda por classe terapêutica** (benzodiazepínicos = score 2, BCCa di-hidropiridínicos = score 1, etc.)
10. **Ajuste renal por faixa de ClCr** (Cockcroft-Gault, regras KDIGO)
11. **Ajuste hepático Child-Pugh A/B/C** (com aliases reconhecidos: "cirrose com ascite" → child_b)
12. **Constraints de sinais vitais** (ex: PA <110 + BCCa di-hidropiridínico = warning)

### Cobertura atual

Aproximadamente **48 princípios ativos** estão cobertos no motor hoje, organizados em 14 classes:

- **Anti-hipertensivos**: losartana, enalapril, anlodipino, nifedipino, propranolol (não-seletivo), atenolol/metoprolol/carvedilol (cardiosseletivos)
- **Antidiabéticos**: metformina, glibenclamida, gliclazida, empagliflozina, dapagliflozina
- **Antiplaquetários e Anticoagulantes**: AAS, clopidogrel, varfarina, rivaroxabana, apixabana, dabigatrana
- **Estatinas**: sinvastatina, atorvastatina, rosuvastatina
- **IBPs**: omeprazol, pantoprazol, esomeprazol
- **Antidepressivos**: sertralina, fluoxetina, escitalopram, mirtazapina
- **Hipnóticos/Ansiolíticos**: clonazepam, diazepam, alprazolam, zolpidem
- **Antipsicóticos**: haloperidol, risperidona, quetiapina, olanzapina (todos com Beers AVOID em demência)
- **Antiparkinsonianos**: levodopa+carbidopa, pramipexol, ropinirol
- **Antieméticos**: metoclopramida (Beers AVOID — discinesia tardia), ondansetrona
- **Antibióticos**: amoxicilina, amoxicilina+clavulanato, azitromicina, ciprofloxacino, sulfa+trimetoprima
- **Outros**: paracetamol, dipirona, AINEs (ibuprofeno/naproxeno/diclofenaco), alendronato, levotiroxina, carbonato de cálcio

Cada um deles tem regras codificadas nas 12 dimensões aplicáveis. Por exemplo, olanzapina tem:
- Dose máxima 20 mg/dia (ANVISA)
- Beers AVOID em demência (Box warning FDA — aumenta mortalidade e AVC)
- ACB Score 3 (anticolinérgico forte — constipação, retenção, confusão)
- Fall risk Score 2 (sedação + hipotensão postural + extrapiramidalismo)
- Contraindicação em Parkinson (antagonismo D2 piora motor)
- Ajuste hepático: Child A monitor, Child B reduce 50%, Child C avoid
- Interações: clonazepam (sedação aditiva), levodopa (antagonismo D2)

### Como funciona na prática

Quando médico/enfermagem pergunta à Sofia "é seguro prescrever 0,5 mg de risperidona 12/12h pra Dona Helena, 87 anos, com demência leve?", a Sofia chama uma ferramenta interna que roda essas 12 dimensões. Em ~200ms, ela retorna:

- ✅ Dose dentro do limite (até 6 mg/dia)
- ⚠️ **Beers 2023 AVOID** em demência (severity warning_strong)
- ⚠️ Contraindicação por condição (severity warning_strong)
- ⚠️ ACB +1 (somar ao ACB total da paciente)
- ⚠️ Fall risk +2

A Sofia recebe esse output e responde com linguagem natural, sempre lembrando que **a decisão final é do médico**. Ela informa, não prescreve.

### Validação automática semanal

Há um processo automático que **re-roda o motor toda semana** sobre todas as prescrições ativas. Por quê? Porque uma regra nova adicionada ao motor (interação descoberta, atualização das diretrizes) pode tornar uma prescrição que era segura ontem, hoje insegura. Quando isso acontece, alerta automático na fila pra revisão.

---

## 4. Como a Sofia "lembra" do paciente

A memória é o que torna a Sofia diferente de um chatbot. Hoje ela tem **4 camadas de memória**:

### a) Memória da conversa atual
Últimas 30 mensagens da sessão. Padrão de qualquer LLM. Funciona dentro de cada conversa.

### b) Memória cross-canal (45 minutos)
Cuidador conversa via chat às 8h. Idoso liga via voz às 8h30. A Sofia da ligação **sabe** do que foi conversado no chat, porque um buffer compartilhado mantém os últimos turnos por 45 minutos. UX "uma Sofia só" — você troca de canal e ela continua a conversa.

### c) Memória de longo prazo do usuário
Cada usuário (médico, cuidador, familiar, paciente) tem um perfil de memória persistente: resumo de 800 caracteres + fatos estruturados (preferências, contexto, tópicos em curso, preocupações). A cada 20 mensagens novas, a Sofia re-extrai esse perfil via IA. Quando o mesmo usuário volta dias depois, a Sofia já vem com contexto carregado: "lembra que você está estudando a interação levodopa+metoclopramida, vamos seguir daí?".

LGPD: opt-in via flag por usuário. Pacientes B2C precisam consentir explicitamente antes de a memória ser ativada.

### d) Recall semântico (qualquer mensagem do passado)
Toda mensagem é **vetorizada** (768 dimensões via embedding semântico) e indexada. Quando médico pergunta "lembra que comentei sobre dor lombar do Sr Antônio em fevereiro?", a Sofia faz busca por similaridade e traz as mensagens exatas dos últimos 90 dias. Não é resumo — é **recall verbatim**, com timestamp e canal de origem.

### Memória coletiva anonimizada (cross-tenant)

Há também um pipeline diário que extrai **padrões agregados** de TODAS as interações Sofia↔Profissional (com PII removida via regex + IA), gerando insights tipo "12 médicos esta semana perguntaram sobre interação levodopa + metoclopramida". Quando frequência ≥ 3, vira chunk de conhecimento e a Sofia passa a antecipar essa dúvida.

LGPD por design: dados crus nunca saem da tabela original; staging só guarda texto anonimizado; threshold mínimo evita re-identificação.

---

## 5. Segurança e posicionamento

Esse é o ponto mais sensível em healthcare. Sofia opera com **inteligência mas sem autoridade**:

### Sofia FAZ:
- Detecta padrões clínicos (ex: 3 quedas em 5 dias, dor persistente)
- Classifica severidade (info / atenção / urgente / crítico)
- Roda o motor de cruzamentos (12 dimensões)
- Mantém memória longitudinal por paciente
- Propõe escalações ao humano quando algo precisa de atenção

### Sofia NÃO FAZ:
- Não diagnostica
- Não prescreve
- Não decide tratamento
- Não substitui consulta médica
- Não age sozinha em situação crítica — sempre chama humano

### A camada de segurança ("Safety Guardrail")

Antes de qualquer ação clínica chegar ao banco de dados ou disparar uma chamada, ela passa por um **router determinístico** que decide:

| Tipo de ação | O que faz |
|---|---|
| **Informativa** (ex: responder dose máxima) | Executa direto + disclaimer auto-injetado |
| **Registrar histórico** (criar relato) | Salva no banco + notifica família se severity ≥ atenção |
| **Convocar atendente humano** | Vai pra fila de revisão, atendente decide aprovar/rejeitar |
| **Emergência real-time** (idoso fala "dor no peito agora") | Pula a fila, escala imediatamente |
| **Modificar prescrição** | **BLOQUEADO no piloto** (precisa médico responsável formal) |

Há um **circuit breaker** que pausa automaticamente o tenant se mais de 5% das ações em 5 minutos caírem na fila — protege contra "Sofia maluca" que estaria escalando demais.

Toda saída clínica da Sofia é **acompanhada de disclaimer natural** ("isso é informação pra te apoiar — confirme sempre com seu médico"). Ela é instruída a variar a forma pra não soar robótico.

### Biometria de voz — quem é quem na ligação

Em healthcare, **saber com certeza quem está do outro lado da linha não é detalhe — é segurança clínica**. Quando a Sofia liga pra Sr. José pós-IAM e quem atende é a esposa, neta ou cuidadora informal, o conteúdo da conversa muda completamente: confidencialidade LGPD, validade do dado clínico relatado, roteamento da escalação.

Cada usuário cadastrado (paciente, familiar, cuidador, médico, enfermagem) tem um **voiceprint** (representação matemática vetorial da voz, não áudio cru) registrado a partir das primeiras interações. Em ligações subsequentes, a Sofia confirma identidade nos primeiros segundos:

- **Atende a esposa do Sr. José em vez dele**: persona muda automaticamente de "paciente" pra "familiar". Linguagem clínica permitida (esposa pode receber explicação farmacológica), mas o registro vai pro prontuário marcando "informação relatada por terceiro, não confirmada com paciente diretamente". Filha não consegue fingir adesão do pai.

- **Atende alguém não cadastrado** (visita ocasional, vizinho, faxineira): Sofia trata como interlocutor desconhecido. Cumprimenta sem revelar diagnóstico, pergunta quem está, registra contato no prontuário, e ajusta continuidade. **Protege contra vazamento de dados sensíveis pra pessoa errada que atendeu o telefone.**

- **Cobertura LGPD**: voiceprint é dado biométrico sensível (Art. 11), tem TCLE específico, é armazenado como vetor matemático em servidor brasileiro, com expiração configurável e direito de exclusão.

**Biomarcadores vocais** (fase de estudo, não em produção): literatura recente (Mayo Clinic, MIT Voice Foundation 2023-2025) mostra que parâmetros vocais quantitativos (jitter, shimmer, ritmo, prosódia, fluência) detectam sinais precoces de desidratação aguda em idoso, descompensação cardíaca, depressão, declínio cognitivo. A Sofia já grava todas as ligações pra gerar transcrição via STT — tem a base técnica pra extrair esses parâmetros. Quando ativados, geram **observação clínica**, não diagnóstico, e vão pro prontuário pra equipe avaliar.

**Aqui sua expertise é central**: definir quais sinais vocais merecem ser monitorados, calibrar limiares por paciente (cada idoso tem baseline próprio), e formalizar o que é "observação clínica" vs o que é "alerta acionável" — cuidando do balanço entre captação precoce de descompensação e geração de fadiga de alerta na equipe.

### Risk Scoring por paciente (em produção)

Cada paciente tem um score 0-100 calculado a partir de 3 sinais determinísticos:

1. Frequência de queixas registradas (últimos 7 dias)
2. Adesão a medicação (% confirmada vs planejada, últimos 7 dias)
3. Quantidade de eventos urgent/critical (últimos 7 dias)

Resultado: paciente classificado em baixo / moderado / alto / crítico, com **breakdown** explicando o porquê. Hoje no piloto identificou 2 pacientes críticos automaticamente que estavam invisíveis no painel humano.

Esse motor é Fase 1 (threshold absoluto). Próxima fase = **baseline individual** — comparar o paciente contra ele mesmo (cada idoso tem padrão próprio de fala/silêncio/queixa). Comparação por desvio, não valor absoluto.

---

## 6. As ligações: como funciona hoje

A ligação telefônica é talvez o canal mais importante pra B2C, porque idoso muitas vezes não usa app/web.

### Fluxo de uma ligação outbound (Sofia liga)

1. Sistema detecta "hora de check-in matinal pra Dona Helena, 8h30"
2. Sofia abre conexão com motor de voz (xAI Grok Voice Realtime, modelo speech-to-speech)
3. PJSIP nosso disca pro telefone da Helena (DDD 51, BRT)
4. Helena atende → Sofia se apresenta com "Bom dia Dona Helena, é a Sofia da ConnectaIACare"
5. Conversa natural por 3-5 minutos, com memória, com tools (consulta medicação, registra relato)
6. Quando Helena interrompe Sofia ("não, espera, eu queria falar de outra coisa"), Sofia para na hora — interrupção em <500ms
7. No final, ela se despede com saudação correta pro horário
8. Histórico todo gravado, embedding gerado, memória atualizada

### O que cada cenário cobre hoje (5 playbooks ativos)

1. **paciente_checkin_matinal** — Sofia liga 8h-9h pro paciente B2C, pergunta como passou a noite, lembra das medicações, capta queixas
2. **cuidador_retorno_relato** — Sofia liga pro cuidador profissional pra atualizar status de um relato em aberto
3. **familiar_aviso_evento** — Sofia liga pro familiar avisando sobre evento clínico (queda, febre persistente, mudança comportamento). Tom seguro, anti-pânico
4. **paciente_enrollment_outbound** — Sofia liga pra novo paciente que demonstrou interesse, faz onboarding leve
5. **comercial_outbound_lead** — Sofia liga pra lead, qualifica + agenda demo

Cada cenário tem **prompt completo** (~7-15 KB) com regras anti-pânico, anti-diagnóstico, RBAC LGPD. Admin pode editar via interface dedicada (`/admin/cenarios-sofia`). Mudanças entram em vigor na próxima ligação, sem release.

### O que mudou ontem (fase de polimento)

A Sofia agora respeita **interrupção do usuário em tempo real**: se você começar a falar enquanto ela fala, ela para imediatamente, drena o áudio bufferizado e cancela a geração no servidor da Grok. É a diferença entre "robô que precisa terminar a frase" e "conversa natural".

---

## 7. Roadmap — o que vem a seguir

### Já está em produção (pra você testar)
- WhatsApp como canal de entrada (texto, áudio, foto/OCR, botões interativos)
- Chat texto web/app + voz browser + ligação telefônica funcionando
- Motor clínico 48 princípios ativos × 12 dimensões
- Memória 4 camadas
- Safety Guardrail Layer
- Risk Scoring inicial (3 sinais)
- 5 cenários de ligação editáveis
- Memória coletiva anonimizada cross-tenant
- Biometria de voz (identificação do interlocutor)
- OCR clínico (receita, embalagem, bula, exame, atestado, displays)
- Visão multimodal pra lesão / ferida / edema (gera observação, não diagnóstico)

### Curto prazo (próximas 2-3 semanas)

**Transferência para central de atendimento humana** — quando a Sofia identifica situação que precisa de pessoa, ela disca para um ramal próprio do paciente, e a central de atendimento (que já roda 24h pra outros clientes) atende com o contexto completo na tela: histórico, último relato, transcrição da Sofia, sinais vitais. O atendente decide: chamar 192? família? agendar teleconsulta? resolver direto pelo telefone?

**Modelagem por tipo de cliente**:
- B2C individual (idoso direto): ramal próprio → atendente da ConnectaIA Care
- Casa geriátrica: ramal compartilhado → cuidador interno da casa
- Clínica: ramal compartilhado → enfermagem/equipe da clínica
- Hospital (futuro): integração com sistema próprio

**Versionamento de prompts dos cenários** — admin edita prompt em modo DRAFT, testa contra "golden dataset" (10 conversas-tipo por cenário), só depois promove pra PUBLISHED. Toda versão fica registrada (auditável). Diff visual entre versões.

**Cron worker proativo** — ao invés de checkin estático ("8h30 todo dia"), Sofia decide: "Helena relatou tontura hoje cedo, vou ligar agora pra checar" em vez de esperar o próximo horário programado.

**Tela admin de fila de revisão** — cuidador/familiar/atendente vê pendências, aprova ou rejeita com 1 clique. Push notification em tempo real.

**Frontend do Risk Scoring** — dashboard com pacientes em alto risco, com breakdown explicativo ("por que esse paciente é crítico?"). Tendência (improving/stable/worsening).

### Médio prazo (1-3 meses)

**Inbound calls** — Sofia atende ligações que chegam (fase atual é só outbound). Roteador identifica caller_id e direciona pra cenário certo: paciente conhecido → modo familiar; profissional cadastrado → modo clínico; desconhecido → comercial.

**Baseline individual** por paciente — em vez de threshold absoluto ("mais de 3 queixas = alto risco"), comparamos o paciente contra ele mesmo. Idoso que sempre teve baseline de 5 queixas/semana não dispara alarme; idoso que aumentou de 1 para 3 dispara.

**Mais princípios ativos no motor** — meta de 80 cobertos (95% das prescrições geriátricas brasileiras). **Aqui é onde sua opinião é central**: quais são as classes mais frequentes que ainda faltam? Onde as 12 dimensões precisam de afinamento?

**Detecção de padrões longitudinais** — Sofia identifica "esse paciente mencionou cansaço 5× esse mês" e flag pra equipe.

**Recall semântico cross-paciente** — médico pergunta "que outros pacientes com esse mesmo padrão de queda já tivemos no sistema?". Sofia busca em todo histórico anonimizado.

### Longo prazo (6-12 meses)

**WhatsApp Calling outbound nativo** — Sofia chama via WhatsApp (não PSTN), tocando o WhatsApp do paciente com foto verificada da equipe, qualidade superior à ligação tradicional, sem custo de minuto telefônico. Em estudo de maturidade da Meta Business API.

**Plano "Cuidado Sem Limites" B2C massivo** — idosos que moram sozinhos, contratam direto via WhatsApp, sem clínica intermediária. Esse é o cenário Dona Helena.

**Federated learning entre tenants** — insights coletivos com diferential privacy mais formal, opt-out per-tenant.

**Imagem multimodal** — Sofia analisa foto de receita, etiqueta de remédio, lesão de pele.

---

## 8. O que está sendo decidido agora

### Piloto em casas geriátricas

Vamos colocar a Sofia em **5-10 casas geriátricas mais simples**, gratuitamente, pra termos casos de uso reais. Critério: casas com cuidador presencial 24h (humano de backup), rotina estruturada, prontuário disponível. Ambiente é mais hostil que cuidador idoso sozinho (TV ligada, vários pacientes, equipe técnica limitada) — mas é onde a gente valida o produto antes de B2C massivo.

Equipamento por casa: ainda em definição. Avaliando entre tablet com PWA Sofia, Raspberry Pi com microfones distribuídos, ou tablet + botão físico "Falar com Sofia". **Não vamos usar Alexa/Google** por questões de LGPD (Amazon/Google retêm o áudio).

### Conformidade regulatória

Estamos em "cinza ativo" como toda healthtech IA brasileira. Princípios que a gente já segue (sem registro ANVISA ainda):
- Sofia posicionada como **suporte informacional**, não dispositivo médico
- Toda saída clínica com disclaimer explícito
- Audit chain criptográfico (LGPD compliant)
- TCLE simples em 3 telas pro paciente (ainda em desenho)

Quando crescermos, vamos enquadrar como SaMD (Software como Dispositivo Médico) Classe II junto à ANVISA. Esse é um trabalho que vai precisar de você, junto com farmacêutico responsável e advogado de saúde.

### Análises externas em curso

Pedimos análise crítica do projeto pra 4 fontes (3 LLMs externos: Gemini 2.5 Pro, ChatGPT 5, Grok + minha análise interna). Convergiram em pontos importantes:
- Cross-channel state drift (resolvido — buffer 45min)
- Risk scoring determinístico (resolvido — Fase 1 implementada)
- Versionamento de prompts (schema pronto, UI pendente)
- Não fazer voice cloning (assumido — voz da Sofia sempre transparente)
- Adotar plataformas voice maduras (LiveKit/Vapi) em vez de manter PJSIP próprio (decisão híbrida tomada — LiveKit pro piloto, PJSIP fica pra escala)

---

## 9. Onde sua expertise mais entra

Sua formação em biomedicina e farmácia é estratégica em várias frentes:

### Imediato — validação clínica do que já temos

1. **Auditoria do motor de 12 dimensões** — sua leitura crítica das regras codificadas pra cada um dos 48 princípios ativos. Especificamente Beers 2023, Child-Pugh, KDIGO. Há erros? Há diretrizes mais novas que não consideramos?
2. **Revisão dos 5 cenários de ligação** — os prompts têm regras clínicas (anti-pânico, anti-diagnóstico). Estão calibrados? Falta sensibilidade clínica em algum lugar?
3. **STOPP/START** — hoje usamos só Beers. STOPP/START Brasil é mais aplicável a idoso brasileiro?

### Curto prazo — expansão do motor

1. **Cobertura ampliada** — quais são os 30+ princípios ativos que faltam pra cobrir 95% da prescrição geriátrica brasileira?
2. **Polifarmácia** — hoje detectamos só "≥5 medicamentos". Faz sentido? Como o STOPP/Fleetwood scores poderiam ajudar?
3. **Cascatas de prescrição** — hoje não detectamos cascatas (AINE → HAS → anti-hipertensivo, BCCa → edema → diurético). Vale codificar?

### Médio prazo — frente clínica do produto

1. **Material clínico** — landing page, materiais comerciais, pitch tech precisam de revisão clínica antes de ir pra fora
2. **Comitê de governança IA** — preciso atender CFM 2.314/2022 e quando registrar como SaMD na ANVISA
3. **Farmacêutico responsável** — é necessário formalizar pra escalar, especialmente pra B2C (você potencialmente?)

### Longo prazo — direcionamento estratégico

1. **Diferencial competitivo clínico** — onde a ConnectaIACare deve mirar pra ser referência clínica? Geriatria? Crônicos? Pós-alta?
2. **Parcerias acadêmicas** — universidades de farmácia/biomédica que poderiam validar nossos resultados em pesquisa formal
3. **Publicações** — quando tivermos 100+ pacientes acompanhados, vale publicar resultados

---

## 10. Perguntas pra você responder na primeira leitura

Não é obrigatório responder agora — leve pra refletir. Mas o que mais nos ajuda da sua entrada são respostas a essas perguntas:

1. **Olhando a lista de 48 princípios ativos cobertos**, qual classe ou fármaco você considera CRITICAMENTE ausente pra geriátrica brasileira?
2. **Beers 2023 é referência adequada** ou deveríamos somar STOPP/START + Brasil? Existem listas brasileiras específicas?
3. **A frase do disclaimer** ("Esta é informação para apoiar a sua decisão — quem decide é sempre você com o médico responsável") está adequada? Você reescreveria?
4. **No cenário de ligação familiar avisando sobre evento clínico** (queda, febre), o tom "seguro mas não dramatizar" está correto? Há armadilhas de comunicação que você sabe que devemos evitar?
5. **Tem algum padrão de polifarmácia em idoso brasileiro** que você acha que devemos detectar e que provavelmente não detectamos?
6. **Risco de cascata de prescrição** — vale a pena codificar detecção (ex: paciente toma AINE + IECA + diurético = "triple whammy" → IRA aguda)? Tem outras cascatas que você considera críticas?
7. **CFM 2.314/2022** — você tem leitura pessoal sobre como devemos enquadrar a Sofia?
8. **Pra escalar pra B2C massivo (Dona Helena)** — qual é a sua preocupação clínica/farmacológica número 1 que você acha que devemos mitigar antes?

---

## 11. Próximo passo

Lê com calma. Marca dúvidas. Discutimos numa call.

Pra você ter contexto técnico se quiser explorar mais:
- O documento técnico completo está em `docs/sofia_overview_analise_externa.md` (44KB, denso, pra times de engenharia)
- O resumo da última sessão de implementação está em `docs/sessao_noturna_2026-04-27.md`

Qualquer coisa: alexandre@connectaia.com.br

Bem-vindo ao time, Henrique. A frente clínica do produto não pode ser construída sem você.
