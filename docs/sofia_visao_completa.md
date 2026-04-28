# Sofia — Plataforma Clínica ConnectaIACare

> Visão técnica completa da plataforma · Material para revisão clínica
> ConnectaIACare © 2026 · Conteúdo confidencial · uso restrito

---

## Sobre este documento

Este é o material técnico-clínico de referência da plataforma **Sofia**, da ConnectaIACare. Cobre arquitetura, canais de entrada, motor clínico determinístico, sistemas de inteligência, governança regulatória e roadmap. Foi escrito para ser lido como documento contínuo — não é apresentação. Pode ser usado como base para discussões com profissionais de saúde, comitês técnicos ou parcerias.

**Convenção de status** usada ao longo do texto:

- ✅ em produção
- 🟡 em finalização
- 🔵 roadmap próximo (8-12 semanas)
- 🟣 visão futura (3-12 meses)

---

## 1. Visão geral

A ConnectaIACare é uma plataforma de assistência inteligente conversacional para idosos e pacientes crônicos no Brasil. O núcleo da plataforma é a **Sofia**, uma IA conversacional integrada a um motor clínico determinístico, capaz de manter relacionamento contínuo com o paciente, sua família, cuidadores e equipe clínica.

A diferença para outras IAs em saúde é que a Sofia tem inteligência mas **não tem autoridade clínica**. Toda decisão sobre o paciente passa por humano — médico, enfermagem, atendente clínico ou família. A Sofia informa, lembra, escala, escuta, gera observação clínica. Não diagnostica, não prescreve, não decide.

A plataforma é multi-canal (WhatsApp, chat web, voz no browser, ligação telefônica, teleconsulta), multi-persona (paciente, cuidador, familiar, enfermagem, médico, administrador) e opera tanto em modelo B2C (idoso individual) quanto B2B (casa geriátrica, clínica, hospital).

---

## 2. O problema clínico

A polifarmácia em geriatria brasileira combina três fatores que criam risco evitável:

- **Volume**: idoso 65+ usa em média 5 a 7 medicações simultâneas. Cada medicação adicional aumenta probabilidade de interação, efeito adverso, e cascata de prescrição.
- **Causa farmacológica**: 25 a 30% das readmissões hospitalares evitáveis no Brasil tem causa farmacológica. A combinação errada de drogas, ajuste de dose inadequado em idoso com função renal limítrofe, ou adesão imperfeita são os fatores principais.
- **Cascatas de prescrição**: até um terço dos idosos recebe medicação para tratar efeito adverso de outra medicação que poderia simplesmente ser retirada. Triple Whammy (AINE + IECA/BRA + Diurético) e antipsicótico + antiparkinsoniano são exemplos clássicos.

O conhecimento clínico para evitar isso já existe — Critérios de Beers 2023, STOPP/START, KDIGO, Child-Pugh — mas raramente é aplicado fora da consulta geriátrica especializada. Em pronto-socorro, clínico geral ou especialistas focais, esse conhecimento fica de fora.

A questão técnica que a Sofia resolve é: **como aplicar esse conhecimento clínico em toda interação, em escala, sem depender de geriatra disponível em todas as situações?**

---

## 3. Arquitetura geral

A plataforma está organizada em cinco camadas hierárquicas, da entrada do dado bruto até a governança humana.

### 3.1 Camada 1 — Canais de entrada (multimodais)

WhatsApp · Chat web/app · Voz no browser · Ligação telefônica · Teleconsulta integrada.

Cada canal aceita texto, áudio, vídeo (em teleconsulta), imagem (com OCR), interação por botões. Persona é detectada automaticamente por canal e por biometria de voz, ajustando tom e capacidades disponíveis.

### 3.2 Camada 2 — Sofia (LLM conversacional)

A IA conversacional cuida da interação natural com o usuário. Usa modelo de linguagem state-of-the-art em português brasileiro, com persona ajustada por interlocutor (paciente recebe tom calmo e linguagem simples; profissional clínico recebe linguagem técnica permitida).

Sofia detecta intenção, gera resposta, e quando precisa de dado clínico chama uma das 16 ferramentas (tools) clínicas estruturadas. Mantém memória em 4 camadas (detalhada na seção 7).

### 3.3 Camada 3 — Motor clínico determinístico

Esta é a parte mais crítica e diferenciada. Toda validação clínica é feita por **código nativo Python**, não por IA generativa. Beers AVOID em demência é uma regra que retorna em ~200 milissegundos, sempre igual, auditável, versionada. Sem alucinação possível.

São 12 dimensões clínicas validadas simultaneamente, mais 1 dimensão adicional para cascatas de prescrição. 48 princípios ativos cobertos hoje. Detalhado na seção 6.

### 3.4 Camada 4 — Safety Guardrail Layer

Toda ação clínica que a Sofia produziria — registrar evento, agendar teleconsulta, escalar atendente, modificar prescrição — passa por um router determinístico. Esse router decide entre quatro destinos: executar diretamente, enfileirar para revisão humana, escalar emergência em tempo real, ou bloquear. Modificação de prescrição está hard-coded como bloqueada na configuração padrão.

### 3.5 Camada 5 — Auditoria e governança

Toda ação sensível é registrada em uma audit chain criptográfica (hash chain SHA-256), inviolável computacionalmente. Itens enfileirados pela Camada 4 vão para a fila de revisão, onde a equipe clínica humana aprova ou rejeita.

---

## 4. Canais de entrada

A plataforma absorve a heterogeneidade de uso digital do idoso brasileiro. Diferente de soluções que exigem instalação de aplicativo dedicado (taxa de abandono >60% nos primeiros 14 dias em telemonitoramento), a Sofia vai onde o paciente já está.

### 4.1 WhatsApp Business ✅

Mais de 90% dos brasileiros adultos usam WhatsApp diariamente. Para o idoso 65+, frequentemente é o único aplicativo digital usado. Operamos via WhatsApp Business Cloud API homologada com a Meta, com criptografia ponta-a-ponta nativa, integradores certificados com servidores brasileiros, e templates de mensagem proativa pré-aprovados para healthcare. Opt-in explícito do paciente registrado em TCLE específico.

