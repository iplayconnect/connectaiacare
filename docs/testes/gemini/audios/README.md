# Gemini 3.1 Flash TTS — Samples pt-BR (2026-04-24)

Áudios gerados com `gemini-3.1-flash-tts-preview` via REST API, voz "Kore".

## Arquivos

| Arquivo | Cenário | Prompt (prefixo de estilo) |
|---------|---------|----------------------------|
| `tts_checkin_warm.mp3` | Check-in matinal rotina | `Say warmly:` |
| `tts_attention_change.mp3` | Alteração PA paciente (attention) | `Say in a serious but calm tone:` |
| `tts_urgent_fall.mp3` | Queda com SAMU (urgent/critical) | `Say urgently and firmly:` |
| `tts_reassurance.mp3` | Confirmação pós-susto | `Say gently and warmly:` |

## Observações técnicas

- **Formato retornado pela API**: PCM raw L16 mono 24kHz (sem container). Script envolve em WAV RIFF válido.
- **MP3**: conversão via `ffmpeg -acodec libmp3lame -ab 96k -ar 22050 -ac 1`
- **Latência de geração**: 5-11s no primeiro request (preview endpoint, pode variar com versão stable)
- **Voz**: `Kore` (feminina, padrão pro pt-BR). Gemini TTS oferece 30+ vozes pré-definidas.

## Audio tags

**Limitação descoberta**: o modelo `gemini-3.1-flash-tts-preview` **não aceita** tags estilo `[warm] [urgent]` inline como a análise original indicava. Em vez disso, controle de estilo é via **prefixos em inglês** tipo `"Say warmly:"` ou `"Say in a serious tone:"` no início do texto.

Isso é **menos ergonômico** que tags inline, mas ainda funcional. No código de produção, o wrapper `gemini_tts_service.py` (a criar) vai mapear nossa classificação clínica pra prefixos apropriados:

```python
STYLE_PREFIXES = {
    "routine":    "Say warmly and gently: ",
    "attention":  "Say in a calm but serious tone: ",
    "urgent":     "Say firmly and directly: ",
    "critical":   "Say urgently with clear authority: ",
    "reassuring": "Say gently and reassuringly: ",
}
```

## Próximos passos

1. **Avaliação qualitativa humana**: Alexandre + Murilo escutam os 4 áudios e julgam "soa natural pt-BR geriátrico?"
2. Se sim → próxima iteração testa controle mais granular (multi-speaker dialog, mais vozes)
3. Se não → adiar migração TTS, manter ElevenLabs
