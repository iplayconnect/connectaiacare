-- ConnectaIACare — Atualização da memória da Sofia (abr/2026).
--
-- Sofia é o cérebro da plataforma e precisa conhecer TODAS as features
-- recém-implementadas para responder corretamente a usuários e
-- profissionais. Adiciona chunks em aia_health_knowledge_chunks sobre:
--
--   - Sistema de revisão clínica (auto_pending → verified)
--   - RENAME 2024 como base oficial de cobertura
--   - Cascatas batch 2 (anticolinérgico + opioide + IMAO)
--   - Antibióticos + antiácidos (time_separation)
--   - Biometria de voz (Resemblyzer 256-dim, identify_1toN)
--   - Proactive Caller + Risk Score
--   - Cascade detection (dim 13)
--
-- Embeddings ficam NULL — query_clinical_guidelines usa ILIKE até o
-- pgvector retrieval ser ativado. Quando ativar, backfill em lote.

BEGIN;

-- ════════════════════════════════════════════════════════════════════
-- 1. Sistema de revisão clínica (auto_pending)
-- ════════════════════════════════════════════════════════════════════

INSERT INTO aia_health_knowledge_chunks
    (tenant_id, domain, subdomain, title, content, summary, keywords,
     priority, confidence, source, source_type)
VALUES
('default', 'company', 'clinical_review_system',
 'Revisão clínica de regras auto_pending — fluxo de curadoria',
 'A partir de abr/2026 o motor de cruzamentos opera com flags de revisão
em todas as tabelas clínicas (dose_limits, condition_contraindications,
anticholinergic_burden, fall_risk):

• auto_generated BOOLEAN — TRUE quando a regra foi populada por script
  a partir de fonte estruturada (RENAME 2024, Beers, STOPP/START).
• review_status TEXT — verified | auto_pending | auto_approved.

Quando uma regra está em auto_pending, a Sofia injeta um disclaimer
REFORÇADO no output das tools clínicas (⚠️ "esta informação foi gerada
automaticamente a partir de fontes oficiais e ainda está em revisão
clínica — confirme com seu médico ou farmacêutico").

Curador (super_admin ou admin_tenant) revisa em /admin/regras-clinicas/
revisao com tabs por dimensão. Aprovar move para verified e remove
disclaimer reforçado. Rejeitar desativa (active=FALSE) com motivo
obrigatório. Médicos e enfermeiros podem visualizar a fila mas não
aprovam (RBAC).

Endpoints:
• GET /api/clinical-rules/review/pending — fila unificada por tabela.
• POST /api/clinical-rules/review/<slug>/<row_id>/approve — verified +
  reviewed_by + audit_log.
• POST /api/clinical-rules/review/<slug>/<row_id>/reject — active=FALSE
  com motivo + audit_log.

Toda aprovação/rejeição grava em aia_health_audit_chain (LGPD).',
 'Regras com review_status=auto_pending recebem disclaimer reforçado; curador aprova em /admin/regras-clinicas/revisao.',
 ARRAY['revisao clinica', 'auto_pending', 'verified', 'curadoria', 'review_status', 'auto_generated', 'disclaimer'],
 90, 'high', 'internal', 'internal_curated'),

-- ════════════════════════════════════════════════════════════════════
-- 2. RENAME 2024 como base oficial de cobertura
-- ════════════════════════════════════════════════════════════════════

('default', 'company', 'rename_2024_coverage',
 'RENAME 2024 — base oficial do motor (Ministério da Saúde / CONITEC)',
 'A RENAME 2024 (Relação Nacional de Medicamentos Essenciais — Ministério
da Saúde via CONITEC) é a base oficial de cobertura do motor da
ConnectaIACare. Todos os princípios ativos da RENAME que são relevantes
para nosso público alvo (idosos, pacientes crônicos) estão sendo
codificados nas 12 dimensões + cascata.

Tabelas:
• aia_health_rename_drugs — catálogo canônico (princípio_ativo,
  rename_componente, rename_edicao, motor_coverage:
  not_started|in_progress|covered).
• aia_health_rename_coverage_summary VIEW — breakdown:
  - covered_verified (curadoria humana validou)
  - covered_auto_pending (populado automático, aguarda revisão)

Cobertura atual (abr/2026):
• 100% dos fármacos do Componente Básico relevantes para geriatria.
• 35+ fármacos validados pelo farmacêutico Henrique Bordin (cardio,
  endócrino, SNC, pneumo, opioides, antialérgicos, ósseo).
• 10 antibióticos comunitários + 4 antiácidos não-IBP com cobertura
  Beers + interações por absorção (time_separation).

Próximas etapas: ampliar Componente Estratégico + Especializado conforme
demanda dos casos reais.

Quando Sofia menciona uma regra clínica, ela pode citar "conforme RENAME
2024 / Beers 2023 / KDIGO" para dar âncora oficial à informação.',
 'RENAME 2024 (CONITEC) é a base oficial de cobertura do motor; 35+ fármacos validados por farmacêutico (abr/2026).',
 ARRAY['rename', 'conitec', 'ministerio saude', 'cobertura', 'motor', 'henrique bordin'],
 90, 'high', 'rename_2024', 'clinical_guideline'),

