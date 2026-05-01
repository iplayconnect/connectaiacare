# Carta para Henrique — Revisão clínica do classificador

> Texto pra Alexandre encaminhar pro Henrique assim que o user dele
> estiver criado e a página estiver no ar.

---

Henrique,

Preciso de você como referência clínica numa coisa importante:
**validar a "régua" que a Sofia usa pra classificar relatos de
cuidadores**. Toma 30-45 min, e é o que destrava o classificador
pra ir pra produção no piloto.

## Por quê isso importa

Quando o cuidador relata algo no WhatsApp ou no app —
"Dona Maria não jantou e está reclamando do estômago" — a Sofia
precisa decidir, em milissegundos, se é:

- **relato_geral** — informativo, sem ação clínica
- **cuidado_higiene** — banho, troca, curativo, etc.
- **alimentacao_hidratacao**
- **medicacao** — tomou / não tomou / reagiu
- **sinal_vital** — PA, glicemia, etc.
- **intercorrencia** — queda, perda de consciência, evento agudo
- **sintoma_novo** — dor, mal-estar, mudança de comportamento
- **apoio_emocional** — cuidador exausto, paciente triste

A categoria define se Sofia escala pro médico, dispara alerta crítico,
registra em silêncio ou pede mais contexto. **Errar aqui é o que mais
machuca**: classificar uma queda como "relato geral" é grave;
classificar uma reclamação banal como "intercorrência" gera fadiga
de alarme.

## O que você precisa fazer

Eu treinei o classificador num corpus de casos. A maioria foi rotulada
por LLM (DeepSeek V4-Pro). Antes desse corpus virar nosso "padrão-ouro"
de avaliação, **um clínico precisa olhar caso a caso**.

Os casos limítrofes são do tipo:

> "Tomou o remédio às 8h mas reclamou que ficou enjoado"
>      → medicacao? sintoma_novo? os dois?

> "Hoje ele recusou o banho de novo, terceira vez na semana"
>      → cuidado_higiene? sintoma_novo (mudança de comportamento)?

> "Bebeu pouca água hoje, urinou bem escuro"
>      → alimentacao_hidratacao? sinal_vital (sinal de desidratação)?

São esses que precisam do seu olho.

## Passo a passo

1. **Você vai receber por WhatsApp** o link de definição de senha
   (o sistema da ConnectaIACare manda link de reset por Zap, não email).
   Define a sua senha de primeiro acesso.

2. **Entra na plataforma** e clica em "Revisão · Corpus" no menu lateral
   (à esquerda). Funciona bem no celular também.

3. **A tela mostra UM caso por vez**:
   - O texto do relato (já vem em destaque)
   - 8 botões — você escolhe a categoria que faz sentido clínico
   - Já vem **pré-selecionada** a sugestão do LLM. Se concordar, só clica
     em "Salvar e ir pro próximo". Se discordar, escolhe outra antes.
   - Campo opcional de severidade (rotina/atenção/urgente/crítico)
   - Campo livre de justificativa — escreva uma linha sempre que
     marcar algo "não-óbvio". Ex: *"marquei como sintoma_novo porque
     recusa repetida pode ser sinal de delirium incipiente"*.

4. **Botão "Passar"** se você não souber decidir agora — o caso volta
   pra fila e aparece pra outro revisor (ou pra você de novo depois).

5. Você pode **parar a qualquer hora**. O sistema lembra onde você estava
   e te mostra o próximo pendente quando voltar.

6. Quando terminar, eu rodo o classificador novamente contra o corpus
   revisado e te mando o resultado (precisão, recall, F1 por categoria).

## Sobre as categorias

Algumas dicas práticas que conversamos:

- **Hierarquia em conflito**: se um relato cabe em duas, prefira a
  mais específica e clinicamente acionável. *"Caiu mas não bateu a
  cabeça"* → `intercorrencia` (não `relato_geral`), porque queda
  exige protocolo independente do desfecho.
- **Sinal vital ≠ medição**: "tomei a pressão, deu 130x80" é
  `sinal_vital`. "Está com tontura" é `sintoma_novo` (mesmo que
  você suspeite de hipertensão, a Sofia não pode inferir isso aqui).
- **Medicação engloba reação**: "tomou losartana e ficou tonto" é
  `medicacao` (efeito adverso é informação sobre o medicamento). Mas
  "está tonto" sozinho é `sintoma_novo`.
- **Cuidado vs. higiene**: troca de fralda, banho, curativo,
  hidratação da pele → `cuidado_higiene`. Já alimentar, dar de beber
  → `alimentacao_hidratacao`.
- **Recusa repetida**: pode ser `sintoma_novo` quando indica mudança
  de comportamento clinicamente relevante (depressão, delirium,
  declínio funcional). Você decide se é forte o suficiente.

Não tem resposta "certa" pra todos os casos — onde houver dúvida real,
escreva sua justificativa e eu vou usar isso pra documentar o critério.

## Prazo

Não tem urgência cega — mas seria bom fechar até **[ALEXANDRE: COLOCAR DATA]**.
Sem essa validação, o classificador continua rodando com a "versão
Alexandre", que é boa mas não tem chancela clínica.

Qualquer dúvida, me chama no Zap.

Abraço,
Alexandre
