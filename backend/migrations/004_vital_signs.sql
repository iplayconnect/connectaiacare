-- ConnectaIACare — Vital Signs (MedMonitor integration-ready)
-- Schema FHIR-compatível com códigos LOINC para preparar integração com
-- MedMonitor (Fase 2 MONITOR) e eventual exportação via FHIR Observation.
-- Data: 2026-04-20

BEGIN;

-- =====================================================
-- Vital signs / aferições
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_vital_signs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    patient_id UUID NOT NULL REFERENCES aia_health_patients(id) ON DELETE CASCADE,

    -- Tipo de medição (LOINC-aligned)
    vital_type TEXT NOT NULL CHECK (vital_type IN (
        'blood_pressure_systolic',    -- LOINC 85354-9 — mmHg
        'blood_pressure_diastolic',   -- LOINC 8462-4  — mmHg
        'heart_rate',                 -- LOINC 8867-4  — bpm
        'temperature',                -- LOINC 8310-5  — °C
        'oxygen_saturation',          -- LOINC 59408-5 — %
        'blood_glucose',              -- LOINC 2339-0  — mg/dL
        'respiratory_rate',           -- LOINC 9279-1  — rpm
        'weight',                     -- LOINC 29463-7 — kg
        'blood_pressure_composite'    -- composite: guarda systolic+diastolic em payload
    )),

    -- Valores
    value_numeric NUMERIC(8,2),        -- valor primário (ex: 128.00 mmHg sistólica)
    value_secondary NUMERIC(8,2),      -- valor secundário (ex: 82.00 diastólica quando vital_type=composite)
    unit TEXT NOT NULL,                -- 'mmHg' | 'bpm' | 'celsius' | 'percent' | 'mg/dl' | 'kg' | 'rpm'

    -- Classificação clínica da medição (mesma taxonomia do sistema)
    status TEXT NOT NULL DEFAULT 'routine' CHECK (status IN (
        'routine',     -- dentro da faixa ideal
        'attention',   -- borderline, merece observação
        'urgent',      -- fora da faixa, requer ação
        'critical'     -- valor de emergência
    )),

    -- Origem da medição
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN (
        'manual',         -- digitado pela enfermagem no dashboard
        'medmonitor',     -- dispositivo MedMonitor (Fase 2)
        'wearable',       -- Apple Health / Android Health Connect
        'whatsapp_relato',-- mencionado pelo cuidador no áudio (extracted)
        'imported'        -- importação manual de histórico
    )),

    -- Metadata
    device_id TEXT,                    -- ID do dispositivo MedMonitor/wearable
    measured_by TEXT,                  -- profissional que aferiu (se manual)
    notes TEXT,
    loinc_code TEXT,                   -- ex: '85354-9' (redundante mas útil para FHIR export)

    -- Timestamps
    measured_at TIMESTAMPTZ NOT NULL,  -- quando foi aferido (no paciente)
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- quando chegou ao sistema
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vitals_patient_measured
    ON aia_health_vital_signs(patient_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_vitals_tenant_type
    ON aia_health_vital_signs(tenant_id, vital_type, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_vitals_status
    ON aia_health_vital_signs(status) WHERE status IN ('urgent','critical');

-- =====================================================
-- Faixas de referência (por tipo + opcionalmente por paciente)
-- Permite definir thresholds customizados por paciente ou usar default populacional.
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_vital_ranges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    patient_id UUID REFERENCES aia_health_patients(id) ON DELETE CASCADE,  -- NULL = default populacional
    vital_type TEXT NOT NULL,

    -- Faixas
    routine_min NUMERIC(8,2),
    routine_max NUMERIC(8,2),
    attention_min NUMERIC(8,2),
    attention_max NUMERIC(8,2),
    urgent_min NUMERIC(8,2),
    urgent_max NUMERIC(8,2),
    -- Abaixo de urgent_min ou acima de urgent_max = critical

    unit TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ranges_patient
    ON aia_health_vital_ranges(patient_id, vital_type) WHERE patient_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ranges_default
    ON aia_health_vital_ranges(vital_type) WHERE patient_id IS NULL;

DROP TRIGGER IF EXISTS trg_ranges_updated ON aia_health_vital_ranges;
CREATE TRIGGER trg_ranges_updated BEFORE UPDATE ON aia_health_vital_ranges
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();

-- =====================================================
-- Faixas default populacional para idosos (>65 anos)
-- Baseado em: SBH (Soc. Bras. de Hipertensão), SBD (Soc. Bras. de Diabetes),
-- diretrizes geriátricas (menos agressivas que adultos jovens).
-- =====================================================
INSERT INTO aia_health_vital_ranges
    (patient_id, vital_type, routine_min, routine_max, attention_min, attention_max, urgent_min, urgent_max, unit, notes)
VALUES
    (NULL, 'blood_pressure_systolic', 110, 140, 100, 150, 90, 180, 'mmHg',
     'Idosos: alvo mais flexível (<150 aceitável após 80a). Crítico: <90 (hipotensão) ou >180 (crise hipertensiva).'),

    (NULL, 'blood_pressure_diastolic', 60, 90, 55, 95, 50, 110, 'mmHg',
     'Crítico: <50 ou >110.'),

    (NULL, 'heart_rate', 55, 90, 50, 100, 40, 130, 'bpm',
     'Idosos em betabloqueador tipicamente 50-70. Crítico: <40 (bradi) ou >130 (taqui).'),

    (NULL, 'temperature', 36.0, 37.5, 35.5, 38.0, 34.5, 39.5, 'celsius',
     'Idosos têm temperatura basal ~0.5°C mais baixa. Hipotermia em idoso = <35.5 é já atenção.'),

    (NULL, 'oxygen_saturation', 94, 100, 90, 100, 85, 100, 'percent',
     'DPOC crônico pode ter baseline 88-92. Crítico: <85.'),

    (NULL, 'blood_glucose', 70, 180, 60, 250, 50, 400, 'mg/dl',
     'Idosos: alvo mais flexível para evitar hipoglicemia. <60 é urgente. <50 crítico.'),

    (NULL, 'respiratory_rate', 12, 20, 10, 24, 8, 30, 'rpm',
     'Taquipneia em idoso (>24) pode indicar IC ou pneumonia.'),

    (NULL, 'weight', 0, 999, 0, 999, 0, 999, 'kg',
     'Peso em si não tem range universal. Alerta por delta (>2kg/semana = atenção).');

-- =====================================================
-- Seed: 7 dias de sinais vitais mock para os 8 pacientes
-- Gera ~1200 medições (variadas por tipo + realista por condição clínica)
-- =====================================================

DO $$
DECLARE
    patient_rec RECORD;
    day_offset INT;
    base_sys INT; base_dia INT; base_hr INT; base_temp NUMERIC; base_spo2 INT; base_glu INT; base_wt NUMERIC;
    sys_v INT; dia_v INT; hr_v INT; temp_v NUMERIC; spo2_v INT; glu_v INT; wt_v NUMERIC;
    status_sys TEXT; status_spo2 TEXT; status_glu TEXT;
    measured TIMESTAMPTZ;
BEGIN
    FOR patient_rec IN
        SELECT id, full_name, conditions FROM aia_health_patients WHERE tenant_id = 'connectaiacare_demo'
    LOOP
        -- Define baseline por paciente baseado em condições conhecidas
        base_sys := CASE
            WHEN patient_rec.conditions::text LIKE '%Hipertens%' THEN 135
            WHEN patient_rec.conditions::text LIKE '%IC%' OR patient_rec.conditions::text LIKE '%Insufici%cia cardi%' THEN 125
            ELSE 120
        END;
        base_dia := CASE
            WHEN patient_rec.conditions::text LIKE '%Hipertens%' THEN 85
            ELSE 75
        END;
        base_hr := CASE
            WHEN patient_rec.conditions::text LIKE '%Insufici%cia cardi%' OR patient_rec.conditions::text LIKE '%IC%' THEN 78
            WHEN patient_rec.conditions::text LIKE '%Parkinson%' THEN 68
            ELSE 72
        END;
        base_temp := 36.5;
        base_spo2 := CASE
            WHEN patient_rec.conditions::text LIKE '%DPOC%' THEN 92
            ELSE 97
        END;
        base_glu := CASE
            WHEN patient_rec.conditions::text LIKE '%Diabet%' THEN 145
            ELSE 95
        END;
        base_wt := 58 + (random() * 25)::NUMERIC(5,2);  -- 58-83 kg variado

        -- 7 dias × 2-3 medições por dia
        FOR day_offset IN 0..6 LOOP
            FOR i IN 1..3 LOOP
                measured := NOW() - (day_offset * INTERVAL '1 day') - (i * INTERVAL '4 hours');

                -- Gerar valores com ruído realista (±10%)
                sys_v := base_sys + (random() * 30 - 15)::INT;
                dia_v := base_dia + (random() * 16 - 8)::INT;
                hr_v := base_hr + (random() * 20 - 10)::INT;
                temp_v := (base_temp + (random() * 0.8 - 0.4))::NUMERIC(4,2);
                spo2_v := base_spo2 + (random() * 4 - 2)::INT;
                glu_v := base_glu + (random() * 60 - 30)::INT;

                -- Classificar status
                status_sys := CASE
                    WHEN sys_v >= 180 OR sys_v < 90 THEN 'critical'
                    WHEN sys_v >= 150 OR sys_v < 100 THEN 'urgent'
                    WHEN sys_v >= 141 OR sys_v < 110 THEN 'attention'
                    ELSE 'routine'
                END;
                status_spo2 := CASE
                    WHEN spo2_v < 85 THEN 'critical'
                    WHEN spo2_v < 90 THEN 'urgent'
                    WHEN spo2_v < 94 THEN 'attention'
                    ELSE 'routine'
                END;
                status_glu := CASE
                    WHEN glu_v < 50 OR glu_v > 400 THEN 'critical'
                    WHEN glu_v < 60 OR glu_v > 250 THEN 'urgent'
                    WHEN glu_v < 70 OR glu_v > 180 THEN 'attention'
                    ELSE 'routine'
                END;

                -- Inserir PA composta (sistólica + diastólica em 1 record)
                INSERT INTO aia_health_vital_signs
                    (patient_id, vital_type, value_numeric, value_secondary, unit, status, source, loinc_code, measured_at)
                VALUES
                    (patient_rec.id, 'blood_pressure_composite', sys_v, dia_v, 'mmHg', status_sys, 'manual', '85354-9', measured);

                -- FC
                INSERT INTO aia_health_vital_signs
                    (patient_id, vital_type, value_numeric, unit, status, source, loinc_code, measured_at)
                VALUES
                    (patient_rec.id, 'heart_rate', hr_v, 'bpm',
                     CASE WHEN hr_v < 40 OR hr_v > 130 THEN 'critical'
                          WHEN hr_v < 50 OR hr_v > 100 THEN 'urgent'
                          WHEN hr_v < 55 OR hr_v > 90 THEN 'attention'
                          ELSE 'routine' END,
                     'manual', '8867-4', measured);

                -- Temperatura (1x/dia, não 3x)
                IF i = 1 THEN
                    INSERT INTO aia_health_vital_signs
                        (patient_id, vital_type, value_numeric, unit, status, source, loinc_code, measured_at)
                    VALUES
                        (patient_rec.id, 'temperature', temp_v, 'celsius',
                         CASE WHEN temp_v > 38.0 OR temp_v < 35.5 THEN 'urgent'
                              WHEN temp_v > 37.5 OR temp_v < 36.0 THEN 'attention'
                              ELSE 'routine' END,
                         'manual', '8310-5', measured);
                END IF;

                -- SpO2
                INSERT INTO aia_health_vital_signs
                    (patient_id, vital_type, value_numeric, unit, status, source, loinc_code, measured_at)
                VALUES
                    (patient_rec.id, 'oxygen_saturation', spo2_v, 'percent', status_spo2, 'manual', '59408-5', measured);

                -- Glicemia (só em diabéticos, 2x/dia)
                IF patient_rec.conditions::text LIKE '%Diabet%' AND i <= 2 THEN
                    INSERT INTO aia_health_vital_signs
                        (patient_id, vital_type, value_numeric, unit, status, source, loinc_code, measured_at)
                    VALUES
                        (patient_rec.id, 'blood_glucose', glu_v, 'mg/dl', status_glu, 'manual', '2339-0', measured);
                END IF;

                -- Peso (1x por semana, no dia 0 / mais recente)
                IF day_offset = 0 AND i = 1 THEN
                    wt_v := (base_wt + (random() * 0.6 - 0.3))::NUMERIC(5,2);
                    INSERT INTO aia_health_vital_signs
                        (patient_id, vital_type, value_numeric, unit, status, source, loinc_code, measured_at)
                    VALUES
                        (patient_rec.id, 'weight', wt_v, 'kg', 'routine', 'manual', '29463-7', measured);
                END IF;
            END LOOP;
        END LOOP;
    END LOOP;
END $$;

COMMIT;
