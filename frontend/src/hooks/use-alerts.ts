/**
 * use-alerts — hook de acesso aos alertas clínicos em triagem.
 *
 * Fonte de dados: mock com 10 alertas distribuídos nos 4 níveis (critical,
 * urgent, attention, routine) + estados de ACK/escalação/ligação.
 *
 * Quando backend expuser GET /api/alerts, swap interno aqui.
 */

export type AlertClassification = "routine" | "attention" | "urgent" | "critical";

export interface AlertPatient {
  id: string;
  name: string;
  age: number;
  unit: string;
  ward: string;
  room: string;
  seed?: number;
}

export interface VitalsSnapshot {
  bp?: string; // "170/100"
  hr?: number;
  spo2?: number;
  temp?: number;
}

export interface CallState {
  status: "dialing" | "connected" | "completed" | "failed";
  target?: string;
  started_at?: string;
}

export interface ClinicalAlert {
  id: string;
  classification: AlertClassification;
  patient: AlertPatient;
  report_id?: string;
  excerpt: string;
  ai_reason?: string;
  created_at: string;
  minutes_ago: number;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  escalated_to?: string | null;
  call_state?: CallState | null;
  vitals_snapshot?: VitalsSnapshot;
}

// ══════════════════════════════════════════════════════════════════
// Mock data (10 alertas — do Opus Design)
// ══════════════════════════════════════════════════════════════════