-- ════════════════════════════════════════════════════════════════════
-- 3. Cascatas (dimensão 13) — anticolinérgico + opioide + IMAO
-- ════════════════════════════════════════════════════════════════════

('default', 'company', 'cascade_detection',
 'Cascade detection — dimensão 13 do motor',
 'Cascatas iatrogênicas são a 13ª dimensão do motor (além das 12
originais). Detectam quando médico prescreve fármaco B para tratar
efeito adverso causado pelo fármaco A — ciclo que multiplica polifarmácia
em vez de resolver causa.

Tabela: aia_health_drug_cascades. Cada linha define drug_a (causador) +
drug_c (medicamento de resgate prescrito reativamente) com
match_pattern (a_only, a_and_c, a_or_c).

Cascatas codificadas (abr/2026):
1. ACB cumulativo → demência → IChE (anticolinérgico → memantina/donepezil).
2. Opioide → constipação → laxante crônico (lactulose, bisacodil, sene,
   macrogol, óleo mineral, picossulfato). Profilaxia: laxante + hidratação
   desde início. Refratária: antagonista μ periférico (metilnaltrexona,
   naloxegol).
3. IMAO + alimentos ricos em tirosina (queijo curado, embutido, vinho
   fermentado, fava) → crise hipertensiva. Médico desconhecendo a
   interação prescreve anti-hipertensivo de resgate sem orientar dieta.
4. AINE → HAS → anti-hipertensivo.
5. BCCa di-hidropiridínico → edema → diurético.
6. Inibidor colinesterase (donepezil) → bradicardia → marca-passo.
7. Estatina → mialgia → AINE/analgésico.
8. ISRS → SIADH/hiponatremia → restrição hídrica/cloreto sódio.

Quando dispatcher detecta cascata, gera alerta em /alertas/clinicos com
recomendação (ex: "considerar suspensão do drug_a ao invés de adicionar
drug_c").

Sofia pode invocar query_drug_rules para verificar se um caso específico
matches alguma cascata.',
 'Dimensão 13: detecta padrões iatrogênicos onde médico prescreve B reativamente para tratar efeito de A.',
 ARRAY['cascata', 'cascade', 'iatrogenico', 'polifarmacia', 'anticolinergico', 'opioide', 'imao', 'aine'],
 85, 'high', 'internal', 'internal_curated'),

-- ════════════════════════════════════════════════════════════════════
-- 4. Antibióticos comunitários + antiácidos (time_separation)
-- ════════════════════════════════════════════════════════════════════

('default', 'medications', 'antibiotics_community',
 'Antibióticos comunitários — Beers + interações chave',
 'Antibióticos de uso comunitário codificados (abr/2026):

Beers AVOID/CAUTION em idoso:
• Ciprofloxacino, levofloxacino, moxifloxacino — risco aumentado de
  ruptura de tendão (Aquiles) + delirium + neuropatia + alargamento QT.
  Beers CAUTION ≥65a + dose reduzida em ClCr < 50.
• Nitrofurantoína — evitar se ClCr < 30 (acúmulo + neuropatia +
  toxicidade pulmonar). Beers AVOID em ClCr<30.
• Sulfametoxazol+Trimetoprim — hiperpotassemia em IRC + interação com
  IECA/ARA2/varfarina; AVOID em ClCr<30.
• Claritromicina — múltiplas interações CYP3A4 (estatinas, varfarina,
  diltiazem). Major com sinvastatina, atorvastatina (rabdomiólise).

Outros antibióticos:
• Metronidazol — efeito dissulfiram-like com álcool (24h após dose).
  Inibe varfarina (potencializa anticoagulação).
• Azitromicina, doxiciclina, amoxicilina, amoxicilina+clavulanato,
  cefuroxima.

Sofia deve sempre lembrar: ajuste renal + reação cruzada penicilina ↔
β-lactâmicos.',
 'Quinolonas + nitrofurantoína + bactrim em idoso exigem ClCr; claritromicina interage com estatinas.',
 ARRAY['antibiotico', 'quinolona', 'ciprofloxacino', 'nitrofurantoina', 'metronidazol', 'claritromicina', 'beers'],
 80, 'high', 'beers_2023', 'clinical_guideline'),