A entrada via WhatsApp não é "chat tradicional". Para geriatria brasileira, a forma mais natural de relato é áudio mais foto. A plataforma processa cada tipo de entrada de forma diferenciada:

**Áudio do WhatsApp.** O paciente fala 30 segundos: "Sofia, hoje minha mãe acordou confusa, não soube onde tava, e ela tá bebendo pouca água". A Sofia transcreve via Speech-to-Text, estrutura clinicamente o conteúdo extraindo sintomas (confusão mental aguda, baixa ingesta hídrica), confronta com motor clínico (idosa + medicações + baixa ingesta hídrica = suspeita de delirium hipoativo por desidratação), classifica severidade, e dispara para o prontuário. Tudo a partir de um áudio do WhatsApp.

**OCR de receita médica.** O paciente sai do hospital, fotografa a receita ao chegar em casa. A Sofia extrai medicamentos, doses e posologias, e confronta com a prescrição registrada no prontuário. Se a farmácia entregou medicação errada, ou se o paciente está olhando uma receita anterior misturada com a nova, a Sofia detecta divergência e escala para a equipe clínica antes da primeira dose. Esse é um detector de erro de medicação no momento certo: antes de o paciente tomar dose errada.

**OCR de embalagem.** Idoso esqueceu o nome do remédio, manda foto da caixa. A Sofia identifica princípio ativo, dose, lote e validade. Confronta com o que ele deveria estar tomando.

**OCR de bula.** Paciente está em dúvida sobre efeito colateral, manda foto da bula. A Sofia lê, identifica a seção relevante, explica em linguagem simples ("isso aqui significa que o remédio pode dar tontura nos primeiros dias, é normal").

**OCR de exame laboratorial.** Paciente recebeu hemograma e fotografa. A Sofia extrai dados estruturados (Hb, leucócitos, creatinina, eletrólitos), arquiva no prontuário via FHIR, e roda alertas clínicos automáticos. Se creatinina subiu, a Sofia avisa a equipe para revisar ajuste renal das medicações.

**Visão multimodal de lesão, ferida ou edema.** Paciente fotografa. A Sofia identifica sinais visuais sugestivos (vermelhidão, exsudato, deiscência de sutura, edema localizado), gera observação clínica para o prontuário. Não diagnostica.

**Foto do display de aparelho.** Paciente fotografa o glicosímetro, oxímetro ou aparelho de pressão. A Sofia extrai o valor, registra com flag "auto-relato via foto" para diferenciar de equipamento integrado, e roda alertas se valor está fora da faixa de referência do paciente.

**Lembretes proativos com botões interativos.** A Sofia manda "Sr. José, está na hora do enalapril. Já tomou?" com botões interativos [Sim, tomei] [Ainda não] [Não vou tomar agora]. A resposta vai direto para o prontuário via FHIR. Em 3 toques, paciente registra adesão sem digitar.

**Família integrada via grupo.** Familiar autorizado pode estar em grupo familiar do paciente, recebendo atualizações de saúde periódicas com consentimento explícito. A Sofia distingue mensagens do grupo (compartilhadas) de mensagens privadas (paciente-Sofia confidenciais).

### 4.2 Chat web/app ✅

Quando há tempo para escrever, anexar arquivo, conversar com mais detalhe. Profissional cadastra paciente, médico consulta dose máxima de uma medicação, família acessa painel completo do paciente. Persona profissional preferida.

### 4.3 Voz no browser ✅

Botão flutuante no painel. Usado quando o cuidador está com mãos ocupadas, ou quando o paciente tem dificuldade para digitar. Modelo speech-to-speech state-of-the-art em português brasileiro, com latência conversacional natural e capacidade de interrupção em tempo real (Sofia para de falar imediatamente quando o usuário começa a falar).

### 4.4 Ligação telefônica direta ✅

A Sofia liga ou atende com voz natural. Crítico para o idoso que não usa smartphone ou aplicativo. Funciona como uma ligação humana qualquer — a Sofia cumprimenta pelo nome, conversa, escuta. Cinco cenários de ligação outbound em produção (detalhados na seção 7.5). Inbound calls (Sofia atende ligações que chegam) está no roadmap próximo (🔵).

### 4.5 Ligação via WhatsApp 🟣

Em estudo. A Meta liberou em 2024 a possibilidade de chamadas de voz outbound via WhatsApp Business API. Para o idoso brasileiro, isso é estratégico: chamada via WhatsApp não consome créditos de ligação, toca o WhatsApp que ele já reconhece, mostra a foto e nome verificado da equipe no caller, e tem qualidade de voz superior à PSTN tradicional. Avaliando maturidade da API para incorporação.

---

## 5. Biometria de voz e biomarcadores vocais

Em healthcare, saber com certeza quem está do outro lado da linha não é detalhe — é segurança clínica.

Quando a Sofia liga para um paciente pós-IAM e quem atende é a esposa, neta ou cuidadora informal, o conteúdo da conversa muda completamente: questões de privacidade (LGPD), validade da informação reportada (a esposa não sabe se o paciente realmente tomou a medicação fora da vista dela), e roteamento da escalação clínica (família precisa ser notificada, profissional pode receber dados clínicos crus, paciente precisa de cuidado de comunicação).

### 5.1 Biometria de voz ✅

Cada usuário cadastrado na plataforma (paciente, familiar, cuidador profissional, médico, enfermagem) tem um voiceprint registrado a partir das primeiras interações. Voiceprint é representação matemática vetorial da voz, não áudio cru, armazenado em servidor brasileiro. Em ligações subsequentes, a Sofia confirma a identidade automaticamente nos primeiros segundos.

**Identificação automática do interlocutor.** Se o telefone do paciente atende mas a voz é da filha, a Sofia reconhece e ajusta automaticamente:

