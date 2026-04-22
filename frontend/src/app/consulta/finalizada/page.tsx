import { Check, Heart } from "lucide-react";

export const dynamic = "force-dynamic";

// ═══════════════════════════════════════════════════════════════
// /consulta/finalizada — tela de agradecimento ao paciente/familiar
// após encerrar a sala. Não requer autenticação.
// ═══════════════════════════════════════════════════════════════

export default function ConsultaFinalizadaPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-[#050b1f] via-[#0a1028] to-[#0d1f2b]">
      <div className="max-w-md w-full text-center">
        <div className="w-20 h-20 rounded-full bg-classification-routine/15 border border-classification-routine/30 flex items-center justify-center mx-auto mb-6">
          <Check className="h-10 w-10 text-classification-routine" strokeWidth={2.5} />
        </div>

        <h1 className="text-2xl font-semibold mb-3">Consulta encerrada</h1>
        <p className="text-sm text-muted-foreground leading-relaxed mb-8">
          Obrigado por utilizar a teleconsulta. O(a) profissional está finalizando o
          prontuário e as orientações serão enviadas à central de cuidadores.
        </p>

        <div className="glass-card rounded-2xl p-5 border border-white/[0.08] mb-6">
          <div className="flex items-start gap-3 text-left">
            <Heart className="h-5 w-5 text-accent-cyan flex-shrink-0 mt-0.5" />
            <div className="text-xs text-muted-foreground leading-relaxed">
              <p className="text-foreground font-medium mb-1">O que acontece agora?</p>
              <ul className="space-y-1">
                <li>• O(a) médico(a) finaliza a documentação clínica</li>
                <li>• Orientações chegam ao cuidador responsável</li>
                <li>• Em caso de dúvida, a central continua de plantão</li>
              </ul>
            </div>
          </div>
        </div>

        <p className="text-[11px] text-muted-foreground/70 italic">
          Plataforma ConnectaIACare — cuidado geriátrico assistido por IA
        </p>
      </div>
    </div>
  );
}
