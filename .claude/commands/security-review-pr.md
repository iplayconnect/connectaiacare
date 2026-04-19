---
description: Security review de mudanças não commitadas ou de um PR, usando o checklist do SECURITY.md
argument-hint: [pr-number | diff]
---

Faça uma revisão de segurança das alterações atuais (ou de um PR específico se `$ARGUMENTS` for um número) seguindo o **checklist do SECURITY.md §7** deste projeto.

**Contexto deste projeto**: plataforma de saúde com dados sensíveis (LGPD Art. 11). Consequências de falha de segurança são regulatórias + jurídicas + potencialmente clínicas.

## Processo

1. **Obter o diff**:
   - Se `$ARGUMENTS` for um número de PR: `gh pr diff $ARGUMENTS`
   - Caso contrário: `git diff HEAD` (mudanças não commitadas) + `git diff main..HEAD` (commits no branch atual que não estão em main)

2. **Para cada arquivo modificado, cheque**:

### Input handling
- [ ] Todo input externo (webhook, API, frontend) é validado com Pydantic ou schema explícito
- [ ] Tamanho máximo definido para strings e payloads
- [ ] Tipos verificados (UUID real, não string qualquer)
- [ ] Enums usam allowlist (ex: `classification in {"routine","attention","urgent","critical"}`)

### SQL / Database
- [ ] Todas as queries usam `%s` parametrizado
- [ ] Nenhum f-string ou `.format()` com valor dinâmico em SQL
- [ ] Nomes de tabela/coluna dinâmicos (ORDER BY, etc.) usam allowlist
- [ ] Migrations são idempotentes (`CREATE TABLE IF NOT EXISTS`, `INSERT...ON CONFLICT`)

### LLM / Prompts
- [ ] Input do usuário encapsulado em tag XML-like no prompt (`<transcription>...</transcription>`)
- [ ] System prompt tem "REGRAS INVIOLÁVEIS" contra seguir instruções do payload
- [ ] Output da LLM é validado contra schema (classification ∈ allowlist, etc.)
- [ ] Keywords de emergência (queda, sangramento, AVC, etc.) forçam escalação mesmo se IA classifica baixo
- [ ] Prompt + resposta são logados (mas sem PII em plaintext)

### Authentication / RBAC
- [ ] Endpoint que toca PHI tem `@require_auth`
- [ ] RBAC checa role esperada antes de retornar dados
- [ ] Audit log em `aia_health_audit_chain` antes de retornar PHI

### Subprocess / Filesystem
- [ ] `subprocess.run` usa lista de args (nunca `shell=True` com input do usuário)
- [ ] Uploads de arquivo usam `werkzeug.utils.secure_filename`
- [ ] Caminhos resolvidos com `os.path.abspath` e validados contra diretório permitido

### Logs / Observability
- [ ] Nenhum `print()` — usa `logger.info()` com structlog
- [ ] Dados de paciente logados APENAS como ID, nunca plaintext
- [ ] Transcrição, fotos, embeddings nunca em logs
- [ ] Secrets (chaves API, senhas) nunca em logs

### Secrets
- [ ] Nenhuma string literal de API key, senha, token no código
- [ ] `.env.example` atualizado se adicionou variável, mas sem valor real
- [ ] Nada novo commitado em `.env` (confirmar `.gitignore`)

### Dependencies
- [ ] Pacotes novos em `requirements.txt` ou `package.json` têm versão pinada
- [ ] Pacotes são bem conhecidos (não typo-squat)

### Frontend (se houver mudanças .tsx)
- [ ] Nenhum `dangerouslySetInnerHTML` com conteúdo de usuário
- [ ] Dados sensíveis (PHI) não vão para console.log ou localStorage
- [ ] Todos os fetches incluem `credentials: 'include'` se precisam de auth

### LGPD específico
- [ ] Nova tabela com dados pessoais tem auditoria ligada a `aia_health_audit_chain`
- [ ] Endpoint que retorna PHI é contabilizado em `aia_health_voice_consent_log` (ou log similar de `data_accessed`)
- [ ] Retenção de dados pensada (TTL, cleanup job)

## Formato do relatório

Entregue em markdown:
- **Severidade**: Critical | High | Medium | Low | Info
- Para cada achado:
  - Arquivo:linha
  - O que está errado
  - Por que é um problema (LGPD? Prompt injection? SQL injection?)
  - Correção sugerida (código snippet quando útil)

Termine com resumo: `N findings (Critical: X, High: Y, Medium: Z, Low: W, Info: V)`.

**Se nenhum problema encontrado**: diga explicitamente "✅ Nenhum problema de segurança encontrado no diff" e confirme que checou cada categoria acima.