- **Persona muda**: passa de "paciente" para "familiar". Linguagem clínica permitida (a filha pode receber explicações farmacológicas), mas o registro vai para o prontuário marcando "informação relatada por terceiro, não confirmada com paciente".
- **Tom muda**: deixa de ser conversacional/calmo e passa a ser direto/informativo.
- **Compliance LGPD**: dados clínicos do paciente só são detalhados se o familiar tem permissão registrada como vínculo (filha responsável legal, responsável de cuidado declarado).

**Detecção de pessoa não cadastrada.** Se atende quem a Sofia não reconhece, ela trata como interlocutor desconhecido: cumprimenta sem revelar dados clínicos, pergunta quem está falando, registra o contato no prontuário, e adapta a continuidade da conversa. Protege contra vazamento de dados sensíveis para visita ocasional, faxineira ou vizinho que atendeu.

**Cobertura LGPD.** Voiceprint é dado biométrico sensível sob Art. 11 da LGPD. Operamos com TCLE específico para coleta e processamento, expiração configurável, direito de exclusão a qualquer momento.

### 5.2 Biomarcadores vocais 🟣

Em fase de estudo, não em produção. A literatura recente (publicações Mayo Clinic, MIT Voice Foundation 2023-2025) mostra que análise quantitativa de parâmetros vocais (jitter, shimmer, ritmo, pausas, intensidade, prosódia, fluência) detecta sinais precoces de:

- Desidratação aguda em idoso (alteração de timbre, ressecamento de fala)
- Insuficiência cardíaca descompensada (dispneia mascarada na conversa)
- Quadros depressivos (lentificação, diminuição de prosódia)
- Declínio cognitivo longitudinal (alteração de fluência, repetição, perda de coerência)

A Sofia já grava todas as ligações para gerar transcrição via Speech-to-Text — tem a base técnica para extrair esses parâmetros. Quando ativados, geram observação clínica (não diagnóstico) que vai para o prontuário, e a equipe clínica decide se o sinal merece investigação. Mesma filosofia central da plataforma: inteligência sem autoridade.

Roadmap de validação clínica conjunta seria parte de pilotos avançados.

---

## 6. Motor clínico determinístico

O motor clínico é o coração técnico da plataforma. É código nativo Python, não IA generativa, validando toda prescrição em **12 dimensões simultaneamente** mais uma dimensão adicional para cascatas de prescrição. Saída estruturada em ~200 milissegundos. Cada dimensão é uma tabela versionada no banco de dados com fonte clínica citada.

A diferença para soluções que usam LLM para "raciocinar" sobre interações é que aqui as regras são determinísticas — Beers AVOID em demência retorna sempre o mesmo resultado, é auditável, versionada. Quando atualizamos uma regra, todas as prescrições ativas no sistema são re-validadas (ver seção 6.4).

### 6.1 As 12 dimensões clínicas

**Dimensão 1 — Dose máxima diária.** Tabela `aia_health_drug_dose_limits`. Por princípio ativo, com dose máxima ajustada para idoso ≥65. Fonte: ANVISA Bulário Eletrônico, FDA labels, Beers 2023. Exemplo: olanzapina 20 mg/dia.

**Dimensão 2 — Critérios de Beers 2023.** Tabela `aia_health_drug_beers`. Distinguimos AVOID em qualquer idoso de AVOID em condição específica (demência, history of falls, IRC, etc), porque Beers é contextual. Exemplo: olanzapina AVOID em demência (FDA Box warning — aumenta mortalidade e AVC).

**Dimensão 3 — Alergias e reações cruzadas.** Tabela `aia_health_allergy_crossreactivity`. Exemplo: alergia a penicilina implica em reação cruzada para todos os β-lactâmicos. Sulfa cruza com probenecida. AAS cruza com AINEs.

**Dimensão 4 — Duplicidade terapêutica.** Detecção por classe e por princípio ativo. Exemplo: sertralina e escitalopram coexistindo = duplicação SSRI.

**Dimensão 5 — Polifarmácia.** Threshold de ≥5 medicamentos com peso por classe terapêutica. Idoso com 8 medicações + 2 anticolinérgicos gera score alto de polifarmácia.

**Dimensão 6 — Interações medicamento-medicamento.** Tabela `aia_health_drug_interactions` com 40 pares de princípios ativos e classes. Severidade gradativa: contraindicated, major, moderate, minor. Exemplo: ciprofloxacino + amiodarona = QT longo (AVOID).

Detalhe importante: temos **interações mitigáveis por espaçamento de horário**, não apenas regras "evitar". Levotiroxina + carbonato de cálcio se resolvem espaçando 4 horas, em vez de evitar.

**Dimensão 7 — Contraindicações por condição clínica.** Tabela `aia_health_drug_contraindications`. Match por código CID-10 da condição do paciente. Exemplo: risperidona contraindicada em paciente com Doença de Parkinson (G20) por antagonismo D2.

**Dimensão 8 — ACB Score (Anticholinergic Cognitive Burden).** Tabela `aia_health_drug_anticholinergic_burden`, escala Boustani (0-3). Score cumulativo: amitriptilina ACB 3 + oxibutinina ACB 3 = total 6 (alto risco cognitivo, associado com declínio, delirium e queda).

**Dimensão 9 — Fall Risk Score.** Tabela `aia_health_drug_fall_risk` por classe terapêutica. Benzodiazepínicos score 2, BCCa di-hidropiridínicos score 1, antipsicóticos atípicos score 1, antipsicóticos típicos score 2.

**Dimensão 10 — Ajuste renal.** Tabela `aia_health_drug_renal_adjustments`. Cockcroft-Gault aplicado para calcular ClCr (preferido vs creatinina pura, porque idoso pode ter creatinina "normal" mas TFG real baixa por sarcopenia). Quatro faixas de ajuste, regras KDIGO 2024. Exemplo: metformina ClCr<30 = AVOID; <45 = max 1 g/dia.

