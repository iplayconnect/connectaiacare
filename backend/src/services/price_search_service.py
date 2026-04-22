"""Price Search Service — busca real de preços de medicamentos.

Estratégia:
    1. Tenta scraper-service (container da ConnectaIA principal na rede
       infra_proxy). Reutilizamos o scrape_auto do scraper-service.
    2. URLs alvo: CliqueFarma (melhor UX de busca) + ConsultaRemedios
       (cobertura ampla).
    3. Extração: Claude Sonnet 4.5 recebe o HTML/texto scrapeado e
       devolve JSON estruturado de ofertas.
    4. Fallback: se scraper não responder, Claude recebe o nome do
       medicamento + lista de sites conhecidos e faz sua melhor análise
       com conhecimento de preços típicos (flagado como "estimated").

Output: PriceOffers ordenados por menor preço.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote_plus

import httpx

from src.services.llm import MODEL_FAST, get_llm
from src.utils.logger import get_logger

logger = get_logger(__name__)

SCRAPER_URL = os.getenv("SCRAPER_SERVICE_URL", "http://scraper-service:5020")
SCRAPER_SECRET = os.getenv("SCRAPER_INTERNAL_SECRET", "voip-internal-secret")
SCRAPER_TIMEOUT = 20.0


# Fontes pra scraping (ordem de prioridade)
PHARMACY_SOURCES = [
    {
        "name": "CliqueFarma",
        "search_url_template": "https://www.cliquefarma.com.br/busca/{query}",
        "priority": 1,
    },
    {
        "name": "ConsultaRemédios",
        "search_url_template": "https://consultaremedios.com.br/busca?termo={query}",
        "priority": 2,
    },
]


EXTRACTION_PROMPT = """Você é um extrator que recebe HTML/texto scrapeado de uma página de busca de medicamentos em farmácia brasileira e retorna ofertas estruturadas.

<scraped_content>
{scraped_text}
</scraped_content>

<searched_medication>
{medication}
</searched_medication>

Tarefa: identifique UP TO 5 ofertas do medicamento buscado. Ignore genéricos demais, similares com nome muito diferente e resultados irrelevantes (anúncios, produtos de outra categoria).

ATENÇÃO: o texto pode estar em formato markdown/texto misto com navegação, menus, e muitas imagens SVG do site. Busque padrões como:
- Nomes de produtos (Domperidona 10mg, Dramin B6, Motilium, etc.)
- Preços em reais (R$ 12,90 · R$15.90 · 34,50 reais)
- Nomes de farmácia (Drogasil, Droga Raia, Panvel, Drogaria São Paulo, Pague Menos, Drogão, etc.)
- Caixas/blisters (30 comprimidos, 20 cápsulas)
- Genérico/similar/referência

Para cada oferta que você identificar, extraia:
- `name`: nome comercial + dose (ex: "Losartana Potássica 50mg 30 comprimidos")
- `price_brl`: preço em reais (número decimal, ex: 12.90). Se não encontrar, null.
- `pharmacy`: nome da farmácia/site (ex: "Drogaria São Paulo", "Pague Menos")
- `url`: URL da página do produto (se aparecer). null se não tiver.
- `notes`: observações curtas (ex: "genérico", "similar", "caixa com 30 comprimidos", "frete grátis")

Retorne JSON no formato EXATO:
{{
  "offers": [
    {{"name": "...", "price_brl": 0.0, "pharmacy": "...", "url": "...", "notes": "..."}}
  ],
  "confidence": "high" | "medium" | "low",
  "notes_for_patient": "frase curta útil pro paciente, ex: 'Preços consultados em CliqueFarma em 22/04/2026. Confirme disponibilidade na farmácia.'"
}}

Se nada for identificado com confiança, retorne `{{"offers": [], "confidence": "low", "notes_for_patient": "..."}}`.
"""


FALLBACK_PROMPT = """Você é um assistente que conhece preços típicos de medicamentos no varejo brasileiro (farmácias populares, redes grandes).

<medication>
{medication}
</medication>

Tarefa: sugira 3-4 **estimativas** de preço em 3-4 farmácias brasileiras conhecidas (Drogaria São Paulo, Pague Menos, Drogasil, Panvel, Drogaraia, Droga Raia, Araújo, Farmácia Pacheco). Use seu conhecimento de preços típicos. Deixe claro que são ESTIMATIVAS (não scrape em tempo real).

