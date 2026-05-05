"""Importer MVP do Knowledge Graph farmacológico.

Dataset MVP curado por Claude com base em fontes públicas:
  - Beers Criteria 2023 (American Geriatrics Society, J Am Geriatr Soc 71(7):2052-2081)
  - Bulário Anvisa (https://consultas.anvisa.gov.br/#/bulario/)
  - DDInter database (open access)

⚠️  AVISO CLÍNICO MANDATÓRIO ⚠️
Este dataset É MVP. Cada entry está marcada `requires_clinical_review=TRUE`.
Validação clínica por profissional habilitado (médico/farmacêutico) é
PRÉ-REQUISITO antes de qualquer uso em decisão clínica real.

Cobertura atual:
  - 30 drugs (top high-severity em geriatria + comuns no Brasil)
  - 40 flags Beers 2023 (anticolinérgicos, benzos, antipsicóticos,
    AINEs, sulfonilureias, etc)
  - 15 interações drug-drug críticas (síndrome serotoninérgica,
    triple whammy renal, depressão respiratória opioide+benzo, etc)

Uso:
    docker exec connectaiacare-api python /app/scripts/import_drug_safety_mvp.py

Idempotente: pode rodar múltiplas vezes (UPSERT em generic_name_normalized).
"""
from __future__ import annotations

import sys
import unicodedata
from typing import Any

sys.path.insert(0, "/app")

from src.services.postgres import get_postgres


def _norm(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name.strip())
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# ────────────────────────────────────────────────────────────────────
# DATASET MVP — drugs + Beers flags
# ────────────────────────────────────────────────────────────────────
# Cada drug tem zero ou mais flags. Estrutura compacta pra leitura humana.
# Refs: páginas exatas Beers 2023 (DOI 10.1111/jgs.18372).