**Dimensão 11 — Ajuste hepático.** Tabela `aia_health_drug_hepatic_adjustments`, Child-Pugh A/B/C. Aliases reconhecidos ("cirrose com ascite" → child_b). Exemplo: olanzapina Child A monitorar, B reduzir 50%, C evitar.

**Dimensão 12 — Constraints de sinais vitais.** Tabela `aia_health_drug_vital_constraints`. Permite alerta quando dose existente perde adequação. Exemplo: paciente em uso de anlodipino chega com PA 100/60 → alerta automático de hipotensão potencial.

### 6.2 Dimensão 13 — Cascatas de prescrição ✅

Esta dimensão tira o motor do "validador de prescrição individual" e transforma em "auditor de regime terapêutico". Cascata é o padrão clássico onde droga A causa efeito adverso, e o médico prescreve droga C para tratar o efeito em vez de suspender A. Polifarmácia evitável + risco aumentado.

Oito cascatas codificadas hoje (curadoria Beers 2023, STOPP/START v2, Rochon BMJ 2017):

| Cascata | Severidade | Exclusão |
|---|---|---|
| Triple Whammy (AINE + IECA/BRA + Diurético) → IRA aguda | major | — |
| HAS induzida por AINE → anti-hipertensivo | moderate | — |
| BCCa-DHP → edema → diurético (ineficaz) | moderate | — |
| Antipsicótico + antiparkinsoniano (paradoxal) | major | Parkinson real (G20/G21) |
| Metoclopramida → discinesia tardia | major | — |
| IBP crônico + suplementos B12/Cálcio | minor | — |
| Anticolinérgico + laxante crônico | moderate | — |
| Corticoide → hiperglicemia → antidiabético | moderate | DM pré-existente (E10-E14) |

Exclusões clínicas codificadas evitam falso positivo: paciente com Parkinson real é excluído da cascata "antipsicótico + antiparkinsoniano" porque o antiparkinsoniano é tratamento legítimo, não cascata.

Roadmap de cascatas adicionais (🔵): diurético tiazídico → hiperuricemia → alopurinol; beta-bloqueador → bradicardia; opioide → constipação → laxante (separada da cascata anticolinérgica).

### 6.3 Cobertura: 48 princípios ativos × 14 classes

```
Anti-hipertensivos (7):     losartana, enalapril, anlodipino, propranolol,
                            atenolol, metoprolol, carvedilol

Antidiabéticos (5):         metformina, glibenclamida, gliclazida,
                            empagliflozina, dapagliflozina

Antiplaq./Anticoag. (6):    AAS, clopidogrel, varfarina, rivaroxabana,
                            apixabana, dabigatrana

Estatinas (3):              sinvastatina, atorvastatina, rosuvastatina

IBPs (3):                   omeprazol, pantoprazol, esomeprazol

Antidepressivos (4):        sertralina, fluoxetina, escitalopram, mirtazapina

Hipnóticos/Ansiolíticos (4): clonazepam, diazepam, alprazolam, zolpidem

Antipsicóticos (4):         haloperidol, risperidona, quetiapina, olanzapina

Antiparkinsonianos (3):     levodopa+carbidopa, pramipexol, ropinirol

Antieméticos (2):           metoclopramida, ondansetrona

Antibióticos (5):           amoxicilina, amoxicilina+clavulanato, azitromicina,
                            ciprofloxacino, sulfa+trimetoprima

Outros:                     paracetamol, dipirona, AINEs (ibuprofeno/naproxeno/
                            diclofenaco), alendronato, levotiroxina,
                            carbonato de cálcio
```

Cobertura estimada: 70 a 80% da prescrição geriátrica brasileira.

**Roadmap próximo (🔵): expansão para 80 princípios ativos** (~95% cobertura). Faltam BCCa não-DHP (verapamil, diltiazem), inibidores de colinesterase (donepezila, rivastigmina, galantamina, memantina), insulinas, broncodilatadores inalatórios (salbutamol, formoterol, tiotrópio), corticoides sistêmicos (prednisona, prednisolona, dexametasona), opioides (tramadol, codeína, morfina), anticonvulsivantes (gabapentina, pregabalina, valproato).

### 6.4 Validação automática semanal ✅

Toda semana o motor re-roda todas as prescrições ativas no banco contra a versão atual das 13 dimensões. A maioria dos sistemas valida na hora da prescrição e esquece. Aqui re-validamos semanalmente porque:

- Nova interação descoberta na literatura → ontem segura, hoje insegura
- Atualização de critérios Beers → fármaco passa a ser AVOID em condição
- Mudança de função renal do paciente → dose anterior virou inadequada
- Cascata recém-codificada → identifica padrões já existentes em pacientes em uso

Achados vão para a fila de revisão clínica (`aia_health_action_review_queue`) com severidade calibrada. Quando os Critérios de Beers 2023 saíram em nova versão, em uma semana todos os pacientes ativos tiveram suas prescrições re-cruzadas. **Achados ficam na fila para a equipe clínica decidir — não modificamos prescrição automaticamente.**

---

## 7. Sistemas de inteligência

### 7.1 Memória em 4 camadas ✅

A Sofia se diferencia de chatbot porque mantém continuidade real do relacionamento clínico através de quatro camadas de memória que operam juntas.

**Memória da conversa atual.** Últimas 30 mensagens da sessão. Padrão de qualquer sistema conversacional.

**Memória cross-canal (45 minutos).** Cuidador conversa via chat às 8h. Idoso liga via voz às 8h30. A Sofia da ligação sabe do que foi conversado no chat porque um buffer compartilhado mantém os últimos turnos por 45 minutos. UX "uma Sofia só" — você troca de canal e ela continua a conversa.

**Memória de longo prazo do usuário.** Cada usuário (médico, cuidador, familiar, paciente) tem perfil de memória persistente: resumo de 800 caracteres mais facts estruturados (preferências, contexto, tópicos em curso, preocupações). A cada 20 mensagens novas, a Sofia re-extrai esse perfil. Quando o mesmo usuário volta dias depois, a Sofia já vem com contexto carregado. LGPD: opt-in via flag por usuário.

