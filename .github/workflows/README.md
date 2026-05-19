# GitHub Actions — ConnectaIACare

## `deploy.yml` — Auto-deploy para produção

Sobe automaticamente toda vez que algo entra em `main` que afeta código
de aplicação. Chama `bash scripts/deploy.sh` na VPS Hostinger via SSH,
valida health endpoint, confirma que workers ficaram com imagem nova.

### Setup inicial (uma vez)

Precisa configurar **2 secrets** em
`https://github.com/iplayconnect/connectaiacare/settings/secrets/actions`:

#### `VPS_SSH_PRIVATE_KEY`

Chave privada (ed25519 ou RSA) que dá acesso a `root@72.60.242.245`.

**Recomendado**: criar uma deploy key dedicada pra GitHub Actions (auditável,
revogável sem mexer no SSH pessoal):

```bash
# No seu Mac
ssh-keygen -t ed25519 -f ~/.ssh/connectaiacare_deploy -N "" \
  -C "github-actions-connectaiacare-$(date +%Y%m%d)"

# Adiciona a chave PÚBLICA na VPS
ssh-copy-id -i ~/.ssh/connectaiacare_deploy.pub root@72.60.242.245
# OU manualmente:
cat ~/.ssh/connectaiacare_deploy.pub
# (copia o output)
ssh root@72.60.242.245 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys'
# (cola o conteúdo da pública e dá Ctrl-D)

# Pega a chave PRIVADA pra colocar no secret
cat ~/.ssh/connectaiacare_deploy
```

Cola o output inteiro de `cat ~/.ssh/connectaiacare_deploy` (incluindo
`-----BEGIN OPENSSH PRIVATE KEY-----` e `-----END OPENSSH PRIVATE KEY-----`)
no secret `VPS_SSH_PRIVATE_KEY` no GitHub.

#### `VPS_HOST_FINGERPRINT`

Fingerprint do host pra evitar prompts "host key verification failed".

```bash
ssh-keyscan -t ed25519 72.60.242.245
```

Copia a linha de saída (algo como `72.60.242.245 ssh-ed25519 AAAA...`) e
cola no secret `VPS_HOST_FINGERPRINT`.

### Trigger paths

Roda só quando algum dos seguintes muda em `main`:

- `backend/**`
- `frontend/**`
- `sofia-service/**`
- `voice-call-service/**`
- `livekit-agent-service/**`
- `docker-compose.yml`
- `scripts/deploy.sh`
- `.github/workflows/deploy.yml`

**Não dispara para**: mudanças puras em `docs/`, `.gitignore`, `README.md`,
arquivos de IDE. Isso economiza minutos do runner e evita rebuilds
desnecessários.

### Disparo manual

Em `https://github.com/iplayconnect/connectaiacare/actions/workflows/deploy.yml`
clica em "Run workflow" → branch main → "Run workflow". Útil pra:

- Forçar redeploy sem novo commit
- Recuperar de falha sem precisar reverter+push
- Testar workflow depois de mudança nele

### Concorrência

`concurrency.group: production-deploy` garante que **só um deploy roda
de cada vez**. Se 3 PRs forem mergeados em 30s, apenas o último na fila
fica esperando (os do meio são cancelados antes de começar). O deploy
em andamento sempre termina (`cancel-in-progress: false`).

### Pegadinha histórica

Workers (`sofia-inbound-worker`, `delivery-worker`) compartilham o
mesmo Dockerfile com `api`. O `deploy.sh` já cuida disso desde o
post-fix de 2026-05-02 (PR #85). O workflow tem um step final
"Sanity check de versão" que imprime as datas de criação dos
containers — se divergirem por horas é sinal de que algo escapou.

### Como revogar acesso

Se a chave vazar ou suspeitar de comprometimento:

```bash
# Opção A: remove da VPS (mais rápido)
ssh root@72.60.242.245 "sed -i '/github-actions-connectaiacare/d' ~/.ssh/authorized_keys"

# Opção B: deleta os secrets no GitHub
# Settings → Secrets and variables → Actions → revogar VPS_SSH_PRIVATE_KEY
```

Toda execução fica auditável em `https://github.com/iplayconnect/connectaiacare/actions`.

---

## Tabela de jobs ativos

| Workflow | Trigger | Job runtime médio |
|---|---|---|
| `deploy.yml` | push em main (paths app) ou manual | ~3-6 min |

(Adicionar aqui novos workflows quando criar.)
