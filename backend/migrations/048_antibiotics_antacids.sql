-- ConnectaIACare — Antibióticos + antiácidos não-IBP.
--
-- Adicionado conforme mensagem do Henrique:
-- "Se adicionarmos antibióticos e antiácidos, vamos estar cobrindo
--  uma gama bem completa dos remédios mais usados para o nosso público alvo"
--
-- Antibióticos comunitários (foco geriatria): cefalexina, cefuroxima,
-- doxiciclina, claritromicina, levofloxacino, metronidazol,
-- nitrofurantoína, norfloxacino. NÃO inclui antibióticos hospitalares
-- (vancomicina, ceftriaxona EV, meropenem) — fora do escopo cuidado
-- contínuo domiciliar.
--
-- Antiácidos não-IBP: hidróxido de alumínio + magnésio, magaldrato,
-- famotidina (H2). Cimetidina NÃO incluída por desuso + Beers AVOID
-- (interações).
--
-- Ranitidina: NÃO incluída — retirada do mercado por NDMA em 2020.
--
-- Tier Verde + Amarelo. Disclaimer reforçado em produção.

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- ANTIBIÓTICOS COMUNITÁRIOS
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto, auto_review_notes)
VALUES
('cefalexina', 'oral', 4000, 'mg', 'antibiotico_cefalosporina_1g', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Cefalosporina 1ª geração — ITU não complicada, infecção pele/parte mole'),
('cefuroxima', 'oral', 1000, 'mg', 'antibiotico_cefalosporina_2g', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Cefalosporina 2ª geração — sinusite, pneumonia comunitária'),
('doxiciclina', 'oral', 200, 'mg', 'antibiotico_tetraciclina', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Tetraciclina — DPOC exacerbação, doença Lyme, leptospirose'),
('claritromicina', 'oral', 1000, 'mg', 'antibiotico_macrolideo', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Macrolídeo — H. pylori (em esquema tríplice), pneumonia atípica. '
 'Cuidado QT longo + interações via CYP3A4'),
('levofloxacino', 'oral', 750, 'mg', 'antibiotico_quinolona', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Quinolona respiratória — pneumonia comunitária, ITU complicada. '
 'FDA black box: tendinite/ruptura tendão, neuropatia periférica'),
('metronidazol', 'oral', 2000, 'mg', 'antibiotico_nitroimidazol', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Anaeróbico — H. pylori (esquema tríplice), C. difficile (1ª linha BR), '
 'tricomoníase, vaginose. Efeito antabuse com álcool.'),
('nitrofurantoina', 'oral', 400, 'mg', 'antibiotico_nitrofurano', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'ITU não complicada — Beers AVOID se ClCr<30 (acumulo + neuropatia)'),
('norfloxacino', 'oral', 800, 'mg', 'antibiotico_quinolona', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Quinolona ITU — restrição ao trato urinário'),
('benzilpenicilina_benzatina', 'intramuscular', 2400000, 'UI', 'antibiotico_beta_lactamico', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Sífilis (todos estágios), profilaxia febre reumática. Dose em UI, não mg.'),
('eritromicina', 'oral', 2000, 'mg', 'antibiotico_macrolideo', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Macrolídeo antigo — alternativa em alergia penicilina. Alta interação CYP3A4')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- ANTIÁCIDOS NÃO-IBP
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto, auto_review_notes)
VALUES
('hidroxido_aluminio_magnesio', 'oral', 6000, 'mg', 'antiacido', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Antiácido de neutralização rápida — uso pontual de 1-2h. '
 'Quelante de muitos fármacos: separar 2-4h de quinolonas, tetraciclinas, '
 'levotiroxina, ferro, bifosfonatos.'),
('magaldrato', 'oral', 4000, 'mg', 'antiacido', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Antiácido similar ao hidróxido Al/Mg — mesmas interações de espaçamento.'),
('famotidina', 'oral', 80, 'mg', 'antagonista_h2', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Bloqueador H2 — alternativa a IBP. Ajuste renal se ClCr<50. '
 'Menor cascata de absorção que IBP (B12, Ca++, Mg++)'),
('bicarbonato_sodio', 'oral', 4000, 'mg', 'antiacido', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Antiácido sistêmico — uso pontual. Cuidado em paciente com IC, HAS '
 '(carga de sódio) ou IRC (alcalose metabólica).')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- BEERS / Contraindicações por condição (antibióticos + antiácidos)
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_condition_contraindications (
    condition_term, condition_icd10,
    affected_principle_active, affected_therapeutic_class,
    severity, rationale, recommendation, source, source_ref, confidence,
    auto_generated, review_status
) VALUES
-- Nitrofurantoína em IRC severa
('IRC com ClCr<30', 'N18', 'nitrofurantoina', NULL,
 'contraindicated',
 'Beers 2023 AVOID em ClCr<30 — acúmulo, ineficácia urinária + neuropatia '
 'periférica',
 'Em ITU não complicada com IRC, preferir cefalexina, fosfomicina ou '
 'sulfa+trimetoprima',
 'beers_2023', 'AGS Beers 2023', 0.95,
 TRUE, 'auto_pending'),

-- Doxiciclina em fotossensibilidade documentada
('idoso ≥65 + exposição solar prolongada', NULL, 'doxiciclina', NULL,
 'caution',
 'Reação fotossensível em pele frágil de idoso',
 'Orientar proteção solar rigorosa durante uso',
 'manual', 'Bula ANVISA', 0.75,
 TRUE, 'auto_pending'),

-- Claritromicina + estatina (rabdomiólise)
('uso concomitante de estatina', NULL, 'claritromicina', NULL,
 'contraindicated',
 'Inibidor potente CYP3A4 → aumenta exposição de sinvastatina e atorvastatina '
 '5-10x → rabdomiólise. Sinvastatina é a pior.',
 'Suspender estatina durante curso de claritromicina (5-14 dias) OU substituir '
 'antibiótico por azitromicina (menos interação)',
 'manual', 'Lexicomp interação severa (curadoria interna)', 0.95,
 TRUE, 'auto_pending'),

-- Levofloxacino — tendinopatia
('idoso ≥65', NULL, 'levofloxacino', NULL,
 'caution',
 'FDA black box: tendinite e ruptura tendão (Aquileu mais comum) em ≥65, '
 'especialmente associado com corticoide. Risco neuropatia periférica',
 'Em uso simultâneo de corticoide, considerar alternativa não-quinolona. '
 'Orientar paciente sobre dor tendínea — suspender imediatamente se aparecer',
 'beers_2023', 'AGS Beers 2023 + FDA', 0.90,
 TRUE, 'auto_pending'),

-- Metronidazol + álcool
('uso concomitante de álcool', NULL, 'metronidazol', NULL,
 'contraindicated',
 'Efeito antabuse — náusea, vômito, taquicardia, hipotensão por bloqueio '
 'da aldeído desidrogenase',
 'Abstinência total durante uso + 48h após última dose',
 'manual', 'Bula ANVISA', 0.95,
 TRUE, 'auto_pending'),

-- Famotidina ajuste renal
('IRC com ClCr<50', 'N18', 'famotidina', NULL,
 'caution',
 'Acúmulo em IRC → confusão mental em idoso',
 'ClCr 30-50: reduzir dose 50%; ClCr<30: 25% da dose; monitor estado mental',
 'kdigo', 'KDIGO 2024', 0.85,
 TRUE, 'auto_pending'),

-- Antiácidos AlMg em IRC
('IRC com ClCr<30', 'N18', 'hidroxido_aluminio_magnesio', NULL,
 'caution',
 'Acúmulo de alumínio (encefalopatia) e magnésio (hipermagnesemia) em IRC',
 'AVOID em IRC severa; em IRC moderada usar pontualmente <1 semana',
 'kdigo', 'KDIGO 2024', 0.85,
 TRUE, 'auto_pending')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- INTERAÇÕES TIME-SEPARATION (mitigáveis por horário) — antiácidos
-- Henrique: "antiácidos é uma classe que normalmente espaçando se evitam
-- muitos contratempos"
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_drug_interactions
    (principle_a, class_b, severity, mechanism, clinical_effect,
     recommendation, onset, source, source_ref, confidence)
VALUES
-- Hidróxido Al/Mg vs quinolonas
('hidroxido_aluminio_magnesio', 'antibiotico_quinolona', 'moderate',
 'Quelação intestinal — antiácido reduz absorção de quinolonas em até 90%',
 'Falha terapêutica do antibiótico se administrado junto',
 'Espaçar 2-4h entre antiácido e quinolona. Antiácido ANTES do antibiótico '
 'ou pelo menos 4h depois.',
 'rapid', 'stockleys', 'Stockley''s Drug Interactions', 0.95),

-- Hidróxido Al/Mg vs tetraciclinas (doxiciclina)
('hidroxido_aluminio_magnesio', 'antibiotico_tetraciclina', 'moderate',
 'Quelação por cátions divalentes (Al³⁺, Mg²⁺) → reduz absorção 50-90%',
 'Falha terapêutica',
 'Espaçar 2-3h. Mesma orientação para alimentos lácteos.',
 'rapid', 'stockleys', 'Stockley''s Drug Interactions', 0.95),

-- Hidróxido Al/Mg vs levotiroxina
('hidroxido_aluminio_magnesio', 'hormonio_tireoide', 'moderate',
 'Quelação reduz absorção de levotiroxina',
 'Hipotireoidismo subclínico/manifesto se uso crônico simultâneo',
 'Espaçar 4h. Levotiroxina deve ser tomada em jejum, antiácido após café.',
 'delayed', 'stockleys', 'Stockley''s Drug Interactions', 0.90),

-- Hidróxido Al/Mg vs ferro oral
('hidroxido_aluminio_magnesio', 'mineral_ferro', 'moderate',
 'Quelação reduz absorção do sulfato ferroso',
 'Ineficácia da suplementação',
 'Espaçar 2-3h ou tomar ferro 1h antes das refeições.',
 'rapid', 'stockleys', 'Stockley''s Drug Interactions', 0.90),

-- Hidróxido Al/Mg vs bifosfonatos
('hidroxido_aluminio_magnesio', 'bifosfonato', 'major',
 'Quelação severa — alendronato/risedronato perdem absorção',
 'Falha terapêutica; pode aparentar ineficácia do bifosfonato',
 'Bifosfonato em jejum 30min antes do desjejum. Antiácido só APÓS o desjejum '
 '(separar 1-2h do bifosfonato no mínimo).',
 'rapid', 'stockleys', 'Stockley''s Drug Interactions', 0.95)
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- ACB SCORE para antibióticos com efeito anticolinérgico discreto
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_drug_anticholinergic_burden
    (principle_active, burden_score, notes, source,
     auto_generated, review_status)
VALUES
('famotidina', 1, 'H2 bloqueador — efeito anticolinérgico leve documentado em ACB scale', 'acb_scale',
 TRUE, 'auto_pending')
-- Cimetidina seria ACB 2 mas não estamos incluindo (Beers AVOID + desuso)
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- FALL RISK SCORE para classes novas
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_drug_fall_risk
    (therapeutic_class, fall_risk_score, rationale, source,
     auto_generated, review_status)
VALUES
('antibiotico_quinolona', 1,
 'Risco neuropatia periférica + tendinopatia (ruptura tendão Aquileu)',
 'fda_black_box', TRUE, 'auto_pending'),
('antibiotico_tetraciclina', 0,
 'Sem aumento direto de risco de queda',
 'manual', TRUE, 'auto_pending'),
('antagonista_h2', 1,
 'Confusão mental em idoso (especialmente em IRC) → risco queda',
 'manual', TRUE, 'auto_pending')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- Atualiza tracker RENAME com antibióticos + antiácidos
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_rename_drugs
    (principle_active, componente, edicao, formas_disponiveis,
     grupo_terapeutico, populacao_alvo, indicacao_sus,
     geriatric_relevance, motor_coverage, notes_curador)
VALUES
-- Antibióticos
('cefalexina', 'basico', '2024', ARRAY['comprimido', 'cápsula', 'suspensão'],
 'Antibiótico cefalosporina 1ª geração', ARRAY['adulto', 'idoso', 'pediatria'],
 'ITU não complicada · pele/parte mole', 'high', 'in_progress',
 'Adicionado por solicitação Henrique. Auto-populate.'),
('cefuroxima', 'basico', '2024', ARRAY['comprimido', 'suspensão'],
 'Antibiótico cefalosporina 2ª geração', ARRAY['adulto', 'idoso', 'pediatria'],
 'Sinusite · pneumonia comunitária', 'high', 'in_progress',
 'Adicionado por solicitação Henrique.'),
('doxiciclina', 'basico', '2024', ARRAY['cápsula', 'comprimido'],
 'Antibiótico tetraciclina', ARRAY['adulto', 'idoso'],
 'DPOC exacerbação · doenças por riquétsia · leptospirose', 'high', 'in_progress',
 'Adicionado por solicitação Henrique.'),
('claritromicina', 'basico', '2024', ARRAY['comprimido'],
 'Antibiótico macrolídeo', ARRAY['adulto', 'idoso'],
 'H. pylori esquema tríplice · pneumonia atípica', 'high', 'in_progress',
 'CUIDADO com estatinas — interação severa via CYP3A4'),
('levofloxacino', 'basico', '2024', ARRAY['comprimido'],
 'Antibiótico quinolona respiratória', ARRAY['adulto', 'idoso'],
 'Pneumonia comunitária · ITU complicada', 'high', 'in_progress',
 'FDA black box tendinite — cuidado com corticoide simultâneo'),
('metronidazol', 'basico', '2024', ARRAY['comprimido', 'suspensão', 'gel'],
 'Antibiótico nitroimidazol', ARRAY['adulto', 'idoso'],
 'H. pylori · C. difficile · vaginose', 'high', 'in_progress',
 'Efeito antabuse com álcool'),
('nitrofurantoina', 'basico', '2024', ARRAY['cápsula', 'suspensão'],
 'Antibiótico nitrofurano', ARRAY['adulto', 'idoso'],
 'ITU não complicada', 'high', 'in_progress',
 'Beers AVOID se ClCr<30'),
('norfloxacino', 'basico', '2024', ARRAY['comprimido'],
 'Antibiótico quinolona urinária', ARRAY['adulto', 'idoso'],
 'ITU recorrente · profilaxia', 'medium', 'in_progress',
 'Auto-populate.'),
('benzilpenicilina_benzatina', 'basico', '2024', ARRAY['injetavel intramuscular'],
 'Antibiótico beta-lactâmico', ARRAY['adulto', 'idoso', 'pediatria'],
 'Sífilis · profilaxia febre reumática', 'medium', 'in_progress',
 'Aplicação intramuscular profunda · dor local'),
('eritromicina', 'basico', '2024', ARRAY['comprimido', 'suspensão'],
 'Antibiótico macrolídeo', ARRAY['adulto', 'idoso'],
 'Alternativa em alergia penicilina · acne (uso prolongado)', 'low', 'in_progress',
 'Pouco usado em geriatria — alta interação CYP3A4'),

-- Antiácidos não-IBP
('hidroxido_aluminio_magnesio', 'basico', '2024', ARRAY['suspensão', 'comprimido mastigável'],
 'Antiácido de neutralização', ARRAY['adulto', 'idoso'],
 'Dispepsia ácida pontual', 'high', 'in_progress',
 'Adicionado por solicitação Henrique. Múltiplas interações time-separation'),
('magaldrato', 'basico', '2024', ARRAY['suspensão', 'comprimido'],
 'Antiácido de neutralização', ARRAY['adulto', 'idoso'],
 'Dispepsia · pirose', 'medium', 'in_progress',
 'Auto-populate.'),
('famotidina', 'basico', '2024', ARRAY['comprimido', 'injetavel'],
 'Antagonista receptor H2', ARRAY['adulto', 'idoso'],
 'DRGE · úlcera péptica · alternativa a IBP', 'high', 'in_progress',
 'Menor cascata de má absorção que IBP'),
('bicarbonato_sodio', 'basico', '2024', ARRAY['comprimido', 'pó'],
 'Antiácido sistêmico', ARRAY['adulto', 'idoso'],
 'Dispepsia pontual · acidose metabólica', 'low', 'in_progress',
 'Cuidado em IC, HAS, IRC — carga de sódio')
ON CONFLICT (principle_active, edicao) DO NOTHING;


COMMIT;