**Recall semântico (verbatim).** Toda mensagem é vetorizada (768 dimensões via embedding semântico) e indexada em banco vetorial dedicado com algoritmo de busca por similaridade (HNSW). Quando médico pergunta "lembra que comentei sobre dor lombar do Sr. Antônio em fevereiro?", a Sofia faz busca semântica e traz as mensagens exatas dos últimos 90 dias. Não é resumo — é recall verbatim, com timestamp e canal de origem (chat ou ligação).

**Memória coletiva anonimizada cross-tenant.** Pipeline diário extrai padrões agregados de todas as interações Sofia↔Profissional (com PII removida via regex + IA), gerando insights tipo "12 médicos esta semana perguntaram sobre interação levodopa + metoclopramida". Quando frequência ≥3, o insight vira chunk de conhecimento e a Sofia passa a antecipar essa dúvida. LGPD por design: dados crus nunca saem da tabela original; staging só guarda texto anonimizado; threshold mínimo evita re-identificação.

### 7.2 Recall semântico cross-paciente ✅

Médico pergunta: *"que outros pacientes tiveram esse mesmo padrão de queda?"* A Sofia busca semanticamente em todos os pacientes do tenant, retornando matches anonimizados:

- patient_id substituído por hash não-reversível (anon-XXXXXXXX)
- Salt único por query — mesmo paciente NÃO é re-identificável entre buscas diferentes
- PII redacted: nome paciente, telefone, email, CPF, datas → tokens
- Restrito a profissionais clínicos (medico, enfermeiro, admin) por RBAC

Permite reflexão sobre padrões coletivos sem expor identidade individual. Profissional pode perguntar "já vimos esse tipo de queixa antes?" e receber 10 snippets anonimizados para raciocinar.

### 7.3 Risk Score por paciente ✅

Cada paciente tem score 0-100 calculado a partir de sinais determinísticos.

**Fase 1 — Threshold absoluto.**

- Sinal 1: frequência de queixas registradas (últimos 7 dias)
- Sinal 2: adesão a medicação (% confirmadas vs planejadas, últimos 7 dias)
- Sinal 3: quantidade de eventos urgent/critical (últimos 7 dias)

Resultado: paciente classificado em low / moderate / high / critical, com breakdown explicando o porquê.

**Fase 2 — Baseline individual ✅.**

Cada paciente comparado contra ele mesmo, não apenas contra threshold absoluto. João com DPOC tem baseline de 5 queixas/semana — para ele, 5 é normal. Maria que normalmente reclamava 1×/semana subindo para 3 = ALARME, mesmo abaixo do threshold absoluto.

Estatística robusta: median + MAD (Median Absolute Deviation) com fator 1.4826. Z-score robusto comparável a stddev mas imune a outliers e funciona bem com N pequeno (4-12 semanas). Janela de 60 dias agregando por semana.

Score combinado = max(threshold absoluto, threshold + bônus baseline). Não duplica punição quando os dois sinais concordam.

### 7.4 Proactive Caller ✅

A Sofia decide DINAMICAMENTE quando ligar para o paciente, não por cron estático. Worker que avalia continuamente (tick a cada 5 minutos) cada paciente ativo:

```
Score de gatilho (0-100):
  + risk_level critical → 60 pontos
  + risk_level high → 35 pontos
  + missed_doses 24h ≥ 3 → 40 pontos
  + open_urgent_events ≥ 2 → 35 pontos
  + gap > 48h sem contato → 15 pontos
  - gap < 4h (acabou de ligar) → -100 pontos (block)

Threshold default: 50 pontos para disparar ligação
```

Configurável por paciente: janela horária preferida, do-not-disturb, intervalo mínimo entre ligações, timezone, scenario_code preferido. Respeita o circuit breaker do Safety Guardrail (se aberto, suspende ligações no tenant).

Toda decisão (will_call ou skip) fica auditável. Skips com razão explícita (fora janela, score baixo, DND ativo, etc).

### 7.5 Cenários de ligação versionados ✅

Cinco cenários de ligação outbound em produção, cada um editável sem release de código:

| Cenário | Persona | Quando dispara |
|---|---|---|
| paciente_checkin_matinal | paciente B2C | 8h-9h diário · também via Proactive Caller dinâmico |
| cuidador_retorno_relato | cuidador profissional | Atualizar status de relato em aberto |
| familiar_aviso_evento | familiar | Avisar sobre evento clínico (queda, febre) — tom anti-pânico |
| paciente_enrollment_outbound | paciente novo | Onboarding leve |
| comercial_outbound_lead | lead comercial | Qualificar e agendar demo |

Cada cenário tem prompt completo (~7-15 KB) com regras anti-pânico, anti-diagnóstico, RBAC LGPD.

**Workflow de versionamento.** Edição vai para DRAFT → testing → published → archived. Admin testa contra "golden dataset" (10 conversas-tipo por cenário) antes de promover. Toda promoção registrada em audit chain com user_id e timestamp. Mudanças entram em vigor na próxima ligação, sem release.

### 7.6 As 16 ferramentas clínicas

A Sofia chama ferramentas estruturadas durante conversa (chat ou voz). Disponibilidade depende da persona:

**Para profissional clínico (medico, enfermeiro, admin):**
- query_drug_rules — consulta regra de fármaco no motor
- check_drug_interaction — interação par×par
- check_medication_safety — validação completa de prescrição (12 dim)
- list_beers_avoid_in_condition — lista AVOID por condição
- query_clinical_guidelines — consulta diretrizes
- recall_semantic_cross_patient — busca padrão em outros pacientes (anonimizado)

