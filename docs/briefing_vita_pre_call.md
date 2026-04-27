# ConnectaIACare — Briefing para o Grupo VITA

> Material preparatório para reunião com Direção Clínica e CEO
> Foco: extensão de cuidado pós-alta hospitalar + acompanhamento domiciliar contínuo
> Material confidencial · ConnectaIACare © 2026

---

## Sumário Executivo

A **ConnectaIACare** opera uma plataforma de **assistência inteligente conversacional** para pacientes em casa, integrável a qualquer prontuário hospitalar (MV, Tasy, Soul MV, Philips Tasy). O núcleo da plataforma é a **Sofia**, uma IA assistente que conversa com paciente, familiar e equipe clínica via **chat texto, voz no aplicativo e ligação telefônica** — mantendo continuidade de relacionamento com baixíssimo custo marginal.

Para o **Grupo VITA**, propomos uma solução de **extensão de cuidado pós-alta** que aborda diretamente o gargalo dos hospitais brasileiros: **15-20% de readmissão em 30 dias**, dos quais aproximadamente um terço evitáveis com vigilância adequada (reações adversas a medicamentos, falta de adesão, identificação tardia de descompensação).

A diferença para outras soluções de telemonitoramento é que a Sofia não é apenas reativa — ela atua **proativamente** todos os dias, com check-ins diários que captam sintomas precocemente, validam adesão a medicações com motor clínico determinístico de 12 dimensões (cobertura de Beers 2023, Child-Pugh, ajuste renal KDIGO, ACB Score, interações medicamentosas, contraindicações por condição), e escala para a equipe clínica humana apenas o que é realmente relevante.

**Em uma frase**: enquanto o paciente está em casa, a Sofia mantém ele clinicamente conectado ao hospital — sem exigir equipe humana 24/7 do hospital.

A proposta deste documento é fundamentar uma reunião com a direção clínica e CEO, na qual discutiremos um **piloto controlado de 60-90 dias com 30-50 pacientes pós-alta de alto risco**, com KPIs definidos em conjunto. O modelo comercial será desenhado em conjunto com o Grupo VITA conforme estrutura preferida (B2B SaaS por leito, B2B per-paciente acompanhado, ou híbrido).

---

## 1. O Problema Real do Hospital Brasileiro

### 1.1 Readmissão como métrica-chave

A readmissão hospitalar em 30 dias é um dos KPIs mais críticos de qualidade hospitalar e simultaneamente um dos mais difíceis de mover. Dados consolidados:

- **Brasil**: taxa média de readmissão em 30 dias varia entre **13% e 22%** dependendo do perfil hospitalar (IBGE/MS dados de 2018-2023)
- **Causas principais de readmissão evitável** (Joint Commission, ANS):
  - Reação adversa a medicamento ou interação medicamentosa não detectada (~25-30% das readmissões evitáveis)
  - Falta de adesão a tratamento prescrito (~20%)
  - Descompensação clínica não captada precocemente (~25%)
  - Confusão pós-alta sobre orientações médicas, esquema medicamentoso, sinais de alerta (~15%)
  - Infecção (~10%)

A literatura é consistente: **das readmissões evitáveis, a maioria poderia ser detectada por monitoramento ativo nos primeiros 7-14 dias pós-alta**.

### 1.2 Por que os hospitais não fazem isso hoje

Não é falta de vontade — é matemática. Vigilância ativa de paciente pós-alta exige:

- Equipe de enfermagem dedicada (custo ~R$ 8-12 mil/mês por enfermeira em horário comercial)
- Sistema de comunicação multicanal (telefone + WhatsApp + app)
- Capacidade de captar sinais clínicos via conversa e disparar protocolos
- Memória longitudinal por paciente (saber o que foi conversado ontem)

Para um hospital de porte médio com 200 altas/mês, vigilância ativa séria precisaria de 3-5 enfermeiras dedicadas. **Custo operacional R$ 30-60 mil/mês**. Para a maioria dos hospitais brasileiros, isso só fecha conta se traduzido em:

- Redução de 5-8% nas readmissões evitáveis
- Margem operacional capturada pelo hospital (e não pela operadora)

Esse cálculo de ROI raramente fecha sem uma camada de **automação inteligente** que reduza custo marginal por paciente acompanhado.

### 1.3 A oportunidade

O paciente típico pós-alta de hospital geral médio:
- 60-70% dos casos: idosos com 2+ comorbidades crônicas
- Recebe alta com 4-7 medicamentos prescritos
- Tem 15-25% de chance de retornar em 30 dias
- Quando retorna, custo médio R$ 8-15 mil por readmissão (variando por procedimento)

