"""Importador CID-10 DATASUS → aia_health_disease_catalog.

Estratégia:
  1. Baixa o arquivo oficial CID-10 2008 do DATASUS (CSV zipped).
  2. Parseia cada linha, normaliza encoding e insere no catálogo.
  3. Flaga is_geriatric_common para uma lista curada de condições
     frequentes em idosos (permite boost no autocomplete).
  4. Adiciona sinônimos populares (ex: "I10" → "pressão alta").

URL de referência:
  http://www2.datasus.gov.br/cid10/V2008/WebHelp/cid10.htm
  Arquivo: http://www.datasus.gov.br/cid10/V2008/downloads/CID-10-SUBCATEGORIAS.CSV

Uso:
  docker exec connectaiacare-api python -m scripts.import_cid10

Idempotente — ON CONFLICT (system, code) DO UPDATE.
"""
from __future__ import annotations

import csv
import io
import os
import sys
import zipfile
from pathlib import Path
from typing import Iterable

import httpx

# Import relativo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.postgres import get_postgres  # noqa: E402
from src.utils.logger import configure_logging, get_logger  # noqa: E402

configure_logging()
logger = get_logger("import_cid10")


# ═══════════════════════════════════════════════════════════════
# Fontes de dados
# ═══════════════════════════════════════════════════════════════

# URL alternativa (GitHub público mirror mantido por devs brasileiros)
# Oferece CSV UTF-8 já limpo. Referência: https://github.com/thiagodp/cid10-json
CID10_CSV_URL = (
    "https://raw.githubusercontent.com/thiagodp/cid10-json/master/cid10-subcategorias.json"
)