**Para pacientes, cuidadores e familiares:**
- get_patient_summary — panorama clínico do paciente
- list_medication_schedules — esquemas ativos
- get_patient_vitals — sinais vitais recentes
- create_care_event — registra queixa/evento (passa por Safety Guardrail)
- schedule_teleconsulta — agenda consulta (passa por Safety Guardrail)
- escalate_to_attendant — aciona atendente humano (passa por Safety Guardrail)
- recall_semantic — busca verbatim no histórico do próprio paciente
- get_my_subscription — plano contratado (B2C)

Cada ferramenta tem schema validado, allowed_personas (RBAC nativo), e integração com Safety Guardrail Layer para ações que precisam revisão humana.

---

## 8. Teleconsulta integrada 🟡

A maioria das jornadas de extensão de cuidado pós-alta esbarra no momento em que o paciente precisa, de fato, falar com um médico. As soluções disponíveis hoje no mercado brasileiro empurram o paciente para plataformas terceiras de telemedicina (Doctoralia, Conexa, etc) — o que cria três problemas:

1. **A continuidade do prontuário se quebra** (o que foi conversado na teleconsulta volta como PDF, sem estruturação).
2. **A relação do paciente com o hospital de origem se dilui** — ele consulta com "qualquer médico" da plataforma, não com a equipe que o conhece.
3. **O hospital perde o ponto de contato** — vira intermediário burocrático.

A ConnectaIACare está finalizando um **módulo de teleconsulta próprio**, integrado à Sofia e ao prontuário do parceiro, especificamente desenhado para extensão de cuidado pós-alta. O módulo segue os requisitos da Resolução CFM 2.314/2022 e correlatas.

### 8.1 Como funciona o fluxo

**Origem do agendamento.** A teleconsulta pode nascer de três caminhos:

- A Sofia identifica situação clínica que precisa de avaliação médica (exemplo: paciente pós-IAM com dispneia aos esforços no D+4) e propõe ao paciente.
- O paciente solicita ativamente via WhatsApp ou chat.
- O médico do parceiro agenda proativamente via painel ao revisar fila de Risk Score.

**Acesso pelo paciente — zero fricção.** O paciente recebe link único via WhatsApp. O link abre direto no navegador do celular — sem instalar app, sem cadastro, sem senha. A sala já está pré-configurada com o nome dele, vinculada automaticamente ao prontuário, registrando início.

**Médico do outro lado — contexto completo.** O médico entra com tela dividida: vídeo do paciente em uma metade, prontuário completo na outra (incluindo tudo que a Sofia conversou nos últimos 30 dias com o paciente, último Risk Score, motor clínico ativo nas medicações, alertas pendentes na fila de revisão). O médico não chega "frio" na consulta — chega com contexto de continuidade de cuidado que nenhuma plataforma terceira de telemedicina entrega.

**Transcrição e estruturação automática durante a consulta.** O áudio é transcrito em tempo real e a Sofia atua como secretária clínica em background: extrai queixas, sintomas, hipóteses diagnósticas mencionadas, condutas propostas. O médico não precisa parar para digitar — fala naturalmente, e ao final tem resumo estruturado pré-preenchido para revisar e aprovar.

### 8.2 A finalização

É aqui que o módulo se diferencia. A "finalização" tem cinco ações automáticas integradas:

1. **Prescrição digital com assinatura.** O médico revisa a prescrição que a Sofia montou a partir da conversa, ajusta, assina digitalmente. A receita vai para o paciente via WhatsApp como PDF + entrada estruturada no prontuário do parceiro. Conformidade com CFM e ANVISA.

2. **Atestado, declaração de comparecimento, encaminhamento** quando aplicável — emitidos no mesmo fluxo, assinados digitalmente, entregues por WhatsApp.

3. **Plano terapêutico atualizado** no prontuário: conduta proposta, próxima reavaliação, sinais de alerta para o paciente observar — vira programa de acompanhamento ativo da Sofia.

4. **Atualização automática do motor clínico.** Se o médico prescreveu nova medicação ou ajustou dose, **o motor de 12 dimensões automaticamente roda a nova prescrição contra o histórico do paciente** — flag de interações novas, pedido de confirmação se houver Beers AVOID, etc. A Sofia continua a partir dali com a prescrição atualizada.

5. **Audit completo** — gravação da consulta (áudio + vídeo, com retenção configurável conforme política do parceiro), transcrição estruturada, dados extraídos, prescrição emitida, todas em audit chain criptográfica. Auditável a qualquer momento, inclusive por auditoria do CFM.

### 8.3 Após a consulta

A Sofia retoma o relacionamento com o paciente já com o plano novo. Liga no horário programado para checar se ele entendeu a conduta, se está tomando a medicação nova certo, se precisa de algo. **A continuidade não se quebra — ela se intensifica após a consulta.**

---

## 9. Segurança e governança

### 9.1 Safety Guardrail Layer ✅

> Princípio: Sofia tem inteligência. Sofia NÃO tem autoridade.

Toda ação clínica que a Sofia produziria passa por router determinístico que decide entre cinco destinos:

| Tipo de ação | Comportamento |
|---|---|
| **Informativa** (responder dose máxima, explicar interação) | Executa direto + disclaimer auto-injetado |
| **Registrar histórico** (criar relato no prontuário, gravar queixa) | Salva no banco + notifica equipe se severidade ≥ atenção |
| **Convocar atendente humano** | Vai para fila de revisão da equipe clínica do parceiro |
| **Emergência real-time** (idoso fala "dor no peito agora") | Bypass — escala imediato + contato com 192 + notificação família em paralelo |
| **Modificar prescrição** | **BLOQUEADO** na configuração padrão (precisa médico responsável formal) |

**Circuit breaker automático.** Se mais de 5% das ações clínicas em 5 minutos caem na fila de revisão, a Sofia auto-pausa o tenant por 30 minutos e notifica o admin. Protege contra "Sofia desregulada" que estaria escalando demais (provável bug de prompt ou de regra).

### 9.2 Audit chain criptográfica LGPD ✅

Toda ação sensível registrada em chain de hash SHA-256:

