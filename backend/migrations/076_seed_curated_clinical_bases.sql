-- =============================================================================
-- 076 — Seed inicial das bases curadas (CID-10 geriátrico + meds + expectations)
-- =============================================================================
--
-- Baseline pra revisão clínica do Henrique → Coordenadora PUC Farmácia.
-- Tudo entra como review_status='draft' — Henrique abre painel admin
-- e marca 'approved' (ou edita) item por item.
--
-- ~150 CIDs cobrindo: cardiovascular, respiratório, endócrino, neuro,
-- psiquiátrico, osteomuscular, infeccioso, oncológico, urinário,
-- digestivo, sensorial, paliativo.
--
-- ~80 medicamentos comuns em geriatria, com classes terapêuticas
-- e match patterns pra detecção em texto livre.
--
-- 8 condições baseline pra cross-validation (HAS, DM, IC, FA,
-- Hipotireoidismo, DPOC, Asma, DAC).
--
-- Idempotente: ON CONFLICT DO NOTHING preserva edições subsequentes.
-- =============================================================================


-- 1. CID-10 geriátrico (~150 entries) ─────────────────────────────────────────

INSERT INTO aia_health_cid10_curated (code, description_pt, description_layman, category) VALUES
-- CARDIOVASCULAR
('I10',     'Hipertensão essencial (primária)',                'Pressão alta',                                                'cardiovascular'),
('I11',     'Doença cardíaca hipertensiva',                    'Doença do coração causada por pressão alta',                  'cardiovascular'),
('I12',     'Doença renal hipertensiva',                       'Doença renal causada por pressão alta',                       'cardiovascular'),
('I13',     'Doença cardíaca e renal hipertensiva',            'Doença do coração e rins causada por pressão alta',           'cardiovascular'),
('I20',     'Angina pectoris',                                 'Dor no peito por falta de oxigênio no coração',               'cardiovascular'),
('I21',     'Infarto agudo do miocárdio (IAM)',                'Infarto do coração',                                          'cardiovascular'),
('I25',     'Doença isquêmica crônica do coração (DAC)',       'Doença das artérias do coração',                              'cardiovascular'),
('I48',     'Fibrilação e flutter atrial (FA)',                'Arritmia do coração',                                         'cardiovascular'),
('I49',     'Outras arritmias cardíacas',                      'Outras alterações do ritmo do coração',                       'cardiovascular'),
('I50.0',   'Insuficiência cardíaca congestiva (ICC)',         'Coração não bombeia bem',                                     'cardiovascular'),
('I50.9',   'Insuficiência cardíaca não especificada (IC)',    'Insuficiência cardíaca',                                      'cardiovascular'),
('I63',     'Infarto cerebral (AVC isquêmico)',                'Derrame por entupimento de artéria',                          'cardiovascular'),
('I64',     'Acidente vascular cerebral (AVC) não especificado', 'Derrame',                                                   'cardiovascular'),
('I65',     'Oclusão arterial pré-cerebral',                   'Obstrução de artéria do pescoço',                             'cardiovascular'),
('I69',     'Sequelas de doença cerebrovascular',              'Sequelas de derrame',                                         'cardiovascular'),
('I70',     'Aterosclerose',                                   'Endurecimento das artérias',                                  'cardiovascular'),
('I73.9',   'Doença vascular periférica',                      'Má circulação',                                               'cardiovascular'),
('I80',     'Tromboflebite e flebite',                         'Inflamação de veia com coágulo',                              'cardiovascular'),
('I82',     'Trombose venosa profunda (TVP)',                  'Coágulo em veia da perna',                                    'cardiovascular'),
('I26',     'Tromboembolismo pulmonar (TEP)',                  'Coágulo no pulmão',                                           'cardiovascular'),
-- RESPIRATÓRIO
('J18',     'Pneumonia bacteriana',                            'Infecção no pulmão',                                          'respiratorio'),
('J15.9',   'Broncopneumonia',                                 'Infecção pulmonar nos brônquios',                             'respiratorio'),
('J20',     'Bronquite aguda',                                 'Inflamação dos brônquios',                                    'respiratorio'),
('J44.0',   'DPOC com infecção respiratória aguda',            'Doença pulmonar obstrutiva crônica com infecção',             'respiratorio'),
('J44.9',   'Doença pulmonar obstrutiva crônica (DPOC)',       'DPOC',                                                        'respiratorio'),
('J45',     'Asma',                                            'Asma',                                                        'respiratorio'),
('J47',     'Bronquiectasia',                                  'Dilatação permanente dos brônquios',                          'respiratorio'),
('J69.0',   'Pneumonia aspirativa',                            'Pneumonia por aspiração de alimento/secreção',                'respiratorio'),
('J81',     'Edema pulmonar',                                  'Acúmulo de líquido no pulmão',                                'respiratorio'),
('J96.0',   'Insuficiência respiratória aguda',                'Falta de ar grave',                                           'respiratorio'),
('J96.1',   'Insuficiência respiratória crônica',              'Falta de ar crônica',                                         'respiratorio'),
-- ENDÓCRINO/METABÓLICO
('E10',     'Diabetes mellitus tipo 1',                        'Diabetes tipo 1',                                             'endocrino_metabolico'),
('E11.9',   'Diabetes mellitus tipo 2 sem complicação',        'Diabetes tipo 2',                                             'endocrino_metabolico'),
('E11.2',   'Diabetes mellitus tipo 2 com nefropatia',         'Diabetes com problema nos rins',                              'endocrino_metabolico'),
('E11.3',   'Diabetes mellitus tipo 2 com retinopatia',        'Diabetes com problema nos olhos',                              'endocrino_metabolico'),
('E11.4',   'Diabetes mellitus tipo 2 com neuropatia',         'Diabetes com problema nos nervos',                            'endocrino_metabolico'),
('E11.5',   'Diabetes mellitus tipo 2 com complicações circulatórias periféricas', 'Diabetes com má circulação',          'endocrino_metabolico'),
('E03',     'Hipotireoidismo',                                 'Tireóide preguiçosa',                                          'endocrino_metabolico'),
('E05',     'Hipertireoidismo (tireotoxicose)',                'Tireóide acelerada',                                          'endocrino_metabolico'),
('E66',     'Obesidade',                                       'Obesidade',                                                   'endocrino_metabolico'),
('E78',     'Distúrbios do metabolismo lipídico (dislipidemia)', 'Colesterol alto',                                            'endocrino_metabolico'),
('E83.5',   'Distúrbios do metabolismo do cálcio',             'Alteração de cálcio no sangue',                               'endocrino_metabolico'),
('E86',     'Depleção de volume (desidratação)',               'Desidratação',                                                'endocrino_metabolico'),
('E87.6',   'Hipocalemia',                                     'Potássio baixo',                                              'endocrino_metabolico'),
-- NEUROLÓGICO
('G20',     'Doença de Parkinson',                             'Parkinson',                                                   'neurologico'),
('G30',     'Doença de Alzheimer',                             'Alzheimer',                                                   'neurologico'),
('G31.0',   'Atrofia cerebral circunscrita (Pick)',            'Demência frontotemporal',                                     'neurologico'),
('F03',     'Demência não especificada',                       'Demência',                                                    'neurologico'),
('F00',     'Demência na doença de Alzheimer',                 'Demência por Alzheimer',                                      'neurologico'),
('F01',     'Demência vascular',                               'Demência por má circulação cerebral',                          'neurologico'),
('G40',     'Epilepsia',                                       'Epilepsia',                                                   'neurologico'),
('G45',     'Acidente isquêmico transitório (AIT)',            'Mini-derrame que se resolveu sozinho',                        'neurologico'),
('G62',     'Polineuropatia',                                  'Doença dos nervos periféricos',                               'neurologico'),
('G81',     'Hemiplegia',                                      'Paralisia de metade do corpo',                                'neurologico'),
('G82',     'Paraplegia/tetraplegia',                          'Paralisia das pernas ou de todo o corpo',                     'neurologico'),
('G93.4',   'Encefalopatia',                                   'Disfunção cerebral',                                          'neurologico'),
('R41.0',   'Desorientação',                                   'Confusão mental',                                             'neurologico'),
('R40.0',   'Sonolência',                                      'Sonolência excessiva',                                        'neurologico'),
('F05',     'Delirium não induzido por substâncias',           'Confusão aguda (delirium)',                                   'neurologico'),
-- PSIQUIÁTRICO
('F32',     'Episódio depressivo',                             'Depressão',                                                   'psiquiatrico'),
('F33',     'Transtorno depressivo recorrente',                'Depressão recorrente',                                        'psiquiatrico'),
('F41.1',   'Transtorno de ansiedade generalizada',            'Ansiedade generalizada',                                      'psiquiatrico'),
('F41.0',   'Transtorno de pânico',                            'Síndrome do pânico',                                          'psiquiatrico'),
('F51.0',   'Insônia não orgânica',                            'Insônia',                                                     'psiquiatrico'),
('F10',     'Transtornos por uso de álcool',                   'Alcoolismo',                                                  'psiquiatrico'),
-- OSTEOMUSCULAR
('M81',     'Osteoporose sem fratura patológica',              'Osteoporose',                                                 'osteomuscular'),
('M80',     'Osteoporose com fratura patológica',              'Osteoporose com fratura',                                     'osteomuscular'),
('M15',     'Osteoartrose poliarticular',                      'Artrose em várias articulações',                              'osteomuscular'),
('M16',     'Coxartrose (artrose do quadril)',                 'Artrose no quadril',                                          'osteomuscular'),
('M17',     'Gonartrose (artrose do joelho)',                  'Artrose no joelho',                                           'osteomuscular'),
('M19',     'Outras artroses',                                 'Outras artroses',                                             'osteomuscular'),
('M54',     'Dorsalgia',                                       'Dor nas costas',                                              'osteomuscular'),
('M62.5',   'Atrofia muscular',                                'Perda de massa muscular',                                     'osteomuscular'),
('M79.7',   'Fibromialgia',                                    'Fibromialgia',                                                'osteomuscular'),
('S72',     'Fratura do fêmur',                                'Fratura do fêmur (ex.: pós-queda)',                           'osteomuscular'),
-- INFECCIOSO
('A41',     'Septicemia (sepse)',                              'Infecção generalizada (sepse)',                               'infeccioso'),
('A46',     'Erisipela',                                       'Erisipela (infecção de pele superficial)',                    'infeccioso'),
('B02',     'Herpes-zóster',                                   'Cobreiro',                                                    'infeccioso'),
('A15',     'Tuberculose pulmonar com confirmação',            'Tuberculose pulmonar',                                        'infeccioso'),
('U07.1',   'COVID-19, vírus identificado',                    'COVID-19',                                                    'infeccioso'),
('B34.2',   'Coronavírus de localização não especificada',     'Coronavírus não especificado',                                'infeccioso'),
('L03',     'Celulite',                                        'Celulite (infecção de tecido subcutâneo)',                    'infeccioso'),
('N10',     'Pielonefrite aguda',                              'Infecção dos rins',                                           'infeccioso'),
('N30',     'Cistite',                                         'Cistite (infecção da bexiga)',                                'infeccioso'),
('N39.0',   'Infecção do trato urinário (ITU)',                'Infecção urinária',                                           'infeccioso'),
('A09',     'Diarreia e gastroenterite presumivelmente infecciosas', 'Diarreia infecciosa',                                  'infeccioso'),
('B95',     'Estafilococos como causa de doenças',             'Infecção por estafilococos',                                  'infeccioso'),
('B96',     'Outras bactérias como causa de doenças',          'Outras infecções bacterianas',                                'infeccioso'),
-- ONCOLÓGICO (apenas categorias amplas — diagnósticos específicos vêm no exame)
('C50',     'Neoplasia maligna da mama',                       'Câncer de mama',                                              'oncologico'),
('C61',     'Neoplasia maligna da próstata',                   'Câncer de próstata',                                          'oncologico'),
('C18',     'Neoplasia maligna do cólon',                      'Câncer de cólon (intestino)',                                 'oncologico'),
('C25',     'Neoplasia maligna do pâncreas',                   'Câncer de pâncreas',                                          'oncologico'),
('C34',     'Neoplasia maligna do brônquio e pulmão',          'Câncer de pulmão',                                            'oncologico'),
('C16',     'Neoplasia maligna do estômago',                   'Câncer de estômago',                                          'oncologico'),
('C44',     'Outras neoplasias malignas da pele',              'Câncer de pele',                                              'oncologico'),
('C90',     'Mieloma múltiplo',                                'Mieloma múltiplo',                                            'oncologico'),
('C92',     'Leucemia mieloide',                               'Leucemia mieloide',                                           'oncologico'),
-- URINÁRIO
('N18',     'Doença renal crônica (DRC/IRC)',                  'Insuficiência renal crônica',                                 'urinario'),
('N17',     'Insuficiência renal aguda',                       'Insuficiência renal aguda',                                   'urinario'),
('N40',     'Hiperplasia prostática benigna (HPB)',            'Próstata aumentada (benigna)',                                'urinario'),
('R32',     'Incontinência urinária não especificada',         'Perda de urina',                                              'urinario'),
('N31',     'Disfunção neuromuscular da bexiga',               'Bexiga neurogênica',                                          'urinario'),
-- DIGESTIVO
('K21.0',   'Doença de refluxo gastroesofágico (DRGE)',        'Refluxo (azia crônica)',                                      'digestivo'),
('K25',     'Úlcera gástrica',                                 'Úlcera no estômago',                                          'digestivo'),
('K58',     'Síndrome do intestino irritável',                 'Intestino irritável',                                         'digestivo'),
('K59.0',   'Constipação',                                     'Prisão de ventre',                                            'digestivo'),
('K70',     'Doença alcoólica do fígado',                      'Doença do fígado por álcool',                                 'digestivo'),
('K74',     'Cirrose hepática',                                'Cirrose',                                                     'digestivo'),
('K92.2',   'Hemorragia digestiva alta (HDA)',                 'Sangramento digestivo alto',                                  'digestivo'),
-- SENSORIAL
('H25',     'Catarata senil',                                  'Catarata',                                                    'sensorial'),
('H40',     'Glaucoma',                                        'Glaucoma',                                                    'sensorial'),
('H35.3',   'Degeneração macular relacionada à idade (DMRI)',  'Degeneração macular',                                         'sensorial'),
('H90',     'Perda de audição condutiva e neurossensorial',    'Perda auditiva',                                              'sensorial'),
('H91.0',   'Presbiacusia',                                    'Perda auditiva relacionada à idade',                           'sensorial'),
-- CUIDADOS PALIATIVOS / OUTROS
('R26',     'Anormalidades da marcha',                         'Dificuldade pra andar',                                       'cuidados_paliativos'),
('R29.6',   'Tendência a quedas',                              'Risco de queda',                                              'cuidados_paliativos'),
('R54',     'Senilidade',                                      'Senilidade',                                                  'cuidados_paliativos'),
('Z51.5',   'Cuidado paliativo',                               'Cuidado paliativo',                                           'cuidados_paliativos'),
('Z74',     'Dependência de cuidador',                         'Dependência de cuidador',                                     'cuidados_paliativos'),
('R64',     'Caquexia',                                        'Perda de peso e massa muscular grave',                        'cuidados_paliativos'),
('R63.4',   'Perda de peso anormal',                           'Perda de peso involuntária',                                  'cuidados_paliativos'),
('L89',     'Úlcera por pressão',                              'Úlcera de pressão (escara)',                                  'cuidados_paliativos'),
('L97',     'Úlcera dos membros inferiores não classificada',  'Úlcera nas pernas',                                           'cuidados_paliativos'),
-- OUTRO (genéricos úteis)
('R51',     'Cefaleia',                                        'Dor de cabeça',                                               'outro'),
('R10',     'Dor abdominal e pélvica',                         'Dor na barriga',                                              'outro'),
('R06.0',   'Dispneia',                                        'Falta de ar',                                                 'outro'),
('R07',     'Dor de garganta e dor torácica',                  'Dor no peito ou garganta',                                    'outro'),
('R11',     'Náusea e vômito',                                 'Enjoo e vômito',                                              'outro'),
('R50',     'Febre não especificada',                          'Febre',                                                       'outro'),
('R55',     'Síncope e colapso',                               'Desmaio',                                                     'outro'),
('Z71.1',   'Pessoa com queixa que se prova não justificada',  'Acompanhamento de queixa',                                    'outro'),
('Z76',     'Pessoa em contato com serviços de saúde',         'Consulta de rotina',                                          'outro')
ON CONFLICT (code) DO NOTHING;


