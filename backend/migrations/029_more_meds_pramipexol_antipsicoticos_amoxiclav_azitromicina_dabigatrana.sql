-- ConnectaIACare — F-E: 8 medicamentos adicionais com cobertura
-- multi-dimensional do motor de cruzamentos.
--
-- 1. Pramipexol (antiparkinsoniano agonista D2/D3)
-- 2. Ropinirol (antiparkinsoniano agonista D2/D3)
-- 3. Risperidona (antipsicótico atípico — Beers AVOID em demência)
-- 4. Quetiapina (antipsicótico atípico — Beers AVOID em demência)
-- 5. Olanzapina (antipsicótico atípico — Beers AVOID em demência)
-- 6. Amoxicilina+Clavulanato (antibiótico beta-lactâmico)
-- 7. Azitromicina (macrolídeo)
-- 8. Dabigatrana (DOAC inibidor direto da trombina)
--
-- Fontes: ANVISA, Beers 2023, FDA, KDIGO, SBGG.

BEGIN;

-- =====================================================
-- 1. dose_limits
-- =====================================================
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, beers_avoid, beers_rationale,
     source, source_ref, confidence, notes)
VALUES
    -- ── Antiparkinsonianos agonistas dopaminérgicos ──
    ('pramipexol', 'oral', 4.5, 'mg', 'antiparkinsoniano_agonista_d2',
     FALSE, NULL,
     'anvisa', 'Bulário ANVISA — Sifrol/Pramipexol: 0,375mg/dia → 4,5mg/dia (máx) divididos em 3 tomadas.',
     0.9,
     'Idoso: iniciar 0,125mg 3×/dia. Alerta sono diurno súbito + transtorno controle impulsos. Ajuste renal obrigatório.'),

    ('ropinirol', 'oral', 24, 'mg', 'antiparkinsoniano_agonista_d2',
     FALSE, NULL,
     'anvisa', 'Bulário ANVISA — Requip: 0,75mg/dia → 24mg/dia divididos em 3 tomadas. RLS: máx 4mg/dia.',
     0.9,
     'Idoso: iniciar 0,25mg 3×/dia. Mesmas advertências do pramipexol (sono súbito, impulsividade).'),

    -- ── Antipsicóticos atípicos (Beers AVOID em demência) ──
    ('risperidona', 'oral', 6, 'mg', 'antipsicotico_atipico',
     TRUE,
     'Beers 2023: AVOID em demência exceto sintomas psicóticos refratários graves. Aumenta mortalidade + AVC. Prolonga QT, hipotensão postural, sedação, sintomas extrapiramidais.',
     'beers_2023', 'Beers 2023 — Strong avoid em demência sem psicose grave',
     0.97,
     'Demência: avaliar reversíveis primeiro. Se necessário, dose mínima eficaz. Reduzir 50% se ClCr <30.'),

    ('quetiapina', 'oral', 800, 'mg', 'antipsicotico_atipico',
     TRUE,
     'Beers 2023: AVOID em demência. Sedação intensa, hipotensão, ganho de peso. Quetiapina é a menos pior do grupo mas ainda evitável.',
     'beers_2023', 'Beers 2023',
     0.97,
     'Idoso: 12,5-50mg/dia. Doses geriátricas raramente >150mg/dia. Hipotensão postural + sedação dose-dependentes.'),

    ('olanzapina', 'oral', 20, 'mg', 'antipsicotico_atipico',
     TRUE,
     'Beers 2023: AVOID em demência. Ganho de peso, dislipidemia, DM, anticolinérgico significativo, sedação.',
     'beers_2023', 'Beers 2023',
     0.97,
     'Idoso: 2,5-7,5mg/dia. ACB score 3 (forte). Evitar em DM e síndrome metabólica.'),

    -- ── Antibióticos ──
    ('amoxicilina+clavulanato', 'oral', 1750, 'mg',
     'antibiotico_beta_lactamico',
     FALSE, NULL,
     'anvisa', 'Bulário ANVISA — Clavulin: 500/125 8/8h ou 875/125 12/12h. Componente clavulanato máx 1g/dia.',
     0.9,
     'Idoso: ajuste renal obrigatório. Diarreia + risco C.difficile. Hepatotoxicidade rara.'),

    ('azitromicina', 'oral', 500, 'mg', 'antibiotico_macrolideo',
     FALSE, NULL,
     'anvisa', 'Bulário ANVISA — Zitromax: 500mg 1×/dia 3-5 dias OU dose única 1500mg.',
     0.9,
     'Prolonga QT — atenção em arritmias e uso concomitante com outros prolongadores. Inibe CYP3A4.'),

    -- ── DOAC ──
    ('dabigatrana', 'oral', 300, 'mg', 'anticoagulante_doac',
     FALSE, NULL,
     'anvisa', 'Bulário ANVISA — Pradaxa: 110mg ou 150mg 12/12h. Idosos ≥80 anos OU ClCr <50: usar 110mg 12/12h. ClCr <30: contraindicado.',
     0.95,
     'NTI alto. Inibidor direto da trombina. Reversor: idarucizumabe.')