Se conseguíssemos reduzir essa readmissão em apenas 3 pontos percentuais com vigilância ativa de baixo custo (de 18% para 15%), o impacto financeiro líquido seria significativo — **mesmo descontando o custo da plataforma**.

---

## 2. O que é a Sofia, em termos clínicos

A Sofia é uma assistente conversacional baseada em **inteligência artificial supervisionada** que opera como camada de relacionamento com o paciente em casa. Ela tem três características que a diferenciam de soluções concorrentes:

### 2.1 Ela tem inteligência clínica determinística — não apenas LLM

Diferente de chatbots que dependem 100% da "intuição" do modelo de linguagem, a Sofia integra um **motor clínico determinístico** que valida toda saída clínica em 12 dimensões antes de qualquer ação:

1. **Dose máxima diária** (parametrizada por princípio ativo, fonte ANVISA + FDA)
2. **Critérios de Beers 2023** (AVOID e Caution para geriatria)
3. **Alergias e reações cruzadas** (penicilina ↔ todos β-lactâmicos, sulfa, etc.)
4. **Duplicidade terapêutica** (mesma classe, mesmo princípio)
5. **Polifarmácia** (carga total ponderada por classe)
6. **Interações medicamento-medicamento** — incluindo interações que podem ser mitigadas espaçando horários (ex: levotiroxina + carbonato de cálcio → 4h de intervalo, em vez de evitar)
7. **Contraindicações por condição clínica** (ex: Parkinson + risperidona; demência + antipsicótico atípico; QT longo + azitromicina)
8. **ACB Score** (Anticholinergic Cognitive Burden cumulativo, soma de toda carga anticolinérgica)
9. **Risco de queda por classe terapêutica** (benzodiazepínico = score 2, BCCa di-hidropiridínico = 1, etc.)
10. **Ajuste renal** (Cockcroft-Gault aplicado a 11 faixas de ClCr, regras KDIGO)
11. **Ajuste hepático Child-Pugh A/B/C** (com aliases reconhecidos: "cirrose com ascite" → child_b)
12. **Constraints de sinais vitais** (ex: PA <110 + BCCa di-hidropiridínico → warning de hipotensão)

Aproximadamente **48 princípios ativos** estão hoje codificados no motor — cobrindo a maioria dos fármacos prevalentes em geriatria brasileira:

- Anti-hipertensivos (losartana, enalapril, anlodipino, propranolol não-seletivo, atenolol/metoprolol/carvedilol cardiosseletivos)
- Antidiabéticos (metformina, glibenclamida, gliclazida, empagliflozina, dapagliflozina)
- Antiplaquetários e anticoagulantes (AAS, clopidogrel, varfarina, rivaroxabana, apixabana, dabigatrana)
- Estatinas (sinvastatina, atorvastatina, rosuvastatina)
- IBPs (omeprazol, pantoprazol, esomeprazol)
- Antidepressivos (sertralina, fluoxetina, escitalopram, mirtazapina)
- Hipnóticos/ansiolíticos (clonazepam, diazepam, alprazolam, zolpidem)
- Antipsicóticos (haloperidol, risperidona, quetiapina, olanzapina — todos com Beers AVOID em demência)
- Antiparkinsonianos (levodopa+carbidopa, pramipexol, ropinirol)
- Antieméticos (metoclopramida — Beers AVOID por discinesia tardia, ondansetrona)
- Antibióticos (amoxicilina, amoxicilina+clavulanato, azitromicina, ciprofloxacino, sulfa+trimetoprima)
- Outros (paracetamol, dipirona, AINEs, alendronato, levotiroxina, carbonato de cálcio)

Cada um desses fármacos tem regras codificadas para todas as 12 dimensões aplicáveis. Por exemplo, **olanzapina** carrega:

- Dose máxima 20 mg/dia
- Beers AVOID em demência (Box warning FDA — aumenta mortalidade e AVC)
- ACB Score 3 (anticolinérgico forte → constipação, retenção urinária, confusão)
- Fall Risk Score 2 (sedação + hipotensão postural + sintomas extrapiramidais)
- Contraindicação em Parkinson (antagonismo D2)
- Ajuste hepático: Child A monitorar, Child B reduzir 50%, Child C evitar
- Interações documentadas com clonazepam (sedação aditiva), levodopa (antagonismo)

Quando médico ou enfermagem pergunta à Sofia "é seguro 0,5 mg de risperidona 12/12h para Dona Helena, 87 anos, com demência leve?", em ~200 ms o motor retorna análise estruturada de risco — sem depender da "memória" do modelo de IA. **Isso é determinístico, auditável e versionado**.