-- 2. Medicamento → classe terapêutica (~80 entries) ───────────────────────────

INSERT INTO aia_health_medication_class_dictionary
    (active_ingredient, brand_names, match_patterns, therapeutic_classes, main_indications) VALUES
-- Anti-hipertensivos (IECA)
('Captopril',     ARRAY['Capoten'],         ARRAY['captopril'],         ARRAY['anti_hipertensivo','IECA'],   ARRAY['HAS','IC']),
('Enalapril',     ARRAY['Renitec'],         ARRAY['enalapril'],         ARRAY['anti_hipertensivo','IECA'],   ARRAY['HAS','IC']),
('Lisinopril',    ARRAY['Zestril'],         ARRAY['lisinopril'],        ARRAY['anti_hipertensivo','IECA'],   ARRAY['HAS','IC']),
('Ramipril',      ARRAY['Triatec'],         ARRAY['ramipril'],          ARRAY['anti_hipertensivo','IECA'],   ARRAY['HAS','IC']),
-- Anti-hipertensivos (BRA)
('Losartana',     ARRAY['Cozaar','Aradois'],ARRAY['losartana','losartan'], ARRAY['anti_hipertensivo','BRA'], ARRAY['HAS','IC','DM_nefropatia']),
('Valsartana',    ARRAY['Diovan'],          ARRAY['valsartana','valsartan'], ARRAY['anti_hipertensivo','BRA'], ARRAY['HAS','IC']),
('Olmesartana',   ARRAY['Benicar'],         ARRAY['olmesartana','olmesartan'], ARRAY['anti_hipertensivo','BRA'], ARRAY['HAS']),
-- Anti-hipertensivos (Diuréticos)
('Hidroclorotiazida', ARRAY['HCTZ'],        ARRAY['hidroclorotiazida','hctz'], ARRAY['anti_hipertensivo','diuretico_tiazidico'], ARRAY['HAS']),
('Furosemida',    ARRAY['Lasix'],           ARRAY['furosemida','lasix'], ARRAY['diuretico_alca'], ARRAY['IC','edema']),
('Espironolactona', ARRAY['Aldactone'],     ARRAY['espironolactona'],   ARRAY['diuretico_poupador_potassio','antagonista_aldosterona'], ARRAY['IC','HAS']),
('Indapamida',    ARRAY['Natrilix'],        ARRAY['indapamida'],        ARRAY['anti_hipertensivo','diuretico_tiazidico'], ARRAY['HAS']),
-- Anti-hipertensivos (BCC)
('Anlodipino',    ARRAY['Norvasc'],         ARRAY['anlodipino','amlodipino'], ARRAY['anti_hipertensivo','BCC'], ARRAY['HAS','angina']),
('Nifedipina',    ARRAY['Adalat'],          ARRAY['nifedipina'],        ARRAY['anti_hipertensivo','BCC'],    ARRAY['HAS','angina']),
('Verapamil',     ARRAY['Dilacoron'],       ARRAY['verapamil'],         ARRAY['anti_hipertensivo','BCC'],    ARRAY['HAS','arritmia']),
('Diltiazem',     ARRAY['Cardizem'],        ARRAY['diltiazem'],         ARRAY['anti_hipertensivo','BCC'],    ARRAY['HAS','angina']),
-- Betabloqueadores
('Atenolol',      ARRAY['Atenol'],          ARRAY['atenolol'],          ARRAY['anti_hipertensivo','BB','betabloqueador'], ARRAY['HAS','angina']),
('Metoprolol',    ARRAY['Selozok','Lopressor'], ARRAY['metoprolol'],    ARRAY['anti_hipertensivo','BB','betabloqueador'], ARRAY['HAS','IC','angina']),
('Carvedilol',    ARRAY['Coreg'],           ARRAY['carvedilol'],        ARRAY['anti_hipertensivo','BB','betabloqueador'], ARRAY['IC','HAS']),
('Bisoprolol',    ARRAY['Concor'],          ARRAY['bisoprolol'],        ARRAY['anti_hipertensivo','BB','betabloqueador'], ARRAY['IC','HAS']),
('Propranolol',   ARRAY['Inderal'],         ARRAY['propranolol'],       ARRAY['BB','betabloqueador'],        ARRAY['HAS','tremor','enxaqueca']),
-- Hipoglicemiantes (DM)
('Metformina',    ARRAY['Glifage','Glucoformin'], ARRAY['metformina'],  ARRAY['hipoglicemiante','biguanida'], ARRAY['DM2']),
('Glibenclamida', ARRAY['Daonil'],          ARRAY['glibenclamida'],     ARRAY['hipoglicemiante','sulfonilureia'], ARRAY['DM2']),
('Gliclazida',    ARRAY['Diamicron'],       ARRAY['gliclazida'],        ARRAY['hipoglicemiante','sulfonilureia'], ARRAY['DM2']),
('Glimepirida',   ARRAY['Amaryl'],          ARRAY['glimepirida'],       ARRAY['hipoglicemiante','sulfonilureia'], ARRAY['DM2']),
('Empagliflozina',ARRAY['Jardiance'],       ARRAY['empagliflozina'],    ARRAY['hipoglicemiante','SGLT2'],    ARRAY['DM2','IC']),
('Dapagliflozina',ARRAY['Forxiga'],         ARRAY['dapagliflozina'],    ARRAY['hipoglicemiante','SGLT2'],    ARRAY['DM2','IC']),
('Sitagliptina',  ARRAY['Januvia'],         ARRAY['sitagliptina'],      ARRAY['hipoglicemiante','DPP4'],     ARRAY['DM2']),
('Linagliptina',  ARRAY['Trayenta'],        ARRAY['linagliptina'],      ARRAY['hipoglicemiante','DPP4'],     ARRAY['DM2']),
('Liraglutida',   ARRAY['Victoza'],         ARRAY['liraglutida'],       ARRAY['hipoglicemiante','GLP1'],     ARRAY['DM2','obesidade']),
('Insulina NPH',  ARRAY['Humulin N','Novolin N'], ARRAY['insulina nph','nph','humulin','novolin'], ARRAY['hipoglicemiante','insulina'], ARRAY['DM1','DM2']),
('Insulina regular', ARRAY['Humulin R'],    ARRAY['insulina regular'],  ARRAY['hipoglicemiante','insulina'], ARRAY['DM1','DM2']),
('Insulina glargina', ARRAY['Lantus','Basaglar'], ARRAY['glargina','lantus','basaglar'], ARRAY['hipoglicemiante','insulina'], ARRAY['DM1','DM2']),
-- Estatinas
('Sinvastatina',  ARRAY['Zocor'],           ARRAY['sinvastatina'],      ARRAY['estatina','hipolipemiante'],  ARRAY['dislipidemia','DAC']),
('Atorvastatina', ARRAY['Lipitor','Citalor'], ARRAY['atorvastatina'],   ARRAY['estatina','hipolipemiante'],  ARRAY['dislipidemia','DAC']),
('Rosuvastatina', ARRAY['Crestor'],         ARRAY['rosuvastatina'],     ARRAY['estatina','hipolipemiante'],  ARRAY['dislipidemia','DAC']),
('Pravastatina',  ARRAY['Pravacol'],        ARRAY['pravastatina'],      ARRAY['estatina','hipolipemiante'],  ARRAY['dislipidemia']),
-- Antiagregantes/anticoagulantes
('AAS',           ARRAY['Aspirina','Bufferin','AAS infantil'], ARRAY['aas','acido acetilsalicilico','aspirina'], ARRAY['antiagregante','AINE'], ARRAY['DAC','prevenção_AVC']),
('Clopidogrel',   ARRAY['Plavix','Iscover'], ARRAY['clopidogrel'],      ARRAY['antiagregante'],              ARRAY['DAC','pos_stent']),
('Varfarina',     ARRAY['Marevan'],         ARRAY['varfarina','marevan','warfarin'], ARRAY['anticoagulante','AVK'], ARRAY['FA','TVP','TEP','prótese_valvar']),
('Rivaroxabana',  ARRAY['Xarelto'],         ARRAY['rivaroxabana','xarelto'], ARRAY['anticoagulante','DOAC'], ARRAY['FA','TVP','TEP']),
('Apixabana',     ARRAY['Eliquis'],         ARRAY['apixabana','eliquis'], ARRAY['anticoagulante','DOAC'],   ARRAY['FA','TVP','TEP']),
('Dabigatrana',   ARRAY['Pradaxa'],         ARRAY['dabigatrana','pradaxa'], ARRAY['anticoagulante','DOAC'], ARRAY['FA']),
('Edoxabana',     ARRAY['Lixiana'],         ARRAY['edoxabana'],         ARRAY['anticoagulante','DOAC'],      ARRAY['FA']),
-- Tireoide
('Levotiroxina',  ARRAY['Puran T4','Synthroid','Euthyrox'], ARRAY['levotiroxina','puran','synthroid','euthyrox','t4'], ARRAY['hormonio_tireoidiano'], ARRAY['hipotireoidismo']),
('Propiltiouracil', ARRAY['Propil'],        ARRAY['propiltiouracil'],   ARRAY['antitireoidiano'],            ARRAY['hipertireoidismo']),
('Metimazol',     ARRAY['Tapazol'],         ARRAY['metimazol'],         ARRAY['antitireoidiano'],            ARRAY['hipertireoidismo']),
-- DPOC / Asma
('Salbutamol',    ARRAY['Aerolin'],         ARRAY['salbutamol','aerolin','albuterol'], ARRAY['broncodilatador','beta2_curta_acao'], ARRAY['asma','DPOC']),
('Formoterol',    ARRAY['Foradil'],         ARRAY['formoterol'],        ARRAY['broncodilatador','beta2_longa_acao'], ARRAY['asma','DPOC']),
('Salmeterol',    ARRAY['Serevent'],        ARRAY['salmeterol'],        ARRAY['broncodilatador','beta2_longa_acao'], ARRAY['asma','DPOC']),
('Tiotrópio',     ARRAY['Spiriva'],         ARRAY['tiotropio','spiriva'], ARRAY['broncodilatador','anticolinergico_longa_acao'], ARRAY['DPOC']),
('Ipratrópio',    ARRAY['Atrovent'],        ARRAY['ipratropio','atrovent'], ARRAY['broncodilatador','anticolinergico_curta_acao'], ARRAY['DPOC','asma']),
('Budesonida',    ARRAY['Pulmicort'],       ARRAY['budesonida','pulmicort'], ARRAY['corticoide_inalatorio'], ARRAY['asma','DPOC']),
('Fluticasona',   ARRAY['Flixotide'],       ARRAY['fluticasona','flixotide'], ARRAY['corticoide_inalatorio'], ARRAY['asma','DPOC']),
('Beclometasona', ARRAY['Clenil'],          ARRAY['beclometasona','clenil'], ARRAY['corticoide_inalatorio'], ARRAY['asma']),
-- Antidepressivos / ansiolíticos
('Sertralina',    ARRAY['Zoloft','Tolrest'], ARRAY['sertralina','zoloft'], ARRAY['antidepressivo','ISRS'], ARRAY['depressao','ansiedade']),
('Fluoxetina',    ARRAY['Prozac'],          ARRAY['fluoxetina','prozac'], ARRAY['antidepressivo','ISRS'], ARRAY['depressao']),
('Escitalopram',  ARRAY['Lexapro'],         ARRAY['escitalopram','lexapro'], ARRAY['antidepressivo','ISRS'], ARRAY['depressao','ansiedade']),
('Citalopram',    ARRAY['Cipramil'],        ARRAY['citalopram'],        ARRAY['antidepressivo','ISRS'],      ARRAY['depressao']),
('Venlafaxina',   ARRAY['Efexor'],          ARRAY['venlafaxina','efexor'], ARRAY['antidepressivo','IRSN'], ARRAY['depressao','ansiedade']),
('Mirtazapina',   ARRAY['Remeron'],         ARRAY['mirtazapina','remeron'], ARRAY['antidepressivo','tetraciclico'], ARRAY['depressao_idoso','insonia']),
('Bupropiona',    ARRAY['Wellbutrin','Zyban'], ARRAY['bupropiona','wellbutrin'], ARRAY['antidepressivo'], ARRAY['depressao']),
-- Benzodiazepínicos (Beers — uso restrito em idoso)
('Diazepam',      ARRAY['Valium'],          ARRAY['diazepam','valium'], ARRAY['benzodiazepinico'],           ARRAY['ansiedade','insonia']),
('Clonazepam',    ARRAY['Rivotril'],        ARRAY['clonazepam','rivotril'], ARRAY['benzodiazepinico'],     ARRAY['ansiedade','epilepsia']),
('Alprazolam',    ARRAY['Frontal'],         ARRAY['alprazolam','frontal'], ARRAY['benzodiazepinico'],      ARRAY['ansiedade','panico']),
('Lorazepam',     ARRAY['Lorax'],           ARRAY['lorazepam'],         ARRAY['benzodiazepinico'],           ARRAY['ansiedade']),
-- Antipsicóticos
('Quetiapina',    ARRAY['Seroquel'],        ARRAY['quetiapina','seroquel'], ARRAY['antipsicotico_atipico'], ARRAY['demencia_agitacao','psicose']),
('Risperidona',   ARRAY['Risperdal'],       ARRAY['risperidona','risperdal'], ARRAY['antipsicotico_atipico'], ARRAY['demencia_agitacao','psicose']),
('Olanzapina',    ARRAY['Zyprexa'],         ARRAY['olanzapina'],        ARRAY['antipsicotico_atipico'],      ARRAY['psicose']),
('Haloperidol',   ARRAY['Haldol'],          ARRAY['haloperidol','haldol'], ARRAY['antipsicotico_tipico'], ARRAY['delirium','psicose']),
-- Demência
('Donepezila',    ARRAY['Eranz','Aricept'], ARRAY['donepezila','eranz','aricept'], ARRAY['anticolinesterasico'], ARRAY['Alzheimer','demencia']),
('Rivastigmina',  ARRAY['Exelon'],          ARRAY['rivastigmina','exelon'], ARRAY['anticolinesterasico'], ARRAY['Alzheimer','demencia']),
('Memantina',     ARRAY['Ebix','Alois'],    ARRAY['memantina','ebix'],  ARRAY['antagonista_NMDA'],           ARRAY['Alzheimer_moderado_grave']),
-- Parkinson
('Levodopa+Carbidopa', ARRAY['Sinemet','Cronomet'], ARRAY['levodopa','sinemet','cronomet','carbidopa'], ARRAY['antiparkinsoniano'], ARRAY['Parkinson']),
('Pramipexol',    ARRAY['Sifrol'],          ARRAY['pramipexol','sifrol'], ARRAY['agonista_dopaminergico'], ARRAY['Parkinson']),
-- Refluxo / digestivo
('Omeprazol',     ARRAY['Losec'],           ARRAY['omeprazol','losec'], ARRAY['IBP','antiulceroso'],         ARRAY['DRGE','ulcera']),
('Pantoprazol',   ARRAY['Pantozol'],        ARRAY['pantoprazol','pantozol'], ARRAY['IBP','antiulceroso'], ARRAY['DRGE','ulcera']),
('Esomeprazol',   ARRAY['Nexium'],          ARRAY['esomeprazol','nexium'], ARRAY['IBP','antiulceroso'], ARRAY['DRGE','ulcera']),
-- Analgésicos / AINE
('Paracetamol',   ARRAY['Tylenol','Vick Pyrena'], ARRAY['paracetamol','tylenol','acetaminofen'], ARRAY['analgesico_simples'], ARRAY['dor','febre']),
('Dipirona',      ARRAY['Novalgina'],       ARRAY['dipirona','novalgina','metamizol'], ARRAY['analgesico_simples'], ARRAY['dor','febre']),
('Ibuprofeno',    ARRAY['Advil','Alivium'], ARRAY['ibuprofeno','advil'], ARRAY['AINE','anti_inflamatorio'], ARRAY['dor','inflamação']),
('Diclofenaco',   ARRAY['Voltaren','Cataflam'], ARRAY['diclofenaco','voltaren'], ARRAY['AINE','anti_inflamatorio'], ARRAY['dor','inflamação']),
('Naproxeno',     ARRAY['Naprosyn'],        ARRAY['naproxeno','naprosyn'], ARRAY['AINE','anti_inflamatorio'], ARRAY['dor','inflamação']),
-- Outros comuns
('Levofloxacina', ARRAY['Levaquin','Tavanic'], ARRAY['levofloxacina','levaquin'], ARRAY['antibiotico','quinolona'], ARRAY['ITU','pneumonia']),
('Amoxicilina',   ARRAY['Amoxil'],          ARRAY['amoxicilina','amoxil'], ARRAY['antibiotico','penicilina'], ARRAY['ITU','infecção']),
('Ciprofloxacina', ARRAY['Cipro'],          ARRAY['ciprofloxacina','cipro'], ARRAY['antibiotico','quinolona'], ARRAY['ITU']),
('Azitromicina',  ARRAY['Zithromax','Astro'], ARRAY['azitromicina','zithromax'], ARRAY['antibiotico','macrolideo'], ARRAY['pneumonia']),
('Cetirizina',    ARRAY['Zyrtec'],          ARRAY['cetirizina','zyrtec'], ARRAY['anti_histaminico'],         ARRAY['rinite','alergia']),
('Loratadina',    ARRAY['Claritin'],        ARRAY['loratadina','claritin'], ARRAY['anti_histaminico'],     ARRAY['rinite','alergia']),
('Prednisona',    ARRAY['Meticorten'],      ARRAY['prednisona','meticorten'], ARRAY['corticoide_oral'],    ARRAY['inflamação','autoimune']),
('Alendronato',   ARRAY['Fosamax'],         ARRAY['alendronato','fosamax'], ARRAY['bifosfonato'],          ARRAY['osteoporose']),
('Cálcio + Vitamina D', ARRAY['Calcium-D','Os-Cal'], ARRAY['calcio','vitamina d','colecalciferol'], ARRAY['suplemento_calcio','vitamina_D'], ARRAY['osteoporose'])
ON CONFLICT (active_ingredient) DO NOTHING;