- Acesso a dados clínicos
- Edição de regras do motor
- Promoção de versão de prompt
- Execução de ferramenta com Safety Guardrail
- Decisão clínica do médico durante teleconsulta

**Inviolável.** Cada hash inclui hash anterior — qualquer adulteração retroativa quebra a chain e o sistema sinaliza. Padrão equivalente a blockchain interna sem custo de descentralização.

**Compliance LGPD:**
- Privacy by design
- Minimização de dados (só o necessário)
- TCLE específico Art. 11 (saúde + biometria de voz)
- DPA com hospitais parceiros (controlador vs operador)
- Direitos do titular: exportação · exclusão a qualquer momento via solicitação à equipe

### 9.3 Fontes citadas no motor

Cada regra tem fonte e referência:

```
beers_2023        — American Geriatrics Society 2023 update
fda               — FDA labels (Box warnings, dose limits)
anvisa            — Bulário Eletrônico ANVISA
kdigo             — KDIGO Clinical Practice Guideline 2024
stockleys         — Stockley's Drug Interactions
lexicomp          — Lexicomp clinical references
stopp_start_v2    — STOPP/START Criteria v2 (Ireland)
rochon_bmj_2017   — Rochon RJ et al, BMJ 2017;359:j5251 (cascades)
manual            — curadoria interna documentada
```

Confidence score por regra (0 a 1). Audit chain criptográfica registra mudanças. Confidence < 0.7 = manual review obrigatório antes de promover para produção.

---

## 10. Posicionamento regulatório

### 10.1 LGPD

Operamos com privacy by design:

- Auditoria criptográfica imutável (audit chain SHA-256)
- Minimização de dados — armazenamos apenas o necessário
- Consentimento explícito — TCLE específico para processamento de dados de saúde (Art. 11), com opt-in e opt-out a qualquer momento
- Responsabilidade compartilhada — ConnectaIACare é controladora dos dados de operação; o parceiro é controlador dos dados clínicos do paciente. Acordos de processamento (DPA) são parte do contrato

Para B2B com hospital ou clínica, oferecemos acordo de operador conforme Art. 39 da LGPD.

### 10.2 ANVISA (RDC 657/2022 e correlatas)

A Sofia, em sua configuração atual, é **ferramenta de apoio à decisão clínica** — não dispositivo médico autônomo. Ela informa, recomenda, escala — não diagnostica nem prescreve.

Em escala (acima de 1.000 pacientes acompanhados), planejamos enquadramento formal como **SaMD Classe IIa** (Software como Dispositivo Médico) junto à ANVISA. Esse processo está sendo planejado com advogado especializado em saúde digital e farmacêutico responsável técnico.

Para pilotos com até 100 pacientes, operamos sob a categoria de "ferramenta de apoio operacional" — mesmo enquadramento de outras soluções de telemonitoramento que estão em produção em hospitais brasileiros.

### 10.3 CFM (Resolução 2.314/2022 e CFM 2.454/2026)

A Sofia respeita estritamente o princípio do **ato médico não-delegado**:

- Não comunica diagnóstico
- Não comunica prognóstico
- Não modifica prescrição autonomamente
- Toda decisão clínica passa por médico responsável designado pelo parceiro

A Resolução CFM 2.454/2026 (publicada 27/02/2026, vigência agosto/2026) detalha o uso de IA em apoio à prática médica. Estamos em conformidade preventiva: comitê de governança IA estabelecido, classificação de risco documentada, médico responsável designado.

---

## 11. Validação científica em curso

Reconhecemos publicamente que validação científica formal está apenas começando. Não fingimos ter robustez de soluções internacionais validadas em estudos de não-inferioridade vs enfermagem em larga escala. Nosso momento é construir essa base.

**Golden dataset interno:**
- 10 conversas-tipo por cenário de ligação (5 cenários ativos = 50 testes)
- Validação manual de saídas clínicas críticas
- Versionamento de prompts (draft → testing → published) com testes contra o golden dataset

**Parcerias acadêmicas em formação:**
- Universidades de Farmácia para revisão por pares
- Co-publicação de resultados após 100 ou mais pacientes acompanhados

**Métricas tracking:**
- Falsos positivos (Sofia escalou e era irrelevante)
- Falsos negativos críticos (paciente teve evento, Sofia não captou)
- Tempo até captura de sintoma novo
- NPS profissional (Sofia ajuda ou atrapalha?)
- Taxa de adesão a recomendações clínicas

---

## 12. Status de cada capacidade

Tabela completa do que está em produção, em finalização, em roadmap próximo, e em visão futura.

| Capacidade | Status |
|---|---|
| Chat texto · 16 tools clínicas | ✅ |
| Voz no browser (speech-to-speech) com interrupção em tempo real | ✅ |
| Ligação telefônica outbound (PJSIP + Grok Voice Realtime) | ✅ |
| WhatsApp Business: texto + áudio + mídia + botões interativos | ✅ |
| OCR clínico (receita, bula, exame, embalagem, atestado) | ✅ |
| Análise visual de lesão · ferida · edema · display de aparelho | ✅ |
| Biometria de voz — identificação do interlocutor | ✅ |
| Motor clínico 12 dimensões · 48 fármacos | ✅ |
| Cascatas de prescrição (dimensão 13) · 8 cascatas | ✅ |
| Memória 4 camadas + cross-canal + recall semântico | ✅ |
| Memória coletiva anonimizada cross-tenant | ✅ |
| Safety Guardrail Layer + circuit breaker | ✅ |
| Audit chain LGPD criptográfica (SHA-256) | ✅ |
| Risk Score por paciente (Fase 1 + Baseline Fase 2) | ✅ |
| Proactive Caller (Sofia decide quando ligar) | ✅ |
| Recall semântico cross-paciente anonimizado | ✅ |
| Versionamento de prompts dos cenários | ✅ |
| 5 cenários de ligação editáveis sem release | ✅ |
| Validação automática semanal do motor | ✅ |
| Teleconsulta integrada (módulo próprio) | 🟡 |
| Cobertura motor 48 → 80 fármacos | 🔵 |
| Cascatas adicionais (tiazídico→hiperuricemia, etc) | 🔵 |
| STOPP/START como camada complementar a Beers | 🔵 |
| Inbound calls (Sofia atende ligações que chegam) | 🔵 |
| WhatsApp Calling outbound (Meta API) | 🟣 |
| Biomarcadores vocais (jitter · shimmer · prosódia) | 🟣 |
| Detecção longitudinal de padrões cognitivos | 🟣 |
| Imagem multimodal avançada com follow-up temporal | 🟣 |
| Plano "Cuidado Sem Limites" B2C massivo | 🟣 |
| Federated learning entre tenants | 🟣 |
| ANVISA SaMD Classe IIa formalizado | 🟣 |
| Co-publicação científica (100+ pacientes) | 🟣 |

