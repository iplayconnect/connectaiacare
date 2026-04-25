-- ConnectaIACare — Seed da base de conhecimento da Sofia.
--
-- Carrega chunks que documentam:
--   1. Plataforma (domain='company'): páginas /admin/regras-clinicas,
--      /alertas/clinicos, motor de cruzamentos, revalidação semanal,
--      auditoria, validação de prescrição, papéis & permissões.
--   2. Geriatria/medicações (domain='geriatrics' ou 'medications'):
--      Beers em demência, DOACs e ClCr, antipsicóticos atípicos em
--      Parkinson, ACB cumulativo, fall risk, Child-Pugh, NTI.
--
-- Embeddings ficam NULL nesta seed — query_clinical_guidelines usa
-- ILIKE por enquanto. Quando o pgvector retrieval estiver ativo, um
-- backfill computa embeddings em lote.

BEGIN;

-- =====================================================
-- 1. PLATAFORMA — funcionalidades + caminhos UI
-- =====================================================

INSERT INTO aia_health_knowledge_chunks
    (tenant_id, domain, subdomain, title, content, summary, keywords,
     priority, confidence, source, source_type)
VALUES
('default', 'company', 'motor_cruzamentos',
 'Motor de cruzamentos clínicos — 12 dimensões',
 'A ConnectaIACare valida toda prescrição contra 12 dimensões deterministicamente antes de salvar:
1. Dose máxima diária (ANVISA / FDA por princípio ativo).
2. Beers AVOID + Beers Caution (Critérios de Beers 2023, geriatria).
3. Alergias documentadas + reações cruzadas (ex: penicilina↔β-lactâmicos).
4. Duplicidade terapêutica (mesmo princípio ou mesma classe).
5. Polifarmácia (carga total ≥ N medicamentos).
6. Interações medicamento-medicamento (com time_separation_minutes para interações por absorção que podem ser mitigadas espaçando os horários, ex: levotiroxina + carbonato de cálcio = espaçar 4h).
7. Contraindicações por condição clínica do paciente.
8. ACB score (Anticholinergic Cognitive Burden cumulativo).
9. Fall risk score (risco de queda por classe terapêutica).
10. Ajuste renal por faixa de ClCr (Cockcroft-Gault, regras KDIGO).
11. Ajuste hepático Child-Pugh A/B/C.
12. Constraints de sinais vitais (ex: PA <110 + BCCa di-hidropiridínico).

A função central é src/services/dose_validator.py:validate(). Retorna severity (info/warning/warning_strong/block) + lista de issues. Severity=block faz POST de medication_schedule retornar 422 (médico precisa passar force=true assumindo responsabilidade — fica em audit chain).',
 'Motor valida prescrição em 12 dimensões antes de salvar; severity=block bloqueia POST com 422.',
 ARRAY['motor', 'cruzamento', 'validacao', 'dose_validator', '12 dimensoes', 'severity', 'block'],
 90, 'high', 'internal', 'internal_curated'),

('default', 'company', 'admin_regras_clinicas',
 'Página /admin/regras-clinicas — CRUD do motor',
 'Em /admin/regras-clinicas o admin_tenant ou super_admin pode editar TODAS as tabelas que alimentam o motor de cruzamentos. Tabs:
• Visão geral (stats agregados de cada tabela).
• Doses máximas — CRUD completo. Inclui flag beers_avoid + therapeutic_class + narrow_therapeutic_index.
• Aliases — mapeamento nome comercial ↔ princípio ativo (Sifrol→pramipexol).
• Interações — CRUD completo, com campo time_separation_minutes (>0 = mitigável espaçando horários).
• Alergias, Contraindicações por condição, Ajuste renal, Ajuste hepático, Fall risk, ACB, Sinais vitais — read-only no momento (escrita prevista para próxima fase).

Toda edição grava em aia_health_audit_chain (LGPD-compliant hash chain). Permissão exigida: super_admin OU admin_tenant.',
 'Admin edita doses, aliases e interações em /admin/regras-clinicas; demais tabelas read-only.',
 ARRAY['admin', 'regras clinicas', 'CRUD', 'dose maxima', 'interacao', 'alias'],
 80, 'high', 'internal', 'internal_curated'),

