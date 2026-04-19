-- ConnectaIACare — Mock data para demo (8 pacientes + cuidadora Joana)
-- Dados fictícios. Qualquer semelhança com pessoas reais é coincidência.
-- Fotos: i.pravatar.cc com seeds estáveis (substituir por fotos reais antes da demo final).

BEGIN;

TRUNCATE aia_health_reports CASCADE;
TRUNCATE aia_health_caregivers CASCADE;
TRUNCATE aia_health_patients CASCADE;
TRUNCATE aia_health_conversation_sessions CASCADE;

-- =====================================================
-- Cuidadora demo
-- =====================================================
INSERT INTO aia_health_caregivers (full_name, cpf, phone, role, shift, active)
VALUES
    ('Joana Oliveira', '123.456.789-00', '5551989592617', 'cuidadora', 'noturno', TRUE);

-- =====================================================
-- Pacientes fictícios — 8 idosos com perfis clínicos realistas
-- =====================================================
INSERT INTO aia_health_patients
    (full_name, nickname, birth_date, gender, photo_url, care_unit, room_number, care_level, conditions, medications, allergies, responsible)
VALUES
(
    'Maria da Silva Santos',
    'Dona Maria',
    '1938-05-12',
    'F',
    'https://i.pravatar.cc/400?img=45',
    'SPA Vida Plena — Ala B',
    '12',
    'semi-dependente',
    '[
        {"code": "I10", "description": "Hipertensão arterial sistêmica", "severity": "moderada", "since": "2010"},
        {"code": "I50", "description": "Insuficiência cardíaca classe funcional II", "severity": "moderada", "since": "2019"},
        {"code": "E11", "description": "Diabetes mellitus tipo 2", "severity": "controlada", "since": "2008"}
    ]'::JSONB,
    '[
        {"name": "Losartana 50mg", "schedule": "08:00, 20:00", "dose": "1 comp"},
        {"name": "Furosemida 40mg", "schedule": "08:00", "dose": "1 comp"},
        {"name": "Metformina 850mg", "schedule": "08:00, 12:00, 20:00", "dose": "1 comp"},
        {"name": "AAS 100mg", "schedule": "12:00", "dose": "1 comp"}
    ]'::JSONB,
    '["Dipirona"]'::JSONB,
    '{"name": "Ana Santos", "relationship": "filha", "phone": "+5551993178926"}'::JSONB
),
(
    'João Oliveira Costa',
    'Seu João',
    '1947-11-03',
    'M',
    'https://i.pravatar.cc/400?img=52',
    'SPA Vida Plena — Ala A',
    '04',
    'dependente',
    '[
        {"code": "G30", "description": "Doença de Alzheimer estágio moderado", "severity": "moderada", "since": "2022"},
        {"code": "I10", "description": "Hipertensão arterial", "severity": "controlada", "since": "2015"}
    ]'::JSONB,
    '[
        {"name": "Donepezila 10mg", "schedule": "20:00", "dose": "1 comp"},
        {"name": "Memantina 20mg", "schedule": "08:00, 20:00", "dose": "1 comp"},
        {"name": "Losartana 25mg", "schedule": "08:00", "dose": "1 comp"}
    ]'::JSONB,
    '[]'::JSONB,
    '{"name": "Ricardo Costa", "relationship": "filho", "phone": "+5551999887766"}'::JSONB
),
(
    'Antonia Ferreira Lima',
    'Dona Antonia',
    '1934-02-28',
    'F',
    'https://i.pravatar.cc/400?img=16',
    'SPA Vida Plena — Ala B',
    '08',
    'dependente',
    '[
        {"code": "G20", "description": "Doença de Parkinson", "severity": "avançada", "since": "2016"},
        {"code": "M81", "description": "Osteoporose", "severity": "severa", "since": "2018"}
    ]'::JSONB,
    '[
        {"name": "Levodopa+Carbidopa 250/25mg", "schedule": "07:00, 11:00, 15:00, 19:00", "dose": "1 comp"},
        {"name": "Pramipexol 0,125mg", "schedule": "08:00, 20:00", "dose": "1 comp"},
        {"name": "Alendronato 70mg", "schedule": "Segunda 07:00", "dose": "1 comp"},
        {"name": "Cálcio + Vitamina D", "schedule": "12:00", "dose": "1 comp"}
    ]'::JSONB,
    '["Haloperidol", "Metoclopramida"]'::JSONB,
    '{"name": "Claudia Lima", "relationship": "filha", "phone": "+5551988776655"}'::JSONB
),
(
    'Pedro Santos Almeida',
    'Seu Pedro',
    '1942-07-17',
    'M',
    'https://i.pravatar.cc/400?img=68',
    'SPA Vida Plena — Ala A',
    '06',
    'independente',
    '[
        {"code": "J44", "description": "DPOC (Doença Pulmonar Obstrutiva Crônica)", "severity": "moderada", "since": "2012"},
        {"code": "I10", "description": "Hipertensão arterial", "severity": "controlada", "since": "2009"}
    ]'::JSONB,
    '[
        {"name": "Tiotrópio inalatório", "schedule": "08:00", "dose": "1 puff"},
        {"name": "Formoterol+Budesonida", "schedule": "08:00, 20:00", "dose": "1 puff"},
        {"name": "Enalapril 10mg", "schedule": "08:00", "dose": "1 comp"}
    ]'::JSONB,
    '[]'::JSONB,
    '{"name": "Marcia Almeida", "relationship": "filha", "phone": "+5551977665544"}'::JSONB
),
(
    'Carmen Rodrigues Pires',
    'Dona Carmen',
    '1950-09-23',
    'F',
    'https://i.pravatar.cc/400?img=49',
    'SPA Vida Plena — Ala C',
    '14',
    'semi-dependente',
    '[
        {"code": "E11", "description": "Diabetes mellitus tipo 2", "severity": "moderada", "since": "2005"},
        {"code": "M17", "description": "Gonartrose bilateral", "severity": "avançada", "since": "2017"}
    ]'::JSONB,
    '[
        {"name": "Metformina 850mg", "schedule": "08:00, 12:00, 20:00", "dose": "1 comp"},
        {"name": "Gliclazida 30mg", "schedule": "08:00", "dose": "1 comp"},
        {"name": "Paracetamol 750mg", "schedule": "se dor", "dose": "1 comp até 4x/dia"}
    ]'::JSONB,
    '["Penicilina"]'::JSONB,
    '{"name": "Roberto Pires", "relationship": "filho", "phone": "+5551966554433"}'::JSONB
),
(
    'José Almeida Nunes',
    'Seu José',
    '1936-01-15',
    'M',
    'https://i.pravatar.cc/400?img=58',
    'SPA Vida Plena — Ala B',
    '10',
    'dependente',
    '[
        {"code": "F03", "description": "Demência vascular", "severity": "moderada", "since": "2021"},
        {"code": "I10", "description": "Hipertensão arterial", "severity": "controlada", "since": "2000"},
        {"code": "I25", "description": "Doença arterial coronariana", "severity": "moderada", "since": "2013"}
    ]'::JSONB,
    '[
        {"name": "Quetiapina 25mg", "schedule": "21:00", "dose": "1 comp"},
        {"name": "Losartana 50mg", "schedule": "08:00", "dose": "1 comp"},
        {"name": "AAS 100mg", "schedule": "12:00", "dose": "1 comp"},
        {"name": "Atorvastatina 20mg", "schedule": "21:00", "dose": "1 comp"}
    ]'::JSONB,
    '[]'::JSONB,
    '{"name": "Helena Nunes", "relationship": "filha", "phone": "+5551955443322"}'::JSONB
),
(
    'Lúcia Pereira Souza',
    'Dona Lúcia',
    '1944-04-08',
    'F',
    'https://i.pravatar.cc/400?img=32',
    'SPA Vida Plena — Ala A',
    '02',
    'dependente',
    '[
        {"code": "I63", "description": "Sequela de AVC isquêmico (2023)", "severity": "moderada", "since": "2023"},
        {"code": "I10", "description": "Hipertensão arterial", "severity": "controlada", "since": "2010"},
        {"code": "I48", "description": "Fibrilação atrial", "severity": "controlada", "since": "2023"}
    ]'::JSONB,
    '[
        {"name": "Varfarina 5mg", "schedule": "18:00 (Seg/Qua/Sex)", "dose": "1 comp"},
        {"name": "Varfarina 2,5mg", "schedule": "18:00 (Ter/Qui/Sab/Dom)", "dose": "1 comp"},
        {"name": "Losartana 50mg", "schedule": "08:00, 20:00", "dose": "1 comp"},
        {"name": "Sinvastatina 20mg", "schedule": "21:00", "dose": "1 comp"}
    ]'::JSONB,
    '[]'::JSONB,
    '{"name": "Paulo Souza", "relationship": "filho", "phone": "+5551944332211"}'::JSONB
),
(
    'Roberto Costa Ribeiro',
    'Seu Roberto',
    '1949-08-30',
    'M',
    'https://i.pravatar.cc/400?img=60',
    'SPA Vida Plena — Ala C',
    '16',
    'semi-dependente',
    '[
        {"code": "I50", "description": "Insuficiência cardíaca classe funcional III", "severity": "severa", "since": "2020"},
        {"code": "E11", "description": "Diabetes mellitus tipo 2 insulinodependente", "severity": "moderada", "since": "2003"},
        {"code": "N18", "description": "Doença renal crônica estágio 3", "severity": "moderada", "since": "2022"}
    ]'::JSONB,
    '[
        {"name": "Carvedilol 25mg", "schedule": "08:00, 20:00", "dose": "1 comp"},
        {"name": "Furosemida 40mg", "schedule": "08:00, 14:00", "dose": "1 comp"},
        {"name": "Espironolactona 25mg", "schedule": "08:00", "dose": "1 comp"},
        {"name": "Insulina NPH 20UI", "schedule": "07:00, 22:00", "dose": "SC"},
        {"name": "Insulina Regular", "schedule": "antes refeições conforme glicemia", "dose": "SC"}
    ]'::JSONB,
    '[]'::JSONB,
    '{"name": "Sandra Ribeiro", "relationship": "filha", "phone": "+5551933221100"}'::JSONB
);

COMMIT;
