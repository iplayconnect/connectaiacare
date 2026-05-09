/**
 * Glossário de acrônimos médicos no client.
 *
 * Decisão Henrique 2026-05-09: sempre escrever termo completo seguido
 * do acrônimo entre parênteses na primeira menção. UI inclusiva pra
 * leigos sem perder rigor técnico.
 *
 * Mantenha sincronizado com backend/src/data/medical_acronyms.yaml.
 * Idealmente exporto via API; por enquanto duplicado pra zero-latência.
 */

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

const GLOSSARY: AcronymEntry[] = [
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

const INDEX: Record<string, AcronymEntry> = Object.fromEntries(
  GLOSSARY.flatMap((e) => [
    [e.acronym, e],
    [e.acronym.toLowerCase(), e],
    [e.acronym.toUpperCase(), e],
  ]),
);

/** Lookup case-insensitive. Retorna null se desconhecido. */
export function lookupAcronym(acronym: string): AcronymEntry | null {
  if (!acronym) return null;
  return (
    INDEX[acronym.trim()] ||
    INDEX[acronym.trim().toLowerCase()] ||
    INDEX[acronym.trim().toUpperCase()] ||
    null
  );
}

/** "Pressão Arterial (PA)". Fallback: só o acrônimo. */
export function formatTerm(acronym: string): string {
  const entry = lookupAcronym(acronym);
  if (!entry) return acronym;
  return `${entry.full_pt} (${entry.acronym})`;
}

/** Mapping vital_type (enum nosso) → label PT-BR formatado. */
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

/** Lista todos por categoria — útil pra UI de glossário. */
export function listByCategory(category: AcronymCategory): AcronymEntry[] {
  return GLOSSARY.filter((e) => e.category === category);
}