('default', 'company', 'alertas_clinicos',
 'Página /alertas/clinicos — alertas do motor',
 'Existem DUAS páginas de alertas distintas:
• /alertas — triagem clínica de care_events (relatos de cuidador, queixas, eventos críticos). Lista alertas vindos de care_events ativos + reports recentes.
• /alertas/clinicos — alertas escritos pelo motor de cruzamentos em aia_health_alerts (validação de dose, interação, contraindicação detectada). Filtros por nível (critical/high/medium/low) e status (open/acknowledged/resolved/active/all). Botões inline para reconhecer ou resolver.

Endpoints: GET /api/alerts/clinical (lista), POST /api/alerts/<id>/acknowledge, POST /api/alerts/<id>/resolve.',
 'Triagem em /alertas (care_events). Cruzamentos automáticos em /alertas/clinicos (motor).',
 ARRAY['alertas', 'clinicos', 'aia_health_alerts', 'acknowledge', 'resolve'],
 80, 'high', 'internal', 'internal_curated'),

('default', 'company', 'revalidacao_semanal',
 'Cron worker dose_revalidation_scheduler',
 'Há um worker em background (dose_revalidation_scheduler.py) que re-roda o motor de cruzamentos sobre TODAS as prescrições ativas. Tick a cada 6h, intervalo de revalidação 7 dias por prescrição. Se uma regra nova for adicionada via /admin/regras-clinicas (ou o paciente ganhar uma condição nova, novo valor de creatinina, etc.), prescrições antigas que passem a violar geram alertas em /alertas/clinicos automaticamente.

Dedupe: não recria alerta se já houver um aberto OU resolvido nos últimos 7 dias com o mesmo conjunto de issue codes para a mesma prescrição. Lock advisory dedicado (DOSE_REVALIDATION_LOCK_KEY=1428367219) garante single-writer entre múltiplos workers Gunicorn.

Variáveis de ambiente: ENABLE_DOSE_REVALIDATION (default true), DOSE_REVAL_TICK_SEC (6h), DOSE_REVALIDATION_INTERVAL_HOURS (168=7d), DOSE_REVAL_BATCH_SIZE (100).',
 'Worker re-valida prescrições ativas a cada 7 dias; alertas novos vão pra /alertas/clinicos.',
 ARRAY['cron', 'revalidacao', 'scheduler', 'background', 'worker'],
 70, 'high', 'internal', 'internal_curated'),

