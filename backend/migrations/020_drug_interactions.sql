-- ConnectaIACare — F2: Drug-Drug Interactions críticas
-- Data: 2026-04-25
--
-- Cruzamento de pares de princípios ativos com efeito clínico documentado.
-- Curadoria Fase 1 — top 40 interações geriátricas mais relevantes.
--
-- Fontes: Critérios de Beers 2023, Stockley's Drug Interactions, FDA
-- DDI database, Lexicomp, bulas ANVISA.
--
-- Severidade clínica:
--   contraindicated = não associar (risco de morte, hemorragia, arritmia)
--   major           = monitorização rigorosa, considerar alternativa
--   moderate        = ajuste de dose ou monitorização
--   minor           = informativo (efeito clínico baixo)

BEGIN;

CREATE TABLE IF NOT EXISTS aia_health_drug_interactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- O par é simétrico — guardamos sempre lex-ordenado (a < b) pra
    -- evitar duplicatas em pares principle×principle ou class×class.
    -- Em pares mistos (principle×class) a coluna oposta fica NULL.
    -- O CHECK abaixo garante que pelo menos um par seja válido.
    principle_a TEXT,
    principle_b TEXT,
    class_a TEXT,
    class_b TEXT,

    severity TEXT NOT NULL CHECK (severity IN (
        'contraindicated', 'major', 'moderate', 'minor'
    )),
    -- Mecanismo curto: "QT prolongation", "Hyperkalemia", "Bleeding risk"
    mechanism TEXT NOT NULL,
    -- Texto humano pt-BR explicando o efeito clínico
    clinical_effect TEXT NOT NULL,
    -- Recomendação prática: "evitar combinação", "espaçar 4h", "monitorar K+"
    recommendation TEXT NOT NULL,
    -- Onset: rapid|delayed|unspecified
    onset TEXT,
    source TEXT NOT NULL CHECK (source IN (
        'beers_2023', 'stockleys', 'lexicomp', 'fda', 'anvisa', 'manual'
    )),
    source_ref TEXT,
    confidence NUMERIC(3,2) NOT NULL DEFAULT 0.85,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Garante que pelo menos um lado seja preenchido (principle ou class)
    CHECK (
        (principle_a IS NOT NULL AND principle_b IS NOT NULL)
        OR (class_a IS NOT NULL AND class_b IS NOT NULL)
        OR (principle_a IS NOT NULL AND class_b IS NOT NULL)
        OR (class_a IS NOT NULL AND principle_b IS NOT NULL)
    )
);

-- Índices pra lookup rápido por par ordenado
CREATE INDEX IF NOT EXISTS idx_drug_interactions_pair_principle
    ON aia_health_drug_interactions(principle_a, principle_b)
    WHERE active = TRUE AND principle_a IS NOT NULL AND principle_b IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_drug_interactions_pair_class
    ON aia_health_drug_interactions(class_a, class_b)
    WHERE active = TRUE AND class_a IS NOT NULL AND class_b IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_drug_interactions_principle_class
    ON aia_health_drug_interactions(principle_a, class_b)
    WHERE active = TRUE AND principle_a IS NOT NULL AND class_b IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_drug_interactions_class_principle
    ON aia_health_drug_interactions(class_a, principle_b)
    WHERE active = TRUE AND class_a IS NOT NULL AND principle_b IS NOT NULL;

-- =====================================================
-- Seed Fase 1 — top interações geriátricas críticas
-- Pares lex-ordenados. Class refere-se a therapeutic_class do dose_limits.
-- =====================================================