### 2.2 Ela tem memória longitudinal por paciente — não esquece

A Sofia mantém **quatro camadas de memória** que juntas dão continuidade real ao relacionamento clínico:

**Memória da conversa atual** — últimas 30 mensagens da sessão. Padrão de qualquer sistema conversacional.

**Memória cross-canal** (45 minutos) — se o cuidador conversa via chat às 8h e o idoso liga via voz às 8h30, a Sofia da ligação **sabe** o que foi conversado no chat. Continuidade entre canais sem o paciente precisar repetir.

**Memória de longo prazo do usuário** — cada usuário (médico, cuidador, familiar, paciente) tem perfil persistente: resumo narrativo + fatos estruturados (preferências, contexto profissional, tópicos em curso, preocupações). Re-extraído automaticamente a cada 20 mensagens. Quando o mesmo usuário volta dias depois, a Sofia já vem contextualizada.

**Recall semântico** — toda mensagem é vetorizada (embeddings 768 dimensões via Gemini Embedding) e indexada com algoritmo HNSW para busca por similaridade. Quando médico pergunta "lembra que comentei sobre dor lombar do Sr Antônio em fevereiro?", a Sofia faz busca semântica e traz as mensagens **exatas** dos últimos 90 dias. Não é resumo — é recall verbatim, com timestamp e canal de origem (chat ou ligação).

Para pós-alta hospitalar, isso significa: **a Sofia consegue identificar deterioração** ao comparar como o paciente fala hoje com como falava há 7 dias.

### 2.3 Ela não tem autoridade — só inteligência

Esse é o ponto mais sensível em healthcare e onde a maior parte das soluções concorrentes erram. A Sofia opera com **inteligência mas sem autoridade clínica**:

| Sofia FAZ | Sofia NÃO FAZ |
|---|---|
| Detecta padrão de queda recorrente, classifica severidade | Decide tratamento sem médico |
| Roda motor de cruzamento com 12 dimensões | Prescreve ou modifica prescrição |
| Mantém memória longitudinal | Diagnostica |
| Propõe escalações ao humano | Substitui consulta médica |
| Acompanha adesão a medicação | Atua sozinha em emergência |

Toda saída clínica da Sofia é acompanhada de **disclaimer natural** ("isso é informação para apoiar sua decisão — quem decide é sempre você com o médico responsável"). Ela é treinada para variar a forma do disclaimer — não soa robótico, soa conversacional.

Há uma camada de software chamada **Safety Guardrail Layer** que intercepta toda ação clínica antes de chegar ao banco de dados ou disparar uma ligação. Esse router determinístico decide para onde a ação vai:

| Tipo de ação | Comportamento |
|---|---|
| **Informativa** (responder dose máxima, explicar interação) | Executa direto + disclaimer |
| **Registrar histórico** (criar relato no prontuário, gravar queixa) | Salva no banco + notifica equipe se severidade ≥ atenção |
| **Convocar atendente humano** | Vai para fila de revisão da equipe clínica do hospital |
| **Emergência real-time** (idoso fala "dor no peito agora") | Bypass — escala imediato + contato com 192 + notificação família em paralelo |
| **Modificar prescrição** | **BLOQUEADO** no piloto (precisa médico responsável formal) |

Há também um **circuit breaker** automático: se mais de 5% das ações clínicas em 5 minutos caem na fila de revisão, a Sofia se auto-pausa por 30 minutos e notifica o admin. Protege contra "Sofia desregulada" que estaria escalando demais (provável bug de prompt ou de regra).

Toda ação fica registrada em uma **audit chain criptográfica** (hash chain SHA-256) que detecta qualquer adulteração retroativa. **LGPD-compliant by design**.

---

## 3. Como Funcionaria no Grupo VITA

### 3.1 Caso de uso 1 — Pós-alta de paciente cardíaco

**Perfil**: Sr. José, 72 anos, alta após IAM com supra-ST. Sai com tripla terapia (AAS + clopidogrel + rosuvastatina), enalapril, carvedilol, omeprazol gastroprotetor. Teve 2 dias de internação em UTI, transferido para UI por mais 3 dias.

**Risco de readmissão**: ~22-28% em 30 dias para esse perfil (literatura Brasil/AHA).

**Como a Sofia atua**:

**Dia 0 (alta)**: Equipe do hospital cadastra o paciente na plataforma com prescrição completa, contato (Sr José + filha responsável). Sofia automaticamente roda motor de 12 dimensões e identifica:
- AAS + clopidogrel + omeprazol → válido (proteção GI necessária com dupla terapia)
- Carvedilol + enalapril → válido (sinérgico, padrão CV)
- Risco de queda agregado: score 2 (carvedilol + enalapril com hipotensão potencial)