-- 3. Cross-validation expectations (8 condições baseline) ─────────────────────

INSERT INTO aia_health_disease_medication_expectations
    (condition_label, cid10_code, condition_match_patterns, expected_therapeutic_classes, prompt_severity, prompt_message, clinical_rationale) VALUES
('Hipertensão Arterial Sistêmica (HAS)', 'I10',
    ARRAY['hipertens','pressao alta','pressão alta','has '],
    ARRAY['anti_hipertensivo','IECA','BRA','BB','BCC','diuretico_tiazidico','diuretico_alca'],
    'medium',
    'Você marcou Hipertensão Arterial (HAS) mas não listou nenhum medicamento anti-hipertensivo. Está em tratamento sem medicamento, ou esqueceu de listar?',
    'HAS sem tratamento medicamentoso aumenta risco de AVC, IAM e nefropatia. Vale documentar se é tratamento não-farmacológico (dieta DASH, atividade física) por escolha clínica.'),

('Diabetes Mellitus (DM)', 'E11.9',
    ARRAY['diabetes','dm 2','dm2','dm tipo 2'],
    ARRAY['hipoglicemiante','biguanida','sulfonilureia','SGLT2','DPP4','GLP1','insulina'],
    'high',
    'Você marcou Diabetes Mellitus (DM) mas não listou nenhum hipoglicemiante. Está em controle só com dieta, ou esqueceu de listar?',
    'DM sem medicação leva a complicações micro e macrovasculares (retinopatia, nefropatia, neuropatia, DAC). DM2 controlado só com dieta é possível em casos leves recém-diagnosticados.'),

