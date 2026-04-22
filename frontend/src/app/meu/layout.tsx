export default function MeuPortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      {/* CSS override: esconde a shell autenticada (sidebar+topbar) nessa rota.
          Portal do paciente é público — não deve mostrar o chrome do CRM. */}
      <style>{`
        body > div > aside,
        body > div > header,
        body > div[data-app-chrome="true"] { display: none !important; }
        body > div { display: block !important; }
        .layout-content, main { padding: 0 !important; }
      `}</style>
      {children}
    </>
  );
}
