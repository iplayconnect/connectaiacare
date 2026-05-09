/**
 * Glossário de acrônimos médicos no client.
 *
 * Decisão Henrique 2026-05-09: backend é fonte de verdade
 * (`backend/src/data/medical_acronyms.yaml`). Frontend mantém um
 * fallback hardcoded pra evitar tela vazia se a API falhar OU pra
 * primeira render antes da API responder.
 *
 * Fluxo:
 *   1. Componente renderiza → usa GLOSSARY hardcoded (síncrono)
 *   2. Em paralelo, AcronymsBootstrap chama loadGlossaryFromApi()
 *      no mount do app
 *   3. API retorna → atualiza _glossary in-memory + reconstrói índice
 *   4. Próximas renderizações usam dados atualizados
 *
 * Como `formatTerm`/`vitalTypeLabel` são síncronos (chamados em render),
 * não dá pra fazer fetch a cada call. O padrão "load once, mutate
 * in-memory" funciona desde que o componente que importa NÃO faça
 * cache do resultado (TS chama a função a cada render — ok).
 */

import { api } from "./api";

export type AcronymCategory =
  | "vital_signs"
  | "comorbidities"
  | "events_acute"
  | "functional"
  | "medications_therapeutics"
  | "regulatory"
  | "org"
  | "care_categories";

export interface AcronymEntry {
  acronym: string;
  full_pt: string;
  full_en?: string;
  category: AcronymCategory;
  notes?: string;
}

// ─── Fallback hardcoded — sincronizado com YAML em 2026-05-09 ──────
// Mantém parity com backend/src/data/medical_acronyms.yaml. Se YAML
// mudar e API estiver up, fetch substitui essa lista. Se API estiver
// down, pelo menos os acrônimos mais comuns funcionam.

const FALLBACK_GLOSSARY: AcronymEntry[] = [
  // Vital signs
  { acronym: "PA", full_pt: "Pressão Arterial", category: "vital_signs" },
  { acronym: "PAS", full_pt: "Pressão Arterial Sistólica", category: "vital_signs" },
  { acronym: "PAD", full_pt: "Pressão Arterial Diastólica", category: "vital_signs" },
  { acronym: "FC", full_pt: "Frequência Cardíaca", category: "vital_signs" },
  { acronym: "FR", full_pt: "Frequência Respiratória", category: "vital_signs" },
  { acronym: "SpO2", full_pt: "Saturação de Oxigênio", category: "vital_signs" },
  { acronym: "T", full_pt: "Temperatura", category: "vital_signs" },
  { acronym: "HGT", full_pt: "Glicemia Capilar", category: "vital_signs" },
  // Comorbidities
  { acronym: "DM", full_pt: "Diabetes Mellitus", category: "comorbidities" },
  { acronym: "HAS", full_pt: "Hipertensão Arterial Sistêmica", category: "comorbidities" },
  { acronym: "DPOC", full_pt: "Doença Pulmonar Obstrutiva Crônica", category: "comorbidities" },
  { acronym: "IC", full_pt: "Insuficiência Cardíaca", category: "comorbidities" },
  { acronym: "ICC", full_pt: "Insuficiência Cardíaca Congestiva", category: "comorbidities" },
  { acronym: "IRC", full_pt: "Insuficiência Renal Crônica", category: "comorbidities" },
  { acronym: "DRC", full_pt: "Doença Renal Crônica", category: "comorbidities" },
  { acronym: "AVE", full_pt: "Acidente Vascular Encefálico", category: "comorbidities" },
  { acronym: "AVC", full_pt: "Acidente Vascular Cerebral", category: "comorbidities" },
  // Acute events
  { acronym: "IAM", full_pt: "Infarto Agudo do Miocárdio", category: "events_acute" },
  { acronym: "SCA", full_pt: "Síndrome Coronariana Aguda", category: "events_acute" },
  { acronym: "TEP", full_pt: "Tromboembolismo Pulmonar", category: "events_acute" },
  { acronym: "TVP", full_pt: "Trombose Venosa Profunda", category: "events_acute" },
  { acronym: "HSD", full_pt: "Hematoma Subdural", category: "events_acute" },
  { acronym: "HSA", full_pt: "Hemorragia Subaracnóidea", category: "events_acute" },
  { acronym: "HDA", full_pt: "Hemorragia Digestiva Alta", category: "events_acute" },
  { acronym: "PCR", full_pt: "Parada Cardiorrespiratória", category: "events_acute" },
  // Functional
  { acronym: "ABVD", full_pt: "Atividades Básicas de Vida Diária", category: "functional" },
  { acronym: "AIVD", full_pt: "Atividades Instrumentais de Vida Diária", category: "functional" },
  // Medications
  { acronym: "AINE", full_pt: "Anti-Inflamatório Não Esteroidal", category: "medications_therapeutics" },
  { acronym: "AINH", full_pt: "Anti-Inflamatório Não Hormonal", category: "medications_therapeutics" },
  { acronym: "IECA", full_pt: "Inibidor da Enzima Conversora de Angiotensina", category: "medications_therapeutics" },
  { acronym: "BRA", full_pt: "Bloqueador do Receptor de Angiotensina", category: "medications_therapeutics" },
  { acronym: "BB", full_pt: "Betabloqueador", category: "medications_therapeutics" },
  // Regulatory
  { acronym: "LGPD", full_pt: "Lei Geral de Proteção de Dados", category: "regulatory" },
  { acronym: "CFM", full_pt: "Conselho Federal de Medicina", category: "regulatory" },
  { acronym: "COREN", full_pt: "Conselho Regional de Enfermagem", category: "regulatory" },
  { acronym: "CRF", full_pt: "Conselho Regional de Farmácia", category: "regulatory" },
  { acronym: "ANVISA", full_pt: "Agência Nacional de Vigilância Sanitária", category: "regulatory" },
  { acronym: "SUS", full_pt: "Sistema Único de Saúde", category: "regulatory" },
  // Org
  { acronym: "ILPI", full_pt: "Instituição de Longa Permanência para Idosos", category: "org" },
  { acronym: "UTI", full_pt: "Unidade de Terapia Intensiva", category: "org" },
  { acronym: "UPA", full_pt: "Unidade de Pronto Atendimento", category: "org" },
  { acronym: "UBS", full_pt: "Unidade Básica de Saúde", category: "org" },
];