('default', 'medications', 'antacids_time_separation',
 'Antiácidos não-IBP — interações por absorção (espaçar)',
 'Antiácidos não-IBP codificados (carbonato de cálcio, hidróxido de
alumínio, hidróxido de magnésio, bicarbonato sódio):

Interações por absorção (mitigáveis com time_separation_minutes):
• Quinolonas (cipro, levo, moxi) — quelação com cátions divalentes
  (Ca++, Mg++, Al+++). Espaçar 4h (240min). a_first.
• Tetraciclinas (doxiciclina, tetraciclina) — quelação. Espaçar 4h. a_first.
• Levotiroxina — inibe absorção. Espaçar 4h, jejum estrito 30min.
  separation_strategy=a_first. food_warning crítico.
• Sulfato ferroso — inibição mútua. Espaçar 2h (120min).
• Bifosfonatos (alendronato, risedronato) — exigem jejum estrito 30min
  + posição ereta. Espaçar 4h de antiácido.

Quando o motor detecta uma dessas combinações, gera alerta com
severity=moderate + orientação de horário ("tomar antibiótico 2h antes
ou 4h depois do antiácido"). É educação, não bloqueio.',
 'Antiácidos com cátions divalentes quelam quinolonas, tetraciclinas, levotiroxina, ferro — espaçar 2-4h.',
 ARRAY['antiacido', 'time_separation', 'levotiroxina', 'quinolona', 'ferro', 'bifosfonato'],
 80, 'high', 'beers_2023', 'clinical_guideline'),

-- ════════════════════════════════════════════════════════════════════
-- 5. Biometria de voz (Resemblyzer)
-- ════════════════════════════════════════════════════════════════════

('default', 'company', 'voice_biometrics',
 'Biometria de voz — identificação de cuidador/paciente por embedding',
 'Resemblyzer 256-dim + pgvector. Tabela aia_health_voice_embeddings.

Fluxo de identificação 1:N (WhatsApp):
1. Áudio chega via Evolution API → bytes ogg/opus.
2. audio_preprocessing.preprocess() — VAD + quality gate (SNR + duração).
3. VoiceBiometricsService._extract() → embedding 256-dim L2-normalized.
4. Cache 5min de embeddings do tenant em memória.
5. identify_1toN() — cosine similarity contra todos cuidadores do
   tenant. Threshold IDENTIFY_1TON_THRESHOLD=0.65, ambiguity margin
   IDENTIFY_AMBIGUITY_MARGIN=0.05 (top1 − top2).
6. Se match: aia_health_reports.caregiver_id + caregiver_voice_method=
   "1:N" + caregiver_voice_candidates JSONB com top scores.

Fluxo de enrollment (ativo):
• POST /api/voice/enroll — audio_base64 + caregiver_id + sample_label.
  Quality gate MIN_ENROLL_QUALITY=0.55. Recomendado 3+ amostras.
• GET /api/voice/enrollment/<caregiver_id> — lista samples.
• DELETE /api/voice/enrollment/<caregiver_id> — revoga.

LGPD: aia_health_voice_consent_log registra todo enroll/identify.
Embedding NÃO é áudio (não-reversível) mas é dado biométrico sensível
(consentimento explícito obrigatório).

Frontend admin (em construção): /admin/biometria-voz.',
 'Resemblyzer 256-dim identifica cuidador em áudios WhatsApp; threshold 0.65 + margem 0.05 desambiguação.',
 ARRAY['biometria voz', 'resemblyzer', 'embedding', 'identify_1ton', 'cuidador', 'voice'],
 80, 'high', 'internal', 'internal_curated'),

-- ════════════════════════════════════════════════════════════════════
-- 6. Proactive Caller + Risk Score
-- ════════════════════════════════════════════════════════════════════