Retorne JSON:
{{
  "offers": [
    {{"name": "...", "price_brl": 0.0, "pharmacy": "...", "url": null, "notes": "estimativa de preço"}}
  ],
  "confidence": "low",
  "notes_for_patient": "Estimativa baseada em preços de referência. Confirme no site ou na loja antes de comprar."
}}
"""


class PriceSearchService:
    def __init__(self):
        self.llm = get_llm()
        self._client = httpx.Client(timeout=SCRAPER_TIMEOUT)

    def search_medication(self, medication: str) -> dict[str, Any]:
        """Busca ofertas pro medicamento dado. Retorna dict compatível com PriceCache."""
        if not medication or not medication.strip():
            return {"medication": medication, "offers": [], "confidence": "low",
                    "source": "noop", "notes_for_patient": "Medicação não informada."}

        # Nome enxuto pra busca (remove palavras descritivas demais)
        query = self._clean_query(medication)

        # Tenta scraper
        for src in PHARMACY_SOURCES:
            url = src["search_url_template"].format(query=quote_plus(query))
            logger.info("price_search_try_scraper", medication=medication, url=url, source=src["name"])
            scraped = self._scrape_url(url)
            if not scraped or not scraped.get("preview_text"):
                continue
            extracted = self._extract_offers(scraped["preview_text"][:8000], medication)
            if extracted.get("offers"):
                extracted["medication"] = medication
                extracted["source"] = src["name"]
                extracted["source_url"] = url
                return extracted

        # Fallback LLM
        logger.info("price_search_fallback_llm", medication=medication)
        fallback = self._llm_fallback(medication)
        fallback["medication"] = medication
        fallback["source"] = "llm_estimate"
        return fallback

    def search_many(self, medications: list[str]) -> list[dict[str, Any]]:
        """Busca várias medicações, devolve lista de resultados."""
        return [self.search_medication(m) for m in medications if m and m.strip()]

    # ═══════════════════════════════════════════════════════════════════
    # Scraping
    # ═══════════════════════════════════════════════════════════════════

    def _scrape_url(self, url: str) -> dict | None:
        """Tenta em 2 níveis: light (rápido, HTTP puro) → advanced (Chromium).

        CliqueFarma/ConsultaRemedios são SPAs com JS pesado. Modo light não
        renderiza resultados dinâmicos; advanced usa headless Chromium e
        entrega 7k+ chars de conteúdo útil.
        """
        # Tenta modo light primeiro (rápido). Se vier vazio, sobe pra advanced.
        for level in ("light", "advanced"):
            try:
                resp = self._client.post(
                    f"{SCRAPER_URL}/scrape/preview",
                    headers={"X-Internal-Secret": SCRAPER_SECRET, "Content-Type": "application/json"},
                    json={"url": url, "follow_links": False, "max_pages": 1, "level": level},
                    timeout=45.0 if level == "advanced" else SCRAPER_TIMEOUT,
                )
                if resp.status_code != 200:
                    logger.warning("scraper_non200", url=url, status=resp.status_code, level=level)
                    continue
                data = resp.json()
                if data.get("status") != "ok":
                    continue
                preview = data.get("preview") or {}
                char_count = preview.get("char_count", 0)
                if char_count < 500:
                    logger.info("scraper_low_content", url=url, level=level, chars=char_count)
                    continue  # Tenta próximo nível
                logger.info("scraper_ok", url=url, level=level, chars=char_count)
                return preview
            except Exception as exc:
                logger.warning("scraper_failed", url=url, level=level, error=str(exc))
        return None

    def _extract_offers(self, scraped_text: str, medication: str) -> dict[str, Any]:
        try:
            result = self.llm.complete_json(
                system="Você é um extrator preciso de ofertas de medicamentos em farmácias brasileiras.",
                user=EXTRACTION_PROMPT.format(
                    scraped_text=scraped_text, medication=medication,
                ),
                model=MODEL_FAST,
                max_tokens=2500,
                temperature=0.1,
            )
            if not isinstance(result, dict):
                return {"offers": [], "confidence": "low",
                        "notes_for_patient": "Não foi possível interpretar os resultados."}
            result.setdefault("offers", [])
            result.setdefault("confidence", "medium")
            result.setdefault("notes_for_patient", "")

            # Ordena por menor preço (nulls no fim)
            result["offers"].sort(
                key=lambda o: (o.get("price_brl") is None, o.get("price_brl") or 9999),
            )
            return result
        except Exception as exc:
            logger.error("extract_offers_failed", error=str(exc))
            return {"offers": [], "confidence": "low",
                    "notes_for_patient": "Erro ao analisar resultados de busca."}

    # ═══════════════════════════════════════════════════════════════════
    # Fallback LLM puro
    # ═══════════════════════════════════════════════════════════════════

    def _llm_fallback(self, medication: str) -> dict[str, Any]:
        try:
            result = self.llm.complete_json(
                system="Você estima preços típicos de medicamentos no varejo brasileiro (2026).",
                user=FALLBACK_PROMPT.format(medication=medication),
                model=MODEL_FAST,
                max_tokens=2500,
                temperature=0.3,
            )
            if not isinstance(result, dict):
                return {"offers": [], "confidence": "low",
                        "notes_for_patient": "Consulte o preço direto na farmácia."}
            result.setdefault("offers", [])
            result.setdefault("confidence", "low")
            result.setdefault(
                "notes_for_patient",
                "Estimativas baseadas em preços de referência. Consulte a farmácia.",
            )
            result["offers"].sort(
                key=lambda o: (o.get("price_brl") is None, o.get("price_brl") or 9999),
            )
            return result
        except Exception as exc:
            logger.error("llm_fallback_failed", error=str(exc))
            return {"offers": [], "confidence": "low",
                    "notes_for_patient": "Busca de preços indisponível no momento."}

    # ═══════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _clean_query(medication: str) -> str:
        """Remove unidades/frases longas pra busca funcionar bem.

        Ex: 'Losartana Potássica 50mg uso contínuo' → 'Losartana 50mg'
        """
        # Pega até as 3 primeiras palavras + mantém dose se mencionada
        parts = medication.split()
        # Detecta dose (padrão tipo "50mg", "500 mg")
        dose_parts = [p for p in parts if any(c.isdigit() for c in p)][:1]
        name_parts = [p for p in parts if not any(c.isdigit() for c in p)][:2]
        cleaned = " ".join(name_parts + dose_parts)
        return cleaned or medication


_instance: PriceSearchService | None = None


def get_price_search_service() -> PriceSearchService:
    global _instance
    if _instance is None:
        _instance = PriceSearchService()
    return _instance