**Dia 1 (manhã)**: Sofia liga 8h30 para Sr José. "Bom dia Sr. José, é a Sofia da ConnectaIACare, falando do hospital VITA onde o senhor saiu ontem. Como passou a noite?". Conversa 4 minutos. Captura: "tomei tudo certo, mas senti um pouco de tontura ao levantar". 

Sofia identifica: tontura ao levantar + carvedilol + enalapril = padrão de hipotensão postural conhecido. Em vez de criar pânico, registra como **atenção** no prontuário, orienta o Sr José a se levantar mais devagar, e cria item na fila de revisão da equipe clínica do hospital VITA. Equipe vê e decide se vale ajustar dose ou apenas monitorar.

**Dia 2-7**: Sofia liga manhã e noite. Acompanha adesão (paciente confirma que tomou cada medicação). Captura sintomas leves. No dia 4, captura "to com falta de ar quando subo escada". Sofia identifica: dispneia aos esforços + pós-IAM + 4 dias = possível descompensação cardíaca. Severidade urgente. **Escala imediato** para equipe clínica do hospital com sumário do que foi conversado nos últimos 7 dias. Equipe agenda teleconsulta em 2h.

Sem a Sofia, esse Sr José provavelmente chegaria ao pronto-atendimento em 48h com edema pulmonar agudo. Com a Sofia, equipe ajustou medicação preventivamente em casa.

**Dia 7-30**: Sofia continua check-ins, mas espaçando para 1× por dia. Adesão continua sendo monitorada. Risco de queda continua sob vigilância.

**Resultado esperado**: redução de ~5-10 pontos percentuais no risco de readmissão para esse perfil específico.

### 3.2 Caso de uso 2 — Paciente com DPOC após exacerbação

**Perfil**: Sra. Maria, 68 anos, alta após internação por exacerbação aguda de DPOC GOLD III. Recebe alta com formoterol + budesonida (LABA+ICS), tiotrópio (LAMA), prednisolona em dose decrescente por 7 dias, azitromicina por 5 dias.

**Risco**: 30-40% de readmissão em 30 dias para DPOC GOLD III pós-exacerbação.

**Como a Sofia atua**:

**Motor flagga imediatamente**:
- Azitromicina + paciente com QT longo conhecido → severity warning (Sofia pergunta na primeira ligação se Maria já fez ECG recente)
- Prednisolona + outras prescrições crônicas → cuidado com hiperglicemia (Maria é diabética?)

**Dia 1-5**: Sofia liga manhã. Pergunta:
- Como dormiu? (DPOC: ortopneia é sinal precoce)
- Tossiu mais que ontem?
- Está usando o broncodilatador certo? (Sofia tem foto da técnica inalatória correta — pode pedir vídeo se Maria tiver dúvida)
- Cansou subindo escada? Lavando louça? (escala MRC)

**Dia 3**: Maria fala "to com mais catarro e ele tá amarelo". Sofia identifica: mudança de cor de catarro em DPOC = critério de Anthonisen para nova exacerbação. Severidade urgente. Escala para equipe clínica VITA com sumário. Equipe decide se reforça antibiótico, se chama para reavaliação, ou se mantém observação.

Sem a Sofia, Maria provavelmente esperaria piorar mais por 2-3 dias antes de procurar PA — chegando com pneumonia franca.

### 3.3 Caso de uso 3 — Idoso pós-cirurgia ortopédica em casa

**Perfil**: Sr. Antônio, 81 anos, alta 5 dias após artroplastia de quadril por fratura. Recebe alta com enoxaparina por 14 dias, paracetamol + tramadol para dor, cefalexina 7 dias profilática, omeprazol gastroprotetor.

**Risco**: TVP/TEP, infecção do sítio cirúrgico, queda nova, delirium pós-operatório, declínio funcional.

**Como a Sofia atua**:

**Motor identifica**:
- Tramadol em idoso → ACB Score +1, Fall Risk Score +1 (Sofia avisa equipe que vale considerar troca para morfina baixa dose se dor descontrolada)
- Tramadol + omeprazol → potencializa risco de hiponatremia em idoso (atenção)

**Dia 1-14**: Sofia liga 2× ao dia. Acompanha:
- Adesão à enoxaparina (crítico — falha = TVP/TEP)
- Sinais locais de infecção (vermelhidão, calor, pus, febre)
- Mobilidade (caminhou hoje quanto?)
- Dor (escala 0-10 + adesão paracetamol/tramadol)
- Cognição (Sofia nota se Sr. Antônio está se repetindo na conversa, falando confuso, perdendo coerência → possível delirium)