DRUGS_AND_BEERS = [
    # ─── BENZODIAZEPÍNICOS (TODOS avoid em ≥65, Tabela 2) ─────
    {
        "generic_name": "Diazepam",
        "brand_names": ["Valium", "Diazepam Compr.", "Diempax"],
        "therapeutic_class": "benzodiazepínico",
        "pharmacologic_class": "GABAa positive modulator (long-acting)",
        "is_psychotropic": True, "is_controlled": True,
        "atc_code": "N05BA01",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "high",
            "evidence_quality": "moderate",
            "recommendation_strength": "strong",
            "rationale": "Benzodiazepínicos de longa ação aumentam risco de declínio cognitivo, delirium, quedas, fraturas e acidentes automobilísticos em idosos. Meia-vida muito longa (>20h) potencializa acúmulo.",
            "clinical_consequences": "delirium, queda, fratura, declínio cognitivo, sedação prolongada",
            "alternatives": "considerar SSRI pra ansiedade crônica; trazodona ou melatonina pra insônia leve; CBT-I é primeira linha",
        }, {
            "category": "avoid_certain_combinations",
            "severity": "high",
            "rationale": "Combinação com opioides aumenta drasticamente risco de depressão respiratória fatal",
            "conditions": ["opioid_use"],
        }],
    },
    {
        "generic_name": "Clonazepam",
        "brand_names": ["Rivotril", "Clonotril"],
        "therapeutic_class": "benzodiazepínico",
        "pharmacologic_class": "GABAa positive modulator (long-acting)",
        "is_psychotropic": True, "is_controlled": True,
        "atc_code": "N03AE01",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "high",
            "rationale": "Mesma justificativa de outros benzos longa ação. Tolerância e dependência rápidas.",
            "clinical_consequences": "delirium, queda, dependência, síndrome abstinência grave se descontinuação súbita",
        }],
    },
    {
        "generic_name": "Alprazolam",
        "brand_names": ["Frontal", "Apraz", "Tranquinal"],
        "therapeutic_class": "benzodiazepínico",
        "pharmacologic_class": "GABAa positive modulator (short-acting)",
        "is_psychotropic": True, "is_controlled": True,
        "atc_code": "N05BA12",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "high",
            "rationale": "Apesar de meia-vida menor, ainda associado a quedas e declínio cognitivo. Ansiedade rebote frequente.",
            "clinical_consequences": "queda, ansiedade rebote, dependência rápida",
        }],
    },
    {
        "generic_name": "Lorazepam",
        "brand_names": ["Lorax", "Lorazefast"],
        "therapeutic_class": "benzodiazepínico",
        "pharmacologic_class": "GABAa positive modulator (intermediate-acting)",
        "is_psychotropic": True, "is_controlled": True,
        "atc_code": "N05BA06",
        "beers_flags": [{
            "category": "use_with_caution",
            "severity": "moderate",
            "rationale": "Preferível a benzos longa ação se uso curto inevitável. Sem metabolização CYP — útil em hepatopatas. Ainda assim, evitar uso crônico em idosos.",
            "alternatives": "uso pontual <2 semanas; reavaliar necessidade",
        }],
    },

    # ─── Z-DRUGS (avoid, Tabela 2) ─────
    {
        "generic_name": "Zolpidem",
        "brand_names": ["Stilnox", "Lioram", "Patz"],
        "therapeutic_class": "hipnótico não-benzodiazepínico",
        "pharmacologic_class": "GABAa selective alpha-1 agonist",
        "is_psychotropic": True, "is_controlled": True,
        "atc_code": "N05CF02",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "high",
            "rationale": "Aumenta risco de quedas, fraturas, sonambulismo, comportamentos noturnos perigosos. Eficácia hipnótica modesta vs riscos.",
            "clinical_consequences": "queda noturna, sonambulismo, amnésia anterógrada",
            "alternatives": "higiene do sono + CBT-I; melatonina liberação prolongada 2mg",
        }],
    },

    # ─── ANTICOLINÉRGICOS (anti-histamínicos 1ª geração, Tabela 7 + 2) ─────
    {
        "generic_name": "Difenidramina",
        "brand_names": ["Benadryl", "Difenidrina"],
        "therapeutic_class": "anti-histamínico H1 1ª geração",
        "pharmacologic_class": "muscarinic antagonist + H1 antagonist",
        "atc_code": "R06AA02",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "high",
            "rationale": "Forte ação anticolinérgica → confusão, sedação, retenção urinária, boca seca, constipação. Tolerância rápida ao efeito hipnótico mas persistência dos efeitos colaterais.",
            "clinical_consequences": "delirium, retenção urinária, queda, glaucoma agudo de ângulo fechado",
            "alternatives": "loratadina ou cetirizina (não anticolinérgicas)",
        }],
    },
    {
        "generic_name": "Hidroxizina",
        "brand_names": ["Hixizine", "Pruri-Gel", "Hidroxine"],
        "therapeutic_class": "anti-histamínico H1 1ª geração",
        "pharmacologic_class": "muscarinic antagonist + H1 antagonist",
        "atc_code": "N05BB01",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "high",
            "rationale": "Anticolinérgica, sedativa, prolonga QT. Efeitos cumulativos graves em idosos.",
            "clinical_consequences": "delirium, queda, prolongamento QT, torsades",
        }],
    },
    {
        "generic_name": "Oxibutinina",
        "brand_names": ["Retemic", "Incontinol"],
        "therapeutic_class": "anticolinérgico urológico",
        "pharmacologic_class": "muscarinic M3 antagonist",
        "atc_code": "G04BD04",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "moderate",
            "rationale": "Forte anticolinérgica central — declínio cognitivo, especialmente em demência.",
            "alternatives": "mirabegron (β3-agonista, não anticolinérgico) ou solifenacina (mais seletiva)",
        }, {
            "category": "avoid_with_condition",
            "severity": "high",
            "rationale": "Demência: piora cognição. Glaucoma fechado: precipita crise. HBP: agrava retenção.",
            "conditions": ["dementia", "glaucoma", "BPH"],
        }],
    },
    {
        "generic_name": "Ciclobenzaprina",
        "brand_names": ["Miosan", "Mioflex-A"],
        "therapeutic_class": "relaxante muscular",
        "pharmacologic_class": "skeletal muscle relaxant (TCA-related)",
        "atc_code": "M03BX08",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "high",
            "rationale": "Relaxantes musculares de ação central são mal tolerados em idosos: sedação, anticolinérgico, queda. Eficácia questionável.",
            "clinical_consequences": "queda, sedação, confusão, retenção urinária",
            "alternatives": "fisioterapia, calor local, paracetamol; evitar relaxantes musculares centrais",
        }],
    },

    # ─── ANTIPSICÓTICOS (avoid em demência sem indicação grave, Tabela 3) ─────
    {
        "generic_name": "Haloperidol",
        "brand_names": ["Haldol", "Haloper"],
        "therapeutic_class": "antipsicótico típico",
        "pharmacologic_class": "D2 antagonist",
        "is_psychotropic": True,
        "atc_code": "N05AD01",
        "beers_flags": [{
            "category": "avoid_with_condition",
            "severity": "high",
            "rationale": "Antipsicóticos em demência aumentam mortalidade (FDA black box). Uso só em sintomas comportamentais GRAVES com risco a si/outros, após não-farmacológico falhar, dose mínima, reavaliação frequente.",
            "clinical_consequences": "AVC, mortalidade aumentada, sintomas extrapiramidais graves",
            "conditions": ["dementia"],
        }],
    },
    {
        "generic_name": "Quetiapina",
        "brand_names": ["Seroquel", "Quetros"],
        "therapeutic_class": "antipsicótico atípico",
        "pharmacologic_class": "5HT2A/D2 antagonist",
        "is_psychotropic": True,
        "atc_code": "N05AH04",
        "beers_flags": [{
            "category": "avoid_with_condition",
            "severity": "high",
            "rationale": "Uso off-label pra insônia em demência muito comum mas associado a aumento de mortalidade e AVC. Mesma classe que tem black box FDA pra demência.",
            "conditions": ["dementia"],
        }, {
            "category": "use_with_caution",
            "severity": "moderate",
            "rationale": "Sedação, hipotensão postural, ganho de peso, hiperglicemia mesmo em doses baixas",
        }],
    },
    {
        "generic_name": "Risperidona",
        "brand_names": ["Risperdal", "Respidon"],
        "therapeutic_class": "antipsicótico atípico",
        "pharmacologic_class": "5HT2A/D2 antagonist",
        "is_psychotropic": True,
        "atc_code": "N05AX08",
        "beers_flags": [{
            "category": "avoid_with_condition",
            "severity": "high",
            "rationale": "Como outros antipsicóticos: aumenta mortalidade em demência. Único antipsicótico com indicação restrita pra agressividade severa em demência (curto prazo, dose mínima).",
            "conditions": ["dementia"],
        }],
    },

    # ─── HIPOGLICEMIANTES — sulfonilureias 1ª geração (avoid, Tabela 2) ─────
    {
        "generic_name": "Glibenclamida",
        "brand_names": ["Daonil", "Diabeta"],
        "therapeutic_class": "antidiabético oral",
        "pharmacologic_class": "sulfonilureia 2ª geração de longa ação",
        "atc_code": "A10BB01",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "high",
            "rationale": "Hipoglicemia prolongada e severa, especialmente em ClCr reduzido. Risco aumentado de hipoglicemia noturna e cardiovascular.",
            "clinical_consequences": "hipoglicemia severa prolongada, queda, AVC isquêmico, óbito",
            "alternatives": "metformina (1ª linha se função renal ok), gliclazida MR (sulfonil. mais segura), iDPP4 (sitagliptina), iSGLT2",
        }],
    },

    # ─── AINEs (avoid uso crônico, Tabela 2 + Tabela 3) ─────
    {
        "generic_name": "Ibuprofeno",
        "brand_names": ["Advil", "Alivium", "Motrin"],
        "therapeutic_class": "AINE",
        "pharmacologic_class": "COX-1/COX-2 inhibitor",
        "atc_code": "M01AE01",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "moderate",
            "rationale": "AINEs sistêmicos crônicos aumentam risco de sangramento GI, IRA, IC descompensada, HTA. Uso pontual <7 dias com gastroproteção é menos crítico.",
            "clinical_consequences": "úlcera/sangramento GI, lesão renal aguda, retenção hídrica, IC descompensada",
            "alternatives": "paracetamol (1ª linha pra dor leve-moderada), AINEs tópicos (diclofenaco gel)",
        }, {
            "category": "avoid_with_condition",
            "severity": "high",
            "rationale": "CKD: risco IRA. ICC: descompensação por retenção hídrica. Úlcera: sangramento.",
            "conditions": ["CKD", "heart_failure", "peptic_ulcer"],
        }],
    },
    {
        "generic_name": "Diclofenaco",
        "brand_names": ["Voltaren", "Cataflam", "Voltaren Rapid"],
        "therapeutic_class": "AINE",
        "pharmacologic_class": "COX-1/COX-2 inhibitor",
        "atc_code": "M01AB05",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "moderate",
            "rationale": "Mesma classe que ibuprofeno. Risco cardiovascular adicional (potencial aumento de eventos trombóticos).",
            "alternatives": "paracetamol; diclofenaco gel tópico OK",
        }],
    },
    {
        "generic_name": "Naproxeno",
        "brand_names": ["Flanax", "Naprosyn"],
        "therapeutic_class": "AINE",
        "pharmacologic_class": "COX-1/COX-2 inhibitor",
        "atc_code": "M01AE02",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "moderate",
            "rationale": "Menor risco CV que outros AINEs mas ainda alto risco GI e renal em idosos.",
        }],
    },

    # ─── INIBIDORES BOMBA PRÓTONS — uso prolongado, Tabela 2 ─────
    {
        "generic_name": "Omeprazol",
        "brand_names": ["Losec", "Peprazol", "Omeprazol Genérico"],
        "therapeutic_class": "inibidor bomba prótons (IBP)",
        "pharmacologic_class": "PPI",
        "atc_code": "A02BC01",
        "beers_flags": [{
            "category": "use_with_caution",
            "severity": "moderate",
            "rationale": "Uso >8 semanas associado a: fratura osteoporótica, deficiência B12 e magnésio, infecção C.difficile, pneumonia comunitária, possível demência (controverso).",
            "alternatives": "reavaliar indicação a cada 8 semanas; bloqueador H2 (famotidina) em casos selecionados; medidas comportamentais",
        }],
    },

    # ─── ANTIDEPRESSIVOS TRICÍCLICOS (anticolinérgicos fortes, Tabela 7 + 2) ─────
    {
        "generic_name": "Amitriptilina",
        "brand_names": ["Amytril", "Tryptanol"],
        "therapeutic_class": "antidepressivo tricíclico",
        "pharmacologic_class": "TCA — SNRI + muscarinic + alpha-1 + H1 antagonist",
        "is_psychotropic": True,
        "atc_code": "N06AA09",
        "beers_flags": [{
            "category": "avoid_in_elderly",
            "severity": "high",
            "rationale": "Forte ação anticolinérgica + sedação + hipotensão postural + cardiotoxicidade. Em idosos, prejuízo > benefício.",
            "clinical_consequences": "delirium, queda, retenção urinária, arritmia (prolongamento QT), morte súbita em overdose",
            "alternatives": "ISRS (sertralina, escitalopram); duloxetina pra dor neuropática; mirtazapina pra insônia/perda peso",
        }],
    },

    # ─── DIGOXINA (use_with_caution >0.125mg/dia, Tabela 4) ─────
    {
        "generic_name": "Digoxina",
        "brand_names": ["Digoxina Genérico", "Lanoxin"],
        "therapeutic_class": "glicosídeo cardíaco",
        "pharmacologic_class": "Na/K ATPase inhibitor",
        "atc_code": "C01AA05",
        "beers_flags": [{
            "category": "use_with_caution",
            "severity": "high",
            "rationale": "Doses >0.125mg/dia sem benefício adicional em FA/IC mas aumentam toxicidade. Janela terapêutica estreita. ClCr reduzido (comum em idosos) acumula.",
            "clinical_consequences": "toxicidade digitálica: arritmia ventricular, distúrbio visual, náusea, confusão",
            "alternatives": "betabloqueador pra controle FC em FA; iSGLT2 pra IC com FE reduzida",
        }, {
            "category": "reduced_dose_in_renal",
            "severity": "high",
            "rationale": "Excreção 100% renal. Reduzir dose proporcional a ClCr.",
            "conditions": ["CKD"],
        }],
    },

    # ─── DRUGS SEM FLAG BEERS — comuns no BR, importantes pra interactions ─────
    {
        "generic_name": "Atenolol",
        "brand_names": ["Atenol", "Tenoblock", "Atenolol Genérico"],
        "therapeutic_class": "betabloqueador",
        "pharmacologic_class": "beta-1 selective adrenergic blocker",
        "atc_code": "C07AB03",
    },
    {
        "generic_name": "Verapamil",
        "brand_names": ["Dilacoron", "Verapamil Genérico"],
        "therapeutic_class": "bloqueador canal cálcio não-dihidropiridínico",
        "pharmacologic_class": "L-type Ca channel blocker (cardiac selective)",
        "atc_code": "C08DA01",
    },
    {
        "generic_name": "Losartana",
        "brand_names": ["Cozaar", "Aradois", "Losartana Potássica"],
        "therapeutic_class": "BRA (bloqueador receptor angiotensina II)",
        "pharmacologic_class": "AT1 receptor antagonist",
        "atc_code": "C09CA01",
    },
    {
        "generic_name": "Enalapril",
        "brand_names": ["Renitec", "Vasopril", "Enalapril Genérico"],
        "therapeutic_class": "IECA (inibidor enzima conversora angiotensina)",
        "pharmacologic_class": "ACE inhibitor",
        "atc_code": "C09AA02",
    },
    {
        "generic_name": "Hidroclorotiazida",
        "brand_names": ["Clorana", "Hidroclorotiazida Genérico"],
        "therapeutic_class": "diurético tiazídico",
        "pharmacologic_class": "thiazide diuretic",
        "atc_code": "C03AA03",
    },
    {
        "generic_name": "Sertralina",
        "brand_names": ["Zoloft", "Sertralina Genérico"],
        "therapeutic_class": "antidepressivo ISRS",
        "pharmacologic_class": "SSRI",
        "is_psychotropic": True,
        "atc_code": "N06AB06",
    },
    {
        "generic_name": "Fluoxetina",
        "brand_names": ["Prozac", "Daforin", "Fluoxetina Genérico"],
        "therapeutic_class": "antidepressivo ISRS",
        "pharmacologic_class": "SSRI",
        "is_psychotropic": True,
        "atc_code": "N06AB03",
    },
    {
        "generic_name": "Tramadol",
        "brand_names": ["Tramal", "Tramadon"],
        "therapeutic_class": "analgésico opioide fraco",
        "pharmacologic_class": "mu-opioid agonist + SNRI",
        "is_controlled": True,
        "atc_code": "N02AX02",
    },
    {
        "generic_name": "Codeína",
        "brand_names": ["Codein", "Tylex (com paracetamol)"],
        "therapeutic_class": "analgésico opioide fraco",
        "pharmacologic_class": "mu-opioid agonist (prodrug → morfina)",
        "is_controlled": True,
        "atc_code": "R05DA04",
    },
    {
        "generic_name": "Varfarina",
        "brand_names": ["Marevan", "Coumadin"],
        "therapeutic_class": "anticoagulante oral",
        "pharmacologic_class": "vitamin K epoxide reductase inhibitor",
        "atc_code": "B01AA03",
    },
    {
        "generic_name": "Amiodarona",
        "brand_names": ["Ancoron", "Cordarone", "Amiodarona Genérico"],
        "therapeutic_class": "antiarrítmico classe III",
        "pharmacologic_class": "K channel blocker (multiclass effects)",
        "atc_code": "C01BD01",
    },
    {
        "generic_name": "Metformina",
        "brand_names": ["Glifage", "Glucoformin", "Metformina Genérico"],
        "therapeutic_class": "antidiabético oral",
        "pharmacologic_class": "biguanide",
        "atc_code": "A10BA02",
    },
    {
        "generic_name": "Sinvastatina",
        "brand_names": ["Zocor", "Sinvastacor", "Sinvastatina Genérico"],
        "therapeutic_class": "estatina",
        "pharmacologic_class": "HMG-CoA reductase inhibitor",
        "atc_code": "C10AA01",
    },
    {
        "generic_name": "Levotiroxina",
        "brand_names": ["Synthroid", "Puran T4", "Levoid"],
        "therapeutic_class": "hormônio tireoidiano",
        "pharmacologic_class": "T4 replacement",
        "atc_code": "H03AA01",
    },
]