Nada inventado. Tudo o que está em ✅ pode ser testado hoje. 🟡 está na reta final. 🔵 estamos codificando ativamente. 🟣 é visão estratégica que depende de dados, validação científica ou pesquisa em andamento.

---

## 13. Roadmap clínico expandido

### 13.1 Próximas 8 a 12 semanas (🔵)

- Cobertura motor 48 → 80 princípios ativos. Curadoria depende de input clínico-farmacológico sênior.
- Cascatas adicionais: diurético tiazídico → hiperuricemia → alopurinol; beta-bloqueador → bradicardia; inibidor de colinesterase → bradicardia; opioide → constipação → laxante (separada da cascata anticolinérgica); antipsicótico → síndrome neuroléptica → bromocriptina (rara mas grave).
- STOPP/START como camada complementar a Beers — avaliar se traz valor adicional ou se Beers já cobre 80% do clinicamente relevante.
- Inbound calls: Sofia atende ligações que chegam, com roteador identificando caller_id (paciente conhecido → modo familiar; profissional cadastrado → modo clínico; desconhecido → comercial).
- LiveKit Cloud + SIP trunk redundante para resiliência da camada de voz em escala.

### 13.2 Três a seis meses (🟣)

- Biomarcadores vocais: análise quantitativa de jitter, shimmer, prosódia, fluência para detecção precoce de desidratação, descompensação cardíaca, depressão, declínio cognitivo. Geração de observação clínica (não diagnóstico).
- Detecção longitudinal de padrões cognitivos. Cada idoso tem padrão próprio de fala, silêncio, queixa. Comparação por desvio individual ao longo do tempo, não apenas pontual.
- Recall semântico cross-tenant com differential privacy formal (insights coletivos protegidos).
- WhatsApp Calling outbound nativo via Meta Business API.
- Imagem multimodal avançada: análise visual de lesão/ferida com follow-up temporal — comparar foto de hoje com foto de 3 dias atrás para evolução de cicatrização.

### 13.3 Seis a doze meses (🟣)

- Plano "Cuidado Sem Limites" B2C massivo: idosos que moram sozinhos, contratam direto via WhatsApp, sem clínica intermediária.
- Federated learning entre tenants — modelos compartilhando aprendizado sem compartilhar dados.
- ANVISA SaMD Classe IIa formalizado.
- Co-publicação científica formal de resultados após 100+ pacientes acompanhados.
- Comitê de governança IA estabelecido com geriatra externo + farmacêutico responsável técnico + advogado de saúde digital.

---

## 14. O que NÃO somos

Para calibrar expectativa honestamente:

| O que somos | O que NÃO somos |
|---|---|
| Sistema de apoio à decisão clínica | Substituto de avaliação clínica |
| Validador determinístico de regras conhecidas | Descobridor de novas regras farmacológicas |
| Plataforma de relacionamento longitudinal | Plataforma de prontuário único |
| Co-piloto de profissional | Médico/farmacêutico |
| Engenharia clínica em PT-BR nativo | Versão localizada de produto americano |

A Sofia não diagnostica, não prescreve, não decide. Ela informa, lembra, escala, escuta, gera observação clínica.

A diferença é importante. Não estamos resolvendo "fazer geriatria automaticamente". Estamos resolvendo "tornar o conhecimento geriátrico aplicável em escala em qualquer interação clínica".

---

## 15. Próximos passos

A leitura deste documento pode levar a três caminhos:

**Feedback pontual.** Qualquer profissional clínico-farmacológico interessado pode enviar comentários por email, audio ou texto sobre o que viu — observações sobre regras codificadas, cobertura de fármacos faltantes, calibração de severidade, cascatas adicionais a considerar.

**Discussão técnica aprofundada.** Reunião de 1 hora com demo ao vivo da Sofia, walkthrough do painel admin (regras clínicas, fila de revisão, versionamento de cenários), perguntas técnicas sobre arquitetura ou metodologia.

**Colaboração formal.** Para profissionais com interesse em participar de forma estruturada — consultoria honorária, participação no comitê de governança IA, papel de farmacêutico responsável técnico para registro ANVISA SaMD, co-autoria científica.

NDA padrão da plataforma é assinado antes do compartilhamento de documentação técnica detalhada (dicionário das 13 dimensões, dump de regras codificadas, acesso ao painel admin).

---

## 16. Material complementar disponível mediante NDA

- Documentação técnica do motor com as 13 dimensões detalhadas
- Lista completa dos 48 princípios ativos com regras codificadas em formato YAML
- Dump anonimizado da fila de revisão com exemplos reais de saídas clínicas
- Acesso ao painel admin de regras clínicas (`/admin/regras-clinicas`)
- Demo guiada de 20 minutos ao vivo da Sofia em ambiente controlado
- Documentação da arquitetura técnica completa da plataforma
- Roadmap detalhado por trimestre

---

## 17. Contato

Para discussões técnicas, parcerias clínicas, propostas de pilotos ou solicitação do material complementar:

**ConnectaIACare**
contato@connectaia.com.br

---

*Material preparado para revisão técnica clínico-farmacológica · ConnectaIACare © 2026.*
