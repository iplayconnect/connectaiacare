# ConnectaIACare — Pitch Deck

> **Uso**: formato markdown pronto para conversão a PPTX/Keynote/Google Slides.
> **Duração alvo**: 15-20 minutos + Q&A.
> **Audiência**: Murilo (Tecnosenior + MedMonitor), Vinicius (Amparo), e futuros investidores.

---

## Slide 1 — Capa

### ConnectaIACare
**O hospital vai até o paciente.**

Plataforma de cuidado integrado com Inteligência Artificial para idosos e pacientes crônicos.

*Uma parceria ConnectaIA · Tecnosenior · MedMonitor · Amparo*

Abril 2026

---

## Slide 2 — O problema

A jornada do paciente não termina na alta hospitalar — mas o cuidado, sim.

- **72% das reinternações** em idosos acontecem por falhas de adesão ou detecção tardia de sinal de alerta em casa.
- **Equipes médicas perdem visibilidade** no período mais crítico (primeiros 30 dias pós-alta).
- **Cuidadores sobrecarregados** registram pouco, registram mal, ou não registram.
- **Famílias vivem na ansiedade** sem saber como está o familiar entre consultas.
- **O cuidado atual é reativo.** Alguém tem uma crise, alguém chama o SAMU, alguém interna. Repete-se o ciclo.

> O Brasil tem 31 milhões de idosos hoje. Em 2040 serão 57 milhões. Nosso sistema de saúde não comporta esse crescimento com a lógica atual.

---

## Slide 3 — Nossa visão

**Transformar a casa do paciente em uma extensão do hospital — com discrição, inteligência e humanidade.**

Três camadas integradas:
1. **Ambiente inteligente** — sensores monitoram queda, gás, movimento, temperatura.
2. **Dados clínicos contínuos** — dispositivos medem pressão, glicemia, SpO₂, peso.
3. **Assistente 24h** — IA conversa, orienta, alerta e aprende a história de cada paciente.

*Tudo integrado via WhatsApp — o aplicativo que cuidador, paciente e família já usam.*

**Não substituímos o médico. Somos os olhos, ouvidos e memória da equipe clínica dentro da casa do paciente.**

---

## Slide 4 — O mundo já está fazendo isso

| Região | Quem | O que |
|--------|------|-------|
| **EUA** | **Sensi.ai** — 80% das principais redes de home care dos EUA | Monitoramento de idosos via áudio passivo 24/7. ROI documentado: +88% clientela, +50% receita, +85% horas faturáveis |
| **EUA** | Hippocratic AI (~US$ 500M de funding) | LLM vertical saúde para cuidado pós-alta |
| **EUA** | Current Health (adquirida pela Best Buy Health) | Hospital-at-home com wearables + plataforma |
| **EUA** | Biofourmis | RPM + digital therapeutics com FDA approval |
| **EUA** | Anthropic — lançou **Claude for Healthcare** em jan/2026 | Substrato de IA com conectores HIPAA + Agent Skills para FHIR + integração Apple Health / Android Health Connect — **valida mercado e fornece infra pronta** |
| **China** | Tsinghua AI Hospital | 14 médicos virtuais de IA em hospital-piloto |
| **China** | Ping An Good Doctor | 400M+ usuários em plataforma verticalizada |
| **Europa** | Ada Health, Corti, Nabla | Triagem, emergência, documentação clínica |

**Brasil**: nenhum player integra casa + IoT + IA + prontuário + cuidador em português nativo com parceiros locais. **Janela de 2-3 anos para liderar** antes que players globais localizem.

**Leitura desse quadro**: o mercado global está validado. O maior fabricante de modelos de IA do mundo investiu em healthcare vertical. Sensi.ai prova que o modelo B2B para home care converte e escala. Nossa tese não é especulativa — é replicar com diferenciais locais.

---

## Slide 5 — A equipe certa, no momento certo

### ConnectaIA
Infraestrutura de IA vertical em saúde em produção. Multi-tenant, orquestração de agentes especializados, voz bidirecional conversacional natural, integração nativa com WhatsApp, roteador de modelos de raciocínio de última geração, biometria de voz de produção, conectores padronizados para integrações externas. **Já roda 24/7 em clientes pagantes.**

### Tecnosenior
10+ anos em tele-assistência geriátrica. SPAs e residências com sensores instalados. Central humana 24h. **Parceria existente com ConnectaIA (SOS + Queda).**

### MedMonitor
Plataforma homologada de aferição de sinais vitais. Dispositivos clinicamente validados em uso real.

### Amparo
Atenção primária digital em escala. Monitoramento de pacientes crônicos.

*Quatro especialidades, um produto. Fortemente complementares.*

---

## Slide 6 — Como funciona (hoje, MVP geriátrico)