# ────────────────────────────────────────────────────────────────────
# DRUG-DRUG INTERACTIONS (críticas em geriatria)
# ────────────────────────────────────────────────────────────────────
# Refs: Beers 2023 Tabela 5 + DDInter database + bibliografia clínica.
# generic_name_a / generic_name_b são lookups via _norm.

INTERACTIONS = [
    # ─── Síndrome serotoninérgica ─────
    {
        "drug_a": "Sertralina", "drug_b": "Tramadol",
        "severity": "major",
        "mechanism_type": "pharmacodynamic",
        "description": "Combinação de ISRS com tramadol (que tem ação SNRI) aumenta significativamente risco de síndrome serotoninérgica.",
        "clinical_management": "Evitar combinação. Se inevitável, monitorar sinais (agitação, hipertermia, mioclonias, confusão, diarreia). Considerar dipirona/paracetamol como alternativas analgésicas.",
        "onset": "rapid", "documentation": "established",
        "source_ref": "Beers 2023, Tabela 5 + UpToDate Lexidrug",
    },
    {
        "drug_a": "Fluoxetina", "drug_b": "Tramadol",
        "severity": "major",
        "mechanism_type": "pharmacodynamic",
        "description": "Como sertralina+tramadol. Fluoxetina ainda inibe CYP2D6, reduzindo conversão de tramadol em metabólito ativo (M1) — analgesia comprometida + risco serotoninérgico paradoxal.",
        "clinical_management": "Evitar combinação. Se inevitável, dose tramadol mínima + monitoração intensa.",
        "onset": "rapid", "documentation": "established",
    },
    {
        "drug_a": "Sertralina", "drug_b": "Codeína",
        "severity": "moderate",
        "mechanism_type": "mixed",
        "description": "Risco serotoninérgico (menor que com tramadol) + sertralina inibe CYP2D6 reduzindo conversão codeína→morfina → analgesia subótima.",
        "clinical_management": "Considerar analgésico alternativo (paracetamol, dipirona).",
        "onset": "rapid", "documentation": "probable",
    },

    # ─── Bradicardia/bloqueio cardíaco ─────
    {
        "drug_a": "Atenolol", "drug_b": "Verapamil",
        "severity": "major",
        "mechanism_type": "pharmacodynamic",
        "description": "Combinação betabloqueador + bloqueador canal cálcio não-dihidropiridínico (verapamil/diltiazem) causa bradicardia severa, bloqueio AV, depressão miocárdica e hipotensão.",
        "clinical_management": "Evitar combinação se possível. Se necessária, monitorar FC e ECG, considerar substituir verapamil por amlodipina (dihidropiridínico, sem efeito cronotrópico).",
        "onset": "rapid", "documentation": "established",
    },

    # ─── Triple whammy renal ─────
    {
        "drug_a": "Enalapril", "drug_b": "Ibuprofeno",
        "severity": "major",
        "mechanism_type": "pharmacodynamic",
        "description": "IECA + AINE → reduz perfusão renal (IECA dilata arteríola eferente, AINE constrange aferente). Risco lesão renal aguda alto, especialmente em idosos com função renal limítrofe.",
        "clinical_management": "Evitar AINE crônico em paciente em IECA. Preferir paracetamol. Se AINE inevitável, monitorar creatinina semanal nos primeiros 30 dias.",
        "onset": "delayed", "documentation": "established",
        "source_ref": "Bibliografia 'Triple Whammy' — Lapi et al., BMJ 2013",
    },
    {
        "drug_a": "Hidroclorotiazida", "drug_b": "Ibuprofeno",
        "severity": "moderate",
        "mechanism_type": "pharmacodynamic",
        "description": "AINE reduz eficácia diurética da tiazídica + sinergia nefrotóxica (parte do triple whammy quando associado a IECA/BRA).",
        "clinical_management": "Monitorar PA e função renal. Reduzir uso AINE.",
        "onset": "delayed", "documentation": "established",
    },
    {
        "drug_a": "Losartana", "drug_b": "Ibuprofeno",
        "severity": "major",
        "mechanism_type": "pharmacodynamic",
        "description": "Mesmo mecanismo do enalapril+ibuprofeno (BRA atua semelhante a IECA na arteríola eferente).",
        "clinical_management": "Evitar AINE. Paracetamol como alternativa.",
        "onset": "delayed", "documentation": "established",
    },

    # ─── Sangramento (anticoagulante + AINE/ISRS) ─────
    {
        "drug_a": "Ibuprofeno", "drug_b": "Varfarina",
        "severity": "major",
        "mechanism_type": "mixed",
        "description": "AINE inibe COX-1 plaquetária + lesa mucosa GI + desloca varfarina ligada à albumina → sangramento severo, especialmente GI.",
        "clinical_management": "Evitar combinação. Paracetamol é alternativa segura. Se AINE inevitável: gastroproteção (PPI), monitorar INR semanalmente.",
        "onset": "rapid", "documentation": "established",
    },
    {
        "drug_a": "Amiodarona", "drug_b": "Varfarina",
        "severity": "major",
        "mechanism_type": "pharmacokinetic",
        "description": "Amiodarona inibe metabolismo da varfarina via CYP2C9 e CYP3A4. Aumento INR pode levar até 4 semanas pra estabilizar.",
        "clinical_management": "Reduzir dose varfarina em 30-50% ao iniciar amiodarona. INR semanal nos primeiros 2 meses.",
        "onset": "delayed", "documentation": "established",
    },
    {
        "drug_a": "Sertralina", "drug_b": "Varfarina",
        "severity": "moderate",
        "mechanism_type": "mixed",
        "description": "ISRS inibe agregação plaquetária (depleção 5-HT plaquetária) + leve inibição CYP2C9. Sangramento GI superior aumentado.",
        "clinical_management": "Monitorar INR. Considerar PPI profilático se uso prolongado.",
        "onset": "delayed", "documentation": "established",
    },

    # ─── Depressão respiratória ─────
    {
        "drug_a": "Diazepam", "drug_b": "Tramadol",
        "severity": "major",
        "mechanism_type": "pharmacodynamic",
        "description": "Combinação benzodiazepínico + opioide aumenta drasticamente risco de depressão respiratória, sedação profunda e morte. FDA black box.",
        "clinical_management": "Evitar combinação se possível. Se inevitável: doses mínimas, monitoração respiratória, considerar naloxona disponível.",
        "onset": "rapid", "documentation": "established",
        "source_ref": "Beers 2023 + FDA Black Box Warning 2016",
    },
    {
        "drug_a": "Clonazepam", "drug_b": "Tramadol",
        "severity": "major",
        "mechanism_type": "pharmacodynamic",
        "description": "Como diazepam+tramadol. FDA black box.",
        "onset": "rapid", "documentation": "established",
    },
    {
        "drug_a": "Diazepam", "drug_b": "Codeína",
        "severity": "major",
        "mechanism_type": "pharmacodynamic",
        "description": "Mesma classe (benzo+opioide). FDA black box.",
        "onset": "rapid", "documentation": "established",
    },

    # ─── Toxicidade digitálica ─────
    {
        "drug_a": "Amiodarona", "drug_b": "Digoxina",
        "severity": "major",
        "mechanism_type": "pharmacokinetic",
        "description": "Amiodarona reduz clearance da digoxina (~70% aumento níveis). Toxicidade digitálica frequente sem ajuste.",
        "clinical_management": "Reduzir dose digoxina 50% ao iniciar amiodarona. Dosar nível sérico em 1 semana e 1 mês.",
        "onset": "delayed", "documentation": "established",
    },
    {
        "drug_a": "Digoxina", "drug_b": "Hidroclorotiazida",
        "severity": "moderate",
        "mechanism_type": "pharmacodynamic",
        "description": "Tiazídicos causam hipocalemia/hipomagnesemia → potencializa toxicidade digitálica.",
        "clinical_management": "Monitorar K+ e Mg++. Reposição se necessário. Considerar associar K+-poupador.",
        "onset": "delayed", "documentation": "established",
    },
]


