"use client";

/**
 * Tooltip component baseado em @radix-ui/react-tooltip.
 *
 * Vantagens vs title attr nativo:
 *   • Estilização dark theme consistente com o resto da UI
 *   • Delay configurável (default 300ms — title nativo é ~500ms fixo)
 *   • Posicionamento inteligente (auto-flip se sair da viewport)
 *   • Acessível (ARIA + keyboard navigation)
 *   • Pode conter markup (não só texto plano)
 *
 * Uso:
 *   <Tooltip content="Texto descrevendo a função">
 *     <button>Ação</button>
 *   </Tooltip>
 *
 * Pra delay custom ou side:
 *   <Tooltip content="..." side="right" delayMs={500}>
 *     <Link>Sidebar item</Link>
 *   </Tooltip>
 *
 * Pra renderizar fora da hierarquia DOM:
 *   <Tooltip content="..." withPortal>
 *
 * Provider está montado em root layout via <TooltipProvider> —
 * componente individual só precisa do <Tooltip>.
 */

import * as React from "react";
import * as RadixTooltip from "@radix-ui/react-tooltip";

type Side = "top" | "right" | "bottom" | "left";
type Align = "start" | "center" | "end";

interface TooltipProps {
  children: React.ReactNode;
  content: React.ReactNode;
  side?: Side;
  align?: Align;
  delayMs?: number;
  /** Espaço entre trigger e tooltip (px). Default 6. */
  sideOffset?: number;
  /** Renderiza via portal pra escapar transforms/overflow do parent. */
  withPortal?: boolean;
  /** Desabilita tooltip (ex: condicional baseado em estado). */
  disabled?: boolean;
  /** Max width do conteúdo. Default "260px". */
  maxWidth?: string;
}

export function Tooltip({
  children,
  content,
  side = "right",
  align = "center",
  delayMs = 300,
  sideOffset = 6,
  withPortal = true,
  disabled = false,
  maxWidth = "260px",
}: TooltipProps) {
  if (disabled || !content) {
    return <>{children}</>;
  }

  const Inner = (
    <RadixTooltip.Content
      side={side}
      align={align}
      sideOffset={sideOffset}
      avoidCollisions
      collisionPadding={8}
      className={[
        "z-[60] select-none rounded-lg",
        "border border-white/[0.08]",
        "bg-bg-elevated/95 backdrop-blur-xl",
        "px-3 py-2 text-[11px] leading-relaxed",
        "text-foreground/95",
        "shadow-2xl shadow-black/60",
        // Animações sutis baseadas em data attrs do Radix
        "data-[state=delayed-open]:animate-in",
        "data-[state=closed]:animate-out",
        "data-[state=closed]:fade-out-0",
        "data-[state=delayed-open]:fade-in-0",
        "data-[state=delayed-open]:zoom-in-95",
        "data-[state=closed]:zoom-out-95",
        "data-[side=top]:slide-in-from-bottom-1",
        "data-[side=right]:slide-in-from-left-1",
        "data-[side=bottom]:slide-in-from-top-1",
        "data-[side=left]:slide-in-from-right-1",
      ].join(" ")}
      style={{ maxWidth }}
    >
      {content}
      <RadixTooltip.Arrow className="fill-white/[0.08]" width={10} height={5} />
    </RadixTooltip.Content>
  );

  return (
    <RadixTooltip.Root delayDuration={delayMs}>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      {withPortal ? <RadixTooltip.Portal>{Inner}</RadixTooltip.Portal> : Inner}
    </RadixTooltip.Root>
  );
}

/**
 * Provider global. Monta uma única vez no root layout pra evitar
 * múltiplos providers brigando por focus/timer.
 *
 * Skip delay duration: tempo pra "reusar" o delay quando o usuário
 * navega entre tooltips próximos (sidebar item → próximo item) sem
 * esperar 300ms cada vez. 100ms é o sweet spot.
 */
export function TooltipProvider({
  children,
  delayDuration = 300,
  skipDelayDuration = 100,
}: {
  children: React.ReactNode;
  delayDuration?: number;
  skipDelayDuration?: number;
}) {
  return (
    <RadixTooltip.Provider
      delayDuration={delayDuration}
      skipDelayDuration={skipDelayDuration}
    >
      {children}
    </RadixTooltip.Provider>
  );
}
