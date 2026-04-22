import "@/app/globals.css";

// Layout override — rota /consulta/* é tela cheia (sem Sidebar/TopBar).
// Sobrepõe o RootLayout porque sidebar+topbar consomem 60+14=74 do canto
// esquerdo/superior, inviável pra videochamada. Esta é uma experiência
// full-screen premium dedicada.
export default function ConsultaLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 bg-[hsl(225,80%,6%)] z-[100] overflow-hidden">
      {/* Override via CSS: esconde sidebar/topbar herdados */}
      <style
        dangerouslySetInnerHTML={{
          __html: `
            body > aside, body > header {
              display: none !important;
            }
            main {
              padding-left: 0 !important;
              padding-top: 0 !important;
            }
            main > div {
              padding: 0 !important;
              max-width: none !important;
            }
          `,
        }}
      />
      {children}
    </div>
  );
}