**Dia 6**: Sofia detecta no padrão de fala que Sr. Antônio está mais lento e confuso comparado aos primeiros dias. Severidade atenção. Escala para equipe clínica que liga para Sra. Filha (responsável) confirmando o sinal. Equipe pode antecipar avaliação geriátrica.

**Dia 10**: Sr. Antônio conta que "não consegui levantar pra tomar café porque a perna doeu muito". Sofia identifica: mudança no padrão de mobilidade após 10 dias = sinal de complicação pós-cirúrgica. Escala.

---

## 4. Integração com Sistemas Hospitalares

A maioria dos hospitais brasileiros de médio/grande porte usa um dos seguintes prontuários: **MV, Tasy (Philips), Soul MV, ou prontuários proprietários**. Todos eles oferecem APIs de integração via **HL7 FHIR R4** (padrão internacional para interoperabilidade em saúde).

A integração da Sofia com o prontuário do Grupo VITA seguiria três caminhos:

### 4.1 Recebimento de paciente pós-alta (FHIR Patient + MedicationRequest + Condition)

No momento da alta hospitalar, o sistema VITA dispara uma chamada para a Sofia contendo:
- **Patient resource**: dados demográficos, contatos, condições
- **Encounter resource**: tipo de internação, data alta, motivo
- **MedicationRequest resources**: prescrição completa (princípio ativo, dose, posologia, duração)
- **Condition resources**: diagnósticos (CID-10) ativos
- **AllergyIntolerance resources**: alergias documentadas
- **Observation resources**: últimos sinais vitais, exames laboratoriais relevantes

Sofia automaticamente roda motor de 12 dimensões na prescrição recebida e identifica imediatamente possíveis problemas (interações, doses fora do limite, contraindicações pela condição). Esses achados ficam disponíveis para a equipe clínica antes mesmo do paciente sair do hospital.

### 4.2 Devolução de informações ao prontuário (FHIR Observation + Communication)

A cada interação relevante (queixa registrada, escalação clínica, alerta gerado), a Sofia envia para o prontuário do Grupo VITA:
- **Observation resource**: sintoma reportado, severidade, timestamp
- **Communication resource**: transcrição da conversa relevante
- **CarePlan updates**: marcos do acompanhamento (paciente confirmou medicação, paciente reportou sintoma, alerta escalado)

Equipe clínica VITA vê tudo no prontuário do paciente como um item de timeline pós-alta. **Não precisa abrir outro sistema**.

### 4.3 Alertas e teleconsulta (HL7 Messaging + integração agendamento)

Quando Sofia identifica situação que requer ação clínica humana, ela:
1. Escala via API para o sistema de agenda do Grupo VITA
2. Cria solicitação de teleconsulta com o sumário clínico
3. Notifica equipe via canal acordado (email, push, WhatsApp Business, integração com Slack/Teams se houver)
4. Mantém paciente engajado enquanto a equipe não responde (Sofia: "vou avisar a equipe do VITA, eles vão te dar retorno em breve")

### 4.4 Onde mora a Sofia

A plataforma roda em **arquitetura cloud-native** (Docker, PostgreSQL com pgvector, Redis), pode ser hospedada:
- **Cloud da ConnectaIACare** (modelo SaaS típico, dados em servidores brasileiros conformes LGPD)
- **Cloud privada do Grupo VITA** (se houver requisito de soberania de dados)
- **On-premise** no datacenter do Grupo VITA (se houver requisito operacional)

Cada uma dessas opções tem trade-offs de complexidade e custo, podemos discutir na reunião.

---

## 5. Posicionamento Regulatório e Compliance

### 5.1 LGPD (Lei nº 13.709/2018)

ConnectaIACare opera com **privacy by design**:

- **Auditoria criptográfica imutável**: toda ação sensível (acesso, edição, escalação) é registrada em uma chain de hash SHA-256. Qualquer adulteração retroativa é detectável computacionalmente.
- **Minimização de dados**: armazenamos apenas o necessário para o serviço. Dados crus de mensagem não saem da tabela original.
- **Consentimento explícito**: TCLE específico para processamento de dados de saúde (Art. 11), com opt-in e opt-out a qualquer momento.
- **Responsabilidade compartilhada**: ConnectaIACare é controladora dos dados de operação; Grupo VITA é controlador dos dados clínicos do paciente. Acordos de processamento (DPA) são parte do contrato.
- **Direitos do titular**: paciente pode solicitar exportação ou exclusão de dados a qualquer momento via solicitação à equipe.

