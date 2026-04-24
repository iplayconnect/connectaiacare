"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play, RotateCcw, Sparkles } from "lucide-react";

import {
  CollectedDataPanel,
  type CollectedData,
} from "@/components/onboarding-live/collected-data-panel";
import { StateMachineViz } from "@/components/onboarding-live/state-machine-viz";
import {
  WhatsAppScreen,
  type ChatMessage,
} from "@/components/onboarding-live/whatsapp-screen";

// ═══════════════════════════════════════════════════════════════════
// Onboarding Live Preview — split-screen WhatsApp + Dashboard
//
// Split-screen pitch:
//   Esquerda → WhatsApp simulado (Juliana cadastrando a mãe Maria)
//   Direita  → Dashboard ao vivo: state machine + dados capturados
//
// Modo: scripted por default (seguro pro demo).
//       Cada "cena" avança em ~3-4s, com typing bubble da Sofia.
//       Total: ~90-110 segundos do "oi" até "🎉 Tudo ativado".
//
// Pilot by: botão Play/Pause/Restart no header.
// ═══════════════════════════════════════════════════════════════════

type Scene = {
  message?: ChatMessage;
  state?: string;
  data_patch?: Partial<CollectedData>;
  delay_ms?: number;
  typing_before?: boolean;
};

const SCRIPT: Scene[] = [
  // --- Greeting ---
  {
    message: { id: "1", from: "user", text: "oi", time: "19:42", status: "read" },
    state: "role_selection",
    delay_ms: 1500,
  },
  { typing_before: true, delay_ms: 2000 },
  {
    message: {
      id: "2",
      from: "sofia",
      text:
        "Olá! 👋 Aqui é a *Sofia*, da ConnectaIACare.\n\nEstou aqui pra ajudar você a cuidar de quem você ama, 24h por WhatsApp.\n\nAntes de tudo, me conta: você tá se cadastrando pra você mesmo ou pra monitorar um ente querido?",
      time: "19:42",
    },
    delay_ms: 2500,
  },

  // --- Role ---
  {
    message: {
      id: "3",
      from: "user",
      text: "é pra minha mãe, ela tá ficando esquecida",
      time: "19:43",
      status: "read",
    },
    data_patch: { role: "family" },
    state: "collect_payer_name",
    delay_ms: 1500,
  },
  { typing_before: true, delay_ms: 1800 },
  {
    message: {
      id: "4",
      from: "sofia",
      text:
        "Que carinho cuidar da sua mãe 💙\n\nMe diga SEU nome completo (você que está fazendo o cadastro).",
      time: "19:43",
    },
    delay_ms: 2000,
  },

  // --- Payer name ---
  {
    message: {
      id: "5",
      from: "user",
      text: "Juliana Santos Oliveira",
      time: "19:44",
      status: "read",
    },
    data_patch: { payer_name: "Juliana Santos Oliveira" },
    state: "collect_payer_cpf",
    delay_ms: 1500,
  },
  { typing_before: true, delay_ms: 1500 },
  {
    message: {
      id: "6",
      from: "sofia",
      text:
        "Prazer, *Juliana*! 🤝\n\nAgora preciso do seu CPF — é pra vincular a conta e garantir a segurança dos dados.",
      time: "19:44",
    },
    delay_ms: 2000,
  },

  // --- CPF ---
  {
    message: {
      id: "7",
      from: "user",
      text: "123.456.789-09",
      time: "19:45",
      status: "read",
    },
    data_patch: { payer_cpf_last4: "8909" },
    state: "collect_beneficiary",
    delay_ms: 1500,
  },
  { typing_before: true, delay_ms: 1700 },
  {
    message: {
      id: "8",
      from: "sofia",
      text:
        "✅ CPF confirmado. Agora me conta:\n*Nome completo e idade da sua mãe.*",
      time: "19:45",
    },
    delay_ms: 2000,
  },

  // --- Beneficiary ---
  {
    message: {
      id: "9",
      from: "user",
      text: "minha mãe Maria Aparecida Santos, 78 anos",
      time: "19:46",
      status: "read",
    },
    data_patch: {
      beneficiary_name: "Maria Aparecida Santos",
      beneficiary_age: 78,
    },
    state: "collect_conditions",
    delay_ms: 1500,
  },
  { typing_before: true, delay_ms: 1800 },
  {
    message: {
      id: "10",
      from: "sofia",
      text:
        "💙 *Maria*, 78 anos — anotado.\n\nTem algum problema de saúde já conhecido? (_pressão, diabetes, artrose..._)",
      time: "19:46",
    },
    delay_ms: 2200,
  },

  // --- Conditions ---
  {
    message: {
      id: "11",
      from: "user",
      text: "pressão alta e diabetes",
      time: "19:47",
      status: "read",
    },
    data_patch: { conditions_raw: "pressão alta e diabetes" },
    state: "collect_medications",
    delay_ms: 1500,
  },
  { typing_before: true, delay_ms: 1500 },
  {
    message: {
      id: "12",
      from: "sofia",
      text:
        "Show 👍 Agora as *medicações* que ela toma. Pode mandar texto ou *foto da caixa/receita*.",
      time: "19:47",
    },
    delay_ms: 2200,
  },

  // --- Medications ---
  {
    message: {
      id: "13",
      from: "user",
      text: "Losartana 50mg manhã, Metformina 850mg 2x/dia, Hidroclorotiazida 25mg manhã",
      time: "19:48",
      status: "read",
    },
    data_patch: {
      medications_raw: "Losartana 50mg + Metformina 850mg + Hidroclorotiazida 25mg",
    },
    state: "collect_contacts",
    delay_ms: 1800,
  },
  { typing_before: true, delay_ms: 1400 },
  {
    message: {
      id: "14",
      from: "sofia",
      text:
        "Perfeito 💊\n\nAgora preciso de *contatos de emergência* — pessoas que avisamos se algo acontecer.",
      time: "19:48",
    },
    delay_ms: 2200,
  },

  // --- Contacts ---
  {
    message: {
      id: "15",
      from: "user",
      text: "Juliana 51987654321 filha, Ricardo 51987654322 filho",
      time: "19:49",
      status: "read",
    },
    data_patch: { emergency_contacts_count: 2 },
    state: "collect_address",
    delay_ms: 1500,
  },
  { typing_before: true, delay_ms: 1500 },
  {
    message: {
      id: "16",
      from: "sofia",
      text: "Anotados 🤝\n\nÚltima parte antes do plano: *CEP da residência dela*.",
      time: "19:49",
    },
    delay_ms: 1800,
  },

  // --- Address ---
  {
    message: {
      id: "17",
      from: "user",
      text: "90010-000",
      time: "19:50",
      status: "read",
    },
    data_patch: { address_cep: "90010-000" },
    state: "plan_selection",
    delay_ms: 1400,
  },
  { typing_before: true, delay_ms: 2000 },
  {
    message: {
      id: "18",
      from: "sofia",
      text:
        "📋 Tudo certo! Agora o *plano*:\n\n*1. Essencial* — R$ 49,90/mês\n*2. Família* — R$ 89,90/mês\n*3. Premium* — R$ 149,90/mês\n*4. Premium+Dispositivo* — R$ 199,90/mês\n\nResponda com o número ou nome.",
      time: "19:50",
    },
    delay_ms: 3000,
  },

  // --- Plan ---
  {
    message: {
      id: "19",
      from: "user",
      text: "o Família",
      time: "19:51",
      status: "read",
    },
    data_patch: { plan_sku: "familia" },
    state: "payment_method",
    delay_ms: 1400,
  },
  { typing_before: true, delay_ms: 1800 },
  {
    message: {
      id: "20",
      from: "sofia",
      text:
        "Ótima escolha! *Família* — R$ 89,90/mês 🎉\n\n*Forma de pagamento:*\n💳 *Cartão* — 7 dias grátis + cobrança automática\n📱 *PIX* — começa hoje no 1º mês\n\nCartão ou PIX?",
      time: "19:51",
    },
    delay_ms: 2700,
  },

  // --- Payment ---
  {
    message: {
      id: "21",
      from: "user",
      text: "cartão",
      time: "19:52",
      status: "read",
    },
    data_patch: { payment_method: "credit_card" },
    state: "payment_pending",
    delay_ms: 1400,
  },
  { typing_before: true, delay_ms: 1500 },
  {
    message: {
      id: "22",
      from: "sofia",
      text:
        "💳 Link seguro pra cadastrar o cartão:\n🔗 care.connectaia.com.br/pagamento\n\nMe responde _\"ativar\"_ quando tiver clicado.",
      time: "19:52",
    },
    delay_ms: 2500,
  },
  {
    message: {
      id: "23",
      from: "user",
      text: "ativar",
      time: "19:53",
      status: "read",
    },
    state: "consent_lgpd",
    delay_ms: 1400,
  },
  { typing_before: true, delay_ms: 2000 },
  {
    message: {
      id: "24",
      from: "sofia",
      text:
        "📋 *Últimos termos antes de começar:*\n\n✅ Dados protegidos pela LGPD — uso exclusivo pra cuidado\n✅ *Cancelamento livre* a qualquer momento\n✅ *7 dias de teste grátis* no cartão\n\nResponde *\"aceito\"* pra ativar.",
      time: "19:53",
    },
    delay_ms: 3000,
  },

  // --- Consent ---
  {
    message: {
      id: "25",
      from: "user",
      text: "aceito",
      time: "19:54",
      status: "read",
    },
    data_patch: { consent_signed: true },
    state: "active",
    delay_ms: 1600,
  },
  { typing_before: true, delay_ms: 1800 },
  {
    message: {
      id: "26",
      from: "sofia",
      text:
        "🎉 *Tudo ativado!*\n\nA partir de agora eu acompanho a *Maria* 24h.\n\nAmanhã às 9h já começo o primeiro check-in. Qualquer coisa urgente antes disso, é só me chamar.\n\n_Qualquer dúvida, tô aqui._ 💙",
      time: "19:54",
    },
    delay_ms: 2500,
  },
];

