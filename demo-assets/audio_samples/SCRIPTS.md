# Scripts de áudio para ensaio e backup da demo

Grave estes 3 áudios em ambiente silencioso **antes da reunião** para ter cenários confiáveis de demonstração.

**Instrução**: fale em tom natural, pausado, como uma cuidadora que está no plantão. 30-60 segundos cada.

---

## Áudio 1 — Cenário ROTINA (paciente bem)
**Paciente**: Antonia Ferreira Lima (Dona Antonia, Parkinson)
**Resultado esperado**: classification = routine

Fale:

> "É a Joana, plantão da noite. Passando sobre a Dona Antonia Ferreira. Ela passou bem a noite, dormiu tranquila sem despertar. Tomou a Levodopa das onze da noite certinho. No café da manhã aceitou bem o mingau e o chá, comeu tudo. O humor tá estável, conversou comigo de manhã, tá animada. Sem queixas, sem tremor aumentado. Só registrando que tá tudo dentro do normal."

---

## Áudio 2 — Cenário ATENÇÃO (mudança de padrão cognitivo)
**Paciente**: João Oliveira Costa (Seu João, Alzheimer)
**Resultado esperado**: classification = attention

Fale:

> "Oi, é a Joana. Plantão do Seu João Oliveira. Ele tá mais confuso hoje que os últimos dias. De manhã não reconheceu a filha quando ela ligou, isso é novo. Tá pedindo pra ir embora, repetindo o nome da esposa que já faleceu faz anos. A alimentação tá normal, ele comeu bem. O sono ontem à noite ele acordou umas três vezes, levantou da cama, andou pelo quarto. Quero deixar registrado porque acho que ele tá tendo uma piora no quadro."

---

## Áudio 3 — Cenário URGENTE/CRÍTICO (descompensação cardíaca)
**Paciente**: Maria da Silva Santos (Dona Maria, HAS+IC+DM2)
**Resultado esperado**: classification = urgent ou critical

Fale:

> "Joana falando do plantão da noite. Tô com a Dona Maria da Silva. Preciso avisar que ela não quis jantar hoje. E ela tá com falta de ar, eu percebi quando ela foi do banheiro pra cama, parou pra descansar. O joelho direito tá inchado, bem mais que ontem. Medi a temperatura agora, tá trinta e sete e oito. Ela tá mais quieta que o normal. Acho que a gente precisa chamar alguém pra dar uma olhada nela."

---

## Áudio 4 — Cenário CRÍTICO (suspeita de queda + lesão)
**Paciente**: Lúcia Pereira Souza (Dona Lúcia, pós-AVC + FA + varfarina)
**Resultado esperado**: classification = critical (sangramento + anticoagulado)

Fale:

> "Joana aqui. Emergência com a Dona Lúcia Pereira. Ela caiu no banheiro agora a pouco, bateu a cabeça no lado esquerdo. Tá com um galo grande e começou a sangrar um pouco pelo ouvido. Ela tá consciente mas confusa, não tá lembrando que caiu. Ela toma varfarina. Pressão agora tá dezesseis por nove. Preciso de socorro imediato."

---

## Como gravar

No WhatsApp Web ou celular:
1. Abrir conversa com **555189592617** (V6 ConnectaIACare)
2. Segurar botão de áudio
3. Falar os scripts acima
4. Liberar

Para **backup**, gravar em ambiente silencioso usando app de gravação de voz do iPhone/Android e exportar como `.m4a`. Nomear:
- `audio_01_routine_antonia.m4a`
- `audio_02_attention_joao.m4a`
- `audio_03_urgent_maria.m4a`
- `audio_04_critical_lucia.m4a`

Salvar em `demo-assets/audio_samples/` (esta pasta está no `.gitignore` — não vai pro repo público).