('default', 'company', 'proactive_caller',
 'Proactive Caller — Sofia liga preventivamente para risco alto',
 'Worker dedicado roda a cada 5min (proactive_caller_started tick=300s)
e seleciona pacientes com score de risco elevado para chamada outbound
preventiva via voice-call-service.

Score de risco (aia_health_patient_risk_score):
• score numérico 0-100 + risk_level (low|moderate|high|critical).
• Sinais agregados: alertas críticos abertos, falhas em medicação,
  desvios de baseline (z-score robusto), eventos recentes.
• Recalculado em background.

Critérios de seleção:
• risk_level in (high, critical).
• Sem chamada nas últimas N horas.
• Sem skip flag (paciente recusou chamada recente).
• Janela de horário aceitável (não madrugada).

Ao detectar candidato, Sofia inicia chamada via voice-call-service
(PJSIP + Grok Voice Realtime) com cenário "proactive_check_in" —
pergunta sobre sintomas, adesão, sinais de alarme. Resultado vira
care_event + atualiza trust_score.

Endpoint admin: GET /api/proactive-caller/stats — taxa de sucesso,
skips, conversões em care_event.',
 'Worker tick=5min: seleciona pacientes high/critical e Sofia liga via voice-call-service.',
 ARRAY['proactive', 'caller', 'risk score', 'risco', 'outbound', 'preventivo'],
 80, 'high', 'internal', 'internal_curated'),

-- ════════════════════════════════════════════════════════════════════
-- 7. Multi-canal Sofia
-- ════════════════════════════════════════════════════════════════════

('default', 'company', 'sofia_channels',
 'Canais Sofia — WhatsApp, chat, voice browser, voice call, teleconsulta',
 'Sofia opera em 5 canais simultâneos com mesma identidade e mesma
memória cross-canal:

1. WhatsApp (Evolution API) — texto + áudio + imagem. Pipeline
   _handle_audio inclui Deepgram STT + biometria de voz.
2. Chat web (/sofia) — texto via interface CRM.
3. Voice browser (/sofia voz) — Grok Voice Realtime via WebSocket
   navegador (microfone + speaker).
4. Voice call (PJSIP + Grok) — voice-call-service container, SIP trunk
   Flux em PCMU 8kHz. Inbound (paciente liga) + outbound (proactive
   caller).
5. Teleconsulta (LiveKit) — médico + paciente + Sofia como agente
   passivo (transcrição + alertas).

Active context cross-channel: aia_health_sofia_active_context guarda o
"que estamos conversando agora" por usuário, então se paciente começa
no WhatsApp e liga em seguida, Sofia continua o assunto.

Memória per-user (LGPD opt-in): aia_health_sofia_user_memory com
summary 500-800 chars + key_facts JSONB, re-summarizado a cada N
mensagens via Gemini Flash.',
 'Sofia em 5 canais com active_context cross-channel; memória por usuário com opt-in LGPD.',
 ARRAY['canais', 'multi-canal', 'whatsapp', 'voice', 'teleconsulta', 'cross-channel', 'memoria'],
 85, 'high', 'internal', 'internal_curated'),

-- ════════════════════════════════════════════════════════════════════
-- 8. Time técnico (curadoria clínica)
-- ════════════════════════════════════════════════════════════════════

('default', 'company', 'team_clinical_curation',
 'Time técnico — curadoria clínica',
 'O time responsável pela curadoria clínica do motor (abr/2026):

• Alexandre Veras — CEO/founder ConnectaIACare. WhatsApp +55 51 99616-1700.
• Henrique Bordin — biomédico + farmacêutico, referência clínica/
  farmacológica. Validou os primeiros 35+ fármacos da RENAME 2024 e
  desenhou cascatas opioide e IMAO.

Curadoria via plataforma: novos farmacêuticos/médicos entram com role
admin_tenant ou medico e revisam fila /admin/regras-clinicas/revisao.
Aprovação grava reviewed_by + audit_log — rastreabilidade total de quem
liberou cada regra.

Quando Sofia precisa atribuir autoria a uma regra ("foi validado por
quem?"), pode mencionar Henrique Bordin sem expor dados pessoais
sensíveis. Demais curadores que entrarem aparecem aqui após aprovação
de cadastro.',
 'Henrique Bordin (farmacêutico) é referência clínica; novos curadores entram via plataforma.',
 ARRAY['equipe', 'time', 'curadoria', 'henrique', 'bordin', 'farmaceutico', 'alexandre veras'],
 60, 'high', 'internal', 'internal_curated');

COMMIT;
