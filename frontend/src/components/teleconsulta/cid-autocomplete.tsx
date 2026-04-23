"use client";

import { useEffect, useRef, useState } from "react";
import { Search, Stethoscope, X } from "lucide-react";

type CidResult = {
  id: string;
  code: string;
  code_family: string;
  description: string;
  synonyms: string[];
  is_geriatric_common: boolean;
};

const apiBase = process.env.NEXT_PUBLIC_API_URL || "";

// ═══════════════════════════════════════════════════════════════
// CidAutocomplete — busca CID-10 (DATASUS) com debounce + boost
// para condições comuns em idosos. Usado no SOAP editor, campo
// "Hipótese diagnóstica principal".
// ═══════════════════════════════════════════════════════════════

export function CidAutocomplete({
  description,
  icd10,
  onChange,
  disabled,
}: {
  description: string;
  icd10: string;
  onChange: (next: { description: string; icd10: string }) => void;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState(description);
  const [results, setResults] = useState<CidResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Sincroniza descrição externa
  useEffect(() => {
    setQuery(description);
  }, [description]);

  // Debounced search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 2 || query === description) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(
          `${apiBase}/api/diseases/search?q=${encodeURIComponent(query)}&limit=8`,
          { cache: "no-store" },
        );
        if (res.ok) {
          const data = await res.json();
          setResults(data.results || []);
          setOpen(true);
        }
      } catch {
        // silencioso
      } finally {
        setLoading(false);
      }
    }, 260);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, description]);

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function pick(r: CidResult) {
    setQuery(r.description);
    onChange({ description: r.description, icd10: r.code });
    setOpen(false);
    setResults([]);
  }

  return (
    <div ref={containerRef} className="relative grid grid-cols-1 md:grid-cols-3 gap-2">
      <div className="md:col-span-2 relative">
        <input
          disabled={disabled}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            onChange({ description: e.target.value, icd10 });
          }}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Descrição clínica — busque no CID-10"
          className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 pr-8 text-sm disabled:opacity-60 focus:outline-none focus:border-accent-cyan/40"
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none">
          {loading ? (
            <div className="h-3.5 w-3.5 border border-accent-cyan/60 border-t-transparent rounded-full animate-spin" />
          ) : (
            <Search className="h-3.5 w-3.5" />
          )}
        </div>

        {/* Dropdown */}
        {open && results.length > 0 && !disabled && (
          <div className="absolute z-50 left-0 right-0 top-full mt-1 max-h-80 overflow-y-auto rounded-lg bg-[#0a1028] border border-accent-cyan/20 shadow-2xl">
            {results.map((r) => (
              <button
                key={r.id}
                onClick={() => pick(r)}
                className="w-full flex items-start gap-2 px-3 py-2 text-left hover:bg-accent-cyan/[0.08] transition-colors border-b border-white/[0.04] last:border-0"
              >
                <div className="flex items-center gap-1.5 min-w-[70px]">
                  <span className="text-[10px] font-mono font-bold text-accent-cyan bg-accent-cyan/10 px-1.5 py-0.5 rounded border border-accent-cyan/25">
                    {r.code}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] text-foreground flex items-center gap-1.5">
                    {r.description}
                    {r.is_geriatric_common && (
                      <Stethoscope
                        className="h-3 w-3 text-accent-teal flex-shrink-0"
                        aria-label="Frequente em idosos"
                      />
                    )}
                  </div>
                  {r.synonyms.length > 0 && (
                    <div className="text-[10px] text-foreground/55 truncate mt-0.5">
                      {r.synonyms.slice(0, 3).join(" · ")}
                    </div>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="relative">
        <input
          disabled={disabled}
          value={icd10}
          onChange={(e) =>
            onChange({ description, icd10: e.target.value.toUpperCase() })
          }
          placeholder="CID-10"
          className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 pr-8 text-sm font-mono disabled:opacity-60 focus:outline-none focus:border-accent-cyan/40"
        />
        {icd10 && !disabled && (
          <button
            onClick={() => onChange({ description, icd10: "" })}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            title="Limpar"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}