ON CONFLICT DO NOTHING;

-- Marca como NTI todos os 3 antipsicóticos + dabigatrana (já flag NTI)
UPDATE aia_health_drug_dose_limits SET narrow_therapeutic_index = TRUE
WHERE principle_active IN ('dabigatrana');


-- =====================================================
-- 2. drug_aliases (nomes comerciais comuns no Brasil)
-- =====================================================
INSERT INTO aia_health_drug_aliases (alias, principle_active, alias_type, notes) VALUES
    -- Pramipexol
    ('sifrol', 'pramipexol', 'brand', NULL),
    ('mirapex', 'pramipexol', 'brand', 'EUA'),
    -- Ropinirol
    ('requip', 'ropinirol', 'brand', NULL),
    -- Risperidona
    ('risperdal', 'risperidona', 'brand', NULL),
    ('zargus', 'risperidona', 'brand', NULL),
    -- Quetiapina
    ('seroquel', 'quetiapina', 'brand', NULL),
    ('quetiapina xr', 'quetiapina', 'brand', 'liberação prolongada'),
    -- Olanzapina
    ('zyprexa', 'olanzapina', 'brand', NULL),
    -- Amoxicilina+clavulanato
    ('clavulin', 'amoxicilina+clavulanato', 'brand', NULL),
    ('augmentin', 'amoxicilina+clavulanato', 'brand', 'EUA'),
    ('amoxiclav', 'amoxicilina+clavulanato', 'synonym', NULL),
    -- Azitromicina
    ('zitromax', 'azitromicina', 'brand', NULL),
    ('azimix', 'azitromicina', 'brand', NULL),
    ('selimax', 'azitromicina', 'brand', NULL),
    -- Dabigatrana
    ('pradaxa', 'dabigatrana', 'brand', NULL)
ON CONFLICT DO NOTHING;


-- =====================================================
-- 3. allergy_mappings — penicilina cobre amoxicilina+clavulanato
-- =====================================================
INSERT INTO aia_health_allergy_mappings
    (allergy_term, affected_principle_active, affected_therapeutic_class, severity, rationale, source)
VALUES
    ('penicilina', 'amoxicilina+clavulanato', NULL, 'block',
     'Reação cruzada penicilina ↔ amoxicilina+clavulanato (mesmo grupo β-lactâmico).',
     'manual'),
    ('amoxicilina', 'amoxicilina+clavulanato', NULL, 'block',
     'Mesma molécula base.', 'manual'),
    ('beta-lactamico', NULL, 'antibiotico_beta_lactamico', 'block',
     'Alergia beta-lactâmica documentada → evitar toda a classe.',
     'manual'),
    -- Macrolídeos
    ('macrolideo', NULL, 'antibiotico_macrolideo', 'block',
     'Alergia conhecida a macrolídeos → evitar.', 'manual'),
    ('eritromicina', 'azitromicina', NULL, 'warning',
     'Alergia eritromicina pode ter reação cruzada com azitromicina/claritromicina.',
     'manual')
ON CONFLICT DO NOTHING;


