# salesforce-org-mcp

MCP server para pipelines de orgs Salesforce, integrado com GitHub Actions.

## Ferramentas disponíveis

| Ferramenta | Descrição |
|---|---|
| `run_soql_query` | Executa qualquer query SOQL na org |
| `get_org_limits` | Mostra limites de API, storage, etc. |
| `list_apex_classes` | Lista todas as Apex Classes com status |
| `list_flows` | Lista todos os Flows ativos |
| `trigger_github_deploy` | Dispara deploy via GitHub Actions |
| `get_latest_deploy_status` | Retorna o status do último deploy |

## Pré-requisitos

- Python 3.10+
- Docker (opcional)
- Conta Salesforce com Security Token
- GitHub Token com permissões `repo` e `workflow`

## Instalação

```bash
git clone https://github.com/JeffOdev/salesforce-org-mcp
cd salesforce-org-mcp
pip install -e .
```

## Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `SF_USERNAME` | Email da conta Salesforce |
| `SF_PASSWORD` | Senha da conta Salesforce |
| `SF_SECURITY_TOKEN` | Token de segurança da org |
| `SF_DOMAIN` | `login` para produção, `test` para sandbox |
| `GITHUB_TOKEN` | Personal Access Token do GitHub |
| `GITHUB_REPO` | Repositório no formato `owner/repo` |

## Configuração do Claude Desktop

Edite o arquivo `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "salesforce-org": {
      "command": "salesforce-org-mcp",
      "env": {
        "SF_USERNAME": "seu@email.com",
        "SF_PASSWORD": "SuaSenha123",
        "SF_SECURITY_TOKEN": "SeuToken",
        "SF_DOMAIN": "login",
        "GITHUB_TOKEN": "ghp_SeuToken",
        "GITHUB_REPO": "JeffOdev/salesforce-org-mcp"
      }
    }
  }
}
```

## Secrets do GitHub

Adicione em `Settings → Secrets → Actions`:

| Secret | Como obter |
|---|---|
| `SF_SFDX_URL_SANDBOX` | `sf org display --verbose --target-org <alias> \| grep "Sfdx Auth Url"` |
| `SF_SFDX_URL_PRODUCTION` | Mesmo comando, para a org de produção |

## Rodando com Docker

```bash
docker build -t salesforce-org-mcp .

docker run --rm -i \
  -e SF_USERNAME=seu@email.com \
  -e SF_PASSWORD=SuaSenha \
  -e SF_SECURITY_TOKEN=SeuToken \
  -e GITHUB_TOKEN=ghp_SeuToken \
  -e GITHUB_REPO=JeffOdev/salesforce-org-mcp \
  salesforce-org-mcp
```

## Debugando o MCP

```bash
npx @modelcontextprotocol/inspector
```

Conecte usando STDIO com o comando `salesforce-org-mcp`.

## Fluxo completo

```
Você pede ao Claude Desktop
         ↓
Claude chama trigger_github_deploy()
         ↓
MCP local dispara o workflow via GitHub API
         ↓
GitHub Actions roda na nuvem (grátis)
  ├── Autentica na Salesforce
  ├── Valida o componente
  ├── Faz o deploy
  └── Roda os testes Apex
         ↓
Claude chama get_latest_deploy_status()
         ↓
Você recebe o resultado ✅ ou ❌
```

## Licença

MIT