('default', 'company', 'audit_chain',
 'Auditoria LGPD via hash chain (aia_health_audit_chain)',
 'Toda mudança em dado clínico ou regra do motor é registrada em aia_health_audit_chain. Cada linha contém: timestamp, user_id, action, target_table, target_id, payload, prev_hash, hash. O hash atual = SHA256(payload + prev_hash) — formando uma cadeia inviolável que detecta qualquer adulteração retroativa.

Endpoints que escrevem audit: /api/auth/login (login.success/failure), /api/users/* (user.create/update/disable), /api/profiles/* (profile.create/update/delete), /api/clinical-rules/* (rule.dose_limit/alias/interaction.create/update/delete), /api/medication-schedules forced (schedule.force_create override).',
 'Toda edição clínica vai pra hash chain SHA256; detecta adulteração retroativa.',
 ARRAY['audit', 'lgpd', 'hash chain', 'sha256', 'rastreabilidade'],
 70, 'high', 'internal', 'internal_curated'),

('default', 'company', 'validate_prescription_endpoint',
 'POST /api/clinical-rules/validate-prescription — validação ad-hoc',
 'Endpoint que roda o dose_validator.validate() SEM persistir nada. Usado:
• Pela tool da Sofia check_medication_safety (médico pergunta "é seguro X mg de Y para o paciente Z?").
• Pela UI de prescrição como preview antes de salvar.

Body: { medication_name, dose, times_of_day?, route?, schedule_type?, patient_id? OU patient: {birth_date, allergies, conditions, weight_kg, serum_creatinine_mg_dl} }.

Retorno: { status: "ok", validation: { severity, issues: [{code, severity, message, detail}], computed_daily_dose, principle_active, ratio, source, ... } }.

NÃO escreve aia_health_alerts. Quem cria alertas é o endpoint que de fato persiste a schedule (POST /api/patients/<id>/medication-schedules) ou o dose_revalidation_scheduler.',
 'Endpoint preview de validação; não persiste; não cria alertas.',
 ARRAY['validate-prescription', 'preview', 'sem persistir', 'check_medication_safety'],
 70, 'high', 'internal', 'internal_curated'),

('default', 'company', 'paginas_admin',
 'Páginas administrativas e permissões',
 'Páginas em /admin/* e quem acessa:
• /admin/usuarios — CRUD usuários do tenant. Permissão: users:read/write.
• /admin/perfis — CRUD perfis customizados (papéis com listas de permissions). Permissão: profiles:read/write.
• /admin/regras-clinicas — CRUD do motor de cruzamentos. Permissão: super_admin OU admin_tenant (NÃO usa permission, é por role).
• /admin/auditoria — Ler aia_health_audit_chain. Permissão: audit:read.
• /alertas — Triagem clínica. Permissão: alerts:read.
• /alertas/clinicos — Alertas do motor. Permissão: alerts:read.

Roles do sistema: super_admin (cross-tenant), admin_tenant (admin do próprio tenant), medico, enfermeiro, parceiro, cuidador_pro, familia, paciente_b2c.',
 'Mapa de páginas /admin e permissões correspondentes.',
 ARRAY['admin', 'usuarios', 'perfis', 'auditoria', 'roles', 'permissions'],
 80, 'high', 'internal', 'internal_curated'),

('default', 'company', 'sofia_tools_clinicas',
 'Tools clínicas da Sofia (motor de cruzamentos)',
 'A Sofia tem 4 tools que acessam o motor de cruzamentos clínicos diretamente (apenas para personas medico/enfermeiro/admin_tenant/super_admin):

1. check_medication_safety(medication_name, dose, patient_id?, times_of_day?, route?) — roda as 12 dimensões para uma prescrição candidata SEM persistir. Retorna severity + issues. Use ANTES de criar/atualizar uma medication_schedule.

2. query_drug_rules(medication_name) — devolve TODAS as regras carregadas para um princípio ativo: dose, interações, contraindicações, renal, hepático, ACB, fall risk, alergias. Use para "me conta tudo sobre X".

3. check_drug_interaction(med_a, med_b) — lookup determinístico de um par específico. Inclui interações por classe terapêutica. Retorna severity, mecanismo, time_separation_minutes (>0 = mitigável). Use para "posso usar X com Y?".

4. list_beers_avoid_in_condition(condition) — lista contraindicações para uma condição. Resolve aliases (cirrose child b → child_b). Use para "o que evitar em paciente com X?".',
 'check_medication_safety, query_drug_rules, check_drug_interaction, list_beers_avoid_in_condition.',
 ARRAY['tools', 'sofia', 'check_medication_safety', 'query_drug_rules', 'check_drug_interaction', 'list_beers_avoid'],
 90, 'high', 'internal', 'internal_curated'),

('default', 'company', 'medicamentos_cobertos',
 'Medicamentos cobertos pelo motor (~48 princípios ativos)',
 'Cobertura atual do motor de cruzamentos (princípios ativos com dose máxima + classe terapêutica registradas):

Anti-hipertensivos: losartana, enalapril, anlodipino, nifedipino, propranolol, atenolol, carvedilol, metoprolol.
Antidiabéticos: metformina, glibenclamida, gliclazida, empagliflozina, dapagliflozina.
Antiplaquetários: ácido acetilsalicílico, clopidogrel.
Anticoagulantes: varfarina, rivaroxabana, apixabana, dabigatrana.
Estatinas: sinvastatina, atorvastatina, rosuvastatina.
IBPs: omeprazol, pantoprazol, esomeprazol.
Antidepressivos: sertralina, fluoxetina, escitalopram, mirtazapina.
Hipnóticos/ansiolíticos: clonazepam, diazepam, alprazolam, zolpidem.
Antipsicóticos: haloperidol, risperidona, quetiapina, olanzapina.
Antiparkinsonianos: levodopa+carbidopa, pramipexol, ropinirol.
Antieméticos: metoclopramida, ondansetrona.
Antibióticos: amoxicilina, amoxicilina+clavulanato, azitromicina, ciprofloxacino, sulfametoxazol+trimetoprima.
Outros: paracetamol, dipirona, ibuprofeno, naproxeno, diclofenaco, alendronato, levotiroxina, carbonato de cálcio.

Para confirmar cobertura específica de um medicamento, use query_drug_rules(medication_name) — ele resolve aliases comerciais.',
 '~48 princípios ativos cobertos: cardiovasculares, antibióticos, psicotrópicos, antiparkinsonianos, anticoagulantes.',
 ARRAY['cobertura', 'medicamentos', 'principios ativos', 'lista'],
 70, 'high', 'internal', 'internal_curated'),


-- =====================================================
-- 2. CLÍNICO — narrativas geriátricas
-- =====================================================

('default', 'geriatrics', 'beers_demencia',
 'Beers 2023 — antipsicóticos em demência',
 'Os Critérios de Beers 2023 marcam antipsicóticos atípicos (risperidona, quetiapina, olanzapina) e típicos (haloperidol) como AVOID em demência, EXCETO sintomas psicóticos refratários graves. Box warning FDA: aumenta mortalidade e AVC em idosos com demência.

Conduta recomendada antes de prescrever:
1. Avaliar causas reversíveis de agitação: dor não controlada, infecção (urinária, respiratória), constipação, retenção urinária, polifarmácia anticolinérgica.
2. Tentativa de intervenções não-farmacológicas (música, ambiente, rotina, presença familiar).
3. Se mantido, dose mínima eficaz, revalidar a cada 4 semanas.

Em Parkinson com psicose: NÃO usar risperidona ou olanzapina (antagonismo D2 piora motor). Quetiapina ou clozapina são as opções.',
 'Antipsicóticos AVOID em demência (Beers/FDA box). Em Parkinson, evitar risperidona/olanzapina.',
 ARRAY['beers', 'demencia', 'alzheimer', 'antipsicotico', 'parkinson', 'risperidona', 'quetiapina', 'olanzapina'],
 90, 'high', 'Beers Criteria 2023', 'clinical_guideline'),

('default', 'medications', 'doacs_renal',
 'DOACs e ajuste por ClCr (rivaroxabana, apixabana, dabigatrana)',
 'Os anticoagulantes orais diretos (DOACs) têm ajustes renais distintos:

• Rivaroxabana: ClCr 30-50 → reduzir 15mg/dia. ClCr 15-30 → 15mg/dia (cautela). ClCr <15 → contraindicado.
• Apixabana: dose padrão 5mg 12/12h. Reduzir para 2,5mg 12/12h se ≥2 dos critérios: idade ≥80, peso ≤60kg, creatinina ≥1,5. ClCr <25 → cautela.
• Dabigatrana: ClCr ≥50 → 150mg 12/12h. ClCr 30-50 OU idade ≥80 → 110mg 12/12h. ClCr <30 → CONTRAINDICADO (excretada 80% via rim).

Apixabana é a alternativa preferencial em ClCr <30. Em hepatopatia grave (Child C), evitar todos os DOACs — varfarina é a opção.

Reversores: idarucizumabe para dabigatrana; andexanet-alfa para anti-Xa (rivaroxabana, apixabana) — ainda limitado no Brasil.',
 'DOACs: rivaroxabana, apixabana, dabigatrana — ajustes por ClCr. Dabigatrana contraindicada se ClCr<30.',
 ARRAY['DOAC', 'rivaroxabana', 'apixabana', 'dabigatrana', 'renal', 'ClCr', 'kdigo'],
 90, 'high', 'FDA + KDIGO', 'clinical_guideline'),

('default', 'medications', 'aines_idoso',
 'AINEs em idoso — Beers, varfarina, DOACs',
 'AINEs (ibuprofeno, naproxeno, diclofenaco) têm múltiplos problemas em idoso:

• Beers 2023: AVOID uso crônico — risco GI, cardiovascular, renal, hipertensão.
• AINE + varfarina: contraindicado (sangramento GI + alteração imprevisível de INR).
• AINE + DOAC (rivaroxabana, apixabana, dabigatrana): contraindicado (sangramento GI sob anticoagulação).
• AINE + IECA/ARA + diurético = "triple whammy" → IRA aguda em ~7% dos casos.
• AINE + corticoide: aumenta 4× risco úlcera/sangramento GI.

Alternativas para dor em idoso anticoagulado: paracetamol (até 3g/dia, ajustar em hepatopatia), tópicos (diclofenaco gel, capsaicina), opioides fracos (tramadol — mas atenção a constipação, queda, hiponatremia).',
 'AINEs + anticoagulante = contraindicado. Triple whammy (AINE+IECA+diurético) → IRA.',
 ARRAY['AINE', 'ibuprofeno', 'naproxeno', 'varfarina', 'DOAC', 'sangramento', 'IRA'],
 85, 'high', 'Beers 2023 + FDA', 'clinical_guideline'),

('default', 'geriatrics', 'acb_score',
 'ACB (Anticholinergic Cognitive Burden) — score cumulativo',
 'O ACB score soma a carga anticolinérgica de TODOS os medicamentos do paciente. Pontuação por droga: 0 (nenhum), 1 (fraco), 2 (moderado), 3 (forte).

Score total ≥3 = risco aumentado de declínio cognitivo, delirium, queda, retenção urinária, constipação, xerostomia, visão turva.

Drogas comuns com ACB 3 (forte): amitriptilina, oxibutinina, hidroxizina, clorpromazina, olanzapina, difenidramina, escopolamina.
ACB 2 (moderado): quetiapina, ciclobenzaprina.
ACB 1 (fraco): ranitidina, prednisona, haloperidol em doses baixas, risperidona.

Conduta: para cada droga ACB ≥2, perguntar "tem alternativa não-anticolinérgica?". Em demência, alvo é ACB total <3.',
 'ACB ≥3 = risco cognitivo. Alvo em demência: <3. Olanzapina e amitriptilina pesam 3 cada.',
 ARRAY['ACB', 'anticholinergic', 'burden', 'cumulativo', 'delirium', 'demencia'],
 85, 'high', 'ACB Calculator (Aging Brain Care)', 'clinical_guideline'),

('default', 'geriatrics', 'fall_risk_meds',
 'Medicamentos e risco de queda em idoso',
 'Classes terapêuticas com risco de queda significativo (presentes no fall_risk_score do motor):

• Benzodiazepínicos (clonazepam, diazepam, alprazolam) — score 2 (alto). Sedação + sono fragmentado + ataxia.
• Hipnóticos não-BZD (zolpidem) — score 2. Risco mantido apesar de meia-vida menor.
• Antipsicóticos atípicos (risperidona, quetiapina, olanzapina) — score 2. Hipotensão postural + extrapiramidalismo + sedação.
• Antiparkinsonianos agonistas D2 (pramipexol, ropinirol) — score 1. Hipotensão postural + sono diurno súbito.
• BCCa di-hidropiridínico (anlodipino, nifedipino) — score 1. Hipotensão postural.
• Antidepressivos tricíclicos — score 1-2 dependendo da molécula.
• Diuréticos de alça em altas doses — score 1. Hipovolemia + hipotensão.
• Opioides — score 1-2. Sedação + tontura.

Soma ≥3 + idade ≥75 + osteoporose + episódio prévio de queda = paciente de altíssimo risco — considerar revisão completa de medicações.',
 'Benzodiazepínicos + antipsicóticos atípicos = score 2 cada. Combinação ≥3 + idoso = altíssimo risco.',
 ARRAY['fall risk', 'queda', 'benzodiazepinico', 'antipsicotico', 'idoso', 'score'],
 85, 'high', 'Beers 2023 + STEADI/CDC', 'clinical_guideline'),

('default', 'medications', 'child_pugh_basics',
 'Child-Pugh A/B/C e ajustes de dose',
 'Classificação Child-Pugh estima função hepática residual em cirrose. Baseada em 5 parâmetros: bilirrubina, albumina, INR, ascite, encefalopatia. Score 5-6 = A (compensada), 7-9 = B (moderada), 10-15 = C (descompensada).

Aliases reconhecidos pela ConnectaIACare:
• "cirrose compensada", "hepatopatia leve", "child a" → child_a
• "cirrose com ascite", "hepatopatia moderada", "child b" → child_b
• "cirrose descompensada", "encefalopatia hepática", "falência hepática", "child c" → child_c
• "hepatopatia" sem qualificador → hepatopatia_unspecified (tratado como child_a + warning de confirmar).

Para cada princípio ativo, aia_health_drug_hepatic_adjustments tem regra por severity_class. Ações: avoid, reduce_50pct, reduce_75pct, increase_interval, caution_monitor, no_adjustment.

Drogas que merecem atenção especial em hepatopatia: paracetamol (limitar 2g/dia em A, evitar em B/C), AINEs (evitar em B/C — IRA hepatorrenal), benzodiazepínicos (lorazepam é o mais seguro em hepatopatia), estatinas (sinvastatina/atorvastatina avoid em B/C), quetiapina/olanzapina (CYP3A4 — reduzir em A, avoid em C).',
 'Child A/B/C com aliases. Quetiapina/olanzapina: avoid em C. Lorazepam é o BZD mais seguro em hepatopatia.',
 ARRAY['child-pugh', 'hepatico', 'cirrose', 'hepatopatia', 'ajuste', 'lorazepam'],
 85, 'high', 'AASLD + ANVISA', 'clinical_guideline'),

('default', 'medications', 'qt_prolongadores',
 'Medicamentos prolongadores de QT — risco torsade',
 'Medicamentos com risco de prolongar QTc cobertos pelo motor:

• Amiodarona (alto risco, QT prolongation aditivo).
• Azitromicina (FDA box warning 2013).
• Haloperidol (alto, dose-dependente).
• Quetiapina (moderado).
• Risperidona (moderado).

Pares com aditividade documentada (severity major no motor):
• amiodarona + azitromicina
• azitromicina + haloperidol
• azitromicina + quetiapina

Conduta: ECG basal antes de iniciar combinação. Evitar se QTc basal >450ms (homem) / 470ms (mulher). Atenção a hipocalemia e hipomagnesemia (multiplicam risco). Em síndrome do QT longo congênito → contraindicar azitromicina (trocar por amoxicilina ou doxiciclina).',
 'QT prolongadores: amiodarona, azitromicina, haloperidol, quetiapina, risperidona. Combos = aditivo.',
 ARRAY['QT', 'torsade', 'amiodarona', 'azitromicina', 'haloperidol', 'arritmia'],
 85, 'high', 'FDA 2013 + AHA', 'clinical_guideline'),

('default', 'medications', 'time_separation_interactions',
 'Interações por absorção mitigáveis por horário',
 'Algumas interações medicamentosas são por COMPETIÇÃO de absorção e podem ser ELIMINADAS espaçando os horários. O motor armazena isso em time_separation_minutes na aia_health_drug_interactions.

Exemplos cobertos:
• Levotiroxina + carbonato de cálcio: espaçar 240min (4h). Cálcio quela levotiroxina no estômago.
• Levotiroxina + sulfato ferroso: 240min (4h).
• Levotiroxina + omeprazol/pantoprazol: 240min — IBPs reduzem absorção.
• Alendronato + cálcio/leite/multivitamínico: 60min.
• Alendronato + qualquer alimento: 30-60min em jejum, depois aguardar.
• Tetraciclinas/quinolonas + cálcio/ferro/zinco: 120-240min.

A Sofia, ao detectar uma dessas interações via check_medication_safety ou check_drug_interaction, deve sugerir o espaçamento como solução em vez de evitar a combinação — preserva a indicação clínica.',
 'Interações por absorção: espaçar horários resolve. Levotiroxina+cálcio = 4h. Alendronato+leite = 1h.',
 ARRAY['time_separation', 'absorcao', 'levotiroxina', 'alendronato', 'calcio', 'horario'],
 80, 'high', 'FDA + ANVISA', 'clinical_guideline'),

('default', 'medications', 'nti_drugs',
 'Drogas de Índice Terapêutico Estreito (NTI)',
 'Princípios ativos com janela terapêutica estreita — pequena variação de dose / nível plasmático leva a toxicidade ou perda de efeito. Marcados com narrow_therapeutic_index=TRUE em aia_health_drug_dose_limits.

Drogas NTI cobertas:
• Varfarina (INR alvo 2-3, sangramento se >4).
• Digoxina (toxicidade >2,0 ng/mL — náusea, arritmia, visão amarelada).
• Lítio (intoxicação >1,5 mEq/L — tremor, confusão, convulsão).
• Levotiroxina (TSH alvo estreito).
• Fenitoína (cinética não-linear — pequenos aumentos = grandes elevações séricas).
• Carbamazepina, ácido valpróico (anticonvulsivantes).
• Ciclosporina, tacrolimus (imunossupressores).
• Dabigatrana (DOAC — sem dosagem rotineira mas pequena janela).
• Teofilina.

Conduta com NTI: NÃO trocar marca/genérico sem reavaliação. Confirmar interações antes de adicionar/retirar drogas concomitantes. Monitorar nível sérico quando aplicável (varfarina/INR, digoxina, lítio, tacrolimus).',
 'NTI: varfarina, digoxina, lítio, levotiroxina, fenitoína. Pequena variação = toxicidade ou falha.',
 ARRAY['NTI', 'narrow therapeutic index', 'varfarina', 'digoxina', 'litio', 'fenitoina'],
 80, 'high', 'ANVISA + Stockleys', 'clinical_guideline'),

('default', 'geriatrics', 'polifarmacia',
 'Polifarmácia em idoso',
 'Definição: uso simultâneo de ≥5 medicamentos. Polifarmácia excessiva: ≥10. Quanto mais drogas:
• Risco de interação cresce exponencialmente (5 drogas = 10 pares possíveis; 10 drogas = 45 pares).
• ACB total tende a subir.
• Adesão cai.
• Cascata de prescrição: efeito adverso de uma droga é tratado com OUTRA droga.

Cascatas clássicas: AINE → HAS → anti-hipertensivo. BCCa → edema → diurético. IBP crônico → fratura/B12 baixa. Anticolinérgico → constipação → laxante.

Conduta: revisão de medicações ("deprescribing") quando ≥7 drogas OU ACB ≥3 OU queda recente. Ferramentas: STOPP/START, Beers 2023, Fleetwood. Sofia pode listar todas as drogas ativas via list_medication_schedules e suas regras via query_drug_rules para o médico decidir.',
 'Polifarmácia ≥5 drogas. Cada droga adicionada = revisão de cascata e ACB.',
 ARRAY['polifarmacia', 'deprescribing', 'STOPP', 'cascata', 'idoso'],
 85, 'high', 'Beers 2023 + STOPP/START', 'clinical_guideline')
;

COMMIT;