-- =====================================================
-- 4. drug_interactions
-- =====================================================
-- Pares lex-ordenados (a < b) — mesmo padrão do 020.
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    -- Antipsicóticos + benzodiazepínicos / opioides → sedação grave
    ('clonazepam', 'risperidona', 'major',
     'Aditividade SNC depressor',
     'Sedação intensa + risco depressão respiratória, queda, confusão.',
     'Evitar dupla. Se inevitável, reduzir 50% e monitorar.',
     'beers_2023', 0.92),
    ('diazepam', 'quetiapina', 'major',
     'Aditividade SNC depressor + ACB cumulativo',
     'Sedação grave em idoso, risco aspiração, queda.',
     'Evitar.', 'beers_2023', 0.92),

    -- Antipsicóticos + L-dopa → antagonismo dopaminérgico
    ('levodopa', 'risperidona', 'contraindicated',
     'Antagonismo dopaminérgico D2',
     'Risperidona bloqueia efeito da levodopa → piora motora grave em Parkinson.',
     'Não associar. Em psicose Parkinson, usar quetiapina ou clozapina.',
     'beers_2023', 0.97),
    ('levodopa', 'olanzapina', 'major',
     'Antagonismo dopaminérgico D2',
     'Olanzapina antagoniza levodopa.',
     'Evitar em Parkinson. Preferir quetiapina/clozapina se psicose.',
     'beers_2023', 0.92),

    -- Pramipexol + antipsicóticos típicos/atípicos → antagonismo
    ('pramipexol', 'risperidona', 'major',
     'Antagonismo dopaminérgico',
     'Risperidona inibe efeito do pramipexol.',
     'Evitar.', 'manual', 0.9),
    ('pramipexol', 'metoclopramida', 'major',
     'Antagonismo D2',
     'Metoclopramida inibe pramipexol + induz parkinsonismo.',
     'Evitar.', 'beers_2023', 0.95),
    ('metoclopramida', 'ropinirol', 'major',
     'Antagonismo D2',
     'Metoclopramida inibe ropinirol.',
     'Evitar.', 'beers_2023', 0.95),

    -- Azitromicina + outros prolongadores QT → torsade de pointes
    ('amiodarona', 'azitromicina', 'major',
     'QT prolongation aditivo',
     'Risco torsade de pointes — somatório de bloqueio canais hERG.',
     'Evitar dupla. Se inevitável, ECG basal + monitor QTc.',
     'fda', 0.95),
    ('azitromicina', 'haloperidol', 'major',
     'QT prolongation aditivo',
     'Aditividade sobre QTc.',
     'Evitar.', 'fda', 0.92),
    ('azitromicina', 'quetiapina', 'major',
     'QT prolongation aditivo',
     'Aditividade sobre QTc.',
     'Avaliar ECG antes. Considerar antibiótico alternativo.',
     'fda', 0.9),

    -- Dabigatrana + AINE/antiagregante = sangramento
    ('acido acetilsalicilico', 'dabigatrana', 'major',
     'Bleeding risk',
     'AAS + dabigatrana: sangramento maior 1.5-2×.',
     'Avaliar real necessidade. Se inevitável, dose mínima de AAS + IBP.',
     'fda', 0.95),
    ('dabigatrana', 'ibuprofeno', 'contraindicated',
     'Bleeding risk',
     'AINEs aumentam sangramento GI sob anticoagulação.',
     'Não associar. Paracetamol é alternativa.',
     'fda', 0.97),
    ('dabigatrana', 'naproxeno', 'contraindicated',
     'Bleeding risk',
     'AINEs + DOAC contraindicado.',
     'Não associar.', 'fda', 0.97),
    ('clopidogrel', 'dabigatrana', 'major',
     'Bleeding risk',
     'Dupla antitrombótica aumenta sangramento.',
     'Avaliar real necessidade clínica.',
     'fda', 0.92),

    -- Dabigatrana + amiodarona/verapamil = aumenta níveis (P-gp)
    ('amiodarona', 'dabigatrana', 'major',
     'P-glycoprotein inhibition',
     'Amiodarona inibe P-gp → ↑ exposição de dabigatrana, sangramento.',
     'Reduzir dose dabigatrana ou trocar para outro DOAC.',
     'fda', 0.92),
    ('dabigatrana', 'verapamil', 'major',
     'P-glycoprotein inhibition',
     'Verapamil inibe P-gp → ↑ exposição.',
     'Espaçar 2h ou reduzir dose dabigatrana.',
     'fda', 0.9),

    -- Amoxiclav + alopurinol = rash
    ('alopurinol', 'amoxicilina+clavulanato', 'minor',
     'Rash risk',
     'Aumento incidência de rash maculopapular.',
     'Monitorar pele. Suspender se rash.',
     'manual', 0.7),

    -- Amoxiclav + varfarina = INR pode subir
    ('amoxicilina+clavulanato', 'varfarina', 'moderate',
     'INR potentiation',
     'Antibióticos podem reduzir flora intestinal produtora de vitamina K → ↑ INR.',
     'Monitorar INR durante e após o curso.',
     'manual', 0.8),

    -- Azitromicina + varfarina
    ('azitromicina', 'varfarina', 'moderate',
     'INR potentiation',
     'Macrolídeos podem ↑ INR via CYP/flora.',
     'Monitorar INR.',
     'manual', 0.8)