('Insuficiência Cardíaca (IC)', 'I50.9',
    ARRAY['insuficiencia cardiaca','icc','ic descompensada','insuficiência cardíaca'],
    ARRAY['IECA','BRA','BB','betabloqueador','antagonista_aldosterona','diuretico_alca','SGLT2'],
    'high',
    'Você marcou Insuficiência Cardíaca (IC) mas não listou os medicamentos esperados (IECA/BRA, Betabloqueador (BB) ou Espironolactona). Está em tratamento, ou esqueceu de listar?',
    'IC tem mortalidade 1 ano de 25-30% sem tratamento otimizado. Tripla terapia (IECA/BRA + BB + Espironolactona) é padrão-ouro.'),

('Fibrilação Atrial (FA)', 'I48',
    ARRAY['fibrilac','fa atrial','fibrilação','fa cronica','fa paroxistica'],
    ARRAY['anticoagulante','DOAC','AVK'],
    'critical',
    'Você marcou Fibrilação Atrial (FA) mas não listou anticoagulante (Varfarina, Rivaroxabana, Apixabana, Dabigatrana). Risco grave de AVC embólico — está em uso de anticoagulante?',
    'FA sem anticoagulação tem risco anual de AVC isquêmico de 5-7% (CHA2DS2-VASc ≥ 2). É a inconsistência mais grave em geriatria.'),

