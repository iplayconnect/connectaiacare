import { redirect } from "next/navigation";

// /admin/system/operations/leads — rota legada.
// Toda a UI foi consolidada em /admin/system/operations/comercial/lista
// (Caminho C). Deixa de redirect pra preservar links antigos (sidebar
// antiga, bookmarks, links de pages internas).
export default function LeadsLegacyRedirect() {
  redirect("/admin/system/operations/comercial/lista");
}