```
Cuidador grava áudio WhatsApp
            ↓
Transcrição neural em pt-BR clinicamente correto
            ↓
Extração estruturada: paciente + sintomas + medicações
            ↓
Identificação do paciente na base (fuzzy matching por nome)
            ↓
WhatsApp responde com foto + nome para confirmação
            ↓
Cuidador confirma SIM
            ↓
Motor de raciocínio clínico analisa o relato contextualizado
com histórico do paciente + condições conhecidas + medicações
            ↓
Classifica: ROTINA | ATENÇÃO | URGENTE | CRÍTICO
            ↓
Se urgente/crítico: ligação proativa de voz natural ao familiar
            ↓
Equipe médica recebe no painel web em tempo real
```

**Tempo total**: < 45 segundos do áudio até resposta ao cuidador.

---

## Slide 7 — Diferenciais

1. **Arquitetura agêntica por design** — não é um chatbot médico, é um ecossistema onde múltiplos agentes especializados colaboram invisivelmente por baixo de cada interação: triagem, raciocínio clínico com consulta a ferramentas (vitais, medicações, histórico), comunicação adaptativa, compliance automático. O cuidador só manda um áudio — a plataforma orquestra o resto.
2. **IA vertical em saúde em português clinicamente correto** — adaptada para protocolos geriátricos e terminologia médica brasileira, não IA genérica.
3. **WhatsApp-first** — zero fricção de adoção. Ninguém precisa instalar app.
4. **Compliance CFM 2.314/2022** — IA apoia, médico decide. Juridicamente defensável.
5. **Auditoria imutável de próxima geração** — cadeia criptográfica com ancoragem pública, sem os problemas de blockchain pleno para LGPD.
6. **Motor de interações medicamentosas** — cruza prescrição com relatos e alerta automaticamente.
7. **Agente de voz conversacional 24h** — ligação natural com familiares e equipe, tom geriátrico.
8. **HL7 FHIR R4 nativo** — qualquer hospital do mundo integra sem custo de transformação.
9. **Biometria de voz** — identifica cuidador mesmo com aparelho compartilhado.
10. **Cruzamento sintoma × vital × histórico** — IA cruza relato subjetivo do cuidador com sinais vitais objetivos (MedMonitor) e histórico longitudinal para gerar alertas que nenhum concorrente global faz hoje.

---

## Slide 8 — Roadmap (18 meses)

| Fase | Prazo | Entrega |
|------|-------|---------|
| **MVP Geriatria** | Abril 2026 (sexta) | Relato cuidador + análise + classificação (demo funcional) |
| **Piloto SPA** | Maio-Jun 2026 | 10 idosos em SPA Tecnosenior, validação real |
| **Integração MedMonitor** | Jul-Set 2026 | Sinais vitais contínuos entram na análise |
| **Piloto Amparo** | Ago-Out 2026 | Crônicos em casa via atenção primária digital |
| **Adesivos monitoramento contínuo** | Q4 2026 | Evolução para patch wearable (ECG + SpO₂ 24/7) |
| **Hospital-at-Home** | 2027 | Modelo de reembolso via operadoras de saúde |
| **Expansão verticais** | 2027 | Oncologia, cardiologia, pós-operatório |

---

## Slide 9 — Modelo de negócio

### Vertical Geriatria (foco inicial)
- **B2B2C**: SPAs/ILPIs pagam R$ 80-150 por idoso/mês.
- **Margem**: ~80% (LLM é custo marginal baixo com cache).

### Vertical Crônicos (Amparo)
- **B2B**: atenção primária paga por paciente acompanhado.
- **R$ 50-120/paciente/mês** conforme pacote de monitoramento.

### Vertical Hospital-at-Home (futuro)
- **Reembolso via operadora** (ANS 465/2021 já cobre home care).
- **R$ 300-800/paciente/mês** com dispositivos inclusos.

### TAM Brasil
- Geriatria institucional: ~R$ 1,2 bi/ano.
- Crônicos em casa: ~R$ 12-30 bi/ano.
- Hospital-at-Home: ~R$ 8 bi/ano em 5 anos.

---

## Slide 10 — Próximos passos

**Imediatos (próximos 30 dias):**
1. Formalização NDA + Carta de Intenções entre as 4 partes.
2. Piloto SPA Tecnosenior: 10 idosos, 4 semanas de validação.
3. Integração técnica MedMonitor (API).
4. DPIA conjunta (Relatório de Impacto LGPD).

**90 dias:**
5. Piloto Amparo: 20 pacientes crônicos.
6. Primeira rodada de ajustes de produto com feedback clínico real.
7. Definição da estrutura societária final (JV vs contratos).

**12 meses:**
8. 200+ idosos monitorados em rede Tecnosenior.
9. 500+ pacientes crônicos em Amparo.
10. Primeiros contratos hospital-at-home via operadoras.

---

*Construindo juntos o futuro do cuidado no Brasil.*

**ConnectaIACare — contato: [email do Alexandre]**