// ─── State (mutável após API load) ────────────────────────────────

let _glossary: AcronymEntry[] = FALLBACK_GLOSSARY;
let _index: Record<string, AcronymEntry> = buildIndex(_glossary);
let _loadPromise: Promise<void> | null = null;
let _loadedFromApi = false;

function buildIndex(entries: AcronymEntry[]): Record<string, AcronymEntry> {
  const idx: Record<string, AcronymEntry> = {};
  for (const e of entries) {
    idx[e.acronym] = e;
    idx[e.acronym.toLowerCase()] = e;
    idx[e.acronym.toUpperCase()] = e;
  }
  return idx;
}

/**
 * Carrega glossário do backend. Chamar 1x no mount do app.
 * Idempotente: chamadas concorrentes reusam a mesma promise.
 * Fail-safe: se API falhar, mantém fallback.
 */
export function loadGlossaryFromApi(): Promise<void> {
  if (_loadedFromApi) return Promise.resolve();
  if (_loadPromise) return _loadPromise;

  _loadPromise = (async () => {
    try {
      const res = await api.request<{
        status: string;
        items: AcronymEntry[];
      }>("/api/glossary");
      if (res?.items && Array.isArray(res.items) && res.items.length > 0) {
        _glossary = res.items;
        _index = buildIndex(_glossary);
        _loadedFromApi = true;
      }
    } catch {
      // Graceful: mantém fallback. Não é erro bloqueante.
    } finally {
      _loadPromise = null;
    }
  })();
  return _loadPromise;
}

/** Indica se o glossário atual veio da API (vs fallback). */
export function isGlossaryFromApi(): boolean {
  return _loadedFromApi;
}

// ─── Lookup / format helpers ───────────────────────────────────────

/** Lookup case-insensitive. Retorna null se desconhecido. */
export function lookupAcronym(acronym: string): AcronymEntry | null {
  if (!acronym) return null;
  const trimmed = acronym.trim();
  return (
    _index[trimmed] ||
    _index[trimmed.toLowerCase()] ||
    _index[trimmed.toUpperCase()] ||
    null
  );
}

/** "Pressão Arterial (PA)". Fallback: só o acrônimo. */
export function formatTerm(acronym: string): string {
  const entry = lookupAcronym(acronym);
  if (!entry) return acronym;
  return `${entry.full_pt} (${entry.acronym})`;
}

// ─── Domain-specific helpers ───────────────────────────────────────

/**
 * Mapping vital_type (enum nosso) → label PT-BR formatado.
 * Sincroniza com backend ALLOWED_EVENT_TYPES + aia_health_vital_signs.vital_type.
 */
export function vitalTypeLabel(vitalType: string): string {
  const map: Record<string, string> = {
    blood_pressure_systolic: formatTerm("PAS"),
    blood_pressure_diastolic: formatTerm("PAD"),
    blood_pressure_composite: formatTerm("PA"),
    heart_rate: formatTerm("FC"),
    respiratory_rate: formatTerm("FR"),
    oxygen_saturation: formatTerm("SpO2"),
    temperature: formatTerm("T"),
    blood_glucose: formatTerm("HGT"),
    weight: "Peso",
  };
  return map[vitalType] || vitalType;
}

/** Versão curta (só acrônimo) — útil quando espaço é apertado. */
export function vitalTypeShort(vitalType: string): string {
  const map: Record<string, string> = {
    blood_pressure_systolic: "PAS",
    blood_pressure_diastolic: "PAD",
    blood_pressure_composite: "PA",
    heart_rate: "FC",
    respiratory_rate: "FR",
    oxygen_saturation: "SpO2",
    temperature: "T",
    blood_glucose: "HGT",
    weight: "Peso",
  };
  return map[vitalType] || vitalType;
}

/**
 * Mapping event_type (enum nosso de classificação) → label PT-BR.
 * Não é acrônimo, mas centraliza pra paineis usarem labels consistentes.
 */
export function eventTypeLabel(eventType: string): string {
  const map: Record<string, string> = {
    relato_geral: "Relato geral",
    cuidado_higiene: "Higiene/cuidado",
    alimentacao_hidratacao: "Alimentação/Hidratação",
    medicacao: "Medicação",
    evento_adverso_medicamentoso: "Evento adverso medicamentoso (EAM)",
    sinal_vital: "Sinal vital",
    intercorrencia: "Intercorrência",
    sintoma_novo: "Sintoma novo",
    avaliacao_funcional: "Avaliação funcional",
    evolucao_clinica: "Evolução clínica",
    apoio_emocional: "Apoio emocional",
  };
  return map[eventType] || eventType;
}

/** Lista todos por categoria — útil pra UI de glossário. */
export function listByCategory(category: AcronymCategory): AcronymEntry[] {
  return _glossary.filter((e) => e.category === category);
}

/** Snapshot de todos os entries (após load se já feito, fallback caso contrário). */
export function getAllEntries(): AcronymEntry[] {
  return [..._glossary];
}