ON CONFLICT DO NOTHING;


-- =====================================================
-- 5. condition_contraindications
-- =====================================================
INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_principle_active, affected_therapeutic_class,
     severity, rationale, recommendation, source, confidence)
VALUES
    -- Demência → antipsicóticos atípicos (Beers AVOID)
    ('demencia', NULL, 'antipsicotico_atipico', 'warning',
     'Beers 2023: antipsicóticos em demência aumentam mortalidade e AVC. Box warning FDA.',
     'Avaliar reversíveis (dor, infecção, polifarmácia, ambiente). Se mantido, dose mínima e revalidar a cada 4 semanas.',
     'beers_2023', 0.97),
    ('alzheimer', NULL, 'antipsicotico_atipico', 'warning',
     'Beers 2023: AVOID exceto psicose grave refratária.',
     'Consultar geriatria. Documentar tentativas não-farmacológicas.',
     'beers_2023', 0.97),

    -- Parkinson → antipsicóticos típicos e a maioria dos atípicos
    ('parkinson', 'risperidona', NULL, 'contraindicated',
     'Bloqueio D2 piora motor — exacerba parkinsonismo.',
     'Trocar por quetiapina ou clozapina.',
     'beers_2023', 0.95),
    ('parkinson', 'olanzapina', NULL, 'contraindicated',
     'Bloqueio D2 piora motor.',
     'Quetiapina ou clozapina são alternativas.',
     'beers_2023', 0.95),

    -- Síndrome do QT longo → azitromicina
    ('sindrome qt longo', 'azitromicina', NULL, 'contraindicated',
     'Azitromicina prolonga QT — risco torsade. Box warning FDA 2013.',
     'Trocar por antibiótico não-prolongador (ex: amoxicilina, doxiciclina).',
     'manual', 0.97),

    -- Insuficiência renal grave → dabigatrana
    ('doenca renal cronica', 'dabigatrana', NULL, 'warning',
     'Dabigatrana excretada 80% pelos rins. ClCr <30 contraindica (FDA box).',
     'Confirmar ClCr atual. Se <30 trocar para apixabana.',
     'kdigo', 0.97),

    -- DM + obesidade → olanzapina (piora dislipidemia/DM)
    ('diabetes', 'olanzapina', NULL, 'warning',
     'Olanzapina piora controle glicêmico e dislipidemia.',
     'Preferir aripiprazol ou quetiapina (perfil metabólico melhor).',
     'beers_2023', 0.9)
ON CONFLICT DO NOTHING;


-- =====================================================
-- 6. renal_adjustments
-- =====================================================
INSERT INTO aia_health_drug_renal_adjustments
    (principle_active, clcr_min, clcr_max, action, rationale, source)
