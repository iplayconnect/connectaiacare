# Manual do Gestor — ConnectaIACare

**Versão:** 1.0
**Data:** 2026-05-18
**Para quem:** Gestores de clínica, ILPI (Instituição de Longa Permanência para Idosos), home care, cooperativas de cuidadores e operadoras de saúde.

---

## Índice

1. [Bem-vindo, Gestor](#1-bem-vindo-gestor)
2. [O que muda com a ConnectaIACare na sua operação](#2-o-que-muda-com-a-connectaiacare-na-sua-operação)
3. [Onboarding do seu tenant (primeiros 7 dias)](#3-onboarding-do-seu-tenant-primeiros-7-dias)
4. [Cadastrar a equipe (cuidadores, enfermeiros, médicos, familiares)](#4-cadastrar-a-equipe-cuidadores-enfermeiros-médicos-familiares)
5. [Configurar a Sofia (tom, escopo, autonomia)](#5-configurar-a-sofia-tom-escopo-autonomia)
6. [Importar e cadastrar pacientes em escala](#6-importar-e-cadastrar-pacientes-em-escala)
7. [Escala de cuidadores e vínculos paciente↔cuidador](#7-escala-de-cuidadores-e-vínculos-pacientecuidador)
8. [Plantão (P1/P2/P3) — quem fica de prontidão](#8-plantão-p1p2p3--quem-fica-de-prontidão)
9. [Dashboards e KPIs que você vai olhar todo dia](#9-dashboards-e-kpis-que-você-vai-olhar-todo-dia)
10. [Saúde do Plantão — diagnóstico em uma tela](#10-saúde-do-plantão--diagnóstico-em-uma-tela)
11. [Métricas de SLA — o que prometemos e como medimos](#11-métricas-de-sla--o-que-prometemos-e-como-medimos)
12. [Audit log, LGPD e prestação de contas](#12-audit-log-lgpd-e-prestação-de-contas)
13. [Faturamento, créditos e consumo de IA](#13-faturamento-créditos-e-consumo-de-ia)
14. [Governança da Sofia — Conselho Científico](#14-governança-da-sofia--conselho-científico)
15. [Quando algo dá errado — playbook do gestor](#15-quando-algo-dá-errado--playbook-do-gestor)
16. [Integrações (FHIR, Tecnosenior, CareNote, MedMonitor)](#16-integrações-fhir-tecnosenior-carenote-medmonitor)
17. [FAQ do Gestor](#17-faq-do-gestor)
18. [Checklist mensal](#18-checklist-mensal)
19. [Contatos e suporte](#19-contatos-e-suporte)

---

## 1. Bem-vindo, Gestor

Você é a pessoa responsável por garantir que a ConnectaIACare entregue valor real para os idosos, famílias e equipe da sua operação. Este manual foi escrito **para você** — para que tenha autonomia para configurar, monitorar e prestar contas sem depender de chamado técnico para coisa simples.

A ConnectaIACare é uma plataforma de **acompanhamento contínuo de idosos** que combina:

- **Sofia** — agente de IA conversacional (WhatsApp + voz) que conversa com idosos, cuidadores e familiares
- **Triagem clínica** com pré-check de sintomas agudos
- **Validação farmacológica** automática (interações, contraindicações)
- **Plantão multi-camada** (técnico → clínico → médico → SAMU)
- **Prontuário 360°** de cada paciente
- **Dashboards** em tempo real do seu tenant

O que a ConnectaIACare **não é**:

- Não é prontuário eletrônico médico de hospital (não substitui PEP)
- Não é call center humano sozinho (Sofia faz a triagem, humano valida)
- Não é dispositivo médico aprovado pela ANVISA (é plataforma de software de apoio)
- Não toma decisão clínica autônoma — sempre tem humano no loop em P1/P2

---

## 2. O que muda com a ConnectaIACare na sua operação

### Antes da ConnectaIACare (cenário típico)

- Cuidador anota tudo em caderno ou WhatsApp pessoal
- Sinal vital fica em planilha solta, ninguém olha em tempo real
- Família liga pra gestora 2x por semana cobrando atualização
- Médico revisa prontuário só na visita semanal/quinzenal
- Emergência depende do cuidador ligar pro filho que liga pro médico
- Você descobre problema crônico só quando vira evento agudo

### Com a ConnectaIACare rodando

- Cuidador relata por **WhatsApp** ou **voz** (5 segundos)
- Sofia transcreve, classifica, decide se aciona alguém
- **Família recebe automaticamente** o que precisa saber (sem você intermediar)
- **Médico tem prontuário 360°** atualizado em tempo real
- **Plantão entra em 5 minutos** em P1 (peito, AVC, queda forte)
- Você vê **KPIs do tenant** todo dia: SLA cumprido, alertas resolvidos, cuidadores ativos

### O ganho real (medido em pilotos)

| Métrica | Antes | Com ConnectaIACare |
|---|---|---|
| Tempo médio cuidador → família | 4-12h | **<2 min** (Sofia notifica) |
| Tempo P1 → atendimento humano | 30-90 min | **<5 min** (SLA contratual) |
| % de incidentes com registro auditável | ~20% | **100%** (audit log imutável) |
| Carga de chamadas reativas pra família | alta | -60% (Sofia responde dúvida cotidiana) |
| Visibilidade do gestor sobre operação | reuniões semanais | **tempo real** (dashboards 24/7) |

---

## 3. Onboarding do seu tenant (primeiros 7 dias)

Quando você assina, recebe um tenant isolado (multi-tenancy nativa — seus dados nunca se misturam com outros clientes).

### Dia 1 — Acesso e ambientação

1. **Login** em `https://app.connectaia.com.br/login`
2. Você recebe o perfil **Admin** (ou **Super Admin** se for institucional)
3. Abra a sidebar — você verá agrupamentos:
   - **Operacional** (Inbox, Eventos, Pacientes, Cuidadores)
   - **Clínico** (Prontuário, Triagens, Validação Farmacológica)
   - **Operações** (Handoff, Saúde do Plantão, Contatos de Escalonamento)
   - **Admin** (Usuários, Tenants, Configurações, Audit Log)
4. Configure seu **perfil pessoal** (nome, telefone, foto) — você vai aparecer em handoffs

### Dia 2 — Configurar dados do tenant

- **Razão social, CNPJ, endereço** (vai em contratos e relatórios LGPD)
- **Logo** (aparece em PDFs gerados, e-mails da Sofia institucional)
- **Cores/branding** (opcional — white-label disponível)
- **Fuso horário** padrão (`America/Sao_Paulo`)
- **Idioma padrão** (`pt-BR`)

### Dia 3 — Cadastrar equipe núcleo

Cadastre primeiro:
- 1 **Médico responsável técnico** (RT)
- 1 **Enfermeiro coordenador**
- 2-3 **Cuidadores** que servirão de piloto
- Você mesmo como **Admin**

Detalhes em [Seção 4](#4-cadastrar-a-equipe-cuidadores-enfermeiros-médicos-familiares).

### Dia 4 — Configurar Sofia para o seu tenant

- Tom (formal/amigável)
- Escopo (responde dúvida administrativa? só clínica?)
- Limites (não dá diagnóstico, não prescreve)
- Mensagem de boas-vindas customizada

Detalhes em [Seção 5](#5-configurar-a-sofia-tom-escopo-autonomia).

### Dia 5 — Cadastrar 3-5 pacientes piloto

- Use o **Wizard de Cadastro** (5 passos)
- Vincule familiares responsáveis
- Vincule cuidadores da rotina
- Cadastre medicações e condições

Detalhes em [Seção 6](#6-importar-e-cadastrar-pacientes-em-escala).

### Dia 6 — Configurar plantão e escalonamento

- Quem fica de plantão P1 (telefone que recebe alerta de peito/AVC)
- Quem fica de plantão P2 (fila clínica em até 30min)
- Janelas de horário (dias da semana + faixa horária)

Detalhes em [Seção 8](#8-plantão-p1p2p3--quem-fica-de-prontidão).

### Dia 7 — Treinamento da equipe + Go-Live

- Treinamento curto com cuidadores (30min, online ou presencial)
- Cada cuidador faz cadastro de voz (1 minuto)
- Cada cuidador envia primeiro relato de teste
- Você confere no dashboard que tudo chegou

A partir do **dia 8**, o piloto está oficialmente rodando. Acompanhamos juntos por 30 dias antes de ampliar.

---

## 4. Cadastrar a equipe (cuidadores, enfermeiros, médicos, familiares)

### Perfis disponíveis

| Perfil | Para quem | O que pode fazer |
|---|---|---|
| **Super Admin** | Equipe ConnectaIA | Tudo + cross-tenant + manutenção da plataforma |
| **Admin** | Gestor do tenant | Tudo dentro do seu tenant |
| **Gestor Clínico** | Coordenador médico/enfermeiro | Configurar Sofia clínica, revisar corpus, validar regras |
| **Médico** | Médico assistente | Prontuário, prescrição, validar drug review, teleconsulta |
| **Enfermeiro** | Enfermagem assistencial | Triagem, anotações de enfermagem, validar P2 |
| **Cuidador** | Cuidador formal/informal | Reportar via WhatsApp/voz, sinais vitais, medicação |
| **Familiar** | Família/responsável | Ver paciente, receber alertas, conversar com Sofia |
| **Operador Central** | Plantão 24/7 | Atender fila handoff, escalonar, resolver care_events |
| **Paciente (B2C)** | Idoso autônomo | Conversar com Sofia, sinais vitais, lembretes |

### Como cadastrar (passo a passo)

1. Sidebar → **Admin** → **Usuários**
2. Botão **Novo Usuário**
3. Preencha:
   - Nome completo
   - E-mail (login)
   - Telefone (E.164: `+5511999999999`)
   - Perfil (escolha da tabela acima)
   - CRM / COREN / RT (se médico/enfermeiro)
   - Especialidade (geriatria, clínica, etc.)
4. Sistema gera senha temporária e envia por e-mail
5. Usuário troca na primeira entrada

### Vincular usuário a paciente

Cuidadores, médicos e familiares precisam estar **vinculados** ao paciente para receber notificações:

1. Abra o **prontuário do paciente**
2. Aba **Equipe**
3. **Adicionar vínculo** → escolha usuário → escolha papel (cuidador principal, médico assistente, filha, etc.)
4. Marque permissões:
   - Recebe alerta P1?
   - Recebe alerta P2?
   - Pode editar prontuário?
   - Pode dar alta clínica?

### Importação em lote (CSV)

Para tenants grandes (>20 usuários), use:

- Sidebar → **Admin** → **Usuários** → **Importar CSV**
- Baixe o template (`modelo_usuarios.csv`)
- Preencha e suba
- Sistema valida linha a linha, mostra preview antes de gravar

---

## 5. Configurar a Sofia (tom, escopo, autonomia)

A Sofia é configurável **por tenant**. Você decide o quanto ela pode/deve fazer.

### Acesso

Sidebar → **Admin** → **Configurações** → **Sofia**

### Configurações principais

#### Tom e personalidade

| Opção | Quando usar |
|---|---|
| `formal_clinico` | Operação hospitalar, médicos sêniores |
| `amigavel_acolhedor` | ILPI, home care familiar (padrão) |
| `objetivo_direto` | Operadora grande, alto volume |

#### Escopo de resposta

| Toggle | O que controla |
|---|---|
| **Responde dúvida administrativa** | Sofia pode responder "que horas a enfermeira chega?" ou só dúvida clínica |
| **Pode falar de medicação** | Sofia explica para que serve o remédio (não prescreve) |
| **Pode dar dica de bem-estar** | Sofia sugere exercício leve, hidratação |
| **Encaminha para humano se inseguro** | Sofia escalona em vez de chutar resposta |

#### Limites duros (nunca mudam)

A Sofia **nunca**:
- Dá diagnóstico médico
- Prescreve dose
- Cancela medicação prescrita
- Substitui SAMU em P1 real
- Compartilha dados entre tenants
- Inventa informação clínica do paciente (RAG estrito)

Esses limites estão no **Safety Guardrail Layer** e não podem ser desativados via interface.

#### Mensagem de boas-vindas

A primeira coisa que cada usuário novo recebe da Sofia no WhatsApp. Customizável por tenant. Exemplo padrão:

> Olá! Sou a Sofia da [Nome do Tenant]. Estou aqui para ajudar você a cuidar do [Nome do paciente]. Quando precisar, é só me mandar um áudio ou texto. Em emergência grave, ligue 192 (SAMU). Combinado?

#### Horário de operação

- **24/7** (padrão) — Sofia responde sempre
- **Comercial** (08-18) — fora do horário, mensagem padrão "passamos para o plantão"
- **Personalizado** — você define faixa

### Versionamento

Toda mudança fica **versionada e auditada**. Histórico em:

Sidebar → **Admin** → **Configurações** → **Sofia** → **Histórico de Versões**

Mostra: quem mudou, quando, o que mudou (diff), rollback em 1 clique.

---

## 6. Importar e cadastrar pacientes em escala

### Cadastro individual (Wizard de 5 passos)

Sidebar → **Pacientes** → **Novo Paciente**

**Passo 1 — Identidade**
- Nome completo, CPF, data de nascimento
- Telefone principal (E.164)
- Endereço completo (CEP autocompleta)

**Passo 2 — Familiares**
- Adicione responsáveis (cônjuge, filhos)
- Marque "responsável legal" se aplicável
- Para cada um: nome, telefone, e-mail, grau de parentesco

**Passo 3 — Condições e medicações**
- Condições crônicas (hipertensão, diabetes, demência, etc.)
- Medicações em uso (princípio ativo + dose + horário)
- Alergias conhecidas
- Sistema roda **cross-validation** automaticamente e mostra alertas

**Passo 4 — Equipe e plantão**
- Médico assistente principal
- Enfermeiro de referência
- Cuidadores formais (se houver)
- Marque "este paciente está em plantão 24/7" ou "monitoramento diurno apenas"

**Passo 5 — Comunicação**
- Como a Sofia trata o paciente (Sr./Sra./apelido)
- Quem recebe relatório semanal (e-mail/WhatsApp)
- Família receberá alerta P1? P2? Os dois?
- Aceite LGPD (paciente ou responsável legal assina digital)

Ao final, sistema cria:
- Registro do paciente
- Vínculos com familiares
- Vínculos com cuidadores
- Snapshot de condições/medicações
- Audit log da criação

### Importação em massa (CSV/Excel)

Para ILPIs com 50+ idosos:

1. Sidebar → **Pacientes** → **Importar**
2. Baixe template `modelo_pacientes.xlsx`
3. Preencha (uma linha por paciente, colunas guiadas)
4. Suba o arquivo
5. Sistema valida e mostra:
   - Linhas OK
   - Linhas com aviso (ex: CPF inválido, telefone fora de padrão)
   - Linhas bloqueadas (ex: campo obrigatório vazio)
6. Você corrige o que dá pra corrigir no preview
7. **Importar** — sistema cria todos os pacientes válidos
8. Relatório de importação fica salvo no audit log

### Wizard de complemento

Pacientes importados ficam como **stub** até alguém completar o cadastro. Aparecem em:

Sidebar → **Pacientes** → filtro **Cadastro pendente**

Você (ou um enfermeiro) pode abrir cada stub e completar via wizard ao longo da semana.

---

## 7. Escala de cuidadores e vínculos paciente↔cuidador

### Conceito

Cada paciente pode ter:
- **1 cuidador principal** (responsável diário)
- **N cuidadores de revezamento** (turnos)
- **N familiares** (não substituem cuidador, mas têm acesso)

### Configurar escala

Sidebar → **Cuidadores** → seleciona cuidador → **Escala**

Você define:
- Dias da semana que ele trabalha
- Faixa horária (ex: 07h-19h, ou 19h-07h)
- Pacientes que ele atende nesse turno

A Sofia usa essa escala pra:
- Saber quem está de plantão **agora** quando o paciente reportar algo
- Notificar o cuidador **certo** (não o que está de folga)
- Sugerir backup se cuidador escalado não responde em X minutos

### Notificações automáticas para cuidador

Quando algo acontece com paciente sob responsabilidade dele:
- **Início de turno**: resumo dos pacientes do dia + ocorrências da noite
- **Durante turno**: alertas P2/P3 que envolvem o paciente
- **Fim de turno**: resumo do que aconteceu + sugestão de handover pro próximo turno

Tudo pelo **WhatsApp** — cuidador não precisa abrir app.

---

## 8. Plantão (P1/P2/P3) — quem fica de prontidão

### Classificação de urgência

| Nível | Quando | SLA | Quem responde |
|---|---|---|---|
| **P1 — Crítico** | Dor no peito, AVC, queda forte, desmaio, sangramento ativo | **5 min** | Plantonista P1 + médico responsável + (se contratado) ConnectaLive |
| **P2 — Clínico** | Febre alta sem causa óbvia, dor controlável, alteração comportamental | **30 min** | Enfermeiro de plantão / médico de plantão |
| **P3 — Administrativo** | Dúvida sobre medicação, troca de horário, agenda | **2h** | Recepção / coordenação |

### Configurar contatos de escalonamento

Sidebar → **Admin** → **Operações** → **Contatos de Escalonamento**

Para cada contato, você define:
- Nome + papel
- Telefone (E.164) que receberá o **push WhatsApp**
- Urgências que ele recebe (P1, P2, P3 — pode ser combinação)
- **Janela de plantão** (dias da semana + faixa horária)
- Status: ativo / pausado

**Importante:** se ninguém estiver de plantão para uma urgência X em um momento Y, a Sofia escalona para o nível superior automaticamente (P2 sem plantonista → vira P1 com aviso de escalada).

### Tab "Saúde do Plantão"

Mostra em tempo real:
- Quem está de plantão **agora** para cada nível
- Última atividade de cada plantonista (último P1 recebido)
- Alertas "stale" (plantonista sem atividade há >24h)
- Ranking dos últimos 30 dias (quem mais atende)

Detalhes em [Seção 10](#10-saúde-do-plantão--diagnóstico-em-uma-tela).

### Push para WhatsApp do plantonista

Quando Sofia classifica P1:
1. Aciona ferramenta `notify_oncall`
2. Identifica plantonistas P1 ativos **agora** (cruza escala + status)
3. Publica mensagem no Stream OUTBOUND
4. Worker envia WhatsApp pra todos simultaneamente
5. Primeiro que **reivindicar** vira responsável do handoff
6. Sistema marca `last_p1_received_at` (alimenta health dashboard)

---

## 9. Dashboards e KPIs que você vai olhar todo dia

### Dashboard Principal

Sidebar → **Dashboard**

KPIs do dia:
- Pacientes ativos
- Alertas P1 hoje (e comparativo semana anterior)
- Alertas P2 hoje
- SLA P1 cumprido (%)
- SLA P2 cumprido (%)
- Care events em aberto (analyzing / active)
- Cuidadores ativos nas últimas 24h
- Sofia: mensagens processadas, tempo médio de resposta

### Dashboard Clínico

Sidebar → **Clínico** → **Dashboard Clínico**

KPIs clínicos:
- Validações farmacológicas pendentes (drug review queue)
- Cross-validation alerts ativos (condição × medicação)
- Pacientes sem prontuário atualizado >30 dias
- Cascatas clínicas em curso (paciente passou por triagem→médico→prescrição)

### Dashboard de Cuidadores

Sidebar → **Cuidadores** → **Dashboard**

KPIs operacionais:
- Cuidadores ativos hoje
- Cuidadores sem reportar há >24h
- Top 5 cuidadores por volume de relatos
- Taxa de aderência a horário de medicação

### Dashboard de Famílias

Sidebar → **Famílias** → **Dashboard**

KPIs de engajamento:
- Famílias ativas (que interagiram nos últimos 7d)
- Famílias inativas há >14d (sinal de atrito)
- Volume de mensagens família→Sofia (e tópicos mais frequentes)

### Como criar painel customizado

Sidebar → **Dashboards** → **Novo Painel**

Você arrasta widgets prontos:
- Card de KPI
- Gráfico de barras
- Gráfico de linha (séries temporais)
- Tabela com filtro
- Lista de eventos

Salva como painel privado ou compartilha com o tenant.

---

## 10. Saúde do Plantão — diagnóstico em uma tela

Esta é uma tela **crítica** para gestão operacional. Acesso:

Sidebar → **Admin** → **Operações** → **Contatos de Escalonamento** → aba **Saúde**

### O que mostra

**Hero card (topo):**
- SLA P1 (últimos 7 dias) com cor (verde/amarelo/vermelho)
- SLA P2 (últimos 7 dias)
- SLA P3 (últimos 7 dias)

**Tabela "Plantonistas agora":**
- Nome + telefone + urgência atendida
- Status (ativo / pausado / fora de janela)
- Última atividade (last_p1_received_at)
- Chip visual de janela (dias + horário)
- Indicador "stale" se >24h sem receber nada

**Ranking 30 dias:**
- Top 5 que mais receberam P1
- Top 5 que mais receberam P2
- Quem não recebeu nenhum nos últimos 30 dias (revisar escala)

**Alertas stale:**
- Cards vermelhos listando plantonistas sem atividade há >X dias
- Botão "pausar" ou "remover" direto no card

### Como ler o painel (caso prático)

**Cenário 1 — Tudo verde**
Continue rodando. Confira só semanalmente.

**Cenário 2 — SLA P1 caiu pra 70%**
Investigar:
- Tem plantonista de plantão nos horários onde P1 ocorreu?
- Plantonistas estão respondendo via Sofia ou ignorando?
- Volume de P1 subiu (precisa contratar mais plantonista)?

**Cenário 3 — Alerta stale**
- Cuidador X não recebeu nenhum P1 há 40 dias
- Possível motivo: escala dele coincide com dias de menor volume, ou ele está pausado e ninguém notou
- Ação: revisar escala, redistribuir cobertura, conversar com ele

---

## 11. Métricas de SLA — o que prometemos e como medimos

### SLA contratual (padrão)

| Métrica | Promessa | Como mede |
|---|---|---|
| P1 → primeiro contato humano | ≤ 5 min em 95% dos casos | `created_at` → `claimed_at` do handoff |
| P2 → primeiro contato humano | ≤ 30 min em 90% dos casos | mesmo cálculo |
| P3 → resposta | ≤ 2h em 80% dos casos | mesmo cálculo |
| Sofia → resposta texto | ≤ 3s em 95% dos casos | tempo de processamento |
| Sofia → resposta voz | ≤ 5s em 90% dos casos | inclui STT+LLM+TTS |
| Uptime plataforma | 99.5% mensal | monitoramento externo |

### Cálculo dinâmico (não materializado)

Importante: o "SLA breach" é **calculado dinamicamente** na consulta, não fica como flag no banco. Isso garante que não exista divergência entre "o sistema diz que cumpriu" e "a realidade".

### Onde ver

- Dashboard principal — % do dia
- Saúde do Plantão — % dos últimos 7d
- Relatório mensal — PDF gerado dia 1 de cada mês

### Penalidade contratual

Se SLA P1 ficar <95% por 2 meses consecutivos, há crédito de 10% na mensalidade (cláusula padrão). Configurável no contrato.

---

## 12. Audit log, LGPD e prestação de contas

### Audit log imutável

**Toda** ação no sistema (acesso a prontuário, mudança de medicação, envio de mensagem, escalada, login) é gravada em `aia_audit_log`.

Características:
- **Append-only** (trigger Postgres impede UPDATE/DELETE)
- Inclui: ator, ação, recurso, payload antes/depois, IP, user-agent, timestamp
- Retenção: 5 anos (configurável até 20 anos para tenants regulados)
- Exportável (CSV/JSON) para auditoria externa

### Acesso

Sidebar → **Admin** → **Audit Log**

Filtros:
- Por usuário
- Por paciente
- Por tipo de ação
- Por período
- Por IP

### LGPD — direitos do titular

Sofia + plataforma atendem nativamente:

| Direito | Como atendemos |
|---|---|
| Acesso | Paciente/responsável pede via WhatsApp à Sofia → relatório gerado em 48h |
| Retificação | Editar prontuário via interface (médico/enfermeiro) |
| Exclusão | Botão "esquecer paciente" — pseudonimiza dados, mantém audit log obrigatório legal |
| Portabilidade | Export FHIR R4 (formato padrão de saúde) |
| Revogação de consentimento | Sofia para de atender em 1 min, dados ficam anonimizados após 30 dias |

### Onde isso vive

- `aia_consent_log` — todos os consentimentos (com timestamp e revogação)
- `aia_data_subject_requests` — solicitações LGPD (fluxo + status)
- `aia_audit_log` — append-only de tudo

### Relatório LGPD anual

Sidebar → **Admin** → **Compliance** → **Relatório LGPD**

Gera PDF com:
- Volume de dados processados
- Solicitações LGPD do ano
- Incidentes de segurança (zero, esperamos)
- Encarregado (DPO) — designar e manter atualizado

---

## 13. Faturamento, créditos e consumo de IA

### Modelo de cobrança

Cobramos:
- **Mensalidade fixa por paciente ativo** (escala por volume)
- **Créditos de IA consumidos** (cada chamada de modelo, MCP, transcrição conta)

Você paga apenas pelo que usa. Pacientes inativos (sem atividade >60d) entram em "standby" e não contam para mensalidade até reativar.

### Painel de consumo

Sidebar → **Admin** → **Faturamento** → **Consumo**

Mostra:
- Créditos consumidos no mês (com gráfico diário)
- Top 5 features que mais consomem
- Top 5 pacientes que mais consomem
- Projeção fim de mês
- Saldo atual

### Configurar limite

- Limite duro (corta serviço se ultrapassar — não recomendado)
- Limite suave (avisa, não corta — recomendado)
- Alerta em 50%, 75%, 90% do limite

### Fatura mensal

- Gerada dia 1
- E-mail com PDF + link no painel
- Pagamento via boleto / PIX / cartão recorrente
- Vencimento: 10 dias após emissão

---

## 14. Governança da Sofia — Conselho Científico

A Sofia tem um **Conselho Científico** institucional que valida diretrizes clínicas. Composição:

- **Diretor Científico** (atualmente: Henrique Bordin — biomédico + farmacêutico) — 3-5% participação
- **2-3 Conselheiros** (geriatra, gerontólogo, enfermeiro coordenador) — 0.2% cada
- **Reuniões trimestrais** com pauta de revisão

### O que o Conselho faz

- Revisa **corpus clínico** da Sofia (regras pré-check, cross-validation, escalonamento)
- Aprova mudanças em **rules base** (ex: nova interação medicamentosa adicionada)
- Audita decisões controversas (sample mensal de care_events)
- Publica notas técnicas para a comunidade médica

### Como você participa

Como gestor, você:
- **Não vota** no Conselho (a menos que seja conselheiro)
- Recebe **resumo trimestral** das decisões
- Pode **sugerir mudanças** via canal específico
- Tem acesso ao **registro de versões** do corpus

### Onde ver

Sidebar → **Clínico** → **Conselho Científico** → **Atas e Resoluções**

---

## 15. Quando algo dá errado — playbook do gestor

### "A Sofia não está respondendo"

1. Vai em **Status da Plataforma** (link no rodapé)
2. Se status verde → problema no tenant
3. Sidebar → **Admin** → **Sofia** → **Diagnóstico**
4. Se tudo OK na Sofia → testar uma mensagem direta
5. Se persistir → abrir chamado (Seção 19)

### "Cuidador reclamou que não recebe notificação"

1. Confirme telefone do cuidador (E.164)
2. Vai em **Cuidadores** → ele → **Histórico de Notificações**
3. Veja último envio + status (entregue, lido, falha)
4. Se falha repetida → confirme WhatsApp dele ativo + sem bloqueio
5. Reenvie convite (botão "Reenviar onboarding")

### "Família ligou furiosa que não foi avisada de uma queda"

1. Abra o **prontuário do paciente** → aba **Eventos**
2. Confirme se houve evento de queda (Sofia detectou?)
3. Se sim → veja para quem foi notificado
4. Se família não estava na lista → adicione agora
5. Se estava e não chegou → audit log mostra por quê
6. Comunique família com transparência (com print do audit)

### "SLA P1 caiu pra <70%"

1. Saúde do Plantão → ver alertas
2. Identificar plantonista que não responde
3. Conversar com ele / substituir
4. Revisar volume (precisa contratar mais plantonista?)

### "Tenho um vazamento de dados (suspeita LGPD)"

1. **Abra chamado P1 imediato** com a ConnectaIA (suporte@connectaia.com.br ou ligar)
2. Não mexa em logs (preserva evidência)
3. Notifique seu DPO em até 24h
4. ANPD em até 72h se confirmado
5. Comunicação a titulares conforme orientação jurídica

### "Médico quer revogar acesso de outro médico ao prontuário"

1. Sidebar → **Admin** → **Usuários** → buscar médico
2. Aba **Permissões** → desmarcar paciente / desativar perfil
3. Audit log grava revogação
4. Médico revogado é notificado por e-mail (compliance)

---

## 16. Integrações (FHIR, Tecnosenior, CareNote, MedMonitor)

### Status atual

| Integração | Status | O que faz |
|---|---|---|
| **Tecnosenior CareNote** | ✅ Produção (validado 29/04 com Armindo+Matheus) | Importa anotações de enfermagem do CareNote (id=2) |
| **Evolution API (WhatsApp)** | ✅ Produção | Canal de mensageria |
| **Deepgram STT** | ✅ Produção | Transcrição de voz |
| **MedMonitor** | 🔜 Em desenvolvimento | Importação de sinais vitais de dispositivos |
| **Atente/Vita** | 🔜 Em desenvolvimento | Plataforma de saúde |
| **FHIR R4** | ✅ Export disponível | Portabilidade LGPD + integração com prontuário externo |

### Como ativar uma integração

Sidebar → **Admin** → **Integrações**

Cada integração tem:
- Toggle on/off
- Configuração de credenciais (OAuth ou API key)
- Mapeamento de campos (qual campo do parceiro vira qual campo da Sofia)
- Log de sincronização

### Tecnosenior CareNote (caso de uso real)

Cuidador da ILPI registra rotina no CareNote (tablet beira-leito). Conector:
1. Lê novas anotações a cada 5 min
2. Identifica paciente correspondente na ConnectaIACare
3. Cria evento em `aia_events` com source=`carenote`
4. Sofia analisa se há sinal de alerta
5. Se sim → escala normalmente

Vantagem: equipe **não muda fluxo** — continua usando CareNote, e a ConnectaIACare entra como camada de inteligência por cima.

---

## 17. FAQ do Gestor

**Quanto tempo até o tenant estar 100% rodando?**
7 dias de onboarding + 30 dias de piloto monitorado = 37 dias para considerar maduro.

**Posso ter múltiplos tenants? (ex: ILPI A e ILPI B)**
Sim. Cada um é isolado. Você pode ter perfil Admin em vários. Dados nunca se misturam.

**Sofia "aprende" com meu tenant ou compartilha aprendizado?**
Sofia **não treina modelo** com seus dados. Cada tenant tem corpus isolado. Aprendizado coletivo só acontece se você assinar termo específico (opt-in) para contribuir para baseline.

**Pago por cuidador também?**
Não. Cuidadores são ilimitados. Mensalidade é por **paciente ativo** + consumo de IA.

**Posso desligar a Sofia e usar só dashboards?**
Pode (modo passivo). Mas perde 80% do valor. Recomendamos manter Sofia ativa pelo menos em escopo "responde dúvida + escalona".

**Como saio se quiser cancelar?**
Aviso prévio 30 dias. Export FHIR completo dos dados em 48h. Apagamos tudo em 90 dias após saída (mantemos só audit log obrigatório por 5 anos).

**Posso customizar mensagem da Sofia além do tom?**
Tom + boas-vindas + horário sim, via interface. Prompt completo só com mudança contratual (Pro tier).

**E se eu não tiver médico responsável técnico?**
Tem que ter (exigência legal para operação de saúde). Podemos indicar parceiros se você não tiver.

**Posso usar para outro perfil (não idoso)?**
Plataforma é otimizada pra idoso. Funciona pra qualquer paciente crônico, mas Sofia tem corpus específico. Conversamos sobre adaptação.

**Tenho relatório auditável para acreditadora (ONA, JCI)?**
Sim. Audit log + dashboards + indicadores SLA atendem requisitos básicos. Templates específicos disponíveis.

---

## 18. Checklist mensal

Coisa que recomendamos olhar **todo mês**:

- [ ] SLA P1, P2, P3 dentro do contratado?
- [ ] Plantonistas stale (>30d sem atividade)?
- [ ] Cuidadores inativos (>14d)?
- [ ] Pacientes sem prontuário atualizado >30d?
- [ ] Consumo de créditos dentro do projetado?
- [ ] Famílias inativas >14d (risco churn)?
- [ ] Audit log sem evento suspeito?
- [ ] Backup do export FHIR realizado?
- [ ] Reunião mensal com Conselho Científico (se aplicável)?
- [ ] Feedback de cuidadores coletado e endereçado?

---

## 19. Contatos e suporte

### Suporte técnico

- **E-mail**: suporte@connectaia.com.br
- **WhatsApp**: +55 51 9 9999-9999 (suporte 24/7 para Admins)
- **Painel**: Sidebar → **Suporte** → abrir chamado (recomendado)

### Suporte clínico (Conselho Científico)

- **E-mail**: cientifico@connectaia.com.br
- **Diretor**: Henrique Bordin

### Comercial / Customer Success

- **E-mail**: sucesso@connectaia.com.br
- **Reuniões mensais**: agendadas pelo seu CSM dedicado

### Emergência operacional (P1 plataforma)

- **WhatsApp dedicado**: +55 51 9 8888-8888
- SLA 15min mesmo madrugada
- Apenas para gestor (não compartilhe com cuidadores)

### Documentação

- **Manual completo**: `docs/MANUAL_PLATAFORMA.md` (referência técnica)
- **Manual do cuidador**: `docs/MANUAL_CUIDADOR.md` (pra distribuir pra equipe)
- **Manual do familiar**: `docs/MANUAL_FAMILIAR.md`
- **Manual do idoso (B2C)**: `docs/MANUAL_IDOSO_B2C.md`
- **Manual médico/enfermeiro**: `docs/MANUAL_MEDICO_ENFERMEIRO.md`
- **Manual do operador central**: `docs/MANUAL_OPERADOR_CENTRAL.md`

---

**Última revisão:** 2026-05-18
**Próxima revisão prevista:** 2026-08-18
**Responsável editorial:** Equipe ConnectaIA
**Versionamento:** este manual está em git, toda mudança fica auditada

> Em caso de dúvida não coberta aqui, **abra chamado**. Manual nenhum cobre tudo, e seu feedback faz a próxima versão.