Para B2B com hospital, oferecemos acordo de operador conforme Art. 39 — Grupo VITA como controlador, ConnectaIACare como operadora.

### 5.2 ANVISA (RDC 657/2022 e correlatas)

A Sofia, em sua configuração atual, é uma **ferramenta de apoio à decisão clínica** — não um dispositivo médico autônomo. Ela informa, recomenda, escala — não diagnostica nem prescreve.

Em escala (acima de 1.000 pacientes acompanhados), planejamos enquadramento formal como **SaMD Classe IIa** (Software como Dispositivo Médico) junto à ANVISA. Esse processo está sendo planejado com advogado especializado em saúde digital e farmacêutico responsável (Henrique Bordin, biomédico + farmacêutico em formação, integrante do time clínico).

Para o piloto com Grupo VITA (até 100 pacientes), operamos sob a categoria de "ferramenta de apoio operacional" — mesmo enquadramento de outras soluções de telemonitoramento que estão em produção em hospitais brasileiros.

### 5.3 CFM (Resolução 2.314/2022 e correlatas)

A Sofia respeita estritamente o princípio do **ato médico não-delegado**:
- Não comunica diagnóstico
- Não comunica prognóstico
- Não modifica prescrição autonomamente
- Toda decisão clínica passa por **médico responsável** designado pelo Grupo VITA

A nova **Resolução CFM 2.454/2026** (publicada 27/02/2026, vigência agosto/2026) detalha o uso de IA em apoio à prática médica. ConnectaIACare está em conformidade preventiva: comitê de governança IA estabelecido, classificação de risco documentada, médico responsável designado.

---

## 6. O Time Clínico-Tecnológico

### Alexandre Veras (CEO + Lead de Engenharia)
Mais de 20 anos de experiência em arquitetura de plataformas SaaS escaláveis. Construiu a ConnectaIA, plataforma de automação comercial com IA em produção operando milhões de interações/mês. Lidera o desenvolvimento técnico da Sofia desde 2025.

### Henrique Bordin (Líder Clínico-Farmacológico)
Formado em Biomedicina, formando em Farmácia em 2026. Responsável pela validação clínica do motor de cruzamentos, expansão da cobertura farmacológica (meta de 80+ princípios ativos cobrindo 95% da prescrição geriátrica brasileira), revisão de cenários de ligação, e enquadramento regulatório (CFM + ANVISA).

### Camada de IA
A Sofia opera sobre **xAI Grok Voice Realtime** (modelo speech-to-speech state-of-the-art para latência <500ms) para voz, e **Google Gemini Flash** para reasoning e extração de memória. Embeddings semânticos via Gemini Embedding (768 dimensões com Matryoshka truncation). Dose validator e regras clínicas são código nativo Python — não dependem de LLM.

### Infraestrutura
Plataforma rodando em produção desde início de 2026, com:
- Audit chain criptográfico LGPD-compliant
- Memória cross-session por paciente
- Recall semântico via pgvector (HNSW index)
- Safety Guardrail Layer com circuit breaker automático
- 4 schedulers em background (revalidação semanal, memória coletiva, queue executor, embedding worker)
- Versionamento de prompts dos cenários de ligação (draft → published)

---

## 7. O Que Já Está em Produção — Hoje

Para evitar promessas vazias, listamos abaixo o que está rodando em ambiente de homologação no momento da escrita deste briefing:

| Capacidade | Status | Validado em |
|---|---|---|
| **Chat texto** (web + mobile) com 16 ferramentas clínicas | Em produção | Sim, com pilotos internos |
| **Voz no browser** com Grok Realtime | Em produção | Sim, latência média 500-800ms |
| **Ligação telefônica** outbound (PJSIP + LiveKit) | Em produção | Sim, com 5 cenários ativos |
| **Motor clínico 12 dimensões** | Em produção | Sim, 48 princípios ativos |
| **Memória 4 camadas** | Em produção | Sim, cross-canal validado |
| **Safety Guardrail Layer** | Em produção | Sim, com circuit breaker funcional |
| **Risk Scoring por paciente** | Em produção | Sim, 45 pacientes scored automaticamente |
| **Memória coletiva anonimizada cross-tenant** | Em produção | Sim, pipeline diário |
| **Audit chain LGPD criptográfico** | Em produção | Sim, hash SHA-256 inviolável |
| **5 cenários de ligação editáveis sem release** | Em produção | Sim, admin edita em DRAFT, publica |

**Próximos 60 dias**:
- Integração FHIR R4 com prontuário eleito pelo Grupo VITA
- Cron worker proativo (Sofia decide proativamente quando ligar)
- UI admin para fila de revisão clínica
- Inbound calls (Sofia atende, com roteador de cenário por caller_id)
- Frontend de Risk Scoring com breakdown explicativo