VALUES
    -- Pramipexol
    ('pramipexol', 0, 30, 'avoid',
     'ClCr <30: contraindicado.', 'kdigo'),
    ('pramipexol', 30, 50, 'reduce_50pct',
     'ClCr 30-50: reduzir dose 50% e dividir em 2 tomadas.', 'anvisa'),
    ('pramipexol', 50, 999, 'no_adjustment',
     'ClCr ≥50: sem ajuste.', 'anvisa'),

    -- Ropinirol (excreção renal mínima — só monitorar)
    ('ropinirol', 0, 30, 'monitor',
     'ClCr <30: dados limitados. Iniciar dose mínima e titular devagar.', 'manual'),
    ('ropinirol', 30, 999, 'no_adjustment', 'Sem ajuste.', 'anvisa'),

    -- Risperidona
    ('risperidona', 0, 30, 'reduce_50pct',
     'ClCr <30: reduzir 50% e iniciar 0,5mg 12/12h.', 'kdigo'),
    ('risperidona', 30, 999, 'no_adjustment', 'Sem ajuste.', 'anvisa'),

    -- Quetiapina (metabolismo hepático predominante)
    ('quetiapina', 0, 999, 'no_adjustment',
     'Quetiapina: metabolismo hepático CYP3A4. Sem ajuste renal.', 'anvisa'),

    -- Olanzapina
    ('olanzapina', 0, 999, 'no_adjustment',
     'Olanzapina: sem ajuste renal (metabolismo hepático).', 'anvisa'),

    -- Amoxicilina+clavulanato
    ('amoxicilina+clavulanato', 0, 10, 'reduce_75pct',
     'ClCr <10: 500/125mg 24/24h (componente clavulanato é o limitante).', 'kdigo'),
    ('amoxicilina+clavulanato', 10, 30, 'reduce_50pct',
     'ClCr 10-30: 500/125mg 12/12h.', 'kdigo'),
    ('amoxicilina+clavulanato', 30, 999, 'no_adjustment',
     'Sem ajuste se ClCr ≥30.', 'kdigo'),

    -- Azitromicina (sem ajuste renal de rotina)
    ('azitromicina', 0, 999, 'no_adjustment',
     'Azitromicina: sem ajuste renal — excreção biliar predominante.',
     'anvisa'),

    -- Dabigatrana — chave da segurança
    ('dabigatrana', 0, 30, 'avoid',
     'ClCr <30: CONTRAINDICADO. Trocar para apixabana.', 'fda'),
    ('dabigatrana', 30, 50, 'reduce_50pct',
     'ClCr 30-50: 110mg 12/12h (em vez de 150mg).', 'fda'),
    ('dabigatrana', 50, 999, 'no_adjustment',
     'ClCr ≥50: dose padrão 150mg 12/12h.', 'fda')
ON CONFLICT DO NOTHING;


-- =====================================================
-- 7. hepatic_adjustments
-- =====================================================
INSERT INTO aia_health_drug_hepatic_adjustments
    (principle_active, severity_class, action, rationale, source, confidence)
