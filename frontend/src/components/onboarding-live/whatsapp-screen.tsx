"use client";

import { useEffect, useRef } from "react";
import { Check, CheckCheck, MoreVertical, Phone, Video } from "lucide-react";

export type ChatMessage = {
  id: string;
  from: "user" | "sofia";
  text: string;
  time: string; // "19:42"
  status?: "sent" | "delivered" | "read";
};

interface Props {
  messages: ChatMessage[];
  isTyping?: boolean;
  userPhone?: string;
}

/**
 * Simulador visual de conversa do WhatsApp (tema escuro WhatsApp).
 * - Balões à direita = user (tom claro)
 * - Balões à esquerda = Sofia (tom mais verde sutilmente)
 * - Auto-scroll pro final quando adicionar mensagem nova
 * - Ticks de entrega/leitura (1/2 check)
 * - Typing indicator animado
 */
export function WhatsAppScreen({
  messages,
  isTyping,
  userPhone = "+55 11 98765-4321",
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length, isTyping]);

  return (
    <div className="flex flex-col h-full rounded-2xl overflow-hidden border border-white/10 shadow-[0_20px_60px_rgba(0,0,0,0.5)]">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 py-3 bg-[#1F2C33] border-b border-black/30">
        <div className="relative flex-shrink-0">
          <div className="w-10 h-10 rounded-full accent-gradient flex items-center justify-center font-bold text-slate-900">
            S
          </div>
          <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-[#00A884] border-2 border-[#1F2C33]" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-[#E9EDEF] leading-tight">
            Sofia · ConnectaIACare
          </div>
          <div className="text-[11px] text-[#8696A0] leading-tight">
            {isTyping ? (
              <span className="text-[#00A884]">digitando…</span>
            ) : (
              "online"
            )}
          </div>
        </div>
        <button
          aria-label="Videoconferência"
          className="p-2 rounded-full hover:bg-white/5 transition-colors text-[#AEBAC1]"
        >
          <Video className="h-4 w-4" />
        </button>
        <button
          aria-label="Chamar"
          className="p-2 rounded-full hover:bg-white/5 transition-colors text-[#AEBAC1]"
        >
          <Phone className="h-4 w-4" />
        </button>
        <button
          aria-label="Mais opções"
          className="p-2 rounded-full hover:bg-white/5 transition-colors text-[#AEBAC1]"
        >
          <MoreVertical className="h-4 w-4" />
        </button>
      </header>

      {/* Mensagens */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-3 py-4 space-y-1.5 scroll-smooth"
        style={{
          background:
            "linear-gradient(180deg, #0B141A 0%, #0A1115 100%), url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"40\" height=\"40\" viewBox=\"0 0 40 40\"><circle cx=\"2\" cy=\"2\" r=\"0.5\" fill=\"rgba(255,255,255,0.015)\"/></svg>')",
        }}
      >
        {messages.length === 0 && !isTyping && (
          <div className="flex items-center justify-center h-full text-[#8696A0] text-xs">
            Aguardando mensagem…
          </div>
        )}

        {messages.map((m, idx) => (
          <MessageBubble
            key={m.id}
            message={m}
            isFirstOfGroup={
              idx === 0 || messages[idx - 1].from !== m.from
            }
          />
        ))}

        {isTyping && <TypingBubble />}
      </div>

      {/* Input bar (decorativo) */}
      <div className="flex items-center gap-2 px-3 py-2.5 bg-[#1F2C33] border-t border-black/30">
        <div className="flex-1 rounded-full bg-[#2A3942] px-4 py-2 text-xs text-[#8696A0]">
          Mensagem
        </div>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  isFirstOfGroup,
}: {
  message: ChatMessage;
  isFirstOfGroup: boolean;
}) {
  const isUser = message.from === "user";
  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} animate-fade-up`}
    >
      <div
        className={`
          max-w-[75%] px-2.5 py-1.5 text-[13px] leading-snug shadow-sm
          ${isUser
            ? "bg-[#005C4B] text-[#E9EDEF] rounded-2xl rounded-br-sm"
            : "bg-[#202C33] text-[#E9EDEF] rounded-2xl rounded-bl-sm"
          }
          ${!isFirstOfGroup ? (isUser ? "rounded-br-2xl" : "rounded-bl-2xl") : ""}
        `}
      >
        <p className="whitespace-pre-wrap break-words">{message.text}</p>
        <div className="flex items-center justify-end gap-1 mt-0.5 text-[10px] text-[#8696A0]">
          <span>{message.time}</span>
          {isUser && message.status && (
            <span className="flex-shrink-0">
              {message.status === "read" ? (
                <CheckCheck className="h-3 w-3 text-[#53BDEB]" />
              ) : message.status === "delivered" ? (
                <CheckCheck className="h-3 w-3 text-[#8696A0]" />
              ) : (
                <Check className="h-3 w-3 text-[#8696A0]" />
              )}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function TypingBubble() {
  return (
    <div className="flex justify-start animate-fade-up">
      <div className="bg-[#202C33] rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1">
        <span className="w-1.5 h-1.5 rounded-full bg-[#8696A0] animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="w-1.5 h-1.5 rounded-full bg-[#8696A0] animate-bounce" style={{ animationDelay: "150ms" }} />
        <span className="w-1.5 h-1.5 rounded-full bg-[#8696A0] animate-bounce" style={{ animationDelay: "300ms" }} />
      </div>
    </div>
  );
}
