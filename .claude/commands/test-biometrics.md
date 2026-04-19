---
description: Testa o pipeline de biometria de voz com áudios reais (preprocess, compare, enroll, identify)
argument-hint: [audio-file | --compare a.ogg b.ogg | --enroll <caregiver_id> <audio>]
---

Execute o script de teste de biometria de voz: `scripts/test_voice_biometrics.py`.

## Uso comum

1. **Analisar qualidade de um áudio**:
   ```
   python scripts/test_voice_biometrics.py --audio <path>
   ```
   Mostra: duração, speech detectado, RMS, SNR, clipping, quality overall, se foi rejeitado e por quê.

2. **Comparar dois áudios (mesma pessoa?)**:
   ```
   python scripts/test_voice_biometrics.py --compare <a> <b>
   ```
   Mostra similaridade cosseno e veredito (mesma pessoa / diferente / ambíguo).

3. **Enroll** (adiciona amostra ao cuidador no DB — requer Postgres rodando):
   ```
   python scripts/test_voice_biometrics.py --enroll <caregiver_uuid> <audio>
   ```

4. **Identify** (simula fluxo 1:N do pipeline):
   ```
   python scripts/test_voice_biometrics.py --identify <audio>
   ```

## Quando usar

- Debug de falha biométrica ("por que não identificou a Joana?")
- Calibração: testar áudios reais e ver scores para ajustar thresholds em `voice_biometrics_service.py`
- Onboarding de novos cuidadores: validar que amostras de enrollment têm qualidade mínima
- Detecção de regressão: após mudanças em `audio_preprocessing.py`, rodar contra áudios conhecidos

## Interpretando resultados

**Quality overall**:
- `0.7+` = áudio ótimo (perfil de enrollment ideal)
- `0.5-0.7` = aceitável para enrollment (threshold atual: 0.55)
- `0.3-0.5` = identification OK (threshold atual: 0.30), mas enrollment seria rejeitado
- `< 0.3` = rejeitado em ambos os fluxos

**Similaridade cosseno (compare)**:
- `≥ 0.75` = mesma pessoa, alta confiança → threshold 1:1
- `0.65-0.75` = provavelmente mesma pessoa → threshold 1:N
- `0.50-0.65` = ambíguo
- `< 0.50` = pessoas diferentes

**Rejeições comuns**:
- `audio_silencioso` → volume muito baixo
- `fala_insuficiente_XXXms` → menos de 2s de fala (VAD)
- `audio_clipado_XX%` → distorção por volume alto
- `snr_baixo_X.XdB` → muito ruído de fundo

## Depois do teste

Se você identificar problemas de calibração:
- Thresholds estão em `backend/src/services/voice_biometrics_service.py` (linhas 20-30)
- Parâmetros de preprocessing em `backend/src/services/audio_preprocessing.py` (linhas 20-35)
- Não altere sem consultar um conjunto representativo de áudios