VALUES
    -- Quetiapina (CYP3A4 — alvo hepático)
    ('quetiapina', 'child_a', 'reduce_50pct',
     'CYP3A4 — clearance reduz ~30%. Iniciar 25mg/dia e titular devagar.',
     'fda', 0.9),
    ('quetiapina', 'child_b', 'reduce_75pct',
     'Clearance reduz ainda mais. 12,5mg/dia e monitorar sedação.',
     'fda', 0.9),
    ('quetiapina', 'child_c', 'avoid',
     'Hepatopatia grave: evitar. Trocar para haloperidol dose mínima ou avaliar suspender.',
     'manual', 0.85),

    -- Olanzapina
    ('olanzapina', 'child_a', 'caution_monitor',
     'Possíveis elevações leves de transaminases. Monitorar enzimas hepáticas.',
     'fda', 0.85),
    ('olanzapina', 'child_b', 'reduce_50pct',
     'Reduzir dose pela metade (2,5-5mg/dia).', 'fda', 0.85),
    ('olanzapina', 'child_c', 'avoid',
     'Hepatopatia grave: evitar.', 'manual', 0.85),

    -- Risperidona
    ('risperidona', 'child_a', 'caution_monitor', 'Sem ajuste rotineiro. Monitorar.', 'fda', 0.85),
    ('risperidona', 'child_b', 'reduce_50pct',
     'Reduzir dose. Iniciar 0,5mg 12/12h.', 'fda', 0.85),
    ('risperidona', 'child_c', 'reduce_75pct',
     'Hepatopatia grave: reduzir significativamente. Iniciar 0,25mg 12/12h.',
     'manual', 0.8),

    -- Amoxicilina+clavulanato (hepatotoxicidade colestática rara mas séria)
    ('amoxicilina+clavulanato', 'child_a', 'caution_monitor',
     'Risco hepatotoxicidade colestática (especialmente curso >14d ou homens >55a). Monitorar enzimas. Cursos curtos (<7d).',
     'fda', 0.9),
    ('amoxicilina+clavulanato', 'child_b', 'caution_monitor',
     'Mesmo cuidado, mais rigoroso. Cursos curtos. Reavaliar diariamente.',
     'fda', 0.85),
    ('amoxicilina+clavulanato', 'child_c', 'avoid',
     'Hepatopatia grave: evitar. Preferir antibiótico não-hepatotóxico (ceftriaxona).',
     'manual', 0.85),

    -- Azitromicina
    ('azitromicina', 'child_a', 'no_adjustment', 'Sem ajuste.', 'fda', 0.85),
    ('azitromicina', 'child_b', 'caution_monitor',
     'Hepatotoxicidade rara mas reportada. Monitorar enzimas se uso prolongado.', 'fda', 0.8),
    ('azitromicina', 'child_c', 'avoid',
     'Hepatopatia grave: evitar. Trocar antibiótico.', 'manual', 0.8),

    -- Dabigatrana (excreção renal — hepático tem menos peso)
    ('dabigatrana', 'child_a', 'no_adjustment', 'Sem ajuste rotineiro.', 'fda', 0.85),
    ('dabigatrana', 'child_b', 'caution_monitor',
     'Dados limitados em hepatopatia moderada. Monitorar e considerar alternativa (apixabana).',
     'fda', 0.8),
    ('dabigatrana', 'child_c', 'avoid',
     'Hepatopatia grave: evitar. Apixabana é alternativa.', 'fda', 0.85),

    -- Pramipexol (eliminação renal — hepático sem ajuste)
    ('pramipexol', 'child_a', 'no_adjustment', 'Eliminação renal.', 'fda', 0.85),
    ('pramipexol', 'child_b', 'no_adjustment', 'Sem ajuste.', 'fda', 0.85),
    ('pramipexol', 'child_c', 'caution_monitor', 'Hepatopatia grave: dados limitados, monitorar.', 'manual', 0.7),

    -- Ropinirol (CYP1A2 — hepatic-dependent)
    ('ropinirol', 'child_a', 'caution_monitor', 'Metabolismo CYP1A2. Iniciar dose mínima.', 'fda', 0.85),
    ('ropinirol', 'child_b', 'reduce_50pct', 'Clearance reduzido. Iniciar 0,25mg.', 'fda', 0.8),
    ('ropinirol', 'child_c', 'avoid', 'Hepatopatia grave: evitar.', 'manual', 0.8)
ON CONFLICT DO NOTHING;


-- =====================================================
-- 8. fall_risk
-- =====================================================
INSERT INTO aia_health_drug_fall_risk
    (therapeutic_class, fall_risk_score, rationale)
VALUES
    ('antipsicotico_atipico', 2,
     'Antipsicóticos atípicos: sedação + hipotensão postural + extrapiramidalismo — alto risco queda.'),
    ('antiparkinsoniano_agonista_d2', 1,
     'Agonistas D2/D3: hipotensão postural + sono diurno súbito + alucinações — risco queda.')
ON CONFLICT DO NOTHING;


-- =====================================================
-- 9. anticholinergic_burden
-- =====================================================
INSERT INTO aia_health_drug_anticholinergic_burden
    (principle_active, burden_score, notes) VALUES
    ('olanzapina', 3, 'ACB 3 — anticolinérgico forte (constipação, retenção, confusão).'),
    ('quetiapina', 2, 'ACB 2 — moderado (sedação + xerostomia).'),
    ('risperidona', 1, 'ACB 1 — fraco.'),
    ('pramipexol', 0, NULL),
    ('ropinirol', 0, NULL),
    ('amoxicilina+clavulanato', 0, NULL),
    ('azitromicina', 0, NULL),
    ('dabigatrana', 0, NULL)
ON CONFLICT (principle_active) DO NOTHING;


-- =====================================================
-- 10. vital_constraints
-- =====================================================
INSERT INTO aia_health_drug_vital_constraints
    (therapeutic_class, vital_field, operator, threshold,
     severity, rationale, recommendation, source) VALUES
    ('antipsicotico_atipico', 'bp_systolic', 'lt', 100,
     'warning_strong',
     'PA <100 + antipsicótico atípico: risco hipotensão postural + queda + síncope.',
     'Adiar dose. Reavaliar PA + posição. Considerar redução.',
     'manual')
ON CONFLICT DO NOTHING;


COMMIT;