-- ── ANTICOAGULAÇÃO + AINE/ANTIAGREGANTE = SANGRAMENTO ──
-- Varfarina (anticoagulante_avk) + AAS (antiagregante)
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('acido acetilsalicilico', 'varfarina', 'major',
     'Bleeding risk',
     'AAS + varfarina aumenta risco hemorrágico (gastrintestinal, intracraniano).',
     'Evitar associação. Se inevitável (ex: pós-IAM), monitorar INR e sintomas hemorrágicos rigorosamente.',
     'beers_2023', 0.98),
    ('clopidogrel', 'varfarina', 'major',
     'Bleeding risk',
     'Clopidogrel + varfarina: sangramento maior 2-3× vs varfarina sozinha.',
     'Avaliar real necessidade da dupla. Se inevitável, considerar IBP gastroprotetor + monitorização rigorosa.',
     'beers_2023', 0.95),

    -- Varfarina + AINE = sangramento GI
    ('ibuprofeno', 'varfarina', 'contraindicated',
     'Bleeding risk + INR variability',
     'AINEs aumentam risco de sangramento GI e podem alterar INR de forma imprevisível.',
     'Não associar. Trocar AINE por paracetamol pra dor.',
     'beers_2023', 0.98),
    ('naproxeno', 'varfarina', 'contraindicated',
     'Bleeding risk',
     'AINEs + varfarina: risco de sangramento GI + alteração INR.',
     'Não associar. Paracetamol é alternativa segura.',
     'beers_2023', 0.98),
    ('diclofenaco', 'varfarina', 'contraindicated',
     'Bleeding risk',
     'AINEs + varfarina contraindicado.',
     'Não associar.',
     'beers_2023', 0.98);

