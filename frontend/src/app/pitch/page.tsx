"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import {
  SlideT1,
  SlideT2,
  SlideT3,
  SlideT4,
  SlideT5,
  SlideT6,
  SlideT7,
} from "@/components/pitch/slides";

// ═══════════════════════════════════════════════════════════════════
// Pitch Tech Slides — esteira visual de credibilidade técnica
//
// 7 slides auto-sequenciados OU navegáveis por teclado/cliques.
// Timing alvo: 30-45s/slide narrado por Alexandre (~4 min total).
//
// Navegação:
//   ← →         seta pra direita/esquerda
//   espaço      próximo
//   1-7         ir direto pro slide N
//   F           fullscreen toggle
// ═══════════════════════════════════════════════════════════════════

const SLIDES = [
  { id: "T1", component: SlideT1, label: "Fundação" },
  { id: "T2", component: SlideT2, label: "Compliance" },
  { id: "T3", component: SlideT3, label: "FHIR" },
  { id: "T4", component: SlideT4, label: "Expansão" },
  { id: "T5", component: SlideT5, label: "LLM Router" },
  { id: "T6", component: SlideT6, label: "Integrações" },
  { id: "T7", component: SlideT7, label: "Por que importa" },
];

export default function PitchPage() {
  const [currentIdx, setCurrentIdx] = useState(0);

  const goTo = useCallback(
    (idx: number) => {
      if (idx < 0 || idx >= SLIDES.length) return;
      setCurrentIdx(idx);
    },
    [],
  );

  const next = useCallback(() => {
    goTo(Math.min(currentIdx + 1, SLIDES.length - 1));
  }, [currentIdx, goTo]);

  const prev = useCallback(() => {
    goTo(Math.max(currentIdx - 1, 0));
  }, [currentIdx, goTo]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      // Tab usa default; outras navegações
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") {
        e.preventDefault();
        next();
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        prev();
      } else if (/^[1-7]$/.test(e.key)) {
        goTo(parseInt(e.key, 10) - 1);
      } else if (e.key.toLowerCase() === "f") {
        toggleFullscreen();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [next, prev, goTo]);

  const Current = SLIDES[currentIdx].component;

  return (
    <div className="relative min-h-[calc(100vh-80px)]">
      {/* Slide content */}
      <Current key={SLIDES[currentIdx].id} />

      {/* Navigation — fixo no rodapé */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2">
        <button
          onClick={prev}
          disabled={currentIdx === 0}
          className="p-2 rounded-full border border-white/15 bg-[hsl(222,47%,8%)]/80 backdrop-blur hover:bg-white/5 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Slide anterior"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>

        <div className="flex items-center gap-1.5 px-3 py-2 rounded-full border border-white/10 bg-[hsl(222,47%,8%)]/80 backdrop-blur">
          {SLIDES.map((s, idx) => (
            <button
              key={s.id}
              onClick={() => goTo(idx)}
              className={`h-1.5 rounded-full transition-all ${
                idx === currentIdx
                  ? "w-8 accent-gradient"
                  : "w-1.5 bg-white/20 hover:bg-white/40"
              }`}
              aria-label={`Ir para slide ${s.id}: ${s.label}`}
              aria-current={idx === currentIdx}
            />
          ))}
        </div>

        <button
          onClick={next}
          disabled={currentIdx === SLIDES.length - 1}
          className="p-2 rounded-full border border-white/15 bg-[hsl(222,47%,8%)]/80 backdrop-blur hover:bg-white/5 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Próximo slide"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>

      {/* Slide number indicator */}
      <div className="fixed top-4 right-4 z-50 text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono tabular bg-[hsl(222,47%,8%)]/60 backdrop-blur px-3 py-1.5 rounded-full border border-white/5">
        {SLIDES[currentIdx].id} · {currentIdx + 1} / {SLIDES.length}
      </div>

      {/* Keyboard hint */}
      <div className="fixed bottom-6 right-6 z-50 text-[10px] text-muted-foreground/50 font-mono hidden md:block">
        ← → navegar · espaço próximo · 1-7 ir direto · F fullscreen
      </div>
    </div>
  );
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
}
