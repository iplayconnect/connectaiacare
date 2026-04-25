-- ConnectaIACare — Ajuste hepático por Child-Pugh
-- Data: 2026-04-25
--
-- Espelha renal_adjustments mas com 3 classes de gravidade (A/B/C):
--   child_a = cirrose leve / hepatopatia compensada (TPS 5-6)
--   child_b = cirrose moderada / ascite leve (TPS 7-9)
--   child_c = cirrose grave descompensada / encefalopatia (TPS 10-15)
--
-- Severidade do paciente é inferida via conditions+aliases (sem campo
-- estruturado próprio nessa fase). conditions sem qualificador →
-- assume child_a (leve) com warning pra confirmar.

BEGIN;

-- =====================================================
-- 1. Aliases de severidade hepática
-- =====================================================
-- Mapeamento condition livre → child_a / child_b / child_c

INSERT INTO aia_health_condition_aliases (alias, canonical_term, notes) VALUES
    -- Child A (leve / compensada)
    ('hepatopatia leve', 'child_a', 'cirrose compensada'),
    ('cirrose child a', 'child_a', NULL),
    ('cirrose child-pugh a', 'child_a', NULL),
    ('cirrose compensada', 'child_a', NULL),
    ('hepatopatia compensada', 'child_a', NULL),

    -- Child B (moderada)
    ('hepatopatia moderada', 'child_b', NULL),
    ('cirrose child b', 'child_b', NULL),
    ('cirrose child-pugh b', 'child_b', NULL),
    ('cirrose com ascite', 'child_b', NULL),
    ('hepatopatia com ascite', 'child_b', NULL),

    -- Child C (grave)
    ('hepatopatia grave', 'child_c', NULL),
    ('cirrose child c', 'child_c', NULL),
    ('cirrose child-pugh c', 'child_c', NULL),
    ('cirrose descompensada', 'child_c', 'descompensada / Child C'),
    ('encefalopatia hepatica', 'child_c', 'sinal de descompensação grave'),
    ('hepatopatia grave descompensada', 'child_c', NULL),
    ('insuficiencia hepatica grave', 'child_c', NULL),
    ('falencia hepatica', 'child_c', NULL),

    -- Genérico (sem qualificador) — assume child_a + warning de confirmar
    ('hepatopatia indeterminada', 'hepatopatia_unspecified', NULL)
ON CONFLICT (lower(alias)) DO NOTHING;

-- Os aliases existentes ('hepatopatia', 'cirrose', 'hepatite cronica')
-- seguem mapeando pro termo genérico 'hepatopatia' que vamos tratar
-- como child_a + warning. Não removemos.

-- =====================================================
-- 2. aia_health_drug_hepatic_adjustments
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_drug_hepatic_adjustments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    principle_active TEXT NOT NULL,
    severity_class TEXT NOT NULL CHECK (severity_class IN (
        'child_a', 'child_b', 'child_c', 'hepatopatia_unspecified'
    )),
    action TEXT NOT NULL CHECK (action IN (
        'avoid', 'reduce_50pct', 'reduce_75pct',
        'increase_interval', 'caution_monitor', 'no_adjustment'
    )),
    rationale TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    source_ref TEXT,
    confidence NUMERIC(3,2) NOT NULL DEFAULT 0.85,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_hepatic_adj_unique
    ON aia_health_drug_hepatic_adjustments(principle_active, severity_class)
    WHERE active = TRUE;

-- =====================================================
-- 3. Seed Fase 1 — 35+ princípios ativos
-- =====================================================

-- ── PARACETAMOL — risco hepatotoxicidade ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('paracetamol', 'child_a', 'reduce_50pct',
     'Limitar a 2g/dia em hepatopatia leve.', 'manual'),
    ('paracetamol', 'child_b', 'avoid',
     'Hepatopatia moderada: evitar paracetamol regular. Se inevitável, ≤2g/dia + monitorar TGO/TGP.', 'manual'),
    ('paracetamol', 'child_c', 'avoid',
     'NÃO usar paracetamol em hepatopatia grave — risco hepatotoxicidade aguda.', 'manual'),
    ('paracetamol', 'hepatopatia_unspecified', 'reduce_50pct',
     'Hepatopatia sem severidade especificada: limitar a 2g/dia + confirmar Child-Pugh.', 'manual');

