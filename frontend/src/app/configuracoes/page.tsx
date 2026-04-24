import {
  Activity,
  BookOpen,
  CheckCircle2,
  Database,
  FileSearch,
  FileSignature,
  FlaskConical,
  Globe2,
  HeartPulse,
  Library,
  Lock,
  Network,
  Pill,
  ScrollText,
  Settings,
  ShieldCheck,
  Stethoscope,
  Workflow,
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════════
// /configuracoes — Camada técnica & integrações clínicas
//
// Visão geral das bases de conhecimento, padrões de interoperabilidade,
// catálogos regulatórios e escalas geriátricas que alimentam o motor
// clínico do ConnectaIACare. Pensada pra mostrar profundidade técnica
// em conversas B2B (clínicas, operadoras, ILPIs).
// ═══════════════════════════════════════════════════════════════════

type Status = "active" | "roadmap" | "piloto";

interface Integration {
  name: string;
  short?: string;
  description: string;
  useCase: string;
  status: Status;
  tag?: string;
}

interface IntegrationGroup {
  id: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  subtitle: string;
  items: Integration[];
}

// ──────────────────────────────────────────────────────────────────
// Dados — organizados por domínio clínico / regulatório
// ──────────────────────────────────────────────────────────────────

const GROUPS: IntegrationGroup[] = [
  {
    id: "interop",
    icon: Network,
    title: "Padrões de interoperabilidade",
    subtitle:
      "Formatos abertos para trocar dados clínicos com hospitais, operadoras e prontuários eletrônicos.",
    items: [
      {
        name: "HL7 FHIR R4",
        short: "FHIR",
        description:
          "Padrão global de intercâmbio de dados em saúde (Fast Healthcare Interoperability Resources).",
        useCase:
          "Export de Patient, Observation, Condition, MedicationRequest e Encounter para PEP de parceiros.",
        status: "active",
        tag: "HL7",
      },
      {
        name: "SNOMED CT",
        description:
          "Ontologia clínica internacional com 350 mil conceitos codificados (sintomas, diagnósticos, procedimentos).",
        useCase:
          "Normalização de termos livres das cuidadoras para conceitos clínicos padronizados.",
        status: "piloto",
        tag: "SNOMED International",
      },
      {
        name: "LOINC",
        description:
          "Catálogo universal de observações clínicas e laboratoriais.",
        useCase: "Codificação de sinais vitais, exames e escalas funcionais.",
        status: "active",
        tag: "Regenstrief",
      },
      {
        name: "OpenEHR",
        description:
          "Arquétipos clínicos versionados para modelagem de prontuário.",
        useCase: "Pesquisa & roadmap de expansão multi-tenant hospitalar.",
        status: "roadmap",
      },
    ],
  },
  {
    id: "codificacao",
    icon: Library,
    title: "Catálogos diagnósticos & de procedimentos",
    subtitle:
      "Codificações oficiais exigidas pelo SUS, ANS e operadoras brasileiras.",
    items: [
      {
        name: "CID-10 (Brasil)",
        description:
          "Classificação Estatística Internacional de Doenças — versão brasileira mantida pela DATASUS.",
        useCase:
          "Diagnóstico em prontuário, relatórios clínicos e prescrições.",
        status: "active",
        tag: "OMS · DATASUS",
      },
      {
        name: "CID-11",
        description:
          "Nova versão com codificação pós-coordenada e eixos de funcionalidade.",
        useCase:
          "Transição gradual seguindo cronograma do Ministério da Saúde.",
        status: "roadmap",
        tag: "OMS",
      },
      {
        name: "TUSS — Terminologia Unificada da Saúde Suplementar",
        short: "TUSS",
        description:
          "Codificação obrigatória para faturamento em convênios (ANS Res. Normativa 305).",
        useCase:
          "Preenchimento de guias TISS para consultas e procedimentos ambulatoriais.",
        status: "active",
        tag: "ANS",
      },
      {
        name: "SIGTAP — Tabela de Procedimentos SUS",
        short: "SIGTAP",
        description:
          "Catálogo oficial de procedimentos, órteses, próteses e medicamentos do SUS.",
        useCase: "Parcerias com atenção primária e convênios públicos.",
        status: "roadmap",
        tag: "DATASUS",
      },
      {
        name: "CBHPM",
        description:
          "Classificação Brasileira Hierarquizada de Procedimentos Médicos (AMB).",
        useCase: "Honorários e referência de valores em laudo particular.",
        status: "roadmap",
        tag: "AMB",
      },
    ],
  },
  {
    id: "medicamentos",
    icon: Pill,
    title: "Bases de medicamentos & farmacovigilância",
    subtitle:
      "Fontes oficiais para validar princípio ativo, bula, interações e prescrição eletrônica.",
    items: [
      {
        name: "Bulário Eletrônico ANVISA",
        description:
          "Base oficial brasileira com medicamentos registrados, bulas paciente/profissional e rastreabilidade.",
        useCase:
          "Verificação de registro ativo, apresentações e tarja ao montar lembretes e prescrições.",
        status: "active",
        tag: "ANVISA",
      },
      {
        name: "RxNorm",
        description:
          "Nomenclatura normalizada de medicamentos mantida pela National Library of Medicine (NIH/EUA).",
        useCase:
          "Mapeamento princípio ativo ↔ marca comercial ↔ apresentação.",
        status: "piloto",
        tag: "NLM · NIH",
      },
      {
        name: "Classificação ATC/DDD — OMS",
        description:
          "Sistema anatômico-terapêutico-químico com Doses Diárias Definidas.",
        useCase: "Análise de polifarmácia e carga anticolinérgica em idosos.",
        status: "active",
        tag: "WHO Collaborating Centre",
      },
      {
        name: "Receita digital (modelo CFM/ICP-Brasil)",
        description:
          "Prescrição eletrônica com assinatura digital padrão ICP-Brasil (Res. CFM 2.299/2021).",
        useCase:
          "Após teleconsulta: médico assina e paciente/farmácia valida por QR code.",
        status: "piloto",
        tag: "CFM · ICP-Brasil",
      },
    ],
  },
  {
    id: "decisao",
    icon: Stethoscope,
    title: "Suporte à decisão clínica (CDS)",
    subtitle:
      "Critérios consagrados de segurança medicamentosa e triagem geriátrica.",
    items: [
      {
        name: "Critérios de Beers (AGS 2023)",
        description:
          "Lista da American Geriatrics Society de medicamentos potencialmente inadequados em idosos.",
        useCase:
          "Flag automático quando prescrição inclui droga da lista com alternativa mais segura.",
        status: "active",
        tag: "AGS",
      },
      {
        name: "STOPP/START v3 (2023)",
        description:
          "Critérios europeus de prescrição inapropriada e omissão de tratamento no idoso.",
        useCase:
          "Revisão pós-consulta: sugere adição de tratamentos indicados e retirada de prescrições perigosas.",
        status: "active",
        tag: "EUGMS",
      },
      {
        name: "Interações medicamentosas",
        description:
          "Motor de interações droga-droga, droga-doença, droga-alimento com nível de evidência.",
        useCase:
          "Checagem cruzada ao adicionar medicação no prontuário do paciente.",
        status: "piloto",
        tag: "multiparceiro",
      },
      {
        name: "Protocolos CONITEC / MS",
        description:
          "Protocolos Clínicos e Diretrizes Terapêuticas do SUS.",
        useCase:
          "Fonte de referência para hipertensão, diabetes, demência, Parkinson etc.",
        status: "active",
        tag: "Ministério da Saúde",
      },
    ],
  },
  {
    id: "escalas",
    icon: FileSignature,
    title: "Escalas e instrumentos de avaliação geriátrica",
    subtitle:
      "Instrumentos validados clinicamente para avaliação funcional, cognitiva e de risco.",
    items: [
      {
        name: "Mini-Mental (MEEM)",
        description: "Rastreio cognitivo global (Folstein, 1975).",
        useCase: "Monitoramento de declínio cognitivo em acompanhamento longitudinal.",
        status: "active",
      },
      {
        name: "Índice de Katz · ABVD",
        description: "Atividades Básicas de Vida Diária (banho, vestir-se, alimentar-se etc.).",
        useCase: "Classificação do grau de dependência do idoso.",
        status: "active",
      },
      {
        name: "Escala de Lawton · AIVD",
        description: "Atividades Instrumentais de Vida Diária.",
        useCase: "Avaliar autonomia (telefone, finanças, medicação, transporte).",
        status: "active",
      },
      {
        name: "Escala de Morse (queda)",
        description: "Morse Fall Scale — predição de risco de queda.",
        useCase: "Score automático a partir dos relatos da cuidadora.",
        status: "active",
      },
      {
        name: "Escala de Braden",
        description: "Avaliação de risco para úlcera por pressão.",
        useCase: "Pacientes acamados ou com mobilidade reduzida.",
        status: "active",
      },
      {
        name: "PHQ-9 · GDS-15",
        description:
          "Patient Health Questionnaire e Geriatric Depression Scale.",
        useCase: "Rastreio de sintomas depressivos no idoso.",
        status: "piloto",
      },
      {
        name: "CIRS-G",
        description: "Cumulative Illness Rating Scale — Geriatrics.",
        useCase: "Quantificação da carga de comorbidades.",
        status: "roadmap",
      },
    ],
  },
  {
    id: "evidencia",
    icon: BookOpen,
    title: "Fontes de evidência científica",
    subtitle:
      "Bases consultadas pelo motor de RAG para embasar respostas clínicas com literatura revisada.",
    items: [
      {
        name: "PubMed / MEDLINE",
        description:
          "Base de ~36 milhões de referências biomédicas mantida pela NLM.",
        useCase: "Busca assistida em protocolos clínicos e revisões sistemáticas.",
        status: "active",
        tag: "NLM · NIH",
      },
      {
        name: "SciELO",
        description:
          "Coleção de periódicos científicos brasileiros e latino-americanos.",
        useCase:
          "Evidência em contexto epidemiológico brasileiro (ex.: SUS, ILPI).",
        status: "active",
        tag: "FAPESP · BIREME",
      },
      {
        name: "Cochrane Library",
        description:
          "Padrão-ouro em revisões sistemáticas e meta-análises.",
        useCase: "Ranking de nível de evidência nas recomendações.",
        status: "piloto",
      },
      {
        name: "UpToDate · BMJ Best Practice",
        description: "Referências clínicas sintetizadas (assinatura institucional).",
        useCase:
          "Consulta complementar do médico — link out-of-band, sem export de PHI.",
        status: "roadmap",
      },
    ],
  },
  {
    id: "compliance",
    icon: ShieldCheck,
    title: "Compliance, regulação & privacidade",
    subtitle:
      "Marcos legais, resoluções e certificações que estruturam a operação da plataforma.",
    items: [
      {
        name: "CFM 2.314/2022",
        description:
          "Resolução que regulamenta a telemedicina no Brasil em caráter permanente.",
        useCase:
          "Teleconsulta por vídeo, prescrição à distância e documentação obrigatória.",
        status: "active",
        tag: "Conselho Federal de Medicina",
      },
      {
        name: "CFM 1.821/2007",
        description:
          "Regulamenta digitalização e uso de sistemas informatizados de prontuário.",
        useCase:
          "Preservação, integridade e assinatura digital (NGS2 S-RES).",
        status: "active",
      },
      {
        name: "SBIS · NGS2 (em roadmap)",
        description:
          "Certificação da Sociedade Brasileira de Informática em Saúde para Sistemas de Registro Eletrônico.",
        useCase:
          "Meta: certificação nível 2 após piloto B2B com operadora parceira.",
        status: "roadmap",
        tag: "SBIS · CFM",
      },
      {
        name: "LGPD — Lei Geral de Proteção de Dados",
        description:
          "Lei 13.709/2018, com atenção especial ao Art. 11 (dados sensíveis de saúde).",
        useCase:
          "Consentimento explícito, DPO designado, relatório de impacto (RIPD) e trilha de auditoria.",
        status: "active",
        tag: "ANPD",
      },
      {
        name: "ANVISA SaMD (RDC 657/2022)",
        description:
          "Regulamentação de Software as a Medical Device.",
        useCase:
          "Classificação do sistema e atualização regulatória conforme feature clínica evolui.",
        status: "piloto",
        tag: "ANVISA",
      },
      {
        name: "ISO/IEC 27001 · 27701",
        description:
          "Sistema de gestão de segurança da informação e privacidade.",
        useCase: "Criptografia at-rest/in-transit, gestão de chaves e auditoria.",
        status: "roadmap",
      },
    ],
  },
  {
    id: "identidade",
    icon: FileSearch,
    title: "Identidade & cadastro oficial",
    subtitle:
      "Fontes para validar pessoa física, endereço e vínculo com profissional de saúde.",
    items: [
      {
        name: "CNES — Cadastro Nacional de Estabelecimentos",
        description: "Base pública do Ministério da Saúde.",
        useCase:
          "Validação de ILPIs, clínicas e vínculos profissionais parceiros.",
        status: "piloto",
        tag: "DATASUS",
      },
      {
        name: "CFM · Conselhos Regionais",
        description:
          "Consulta de situação cadastral do CRM do médico responsável.",
        useCase:
          "Validação automática do CRM antes de liberar assinatura de prescrição.",
        status: "active",
      },
      {
        name: "COREN",
        description: "Conselho Regional de Enfermagem.",
        useCase:
          "Validação de COREN ativo para enfermeiros e técnicos de plantão.",
        status: "piloto",
      },
      {
        name: "ViaCEP · Correios",
        description: "Serviço público de resolução de CEP.",
        useCase: "Autocomplete de endereço no cadastro familiar.",
        status: "active",
      },
    ],
  },
  {
    id: "canais",
    icon: Workflow,
    title: "Canais & infraestrutura de atendimento",
    subtitle:
      "Pontes com o mundo real — voz, texto e vídeo — com auditoria ponta a ponta.",
    items: [
      {
        name: "WhatsApp Business Platform",
        description:
          "Canal primário de contato com cuidadoras e familiares.",
        useCase:
          "Relatos de voz, check-ins proativos, notificações com template aprovado.",
        status: "active",
        tag: "Meta Cloud API",
      },
      {
        name: "Teleconsulta por vídeo (WebRTC)",
        description:
          "Salas efêmeras com token JWT TTL 2h e gravação sob consentimento.",
        useCase: "Atendimento com médico assinado + SOAP gerado em rascunho.",
        status: "active",
      },
      {
        name: "Telefonia SIP (VoIP)",
        description:
          "Discagem saindo do alerta clínico direto para o telefone da cuidadora.",
        useCase:
          "Escalada ativa em eventos urgentes/críticos sem depender de app.",
        status: "active",
      },
      {
        name: "SMTP transacional",
        description:
          "Envio de relatórios clínicos, links de agendamento e PDFs assinados.",
        useCase:
          "Comunicação formal com família, operadora e profissionais autorizados.",
        status: "active",
      },
    ],
  },
];

// ──────────────────────────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────────────────────────

export default function ConfiguracoesPage() {
  const total = GROUPS.reduce((acc, g) => acc + g.items.length, 0);
  const active = GROUPS.reduce(
    (acc, g) => acc + g.items.filter((i) => i.status === "active").length,
    0,
  );
  const piloto = GROUPS.reduce(
    (acc, g) => acc + g.items.filter((i) => i.status === "piloto").length,
    0,
  );
  const roadmap = GROUPS.reduce(
    (acc, g) => acc + g.items.filter((i) => i.status === "roadmap").length,
    0,
  );

  return (
    <div className="max-w-6xl mx-auto space-y-6 animate-fade-up pb-12">
      {/* Header */}
      <header className="glass-card rounded-2xl p-6 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl accent-gradient flex items-center justify-center">
            <Settings
              className="h-6 w-6 text-slate-900"
              strokeWidth={2.5}
            />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Configurações técnicas</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Bases clínicas, padrões de interoperabilidade e compliance que
              sustentam o motor ConnectaIACare.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <StatusPill label="Ativos" value={active} tone="green" />
          <StatusPill label="Em piloto" value={piloto} tone="amber" />
          <StatusPill label="No roadmap" value={roadmap} tone="cyan" />
          <StatusPill label="Total" value={total} tone="neutral" />
        </div>
      </header>

      {/* Manifesto técnico curto */}
      <section className="glass-card rounded-2xl p-6 space-y-3">
        <div className="flex items-center gap-2 text-accent-cyan">
          <HeartPulse className="h-4 w-4" />
          <h2 className="text-xs uppercase tracking-[0.18em] font-semibold">
            Nosso compromisso técnico
          </h2>
        </div>
        <p className="text-sm text-foreground/90 leading-relaxed">
          Toda resposta clínica gerada pela plataforma é sustentada por{" "}
          <strong className="text-accent-teal">fontes oficiais, rastreáveis
          e versionadas</strong>: padrões internacionais (HL7 FHIR, SNOMED CT,
          LOINC, ATC/OMS), catálogos brasileiros (CID-10, TUSS, SIGTAP,
          Bulário ANVISA), literatura revisada (PubMed, SciELO, Cochrane) e
          instrumentos geriátricos validados (Beers, STOPP/START, Katz,
          Lawton, Morse, Braden). O motor de IA nunca inventa medicação e
          nunca diagnostica — ele{" "}
          <em>correlaciona o que a cuidadora relata com conhecimento
          publicado</em>, e escala para o profissional humano sempre que a
          decisão exige carimbo.
        </p>

        <div className="flex flex-wrap gap-2 pt-2">
          {[
            "CFM 2.314/2022",
            "LGPD Art. 11",
            "HL7 FHIR R4",
            "ANVISA SaMD",
            "Critérios de Beers 2023",
            "STOPP/START v3",
            "ICP-Brasil",
          ].map((chip) => (
            <span
              key={chip}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold border border-accent-cyan/25 bg-accent-cyan/5 text-accent-cyan"
            >
              <CheckCircle2 className="h-3 w-3" />
              {chip}
            </span>
          ))}
        </div>
      </section>

      {/* Grupos de integração */}
      {GROUPS.map((group) => (
        <IntegrationSection key={group.id} group={group} />
      ))}

      {/* Rodapé — nota regulatória */}
      <footer className="glass-card rounded-2xl p-5 text-[11px] text-muted-foreground leading-relaxed space-y-1">
        <div className="flex items-center gap-2 text-accent-cyan">
          <ScrollText className="h-3.5 w-3.5" />
          <span className="uppercase tracking-wider font-semibold">
            Nota regulatória
          </span>
        </div>
        <p>
          ConnectaIACare é uma plataforma de apoio clínico — não substitui
          avaliação médica. Diagnóstico e prescrição são ato privativo do
          médico (Lei 12.842/2013). A IA atua como camada de triagem,
          documentação e organização de informações, sempre com profissional
          humano no loop. Integrações marcadas como{" "}
          <span className="text-accent-cyan font-semibold">piloto</span> e{" "}
          <span className="text-accent-cyan font-semibold">roadmap</span> são
          compromissos públicos de evolução, não funcionalidade faturada.
        </p>
      </footer>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Components
// ──────────────────────────────────────────────────────────────────

function IntegrationSection({ group }: { group: IntegrationGroup }) {
  const Icon = group.icon;
  return (
    <section className="glass-card rounded-2xl p-5 space-y-4">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-accent-cyan/10 border border-accent-cyan/25 flex items-center justify-center shrink-0">
          <Icon className="h-5 w-5 text-accent-cyan" />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-base font-bold">{group.title}</h2>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
            {group.subtitle}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {group.items.map((item) => (
          <IntegrationCard key={item.name} item={item} />
        ))}
      </div>
    </section>
  );
}

function IntegrationCard({ item }: { item: Integration }) {
  return (
    <div className="solid-card rounded-xl p-4 flex flex-col gap-2 hover:border-accent-cyan/40 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold leading-tight">{item.name}</h3>
          {item.tag && (
            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mt-0.5 font-mono">
              {item.tag}
            </div>
          )}
        </div>
        <StatusBadge status={item.status} />
      </div>

      <p className="text-[12px] text-foreground/80 leading-snug">
        {item.description}
      </p>

      <div className="mt-auto pt-1 text-[11px] text-muted-foreground border-t border-white/5">
        <span className="font-semibold uppercase tracking-wider text-[10px] text-accent-teal">
          Uso no produto ·{" "}
        </span>
        {item.useCase}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: Status }) {
  const map = {
    active: {
      label: "Ativo",
      classes:
        "border-classification-routine/35 bg-classification-routine/10 text-classification-routine",
      icon: <Activity className="h-2.5 w-2.5" />,
    },
    piloto: {
      label: "Piloto",
      classes:
        "border-classification-attention/35 bg-classification-attention/10 text-classification-attention",
      icon: <FlaskConical className="h-2.5 w-2.5" />,
    },
    roadmap: {
      label: "Roadmap",
      classes: "border-accent-cyan/35 bg-accent-cyan/10 text-accent-cyan",
      icon: <Globe2 className="h-2.5 w-2.5" />,
    },
  } as const;
  const cfg = map[status];
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border text-[9px] uppercase tracking-wider font-bold ${cfg.classes}`}
    >
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

function StatusPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "green" | "amber" | "cyan" | "neutral";
}) {
  const toneMap = {
    green:
      "border-classification-routine/30 bg-classification-routine/5 text-classification-routine",
    amber:
      "border-classification-attention/30 bg-classification-attention/5 text-classification-attention",
    cyan: "border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan",
    neutral: "border-white/10 bg-white/5 text-muted-foreground",
  };
  return (
    <div
      className={`px-3 py-2 rounded-xl border ${toneMap[tone]} text-center min-w-[78px]`}
    >
      <div className="text-xl font-bold tabular leading-none">{value}</div>
      <div className="text-[10px] uppercase tracking-wider mt-1 opacity-85">
        {label}
      </div>
    </div>
  );
}

// Componentes de ícones auxiliares referenciados no arquivo mas não usados
// diretamente (mantidos como re-export no import p/ possível uso futuro).
void Database;
void Lock;