---

## 8. Modelo de Piloto Sugerido

Para validar a fit entre a Sofia e o Grupo VITA antes de comprometer com licenciamento, propomos:

### Piloto Controlado — 60 a 90 dias

**Escopo**:
- 30 a 50 pacientes pós-alta de alto risco (a definir conjuntamente: pós-IAM, DPOC pós-exacerbação, pós-cirurgia ortopédica geriátrica, ou outro perfil que o Grupo VITA priorizar)
- Acompanhamento via Sofia por 30 dias após alta
- Equipe clínica VITA mantém visibilidade total via prontuário
- Família/cuidador integrados via aplicativo

**KPIs definidos em conjunto**:
- Taxa de readmissão em 30 dias do grupo Sofia vs grupo controle (mesmo perfil, sem Sofia)
- Tempo médio para captura de sintoma novo
- Adesão a medicação confirmada (% confirmadas vs planejadas)
- NPS do paciente e do familiar
- NPS da equipe clínica (Sofia ajuda ou atrapalha o trabalho?)
- Falsos positivos (Sofia escalou e era irrelevante)
- Falsos negativos críticos (paciente teve evento e Sofia não captou)

**Modelo comercial do piloto**: a discutir com o Grupo VITA. Estamos abertos a:
- Piloto sem custo, com SLA de qualidade definido
- Piloto com custo simbólico de implantação
- Outros formatos que façam sentido para a operação do Grupo VITA

**Após o piloto**: ConnectaIACare e Grupo VITA decidem juntos sobre:
- Expansão para todos os pacientes pós-alta de alto risco
- Modelo comercial em produção (B2B SaaS por leito? per-paciente acompanhado? por especialidade?)
- Roadmap de novas integrações e features priorizadas pelo Grupo VITA
- Possibilidade de co-publicação científica dos resultados

---

## 9. Por Que ConnectaIACare e Não os Outros

Existem várias soluções de telemonitoramento no mercado brasileiro. Listamos abaixo as principais e o diferencial da Sofia:

### Soluções de telemedicina pura (Doctoralia, Conexa, Memed)
Conectam paciente ao médico humano por consulta. Não cobrem o relacionamento contínuo entre consultas. **A Sofia não substitui essas soluções — complementa**.

### Soluções de monitoramento via wearables (Fitbit Health, Apple HealthKit clínico)
Capturam sinais vitais e atividade. Não conversam com o paciente, não captam queixas, não acompanham adesão. **A Sofia integra com esses dados quando disponíveis, mas adiciona a camada conversacional**.

### Chatbots genéricos (qualquer IA conversacional sem motor clínico)
Conversam, mas não validam clinicamente. Risco real de oferecer resposta errada ou perigosa. **A Sofia tem motor determinístico de 12 dimensões antes de qualquer resposta clínica chegar ao paciente**.

### Soluções internacionais (Hippocratic AI, Sensi.ai)
Validadas em estudos de não-inferioridade vs enfermagem em larga escala. Excelentes, mas: não falam português brasileiro nativamente, não integram com prontuários BR, não têm o motor clínico calibrado para fármacos brasileiros, custo elevado. **A Sofia é a versão brasileira nativa dessa categoria**.

### Diferenciais exclusivos da Sofia
1. **Motor clínico determinístico em português brasileiro** com cobertura calibrada para prescrição geriátrica do SUS e da saúde suplementar brasileira
2. **Multi-canal nativo** (chat + voz + ligação) com memória compartilhada
3. **Posicionamento regulatório claro** (suporte, não decisão; CFM + ANVISA roadmap definido)
4. **Preço operacional competitivo** (Grok Voice Realtime + LiveKit cloud + infra própria)

---

## 10. O Que Precisamos do Grupo VITA na Reunião

Para que a reunião seja produtiva, sugerimos a seguinte agenda:

1. **Apresentação do problema do Grupo VITA** (15 min)
   - Volume de altas mensais e perfil
   - Taxa de readmissão atual
   - Tentativas anteriores de extensão de cuidado e o que aprenderam

2. **Demonstração da Sofia ao vivo** (15 min)
   - Conversa real com a Sofia em modo "paciente pós-alta"
   - Mostrar motor clínico em ação
   - Mostrar memória longitudinal
   - Mostrar fila de revisão para equipe clínica

3. **Discussão de fit** (15 min)
   - Como a Sofia se encaixaria no fluxo de alta atual do Grupo VITA
   - Quais perfis de paciente teriam mais ganho
   - Integração com prontuário (qual sistema usam? FHIR disponível?)
   - Modelo comercial preferido pelo Grupo VITA