-- AAS + AINE = duplo dano gástrico (mesmo em profilaxia 100mg)
INSERT INTO aia_health_drug_interactions
    (principle_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('acido acetilsalicilico', 'analgesico_aine', 'major',
     'GI bleeding',
     'AAS profilático + AINE: risco GI somado e perda do efeito antiagregante do AAS.',
     'Evitar AINE em uso crônico. Se necessário curto prazo, IBP profilático + tomar AINE 2h após AAS.',
     'beers_2023', 0.95);

-- ── DUPLO BLOQUEIO RAS = HIPERCALEMIA / IRA ──
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('enalapril', 'losartana', 'major',
     'Hyperkalemia + AKI',
     'IECA + ARA II: aumento de creatinina, hipercalemia, hipotensão e síncope sem benefício clínico adicional.',
     'Não associar. Se preciso bloqueio adicional, considerar antagonista mineralocorticoide com K+ controlado.',
     'beers_2023', 0.98),
    ('captopril', 'losartana', 'major',
     'Hyperkalemia + AKI',
     'IECA + ARA II: combinação sem benefício, risco de IRA e hipercalemia.',
     'Não associar.',
     'beers_2023', 0.98);

-- IECA/ARA + AINE = IRA
INSERT INTO aia_health_drug_interactions
    (class_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('analgesico_aine', 'ieca', 'major',
     'AKI + hyperkalemia',
     'AINE + IECA: pode causar lesão renal aguda (especialmente em idoso, desidratado, ICC).',
     'Evitar associação. Se inevitável, usar paracetamol pra dor, ou monitorar creatinina + K+ semanalmente.',
     'beers_2023', 0.95),
    ('analgesico_aine', 'ara', 'major',
     'AKI + hyperkalemia',
     'AINE + ARA: lesão renal aguda + hipercalemia.',
     'Mesma recomendação que AINE+IECA. Paracetamol preferido.',
     'beers_2023', 0.95),
    ('analgesico_aine', 'diuretico_alca', 'moderate',
     'AKI + diuretic resistance',
     'AINE reduz efeito diurético e aumenta risco de lesão renal em paciente com ICC.',
     'Monitorar peso, creatinina e edema se associação inevitável.',
     'stockleys', 0.85),
    ('analgesico_aine', 'diuretico_tiazidico', 'moderate',
     'AKI + reduced diuretic effect',
     'AINE atenua efeito anti-hipertensivo do tiazídico e aumenta risco renal.',
     'Considerar paracetamol pra dor.',
     'stockleys', 0.85);

-- ── OPIOIDE + BZD = DEPRESSÃO RESPIRATÓRIA (FDA Black Box) ──
INSERT INTO aia_health_drug_interactions
    (class_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('opioide', 'bzd', 'contraindicated',
     'Respiratory depression + sedation',
     'Combinação opióide + benzodiazepínico: risco MORTE por depressão respiratória (FDA Black Box).',
     'NÃO ASSOCIAR. Se inevitável, doses mais baixas possíveis, monitorar SatO2, naloxona disponível.',
     'fda', 0.99),
    ('opioide', 'hipnotico_z', 'major',
     'Respiratory depression + sedation',
     'Opióide + zolpidem: risco somado de sedação, queda e depressão respiratória em idoso.',
     'Evitar associação.',
     'beers_2023', 0.95);

-- BZD + BZD ou BZD + Z-drug
INSERT INTO aia_health_drug_interactions
    (class_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('bzd', 'hipnotico_z', 'major',
     'Excessive sedation + falls',
     'BZD + Z-drug: efeito sedativo somado, risco aumentado de queda noturna e fratura.',
     'Não associar. Escolher um dos dois.',
     'beers_2023', 0.95);

-- ── ESTATINA + MACROLÍDEO/AZOL = MIOPATIA/RABDOMIÓLISE ──
-- Não temos macrolídeos/azóis no seed atual, mas registramos pra quando vier
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('atorvastatina', 'sinvastatina', 'major',
     'Duplicate therapy + myopathy',
     'Duas estatinas — efeito sem benefício, risco somado de miopatia/rabdomiólise.',
     'Suspender uma das duas. Avaliar qual é a indicação real.',
     'manual', 0.95);

-- ── AMIODARONA + DIGOXINA / VARFARINA — sem amiodarona no seed ainda ──

-- ── IECA/ARA + DIURÉTICO POUPADOR DE K+ — sem espironolactona seed ainda ──

-- ── DIGOXINA + DIURÉTICO TIAZÍDICO/ALÇA = HIPOCALEMIA → toxicidade dig ──
INSERT INTO aia_health_drug_interactions
    (principle_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('digoxina', 'diuretico_tiazidico', 'major',
     'Hypokalemia → digitalis toxicity',
     'Diurético tiazídico causa hipocalemia, que aumenta toxicidade digital (arritmias).',
     'Monitorar K+ a cada 2-4 sem. Suplementar K se necessário. Considerar poupador de K.',
     'stockleys', 0.92),
    ('digoxina', 'diuretico_alca', 'major',
     'Hypokalemia → digitalis toxicity',
     'Diurético de alça causa hipocalemia/hipomagnesemia, que potencializa toxicidade digital.',
     'Monitorar K+ e Mg+ semanalmente nas primeiras semanas.',
     'stockleys', 0.92);

-- ── BETA-BLOQUEADOR + DIGOXINA = BRADICARDIA ──
INSERT INTO aia_health_drug_interactions
    (principle_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('digoxina', 'betabloqueador', 'moderate',
     'Bradycardia + AV block',
     'Digoxina + β-bloqueador: bradicardia, bloqueio AV. Útil em FA controlada mas exige monitorização.',
     'Monitorar FC e ECG. Reduzir dose se FC < 50.',
     'lexicomp', 0.88);

-- ── SSRI + ANTICOAGULANTE / ANTIAGREGANTE = SANGRAMENTO GI ──
INSERT INTO aia_health_drug_interactions
    (class_a, principle_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('ssri', 'varfarina', 'major',
     'GI bleeding (impaired platelet aggregation)',
     'SSRI inibe recaptação de serotonina nas plaquetas → risco hemorragia GI quando associado a anticoagulante.',
     'Avaliar real necessidade. Se SSRI essencial, considerar IBP profilático e monitorar INR.',
     'beers_2023', 0.92),
    ('ssri', 'acido acetilsalicilico', 'moderate',
     'GI bleeding',
     'SSRI + AAS aumenta risco GI moderado.',
     'IBP profilático se uso prolongado.',
     'beers_2023', 0.85);

-- ── SSRI + IMAO = SÍNDROME SEROTONINÉRGICA — sem IMAO no seed ──
-- ── SSRI duplo / SSRI + Tramadol = serotonérgico ──
INSERT INTO aia_health_drug_interactions
    (principle_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('tramadol', 'ssri', 'major',
     'Serotonin syndrome',
     'Tramadol + SSRI: risco síndrome serotoninérgica (agitação, hipertermia, mioclonia, convulsão).',
     'Evitar associação. Se necessário analgésico opióide, preferir oxicodona ou morfina (sem efeito serotoninérgico).',
     'lexicomp', 0.92);

-- ── SULFONILUREIA + IECA/SSRI = HIPOGLICEMIA ──
INSERT INTO aia_health_drug_interactions
    (class_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('sulfonilureia', 'ieca', 'moderate',
     'Hypoglycemia',
     'IECA pode potencializar hipoglicemia da sulfonilureia em idoso.',
     'Monitorar glicemia capilar. Educar paciente/cuidador sobre sinais.',
     'stockleys', 0.85);

-- ── ANTICOLINESTERÁSICO + ANTICOLINÉRGICO = OPOSIÇÃO ──
-- (Nada de anticolinérgico forte ainda no seed mas placeholder.)

-- ── ANTIDEPRESSIVOS + DIURÉTICO TIAZÍDICO = HIPONATREMIA ──
INSERT INTO aia_health_drug_interactions
    (class_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('ssri', 'diuretico_tiazidico', 'moderate',
     'Hyponatremia (SIADH-like)',
     'SSRI + tiazídico em idoso: risco de hiponatremia sintomática (confusão, queda).',
     'Monitorar sódio sérico nas primeiras semanas e periodicamente.',
     'beers_2023', 0.88);

-- ── PARACETAMOL + VARFARINA = ↑ INR ──
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('paracetamol', 'varfarina', 'moderate',
     'INR elevation (chronic high-dose)',
     'Paracetamol em dose alta (>2g/dia por dias seguidos) pode aumentar INR em paciente em varfarina.',
     'Limitar paracetamol a 2g/dia em uso prolongado. Monitorar INR mais frequentemente se uso > 7 dias.',
     'stockleys', 0.85);

-- ── CORTICOIDE + AINE = ÚLCERA ──
INSERT INTO aia_health_drug_interactions
    (class_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('corticoide', 'analgesico_aine', 'major',
     'Peptic ulcer + GI bleeding',
     'Corticoide + AINE: risco de úlcera/sangramento GI 4-15× maior que cada um isolado.',
     'Evitar combinação. Se inevitável, IBP profilático obrigatório.',
     'beers_2023', 0.95);

-- ── BETA-BLOQUEADOR + INSULINA/SULFONIL = MASCARA HIPOGLICEMIA ──
INSERT INTO aia_health_drug_interactions
    (class_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('betabloqueador', 'sulfonilureia', 'moderate',
     'Masked hypoglycemia signs',
     'β-bloqueador (não-cardiosseletivo) mascara taquicardia que sinaliza hipoglicemia.',
     'Preferir β-bloqueador cardiosseletivo (atenolol, metoprolol). Educar paciente/cuidador a checar glicemia em sintomas atípicos.',
     'lexicomp', 0.85);

-- ── TIAZIDICO + LITIO = TOXICIDADE LITIO ── (sem litio no seed ainda)

-- ── DUPLICIDADE PROIBIDA: 2 IECA, 2 ARA, 2 AINEs ──
-- Já coberto pelo cruzamento check_duplicate_therapy do F1, mas
-- registramos como interação clara pra log explícito.
INSERT INTO aia_health_drug_interactions
    (class_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('ieca', 'ieca', 'contraindicated',
     'Duplicate class',
     'Dois IECAs simultâneos: hipotensão grave, IRA, hipercalemia.',
     'Suspender um.',
     'manual', 0.99),
    ('ara', 'ara', 'contraindicated',
     'Duplicate class',
     'Dois ARAs simultâneos: hipotensão, IRA, hipercalemia.',
     'Suspender um.',
     'manual', 0.99),
    ('analgesico_aine', 'analgesico_aine', 'major',
     'Duplicate class',
     'Dois AINEs simultâneos: somam toxicidade GI/renal/cardiovascular sem benefício analgésico.',
     'Suspender um.',
     'manual', 0.95),
    ('bzd', 'bzd', 'major',
     'Duplicate class',
     'Dois benzodiazepínicos: sedação somada, risco de queda e depressão respiratória.',
     'Suspender um, com taper se uso crônico.',
     'beers_2023', 0.95);

-- ── ESTATINA + ANTICOAGULANTE/ANTIAGREGANTE = miopatia (raro) ──
-- Já coberto.

COMMIT;