('Hipotireoidismo', 'E03',
    ARRAY['hipotireoid','tireoide preguic','hashimoto'],
    ARRAY['hormonio_tireoidiano'],
    'high',
    'Você marcou Hipotireoidismo mas não listou Levotiroxina (Puran T4 / Synthroid / Euthyrox). Está em tratamento, ou esqueceu de listar?',
    'Hipotireoidismo não-tratado em idoso causa fadiga, ganho de peso, bradicardia, lentificação cognitiva e pode evoluir pra coma mixedematoso.'),

('Doença Pulmonar Obstrutiva Crônica (DPOC)', 'J44.9',
    ARRAY['dpoc','enfisema','bronquite cronica','bronquite crônica'],
    ARRAY['broncodilatador','beta2_longa_acao','anticolinergico_longa_acao','corticoide_inalatorio'],
    'medium',
    'Você marcou DPOC (Doença Pulmonar Obstrutiva Crônica) mas não listou broncodilatador (Tiotrópio, Salmeterol, Formoterol, Budesonida inalatória). Está em tratamento, ou esqueceu?',
    'DPOC sem broncodilatador progride mais rápido com mais exacerbações e hospitalizações.'),

('Asma', 'J45',
    ARRAY['asma','asmatico','asmática'],
    ARRAY['broncodilatador','beta2_curta_acao','beta2_longa_acao','corticoide_inalatorio'],
    'medium',
    'Você marcou Asma mas não listou broncodilatador ou corticoide inalatório. Está em tratamento, ou esqueceu?',
    'Asma persistente sem corticoide inalatório aumenta risco de crise grave e hospitalização.'),

('Doença Arterial Coronariana (DAC)', 'I25',
    ARRAY['doenca arterial coronariana','dac','coronariopatia','infarto previo','iam previo','pos-stent','pós-stent','angina'],
    ARRAY['antiagregante','estatina','BB','betabloqueador'],
    'high',
    'Você marcou Doença Arterial Coronariana (DAC) mas não listou os medicamentos esperados (AAS/Aspirina, Estatina, Betabloqueador). Está em tratamento, ou esqueceu?',
    'DAC sem prevenção secundária (AAS + Estatina + BB) tem risco aumentado de IAM recorrente e morte súbita.')
ON CONFLICT DO NOTHING;
