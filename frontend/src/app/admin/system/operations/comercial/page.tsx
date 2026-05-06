import { redirect } from "next/navigation";

// /admin/system/operations/comercial — index redireciona pro funil.
export default function ComercialIndex() {
  redirect("/admin/system/operations/comercial/funil");
}