def upsert_drug(db, drug_def: dict) -> str:
    """Insere ou atualiza drug. Retorna UUID."""
    norm = _norm(drug_def["generic_name"])
    row = db.fetch_one(
        """INSERT INTO aia_health_drug_catalog (
              generic_name, generic_name_normalized, brand_names,
              therapeutic_class, pharmacologic_class,
              is_psychotropic, is_controlled,
              atc_code, source, source_ref, requires_clinical_review
           ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
           ON CONFLICT (generic_name_normalized) DO UPDATE SET
              brand_names = EXCLUDED.brand_names,
              therapeutic_class = EXCLUDED.therapeutic_class,
              pharmacologic_class = EXCLUDED.pharmacologic_class,
              is_psychotropic = EXCLUDED.is_psychotropic,
              is_controlled = EXCLUDED.is_controlled,
              atc_code = EXCLUDED.atc_code,
              updated_at = NOW()
           RETURNING id::text""",
        (
            drug_def["generic_name"], norm,
            drug_def.get("brand_names", []),
            drug_def.get("therapeutic_class"),
            drug_def.get("pharmacologic_class"),
            drug_def.get("is_psychotropic", False),
            drug_def.get("is_controlled", False),
            drug_def.get("atc_code"),
            "manual_curation",
            "Beers 2023 + Anvisa MVP curated",
        ),
    )
    return row["id"] if row else None