export const MOCK_ALERTS: ClinicalAlert[] = [
  {
    id: "a001",
    classification: "critical",
    patient: {
      id: "p1",
      name: "Maria da Silva Santos",
      age: 87,
      unit: "SPA Vida Plena",
      ward: "Ala B",
      room: "12",
      seed: 0,
    },
    report_id: "r1",
    excerpt:
      "Confusão súbita após almoço, recusou medicação. PA 170/100 mmHg, FC 112 bpm, sudorese e fala arrastada.",
    ai_reason: "Sinais compatíveis com AVC em curso — janela terapêutica de 4,5 h.",
    created_at: "2026-04-23T14:32:00-03:00",
    minutes_ago: 3,
    acknowledged_at: null,
    escalated_to: null,
    call_state: null,
    vitals_snapshot: { bp: "170/100", hr: 112, spo2: 94, temp: 36.8 },
  },
  {
    id: "a002",
    classification: "urgent",
    patient: {
      id: "p4",
      name: "Antônio Ribeiro de Souza",
      age: 82,
      unit: "SPA Vida Plena",
      ward: "Ala A",
      room: "08",
      seed: 3,
    },
    report_id: "r4",
    excerpt:
      "Queda no banheiro há 20 min. Consciente, dor lateral em quadril direito, não consegue apoiar peso.",
    ai_reason: "Possível fratura de fêmur — mobilização restrita, raio-X indicado.",
    created_at: "2026-04-23T14:15:00-03:00",
    minutes_ago: 20,
    acknowledged_at: null,
    escalated_to: null,
    call_state: null,
    vitals_snapshot: { bp: "138/88", hr: 96, spo2: 97, temp: 36.5 },
  },
  {
    id: "a003",
    classification: "urgent",
    patient: {
      id: "p7",
      name: "Teresa Guimarães Lopes",
      age: 79,
      unit: "SPA Vida Plena",
      ward: "Ala C",
      room: "03",
      seed: 4,
    },
    report_id: "r7",
    excerpt:
      "Dispneia progressiva em repouso. Edema em MMII ++. Saturação caiu para 89% em ar ambiente.",
    ai_reason: "Descompensação de ICC — necessita avaliação + possível O₂ suplementar.",
    created_at: "2026-04-23T13:58:00-03:00",
    minutes_ago: 37,
    acknowledged_at: null,
    escalated_to: null,
    call_state: {
      status: "dialing",
      target: "Filha · Patrícia Lopes",
      started_at: "2026-04-23T14:10:00-03:00",
    },
    vitals_snapshot: { bp: "142/86", hr: 104, spo2: 89, temp: 36.9 },
  },
  {
    id: "a004",
    classification: "attention",
    patient: {
      id: "p2",
      name: "João Batista Pereira",
      age: 79,
      unit: "SPA Vida Plena",
      ward: "Ala A",
      room: "04",
      seed: 1,
    },
    report_id: "r2b",
    excerpt:
      "Glicemia pré-almoço 218 mg/dL — terceira aferição elevada em 48h. Relato de sede aumentada.",
    ai_reason: "Hiperglicemia recorrente — revisar esquema de insulina com endócrino.",
    created_at: "2026-04-23T12:45:00-03:00",
    minutes_ago: 110,
    acknowledged_at: null,
    escalated_to: null,
    call_state: null,
    vitals_snapshot: { bp: "128/80", hr: 78, spo2: 97, temp: 36.4 },
  },
  {
    id: "a005",
    classification: "attention",
    patient: {
      id: "p5",
      name: "Rosângela Ferreira Campos",
      age: 84,
      unit: "SPA Vida Plena",
      ward: "Ala B",
      room: "15",
      seed: 5,
    },
    report_id: "r5",
    excerpt:
      "Recusou café e almoço. Sonolenta, pouco comunicativa desde o despertar. Familiares ainda não visitaram hoje.",
    ai_reason:
      "Apatia + baixa ingesta — avaliar humor, sinais de infecção oculta ou efeito medicamentoso.",
    created_at: "2026-04-23T11:20:00-03:00",
    minutes_ago: 195,
    acknowledged_at: null,
    escalated_to: null,
    call_state: null,
    vitals_snapshot: { bp: "118/72", hr: 68, spo2: 96, temp: 36.2 },
  },
  {
    id: "a006",
    classification: "attention",
    patient: {
      id: "p3",
      name: "Olga Martins de Almeida",
      age: 91,
      unit: "SPA Vida Plena",
      ward: "Ala B",
      room: "07",
      seed: 2,
    },
    report_id: "r3b",
    excerpt:
      "Urina com odor forte relatado pela cuidadora. Sem febre, sem queixa álgica. Hidratação adequada.",
    ai_reason: "Possível ITU inicial — coletar EAS + urocultura.",
    created_at: "2026-04-23T10:05:00-03:00",
    minutes_ago: 270,
    acknowledged_at: "2026-04-23T10:12:00-03:00",
    acknowledged_by: "Enf. Júlia Amorim",
    escalated_to: null,
    call_state: null,
    vitals_snapshot: { bp: "132/78", hr: 74, spo2: 97, temp: 36.6 },
  },
  {
    id: "a007",
    classification: "routine",
    patient: {
      id: "p2",
      name: "João Batista Pereira",
      age: 79,
      unit: "SPA Vida Plena",
      ward: "Ala A",
      room: "04",
      seed: 1,
    },
    report_id: "r2",
    excerpt:
      "Dormiu bem. Café da manhã completo. Caminhada no jardim sem queixas. Humor preservado.",
    ai_reason: "Rotina estável — sem alterações dignas de nota.",
    created_at: "2026-04-23T09:40:00-03:00",
    minutes_ago: 295,
    acknowledged_at: null,
    escalated_to: null,
    call_state: null,
    vitals_snapshot: { bp: "122/78", hr: 72, spo2: 98, temp: 36.4 },
  },
  {
    id: "a008",
    classification: "routine",
    patient: {
      id: "p3",
      name: "Olga Martins de Almeida",
      age: 91,
      unit: "SPA Vida Plena",
      ward: "Ala B",
      room: "07",
      seed: 2,
    },
    report_id: "r3",
    excerpt:
      "Aferição de sinais no horário. Glicemia 118 mg/dL. Humor tranquilo, participou da atividade em grupo.",
    ai_reason: "Parâmetros dentro da faixa habitual.",
    created_at: "2026-04-23T09:10:00-03:00",
    minutes_ago: 325,
    acknowledged_at: "2026-04-23T09:18:00-03:00",
    acknowledged_by: "Enf. Júlia Amorim",
    escalated_to: null,
    call_state: null,
    vitals_snapshot: { bp: "124/76", hr: 70, spo2: 97, temp: 36.3 },
  },
  {
    id: "a009",
    classification: "routine",
    patient: {
      id: "p6",
      name: "Benedito Carlos Oliveira",
      age: 76,
      unit: "SPA Vida Plena",
      ward: "Ala A",
      room: "11",
      seed: 3,
    },
    report_id: "r6",
    excerpt:
      "Fisioterapia concluída, tolerou bem os 15 min de esteira. Sem dor residual. Bebeu 1,5L ao longo da manhã.",
    ai_reason: "Evolução funcional positiva — manter plano.",
    created_at: "2026-04-23T08:50:00-03:00",
    minutes_ago: 345,
    acknowledged_at: "2026-04-23T08:55:00-03:00",
    acknowledged_by: "Enf. Júlia Amorim",
    escalated_to: null,
    call_state: null,
    vitals_snapshot: { bp: "126/80", hr: 76, spo2: 98, temp: 36.5 },
  },
  {
    id: "a010",
    classification: "critical",
    patient: {
      id: "p8",
      name: "Francisca Duarte Nogueira",
      age: 89,
      unit: "SPA Vida Plena",
      ward: "Ala C",
      room: "02",
      seed: 4,
    },
    report_id: "r8",
    excerpt:
      "Dor torácica retroesternal em aperto, irradiando para braço esquerdo. Palidez cutânea, sudorese fria.",
    ai_reason: "Quadro de SCA — ECG imediato + ativar protocolo de dor torácica.",
    created_at: "2026-04-22T22:14:00-03:00",
    minutes_ago: 1038,
    acknowledged_at: "2026-04-22T22:15:00-03:00",
    acknowledged_by: "Dr. Rafael Nunes",
    escalated_to: "UTI · Hospital Vita Curitiba",
    call_state: { status: "completed", target: "Filho · Eduardo Nogueira" },
    vitals_snapshot: { bp: "158/94", hr: 118, spo2: 93, temp: 36.7 },
  },
];

// ══════════════════════════════════════════════════════════════════
// Hook loader (Server Component-friendly)
// ══════════════════════════════════════════════════════════════════

export async function getAlerts(): Promise<ClinicalAlert[]> {
  // TODO: quando backend expuser GET /api/alerts, trocar por:
  // const { alerts } = await api.listAlerts();
  // return alerts;
  return MOCK_ALERTS;
}
