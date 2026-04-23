"""Ingere seeds/kb/*.md para aia_health_knowledge_chunks.

Formato esperado dos markdowns (convenção ConnectaIACare):

    # Título da categoria

    > Fonte: ...
    > Domínio: plans
    > Confiança: high

    ---

    ## [domain/subdomain] Título do chunk

    > keywords: kw1, kw2, kw3
    > applies_to_plans: essencial, familia
    > applies_to_roles: family, self
    > priority: 90

    Conteúdo em markdown livre aqui...

    ---

    ## [outro_dominio/outro_subdomain] Próximo chunk
    ...

Regras do parser:
    - Linhas começando com `## [domain/subdomain]` marcam início de chunk
    - Bloco `> keywords: ...` etc. é parseado como metadata
    - Tudo até o próximo `## [...]` ou `---` no topo de linha é o conteúdo
    - Domain no markdown override o default do arquivo

Uso:

    # Dev local
    python -m scripts.seed_kb

    # Produção (dentro do container)
    docker compose exec api python -m scripts.seed_kb

    # Arquivo específico
    python -m scripts.seed_kb seeds/kb/01_plans.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Adiciona raiz do backend ao path (pra rodar como script solto)
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.services.knowledge_base_service import get_knowledge_base  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


SEEDS_DIR = BACKEND_ROOT / "seeds" / "kb"


# ══════════════════════════════════════════════════════════════════
# Parser de markdown
# ══════════════════════════════════════════════════════════════════

CHUNK_HEADER_RE = re.compile(
    r"^##\s+\[([\w_]+)/([\w_]+)\]\s+(.+)$",
    flags=re.MULTILINE,
)

META_LINE_RE = re.compile(
    r"^>\s+(\w+):\s+(.+?)\s*$",
    flags=re.MULTILINE,
)


def parse_markdown_file(path: Path) -> list[dict]:
    """Extrai lista de chunks de um arquivo markdown.

    Returns:
        [{domain, subdomain, title, content, keywords, applies_to_plans,
          applies_to_roles, priority, confidence, source, source_type}]
    """
    text = path.read_text(encoding="utf-8")

    # Encontra todos os headers de chunk
    matches = list(CHUNK_HEADER_RE.finditer(text))
    if not matches:
        logger.warning("kb_seed_no_chunks_in_file", file=str(path))
        return []

    chunks: list[dict] = []
    for i, m in enumerate(matches):
        domain = m.group(1)
        subdomain = m.group(2)
        title = m.group(3).strip()

        # Conteúdo: do fim deste header até início do próximo (ou fim do texto)
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw_body = text[content_start:content_end].strip()

        # Remove separadores `---` trailing
        raw_body = re.sub(r"\n---\s*$", "", raw_body).strip()

        # Extrai metadata das linhas `> key: value`
        meta: dict[str, str] = {}
        for mm in META_LINE_RE.finditer(raw_body):
            key = mm.group(1).strip().lower()
            value = mm.group(2).strip()
            meta[key] = value

        # Remove bloco de metadata do conteúdo (primeira ocorrência contígua de linhas `> ...` no topo)
        cleaned_body = _strip_leading_quote_block(raw_body)

        chunks.append({
            "domain": meta.get("domain", domain),
            "subdomain": subdomain,
            "title": title,
            "content": cleaned_body,
            "summary": _build_summary(cleaned_body),
            "keywords": _parse_list(meta.get("keywords", "")),
            "applies_to_plans": _parse_list(meta.get("applies_to_plans", "")),
            "applies_to_roles": _parse_list(meta.get("applies_to_roles", "")),
            "priority": int(meta.get("priority", 50)),
            "confidence": meta.get("confidence", "high"),
            "source": str(path.name),
            "source_type": "internal_curated",
        })

    return chunks


def _strip_leading_quote_block(body: str) -> str:
    """Remove bloco de linhas `> ...` do topo do body (metadata)."""
    lines = body.splitlines()
    idx = 0
    for line in lines:
        s = line.strip()
        if s.startswith(">") or s == "":
            idx += 1
        else:
            break
    return "\n".join(lines[idx:]).strip()


def _parse_list(raw: str) -> list[str]:
    if not raw or raw.lower() in ("none", "null", "-"):
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _build_summary(content: str, max_chars: int = 200) -> str:
    """Resumo: primeira linha não-vazia até max_chars."""
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(">"):
            continue
        if len(stripped) > max_chars:
            return stripped[:max_chars].rstrip() + "..."
        return stripped
    return ""


# ══════════════════════════════════════════════════════════════════
# Ingestor
# ══════════════════════════════════════════════════════════════════

def ingest_file(path: Path) -> tuple[int, int]:
    """Parseia arquivo + upserta no banco. Retorna (succeeded, failed)."""
    kb = get_knowledge_base()
    chunks = parse_markdown_file(path)
    if not chunks:
        return 0, 0

    success = 0
    failed = 0
    for c in chunks:
        try:
            chunk_id = kb.upsert_chunk(**c)
            if chunk_id:
                success += 1
                logger.info(
                    "kb_seed_upserted",
                    file=path.name, domain=c["domain"],
                    subdomain=c["subdomain"], title=c["title"][:50],
                    id=chunk_id,
                )
            else:
                failed += 1
        except Exception as exc:
            failed += 1
            logger.error(
                "kb_seed_upsert_failed",
                file=path.name, subdomain=c.get("subdomain"),
                error=str(exc),
            )
    return success, failed


def ingest_all(seeds_dir: Path = SEEDS_DIR) -> dict:
    """Ingere todos os *.md do diretório seeds/kb/. Retorna resumo."""
    if not seeds_dir.exists():
        logger.error("kb_seed_dir_missing", path=str(seeds_dir))
        return {"files": 0, "success": 0, "failed": 0}

    total_success = 0
    total_failed = 0
    files_count = 0

    for md_file in sorted(seeds_dir.glob("*.md")):
        print(f"\n📚 Processando: {md_file.name}")
        s, f = ingest_file(md_file)
        total_success += s
        total_failed += f
        files_count += 1
        print(f"   ✓ {s} sucesso, ✗ {f} falha")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📊 Total: {files_count} arquivos processados")
    print(f"   ✓ {total_success} chunks ingeridos")
    print(f"   ✗ {total_failed} falhas")

    # Contagem final por domínio
    try:
        kb = get_knowledge_base()
        counts = kb.count_by_domain()
        if counts:
            print("\n📂 Distribuição por domínio (ativos):")
            for domain, count in sorted(counts.items()):
                print(f"   {domain:25s} {count:4d} chunks")
    except Exception as exc:
        logger.debug("kb_count_by_domain_failed", error=str(exc))

    return {
        "files": files_count,
        "success": total_success,
        "failed": total_failed,
    }


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    if args:
        for arg in args:
            p = Path(arg)
            if not p.exists():
                p = SEEDS_DIR / arg
            if not p.exists():
                print(f"❌ Arquivo não encontrado: {arg}")
                continue
            print(f"\n📚 Ingerindo: {p.name}")
            s, f = ingest_file(p)
            print(f"   ✓ {s} sucesso, ✗ {f} falha")
    else:
        ingest_all()


if __name__ == "__main__":
    main()