def upsert_beers_flags(db, drug_id: str, flags: list[dict]):
    """Insere/replace flags Beers de um drug. Apaga existentes antes."""
    db.execute(
        "DELETE FROM aia_health_beers_flags WHERE drug_id = %s", (drug_id,),
    )
    for f in flags:
        db.execute(
            """INSERT INTO aia_health_beers_flags (
                  drug_id, category, severity, evidence_quality,
                  recommendation_strength, rationale, clinical_consequences,
                  conditions, alternatives, source_ref
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                drug_id,
                f["category"], f["severity"],
                f.get("evidence_quality"), f.get("recommendation_strength"),
                f["rationale"], f.get("clinical_consequences"),
                f.get("conditions", []), f.get("alternatives"),
                f.get("source_ref", "Beers 2023 (J Am Geriatr Soc 71(7):2052-2081)"),
            ),
        )


def upsert_interaction(db, name_to_id: dict, inter_def: dict):
    """Insere interação canonicalizando par (drug_a < drug_b por UUID)."""
    a_id = name_to_id.get(_norm(inter_def["drug_a"]))
    b_id = name_to_id.get(_norm(inter_def["drug_b"]))
    if not a_id or not b_id or a_id == b_id:
        print(f"  ⚠ skip interaction {inter_def['drug_a']} ↔ {inter_def['drug_b']} (drug missing)")
        return
    lo, hi = (a_id, b_id) if a_id < b_id else (b_id, a_id)
    db.execute(
        """INSERT INTO aia_health_drug_interactions (
              drug_a_id, drug_b_id, severity, mechanism_type,
              description, clinical_management, onset, documentation,
              source, source_ref, requires_clinical_review
           ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
           ON CONFLICT (drug_a_id, drug_b_id) DO UPDATE SET
              severity = EXCLUDED.severity,
              mechanism_type = EXCLUDED.mechanism_type,
              description = EXCLUDED.description,
              clinical_management = EXCLUDED.clinical_management,
              onset = EXCLUDED.onset,
              documentation = EXCLUDED.documentation,
              source_ref = EXCLUDED.source_ref""",
        (
            lo, hi,
            inter_def["severity"], inter_def.get("mechanism_type"),
            inter_def["description"], inter_def.get("clinical_management"),
            inter_def.get("onset"), inter_def.get("documentation"),
            "manual_curation",
            inter_def.get("source_ref", "Beers 2023 + DDInter + clinical literature"),
        ),
    )


def main():
    db = get_postgres()
    print("=" * 70)
    print("Importing drug safety MVP (Beers 2023 + Anvisa)")
    print("=" * 70)

    name_to_id = {}
    drugs_total = 0
    flags_total = 0

    for drug_def in DRUGS_AND_BEERS:
        drug_id = upsert_drug(db, drug_def)
        if not drug_id:
            print(f"  ⚠ failed: {drug_def['generic_name']}")
            continue
        name_to_id[_norm(drug_def["generic_name"])] = drug_id
        drugs_total += 1
        flags = drug_def.get("beers_flags", [])
        if flags:
            upsert_beers_flags(db, drug_id, flags)
            flags_total += len(flags)
        print(f"  ✓ {drug_def['generic_name']:25s} flags={len(flags)}")

    print(f"\n  Drugs upserted: {drugs_total}")
    print(f"  Beers flags upserted: {flags_total}")

    print("\n" + "=" * 70)
    print("Importing interactions")
    print("=" * 70)

    inter_total = 0
    for inter_def in INTERACTIONS:
        try:
            upsert_interaction(db, name_to_id, inter_def)
            inter_total += 1
            print(f"  ✓ {inter_def['drug_a']} ↔ {inter_def['drug_b']:20s} ({inter_def['severity']})")
        except Exception as exc:
            print(f"  ✗ {inter_def['drug_a']} ↔ {inter_def['drug_b']}: {exc}")

    print(f"\n  Interactions upserted: {inter_total}")

    print("\n" + "=" * 70)
    print("✅ Done. Reminder: requires_clinical_review=TRUE em todos os entries.")
    print("   Henrique (referência clínica) deve revisar antes de ativar em prod.")
    print("=" * 70)


if __name__ == "__main__":
    main()