# Fallback embarcado: dataset mínimo hardcoded para não bloquear o deploy
# em ambientes sem internet externa. Cobre as condições mais frequentes
# em geriatria. Ampliado via download quando disponível.
SEED_GERIATRIC_FALLBACK = [
    # Cardiovasculares
    {"code": "I10", "description_pt": "Hipertensão essencial (primária)",
     "synonyms": ["pressão alta", "hipertensão", "hipertensão arterial", "HAS"]},
    {"code": "I50", "description_pt": "Insuficiência cardíaca",
     "synonyms": ["insuficiência cardíaca congestiva", "ICC", "IC"]},
    {"code": "I50.0", "description_pt": "Insuficiência cardíaca congestiva",
     "synonyms": ["ICC"], "parent_code": "I50"},
    {"code": "I21", "description_pt": "Infarto agudo do miocárdio",
     "synonyms": ["IAM", "infarto", "ataque cardíaco"]},
    {"code": "I48", "description_pt": "Fibrilação e flutter atrial",
     "synonyms": ["fibrilação atrial", "FA"]},
    {"code": "I63", "description_pt": "Infarto cerebral",
     "synonyms": ["AVC isquêmico", "AVC"]},
    {"code": "I64", "description_pt": "Acidente vascular cerebral (AVC)",
     "synonyms": ["AVC", "derrame", "acidente cerebrovascular"]},
    {"code": "I95", "description_pt": "Hipotensão",
     "synonyms": ["pressão baixa"]},
    {"code": "I95.1", "description_pt": "Hipotensão ortostática",
     "synonyms": ["hipotensão postural", "tontura ao levantar"], "parent_code": "I95"},

    # Endócrinas e metabólicas
    {"code": "E11", "description_pt": "Diabetes mellitus não-insulino-dependente",
     "synonyms": ["diabetes tipo 2", "DM2", "DM tipo 2"]},
    {"code": "E10", "description_pt": "Diabetes mellitus insulino-dependente",
     "synonyms": ["diabetes tipo 1", "DM1"]},
    {"code": "E03", "description_pt": "Outros hipotireoidismos",
     "synonyms": ["hipotireoidismo"]},
    {"code": "E78", "description_pt": "Distúrbios do metabolismo de lipoproteínas",
     "synonyms": ["dislipidemia", "colesterol alto"]},
    {"code": "E66", "description_pt": "Obesidade",
     "synonyms": ["obesidade", "sobrepeso"]},

    # Neurológicas (comum em idosos)
    {"code": "G20", "description_pt": "Doença de Parkinson",
     "synonyms": ["Parkinson", "mal de Parkinson", "DP"]},
    {"code": "G30", "description_pt": "Doença de Alzheimer",
     "synonyms": ["Alzheimer", "DA", "mal de Alzheimer"]},
    {"code": "F03", "description_pt": "Demência não especificada",
     "synonyms": ["demência"]},
    {"code": "F01", "description_pt": "Demência vascular",
     "synonyms": ["demência vascular"]},
    {"code": "G40", "description_pt": "Epilepsia",
     "synonyms": ["epilepsia", "convulsões"]},
    {"code": "R26", "description_pt": "Anormalidades da marcha e da mobilidade",
     "synonyms": ["distúrbio da marcha"]},
    {"code": "R29.6", "description_pt": "Tendência a cair, não classificada em outra parte",
     "synonyms": ["quedas recorrentes", "síndrome da queda"]},

    # Osteomusculares
    {"code": "M19", "description_pt": "Outras artroses",
     "synonyms": ["artrose", "osteoartrite"]},
    {"code": "M15", "description_pt": "Poliartrose",
     "synonyms": ["artrose generalizada"]},
    {"code": "M16", "description_pt": "Coxartrose (artrose do quadril)",
     "synonyms": ["artrose do quadril"]},
    {"code": "M17", "description_pt": "Gonartrose (artrose do joelho)",
     "synonyms": ["artrose do joelho"]},
    {"code": "M81", "description_pt": "Osteoporose sem fratura patológica",
     "synonyms": ["osteoporose"]},
    {"code": "M80", "description_pt": "Osteoporose com fratura patológica",
     "synonyms": ["osteoporose com fratura"]},
    {"code": "M54", "description_pt": "Dorsalgia",
     "synonyms": ["dor nas costas", "lombalgia"]},

    # Respiratórias
    {"code": "J44", "description_pt": "Outras doenças pulmonares obstrutivas crônicas",
     "synonyms": ["DPOC", "enfisema"]},
    {"code": "J45", "description_pt": "Asma",
     "synonyms": ["asma brônquica"]},
    {"code": "J18", "description_pt": "Pneumonia por microorganismo não especificado",
     "synonyms": ["pneumonia"]},

    # Geniturinárias
    {"code": "N39.0", "description_pt": "Infecção do trato urinário",
     "synonyms": ["ITU", "infecção urinária", "cistite"]},
    {"code": "N40", "description_pt": "Hiperplasia da próstata",
     "synonyms": ["próstata aumentada", "HPB"]},
    {"code": "N18", "description_pt": "Doença renal crônica",
     "synonyms": ["DRC", "insuficiência renal crônica"]},

    # Digestivas
    {"code": "K21", "description_pt": "Doença de refluxo gastroesofágico",
     "synonyms": ["refluxo", "DRGE"]},
    {"code": "K29", "description_pt": "Gastrite e duodenite",
     "synonyms": ["gastrite"]},
    {"code": "K59.0", "description_pt": "Constipação",
     "synonyms": ["prisão de ventre", "constipação intestinal"]},

    # Saúde mental
    {"code": "F32", "description_pt": "Episódios depressivos",
     "synonyms": ["depressão"]},
    {"code": "F41", "description_pt": "Outros transtornos ansiosos",
     "synonyms": ["ansiedade", "transtorno de ansiedade"]},
    {"code": "F05", "description_pt": "Delirium não induzido pelo álcool ou por outras substâncias",
     "synonyms": ["delirium", "confusão mental aguda"]},
    {"code": "G47", "description_pt": "Distúrbios do sono",
     "synonyms": ["insônia", "distúrbio do sono"]},

    # Síndromes geriátricas importantes
    {"code": "R41", "description_pt": "Outros sintomas e sinais relativos à função cognitiva",
     "synonyms": ["comprometimento cognitivo", "CCL"]},
    {"code": "R55", "description_pt": "Síncope e colapso",
     "synonyms": ["síncope", "desmaio"]},
    {"code": "R42", "description_pt": "Tontura e instabilidade",
     "synonyms": ["tontura", "vertigem", "instabilidade"]},
    {"code": "E86", "description_pt": "Depleção de volume",
     "synonyms": ["desidratação"]},
    {"code": "Z74.3", "description_pt": "Necessidade de supervisão continuada",
     "synonyms": ["idoso dependente"]},
    {"code": "Z91.81", "description_pt": "Histórico de queda",
     "synonyms": ["histórico de quedas"]},

    # Outras
    {"code": "D64.9", "description_pt": "Anemia não especificada",
     "synonyms": ["anemia"]},
    {"code": "H40", "description_pt": "Glaucoma",
     "synonyms": ["glaucoma"]},
    {"code": "H25", "description_pt": "Catarata senil",
     "synonyms": ["catarata"]},
    {"code": "H90", "description_pt": "Perda de audição por transtorno de condução ou neuro-sensorial",
     "synonyms": ["presbiacusia", "perda auditiva"]},
]


