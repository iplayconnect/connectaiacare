---
description: Deploy do ConnectaIACare para a VPS seguindo o fluxo Local → Git → VPS
argument-hint: [service]
---

Execute o fluxo completo de deploy do ConnectaIACare respeitando as regras do CLAUDE.md.

**Argumento opcional `$ARGUMENTS`**: pode ser `api`, `frontend`, ou nada (= ambos).

Passos:

1. **Verifique o estado local**:
   - `git status` — deve estar clean ou ter apenas alterações que o usuário quer deployar
   - Se houver alterações não commitadas, pergunte ao usuário se quer commitar primeiro (não deploye código não-commitado)
   - `git log --oneline -3` — mostrar últimos commits

2. **Testes de sintaxe** em qualquer arquivo Python modificado:
   ```
   python3 -c "import ast; ast.parse(open('<file>').read())"
   ```
   Se falhar, pare e avise o usuário.

3. **Execute `bash scripts/verify.sh`** para garantir que a estrutura está íntegra. Se houver falhas (não warnings), pare.

4. **Push para o remoto**:
   ```
   git push origin main
   ```

5. **Na VPS** (via SSH `root@72.60.242.245`):
   ```
   cd /root/connectaiacare && bash scripts/deploy.sh $ARGUMENTS
   ```

6. **Validar o deploy**:
   - `docker compose logs --tail 30 api` — sem erros
   - `curl https://demo.connectaiacare.com/health` — retorna `{"status":"ok"}`
   - Se houver alguma classification urgent/critical recente, confirmar que foi processada

7. **Reporte ao usuário**:
   - Commit hash deployado
   - Tempo total
   - Links para logs se algo estranho

**Atenção**:
- NUNCA edite arquivo direto na VPS.
- Se `verify.sh` falhar, investigue antes de prosseguir.
- Se o push falhar, pode ser porque o remote está à frente — faça `git pull --rebase origin main` primeiro.
- Se o deploy na VPS falhar, execute `bash scripts/deploy.sh --rollback` (se implementado) ou `git reset --hard <hash_anterior> && docker compose up -d --build`.
