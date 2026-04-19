# ConnectaIACare

> Plataforma integrada de cuidado para idosos e pacientes crônicos.
> Parceria ConnectaIA + Tecnosenior + MedMonitor + Amparo.

## Status
- **Estado**: MVP Sprint (20-24 abril 2026)
- **Meta**: Demo funcional para reunião de sexta (24/04/2026)
- **Vertical inicial**: Geriatria

## Arquitetura
Stack isolada da ConnectaIA produção. Reutiliza padrões e alguns serviços (Sofia Voz) via API.

- **Backend**: Python 3.12 + Flask + Gunicorn
- **Frontend**: Next.js 14 + React + Tailwind + shadcn/ui
- **DB**: PostgreSQL 16 (database `connectaiacare`)
- **Cache**: Redis 7
- **WhatsApp**: Evolution API (instância V6 repointed)
- **STT**: Deepgram nova-2 pt-BR
- **LLM**: Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5
- **Voz**: Sofia Voz (Grok) via API do sofia-service:5030

## Estrutura
```
backend/          API Flask + serviços
frontend/         Next.js dashboard
infra/            Docker, Traefik, nginx configs
scripts/          Utilitários (seed, geração de mocks)
docs/             Documentação do projeto
demo-assets/      Fotos de pacientes + amostras de áudio
```

## Desenvolvimento
Ver `docs/DEVELOPMENT.md`.