# ═══════════════════════════════════════════════════════════════
# Importação
# ═══════════════════════════════════════════════════════════════

def fetch_datasus_cid10() -> list[dict] | None:
    """Tenta baixar o CID-10 completo do mirror GitHub DATASUS."""
    try:
        logger.info("fetching_cid10", url=CID10_CSV_URL)
        resp = httpx.get(CID10_CSV_URL, timeout=60.0)
        if resp.status_code != 200:
            logger.warning("cid10_fetch_non200", status=resp.status_code)
            return None
        import json as _json
        data = _json.loads(resp.text)
        # Formato esperado: [{"codigo": "A00", "descricao": "..."}, ...]
        if not isinstance(data, list):
            return None
        parsed = []
        for item in data:
            code = (item.get("codigo") or item.get("code") or "").strip()
            desc = (item.get("descricao") or item.get("description") or "").strip()
            if code and desc:
                parsed.append({"code": code, "description_pt": desc})
        logger.info("cid10_fetched", items=len(parsed))
        return parsed
    except Exception as exc:
        logger.warning("cid10_fetch_failed", error=str(exc))
        return None


def enrich_with_synonyms(items: list[dict]) -> list[dict]:
    """Mescla com o seed hardcoded — adiciona sinônimos + flag is_geriatric_common."""
    by_code = {it["code"]: it for it in items}
    for seed in SEED_GERIATRIC_FALLBACK:
        code = seed["code"]
        if code in by_code:
            by_code[code]["synonyms"] = seed.get("synonyms", [])
            by_code[code]["is_geriatric_common"] = True
            if seed.get("parent_code"):
                by_code[code]["parent_code"] = seed["parent_code"]
        else:
            # Adiciona item novo (seed standalone)
            by_code[code] = {
                **seed,
                "is_geriatric_common": True,
            }
    return list(by_code.values())


def insert_batch(items: list[dict]) -> int:
    db = get_postgres()
    ok = 0
    for item in items:
        try:
            code = item["code"]
            family = code.split(".")[0]
            parent = item.get("parent_code")
            is_sub = "." in code

            db.execute(
                """
                INSERT INTO aia_health_disease_catalog
                    (system, version, code, code_family, description_pt, synonyms,
                     is_subcategory, parent_code, is_geriatric_common)
                VALUES ('icd10-datasus', '2008', %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (system, code) DO UPDATE SET
                    description_pt = EXCLUDED.description_pt,
                    synonyms = EXCLUDED.synonyms,
                    is_geriatric_common = aia_health_disease_catalog.is_geriatric_common OR EXCLUDED.is_geriatric_common,
                    updated_at = NOW()
                """,
                (
                    code, family, item["description_pt"],
                    item.get("synonyms") or [],
                    is_sub, parent,
                    bool(item.get("is_geriatric_common")),
                ),
            )
            ok += 1
        except Exception as exc:
            logger.warning("cid10_insert_failed", code=item.get("code"), error=str(exc))
    return ok


def main():
    logger.info("import_cid10_start")
    items = fetch_datasus_cid10() or []
    if not items:
        logger.warning("cid10_fallback_to_seed_only")
    items = enrich_with_synonyms(items)
    logger.info("import_cid10_total", count=len(items))

    ok = insert_batch(items)
    logger.info("import_cid10_complete", inserted=ok)


if __name__ == "__main__":
    main()