const PLAN_PRICES: Record<string, number> = {
  essencial: 4990,
  familia: 8990,
  premium: 14990,
  premium_device: 19990,
};

// ═══════════════════════════════════════════════════════════════════
// Page
// ═══════════════════════════════════════════════════════════════════

export default function OnboardingLivePage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [state, setState] = useState<string>("greeting");
  const [data, setData] = useState<CollectedData>({});
  const [sceneIdx, setSceneIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [isDone, setIsDone] = useState(false);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const playScene = useCallback(
    (idx: number) => {
      if (idx >= SCRIPT.length) {
        setIsDone(true);
        setIsPlaying(false);
        return;
      }

      const scene = SCRIPT[idx];

      if (scene.typing_before) {
        setIsTyping(true);
        timerRef.current = setTimeout(() => {
          setIsTyping(false);
          setSceneIdx(idx + 1);
        }, scene.delay_ms ?? 1500);
        return;
      }

      // Aplicar mudanças
      if (scene.message) {
        setMessages((prev) => [...prev, scene.message!]);
        setIsTyping(false);
      }
      if (scene.state) {
        setState(scene.state);
      }
      if (scene.data_patch) {
        setData((prev) => ({ ...prev, ...scene.data_patch }));
      }

      timerRef.current = setTimeout(() => {
        setSceneIdx(idx + 1);
      }, scene.delay_ms ?? 2000);
    },
    [],
  );

  useEffect(() => {
    if (!isPlaying) return;
    playScene(sceneIdx);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneIdx, isPlaying]);

  const handlePlayPause = () => {
    if (isDone) return;
    if (isPlaying) {
      if (timerRef.current) clearTimeout(timerRef.current);
    }
    setIsPlaying((p) => !p);
  };

  const handleRestart = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setMessages([]);
    setIsTyping(false);
    setState("greeting");
    setData({});
    setSceneIdx(0);
    setIsDone(false);
    setIsPlaying(true);
  };

  const planPrice = data.plan_sku ? PLAN_PRICES[data.plan_sku] : undefined;

  return (
    <div className="space-y-4 max-w-[1600px]">
      {/* Header */}
      <header className="glass-card rounded-2xl p-5 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl accent-gradient flex items-center justify-center">
            <Sparkles className="h-5 w-5 text-slate-900" strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="text-xl font-bold">
              <span className="accent-gradient-text">Sofia</span>
              <span className="text-foreground/80"> ao vivo</span>
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              Onboarding B2C em tempo real · Maria Santos, 78 anos
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isDone && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold bg-classification-routine/10 border border-classification-routine/30 text-classification-routine">
              <span className="w-1.5 h-1.5 rounded-full bg-classification-routine animate-pulse" />
              Assinatura ativada
            </span>
          )}
          <button
            onClick={handlePlayPause}
            disabled={isDone}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan hover:bg-accent-cyan/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label={isPlaying ? "Pausar demo" : "Retomar demo"}
          >
            {isPlaying ? (
              <Pause className="h-3 w-3" />
            ) : (
              <Play className="h-3 w-3" />
            )}
            {isPlaying ? "Pausar" : "Retomar"}
          </button>
          <button
            onClick={handleRestart}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold border border-white/10 bg-white/5 hover:bg-white/10 transition-colors"
            aria-label="Reiniciar demo"
          >
            <RotateCcw className="h-3 w-3" />
            Reiniciar
          </button>
        </div>
      </header>

      {/* Split-screen */}
      <div className="grid grid-cols-1 lg:grid-cols-[460px_1fr] gap-4 h-[720px] lg:h-[780px]">
        {/* Esquerda — WhatsApp */}
        <div className="h-full">
          <WhatsAppScreen messages={messages} isTyping={isTyping} />
        </div>

        {/* Direita — Dashboard ao vivo */}
        <div className="grid grid-rows-[auto_1fr] gap-4 h-full overflow-hidden">
          <StateMachineViz currentState={state} />
          <div className="overflow-auto">
            <CollectedDataPanel data={data} plan_price={planPrice} />
          </div>
        </div>
      </div>

      {/* Subtexto institucional */}
      <footer className="text-center text-xs text-muted-foreground pt-2">
        Dados simulados ·
        <span className="mx-1.5 text-muted-foreground/60">|</span>
        Sofia valida CPF com checksum, hasheia com SHA-256 antes de gravar
        <span className="mx-1.5 text-muted-foreground/60">|</span>
        Aceite LGPD versionado + timestamp imutável (audit chain)
      </footer>
    </div>
  );
}