4. **Próximos passos** (10 min)
   - Definir piloto (escopo, perfil de paciente, duração, KPIs)
   - Cronograma de implementação
   - Identificar champion clínico no Grupo VITA

---

## 11. Anexo — Perguntas Frequentes da Equipe Clínica

### Sobre validação do motor clínico

**P: Quem validou as 12 dimensões e os 48 princípios ativos?**
R: As regras foram codificadas a partir de fontes oficiais (Critérios de Beers 2023 publicados pela American Geriatrics Society, KDIGO Guidelines, FDA labels, ANVISA Bulário Eletrônico). A validação clínica final está sob responsabilidade do líder clínico-farmacológico do time (Henrique Bordin) e está sendo expandida em parceria com universidades de farmácia para revisão por pares.

**P: O motor cobre toda a prescrição que sai do hospital?**
R: Hoje cobre ~48 princípios ativos, que correspondem a aproximadamente 70-80% da prescrição em geriatria brasileira. Para casos não cobertos, a Sofia explicitamente sinaliza "não tenho regra codificada para esse fármaco — sugiro consultar bibliografia" e não tenta improvisar.

**P: O que acontece quando o paciente toma uma medicação não cadastrada?**
R: A Sofia registra no prontuário, mas não roda validação. A equipe clínica é notificada de que há um fármaco fora da cobertura. Esse é um sinal para priorização de expansão do motor.

### Sobre falsos positivos e fadiga de alerta

**P: A Sofia vai gerar muitos alertas falsos e cansar nossa equipe?**
R: Esse é o maior risco que reconhecemos publicamente. Nossa estratégia para mitigar:
1. **Severidade hierárquica** com 4 níveis (info / atenção / urgente / crítico). Apenas urgente e crítico geram notificação imediata para equipe; info e atenção ficam no prontuário.
2. **Circuit breaker automático** — se mais de 5% das ações em 5 minutos caem na fila, a Sofia se auto-pausa e admin é notificado (provável bug ou regra mal calibrada).
3. **Versionamento de prompts** — toda mudança em comportamento da Sofia passa por golden dataset (10 conversas-tipo por cenário) antes de ir pra produção.
4. **Métrica explícita** — "% de alertas que equipe clínica considerou válidos" é parte do SLA.

### Sobre qualidade da voz

**P: A voz da Sofia é confiável? Idoso vai entender?**
R: Recomendamos demonstração ao vivo na reunião. A Sofia opera com xAI Grok Voice Realtime, modelo speech-to-speech state-of-the-art (latência 500-800ms, voz natural em português brasileiro). Em testes com pacientes idosos do piloto interno, a compreensão foi alta. Detalhes técnicos da arquitetura disponíveis sob NDA.

### Sobre escalonamento humano

**P: Quem responde quando a Sofia escala?**
R: Modelo é flexível. No piloto, sugerimos:
- **Hipótese A**: equipe clínica do Grupo VITA responde (enfermagem/médico de plantão da extensão hospitalar)
- **Hipótese B**: ConnectaIACare provê camada de atendimento humano 24/7 (atendentes treinados que recebem o contexto e decidem se contatam família, equipe VITA, ou aciona 192)
- **Hipótese C**: híbrido — VITA responde em horário comercial, ConnectaIACare cobre madrugada/finais de semana

A escolha depende da capacidade operacional preferida pelo Grupo VITA.

### Sobre integração com prontuário

**P: Vocês conseguem integrar com nosso sistema atual?**
R: Sim, via HL7 FHIR R4 (padrão internacional). A integração é desenhada conjuntamente, e o tempo típico de implantação é 4-8 semanas para o primeiro fluxo (recebimento de paciente pós-alta). Outros fluxos podem ser priorizados conforme valor para o Grupo VITA.

---

## 12. Próximo Passo

Após esta leitura, sugerimos:

1. **Equipe clínica do Grupo VITA** marca dúvidas e identifica o perfil de paciente que faria mais sentido para piloto
2. **CEO + Direção Clínica** alinham agenda interna e define disponibilidade para call de 60 minutos
3. **ConnectaIACare** prepara demonstração customizada com o perfil de paciente sugerido pelo Grupo VITA

**Contato para coordenação**:
Alexandre Veras
CEO, ConnectaIACare
alexandre@connectaia.com.br

---

*Este documento é confidencial e foi preparado especificamente para o Grupo VITA. Reprodução ou distribuição sem autorização não é permitida. ConnectaIACare © 2026.*