-- ── DIPIRONA ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('dipirona', 'child_a', 'no_adjustment', 'Sem ajuste em hepatopatia leve.', 'manual'),
    ('dipirona', 'child_b', 'caution_monitor',
     'Hepatopatia moderada: monitorar função hepática.', 'manual'),
    ('dipirona', 'child_c', 'avoid',
     'Hepatopatia grave: evitar pelo risco hepatotoxicidade adicional + sangramento.', 'manual');

-- ── AINEs ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('ibuprofeno', 'child_a', 'caution_monitor',
     'AINE em hepatopatia leve: monitorar função renal + sangramento.', 'manual'),
    ('ibuprofeno', 'child_b', 'avoid',
     'Hepatopatia moderada: AINEs aumentam risco síndrome hepatorrenal.', 'manual'),
    ('ibuprofeno', 'child_c', 'avoid',
     'Hepatopatia grave: AINE CONTRAINDICADO — risco IRA + sangramento varicoso.', 'manual'),
    ('naproxeno', 'child_a', 'caution_monitor', 'Mesma observação.', 'manual'),
    ('naproxeno', 'child_b', 'avoid', 'Mesma observação clínica.', 'manual'),
    ('naproxeno', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual'),
    ('diclofenaco', 'child_a', 'caution_monitor', 'Mesma observação.', 'manual'),
    ('diclofenaco', 'child_b', 'avoid', 'Mesma observação clínica.', 'manual'),
    ('diclofenaco', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual'),
    ('cetoprofeno', 'child_a', 'caution_monitor', 'Mesma observação.', 'manual'),
    ('cetoprofeno', 'child_b', 'avoid', 'Mesma observação clínica.', 'manual'),
    ('cetoprofeno', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual');

-- ── AAS ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('acido acetilsalicilico', 'child_a', 'caution_monitor',
     'AAS em hepatopatia leve: monitorar sangramento + TGO/TGP.', 'manual'),
    ('acido acetilsalicilico', 'child_b', 'avoid',
     'AAS moderada: risco sangramento varicoso.', 'manual'),
    ('acido acetilsalicilico', 'child_c', 'avoid',
     'AAS grave: CONTRAINDICADO.', 'manual');

-- ── OPIOIDES (metabolismo hepático) ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('tramadol', 'child_a', 'reduce_50pct',
     'Hepatopatia leve: 50mg q12h, máx 100mg/dia.', 'lexicomp'),
    ('tramadol', 'child_b', 'reduce_50pct',
     'Hepatopatia moderada: 50mg q12h, máx 100mg/dia. Monitorar sedação.', 'lexicomp'),
    ('tramadol', 'child_c', 'avoid',
     'Hepatopatia grave: evitar tramadol — acúmulo + serotoninérgico.', 'lexicomp'),
    ('codeina', 'child_a', 'reduce_50pct',
     'Codeína: ativação dependente de CYP2D6 hepático.', 'manual'),
    ('codeina', 'child_b', 'avoid', 'Avoid em hepatopatia mod/grave.', 'manual'),
    ('codeina', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual');

-- ── BENZODIAZEPÍNICOS ──
-- Lorazepam é PREFERIDO em hepatopatia (sem metabólitos ativos, glucuronidação)
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('alprazolam', 'child_a', 'avoid',
     'BZD com metabólito ativo: acumula em hepatopatia. Evitar.', 'beers_2023'),
    ('alprazolam', 'child_b', 'avoid', 'Mesma observação clínica.', 'beers_2023'),
    ('alprazolam', 'child_c', 'avoid', 'Mesma observação clínica.', 'beers_2023'),
    ('diazepam', 'child_a', 'avoid',
     'Diazepam: meia-vida prolongada drasticamente em hepatopatia.', 'beers_2023'),
    ('diazepam', 'child_b', 'avoid', 'Mesma observação clínica.', 'beers_2023'),
    ('diazepam', 'child_c', 'avoid', 'Mesma observação clínica.', 'beers_2023'),
    ('clonazepam', 'child_a', 'avoid',
     'Clonazepam: meia-vida longa, acumula.', 'beers_2023'),
    ('clonazepam', 'child_b', 'avoid', 'Mesma observação clínica.', 'beers_2023'),
    ('clonazepam', 'child_c', 'avoid', 'Mesma observação clínica.', 'beers_2023'),
    -- Lorazepam é o BZD preferido (glucuronidação, sem metabólito ativo)
    ('lorazepam', 'child_a', 'caution_monitor',
     'Lorazepam: BZD preferido em hepatopatia (sem metabólito ativo).', 'manual'),
    ('lorazepam', 'child_b', 'reduce_50pct',
     'Hepatopatia moderada: reduzir 50% pela queda de albumina.', 'manual'),
    ('lorazepam', 'child_c', 'reduce_75pct',
     'Hepatopatia grave: reduzir 75% + monitorar nível consciência.', 'manual'),
    -- Zolpidem
    ('zolpidem', 'child_a', 'reduce_50pct',
     'Hepatopatia leve: 5mg/dia.', 'manual'),
    ('zolpidem', 'child_b', 'avoid', 'Hepatopatia moderada+: avoid.', 'manual'),
    ('zolpidem', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual');

-- ── ANTICOAGULANTES ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('varfarina', 'child_a', 'caution_monitor',
     'Hepatopatia leve: INR mais frequente (mensal).', 'manual'),
    ('varfarina', 'child_b', 'caution_monitor',
     'Hepatopatia moderada: INR semanal/quinzenal + observar sangra varicoso.', 'manual'),
    ('varfarina', 'child_c', 'avoid',
     'Hepatopatia grave: anticoagulação imprevisível, risco sangramento extremo.', 'manual'),
    ('rivaroxabana', 'child_a', 'no_adjustment',
     'Hepatopatia leve: dose padrão.', 'fda'),
    ('rivaroxabana', 'child_b', 'avoid',
     'Hepatopatia Child B: contraindicado pelo aumento do efeito anticoagulante.', 'fda'),
    ('rivaroxabana', 'child_c', 'avoid', 'Mesma observação clínica.', 'fda'),
    ('apixabana', 'child_a', 'no_adjustment',
     'Hepatopatia leve: dose padrão.', 'fda'),
    ('apixabana', 'child_b', 'caution_monitor',
     'Hepatopatia Child B: usar com cautela, sem dados robustos.', 'fda'),
    ('apixabana', 'child_c', 'avoid',
     'Child C: contraindicado.', 'fda'),
    ('clopidogrel', 'child_a', 'no_adjustment', 'Sem ajuste em leve.', 'manual'),
    ('clopidogrel', 'child_b', 'caution_monitor', 'Monitorar sangra.', 'manual'),
    ('clopidogrel', 'child_c', 'avoid', 'Risco sangramento extremo.', 'manual');

-- ── ESTATINAS ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('atorvastatina', 'child_a', 'caution_monitor',
     'TGO/TGP basal + 12 sem. Suspender se >3× LSN.', 'fda'),
    ('atorvastatina', 'child_b', 'reduce_50pct',
     'Hepatopatia moderada: dose máxima 40mg.', 'fda'),
    ('atorvastatina', 'child_c', 'avoid',
     'Hepatopatia grave: contraindicada pela hepatotoxicidade.', 'fda'),
    ('sinvastatina', 'child_a', 'caution_monitor', 'Mesma observação.', 'fda'),
    ('sinvastatina', 'child_b', 'reduce_50pct',
     'Hepatopatia moderada: máximo 20mg.', 'fda'),
    ('sinvastatina', 'child_c', 'avoid', 'Avoid grave.', 'fda');

-- ── INIBIDORES BOMBA PRÓTONS ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('omeprazol', 'child_a', 'no_adjustment', 'Sem ajuste leve.', 'manual'),
    ('omeprazol', 'child_b', 'reduce_50pct',
     'Hepatopatia moderada: meia-vida prolonga 5×, máx 20mg/dia.', 'manual'),
    ('omeprazol', 'child_c', 'reduce_50pct', 'Idem moderada.', 'manual'),
    ('pantoprazol', 'child_a', 'no_adjustment', 'Sem ajuste necessário.', 'manual'),
    ('pantoprazol', 'child_b', 'reduce_50pct',
     'Hepatopatia moderada: máx 20mg/dia.', 'manual'),
    ('pantoprazol', 'child_c', 'reduce_50pct', 'Mesma observação.', 'manual');

-- ── ANTIDEPRESSIVOS ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('sertralina', 'child_a', 'reduce_50pct',
     'Hepatopatia leve: iniciar 25mg/dia, máx 100mg/dia.', 'manual'),
    ('sertralina', 'child_b', 'avoid',
     'Hepatopatia moderada: evitar — meia-vida prolonga.', 'manual'),
    ('sertralina', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual'),
    ('fluoxetina', 'child_a', 'reduce_50pct',
     'Fluoxetina: meia-vida já longa, em hepatopatia prolonga ainda mais.', 'manual'),
    ('fluoxetina', 'child_b', 'avoid',
     'Hepatopatia moderada: evitar fluoxetina (longuíssima meia-vida).', 'manual'),
    ('fluoxetina', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual'),
    ('escitalopram', 'child_a', 'reduce_50pct',
     'Hepatopatia leve: dose máxima 10mg/dia.', 'fda'),
    ('escitalopram', 'child_b', 'avoid', 'Avoid moderada.', 'fda'),
    ('escitalopram', 'child_c', 'avoid', 'Mesma observação clínica.', 'fda'),
    ('mirtazapina', 'child_a', 'caution_monitor', 'Monitorar nível consciência.', 'manual'),
    ('mirtazapina', 'child_b', 'reduce_50pct', 'Reduzir 50%.', 'manual'),
    ('mirtazapina', 'child_c', 'reduce_75pct', 'Reduzir 75%.', 'manual');

-- ── ANTIEMÉTICO/PROCINETICO ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('metoclopramida', 'child_a', 'reduce_50pct',
     'Hepatopatia leve: reduzir 50%.', 'manual'),
    ('metoclopramida', 'child_b', 'avoid', 'Avoid moderada.', 'manual'),
    ('metoclopramida', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual');

-- ── L-DOPA ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('levodopa', 'child_a', 'no_adjustment', 'Metabolismo periférico+central.', 'manual'),
    ('levodopa', 'child_b', 'caution_monitor',
     'Hepatopatia moderada: monitorar nível consciência (encefalopatia hepática agrava).', 'manual'),
    ('levodopa', 'child_c', 'caution_monitor',
     'Hepatopatia grave: encefalopatia hepática+L-dopa: confusão somada. Doses mínimas.', 'manual');

-- ── BETA-BLOQUEADORES ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('atenolol', 'child_a', 'no_adjustment',
     'Atenolol é renal — sem ajuste hepático.', 'manual'),
    ('atenolol', 'child_b', 'no_adjustment', 'Sem ajuste necessário.', 'manual'),
    ('atenolol', 'child_c', 'no_adjustment', 'Sem ajuste necessário.', 'manual'),
    ('metoprolol', 'child_a', 'reduce_50pct',
     'Metoprolol é hepático: reduzir 50% em leve.', 'manual'),
    ('metoprolol', 'child_b', 'reduce_75pct', 'Reduzir 75%.', 'manual'),
    ('metoprolol', 'child_c', 'avoid', 'Avoid grave.', 'manual'),
    ('propranolol', 'child_a', 'reduce_50pct',
     'Propranolol é hepático extensivo. Em hepatopatia leve, reduzir 50%.', 'manual'),
    ('propranolol', 'child_b', 'avoid',
     'Avoid moderada — risco hipotensão prolongada + encefalopatia.', 'manual'),
    ('propranolol', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual');

-- ── BCCa ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('anlodipino', 'child_a', 'reduce_50pct',
     'Hepatopatia leve: iniciar 2.5mg/dia.', 'manual'),
    ('anlodipino', 'child_b', 'reduce_50pct', 'Mesma observação.', 'manual'),
    ('anlodipino', 'child_c', 'avoid', 'Avoid grave.', 'manual'),
    ('nifedipino', 'child_a', 'reduce_50pct', 'Mesma observação.', 'manual'),
    ('nifedipino', 'child_b', 'avoid', 'Mesma observação clínica.', 'manual'),
    ('nifedipino', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual');

-- ── DIURÉTICOS ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('furosemida', 'child_a', 'caution_monitor',
     'Hepatopatia leve: monitorar K+/Na+/creatinina.', 'manual'),
    ('furosemida', 'child_b', 'caution_monitor',
     'Hepatopatia moderada com ascite: dose ajustada conforme resposta.', 'manual'),
    ('furosemida', 'child_c', 'caution_monitor',
     'Hepatopatia grave: risco encefalopatia por hipocalemia/desidratação. Combinar com espironolactona.', 'manual'),
    ('hidroclorotiazida', 'child_a', 'caution_monitor',
     'Hepatopatia leve: monitorar.', 'manual'),
    ('hidroclorotiazida', 'child_b', 'avoid',
     'Hepatopatia moderada: avoid — risco encefalopatia hepática.', 'manual'),
    ('hidroclorotiazida', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual');

-- ── IECAs/ARAs ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('enalapril', 'child_a', 'caution_monitor',
     'Pró-droga hepática: ativação reduzida.', 'manual'),
    ('enalapril', 'child_b', 'reduce_50pct', 'Reduzir 50%.', 'manual'),
    ('enalapril', 'child_c', 'avoid', 'Avoid grave.', 'manual'),
    ('captopril', 'child_a', 'caution_monitor', 'Mesma observação.', 'manual'),
    ('captopril', 'child_b', 'reduce_50pct', 'Mesma observação.', 'manual'),
    ('captopril', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual'),
    ('losartana', 'child_a', 'reduce_50pct',
     'Losartana hepática: reduzir 50%.', 'manual'),
    ('losartana', 'child_b', 'reduce_75pct', 'Reduzir 75%.', 'manual'),
    ('losartana', 'child_c', 'avoid', 'Avoid grave.', 'manual');

-- ── DIGOXINA ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('digoxina', 'child_a', 'no_adjustment',
     'Excreção renal predominante — sem ajuste hepático específico.', 'manual'),
    ('digoxina', 'child_b', 'caution_monitor',
     'Hepatopatia moderada: monitorar nível sérico digoxina.', 'manual'),
    ('digoxina', 'child_c', 'caution_monitor', 'Mesma observação.', 'manual');

-- ── ANTIDIABÉTICOS ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('metformina', 'child_a', 'caution_monitor',
     'Hepatopatia leve: monitorar lactato.', 'manual'),
    ('metformina', 'child_b', 'avoid',
     'Hepatopatia moderada: contraindicada — risco acidose lática.', 'kdigo'),
    ('metformina', 'child_c', 'avoid', 'Mesma observação clínica.', 'kdigo'),
    ('glibenclamida', 'child_a', 'caution_monitor',
     'Hepatopatia leve: monitorar hipoglicemia (Beers AVOID).', 'beers_2023'),
    ('glibenclamida', 'child_b', 'avoid', 'Avoid moderada.', 'beers_2023'),
    ('glibenclamida', 'child_c', 'avoid', 'Mesma observação clínica.', 'beers_2023'),
    ('glicazida', 'child_a', 'reduce_50pct', 'Reduzir 50%.', 'manual'),
    ('glicazida', 'child_b', 'avoid', 'Mesma observação clínica.', 'manual'),
    ('glicazida', 'child_c', 'avoid', 'Mesma observação clínica.', 'manual');

-- ── DEMÊNCIA ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('donepezila', 'child_a', 'no_adjustment', 'Sem ajuste necessário.', 'manual'),
    ('donepezila', 'child_b', 'caution_monitor', 'Monitorar nível consciência.', 'manual'),
    ('donepezila', 'child_c', 'reduce_50pct', 'Mesma observação.', 'manual'),
    ('rivastigmina', 'child_a', 'no_adjustment', 'Sem ajuste necessário.', 'manual'),
    ('rivastigmina', 'child_b', 'caution_monitor', 'Mesma observação.', 'manual'),
    ('rivastigmina', 'child_c', 'reduce_50pct', 'Mesma observação.', 'manual'),
    ('memantina', 'child_a', 'no_adjustment', 'Excreção renal — sem ajuste hepático.', 'manual'),
    ('memantina', 'child_b', 'no_adjustment', 'Sem ajuste necessário.', 'manual'),
    ('memantina', 'child_c', 'caution_monitor', 'Monitorar.', 'manual');

-- ── HORMÔNIO TIREOIDE ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('levotiroxina', 'child_a', 'no_adjustment', 'Sem ajuste necessário.', 'manual'),
    ('levotiroxina', 'child_b', 'caution_monitor', 'Monitorar TSH mais frequente.', 'manual'),
    ('levotiroxina', 'child_c', 'caution_monitor', 'Mesma observação.', 'manual');

-- ── CORTICOIDE ──
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source) VALUES
    ('prednisona', 'child_a', 'caution_monitor',
     'Hepatopatia leve: pró-droga depende de hepático pra ativação.', 'manual'),
    ('prednisona', 'child_b', 'caution_monitor',
     'Hepatopatia moderada: considerar prednisolona (não exige ativação hepática).', 'manual'),
    ('prednisona', 'child_c', 'caution_monitor',
     'Hepatopatia grave: trocar por prednisolona.', 'manual');

COMMIT;
