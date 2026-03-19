import contextlib
import sys
import os
import httpx
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send
from simple_salesforce import Salesforce
import uvicorn

# ─── Inicializa o servidor MCP ────────────────────────────────────────────────
mcp = FastMCP("salesforce-org")


# ─── Helper: conecta à org Salesforce ────────────────────────────────────────
def get_sf_client() -> Salesforce:
    return Salesforce(
        username=os.environ["SF_USERNAME"],
        password=os.environ["SF_PASSWORD"],
        security_token=os.environ["SF_SECURITY_TOKEN"],
        domain=os.getenv("SF_DOMAIN", "login"),  # "test" para sandboxes
    )


# ─── FERRAMENTAS EXPOSTAS AO LLM ─────────────────────────────────────────────

@mcp.tool()
async def run_soql_query(soql: str) -> str:
    """Executa uma query SOQL na org Salesforce e retorna os resultados."""
    sf = get_sf_client()
    result = sf.query_all(soql)
    records = result.get("records", [])
    if not records:
        return "Nenhum resultado encontrado."
    lines = []
    for r in records:
        r.pop("attributes", None)
        lines.append(str(r))
    return f"{result['totalSize']} registro(s):\n" + "\n".join(lines)


@mcp.tool()
async def get_org_limits() -> str:
    """Retorna os limites de uso da org Salesforce (API calls, storage, etc.)."""
    sf = get_sf_client()
    limits = sf.limits()
    lines = []
    for key, value in limits.items():
        max_val = value.get("Max", "N/A")
        remaining = value.get("Remaining", "N/A")
        lines.append(f"{key}: {remaining} restantes de {max_val}")
    return "\n".join(lines)


@mcp.tool()
async def list_apex_classes() -> str:
    """Lista todas as Apex Classes da org com seus status."""
    sf = get_sf_client()
    result = sf.query(
        "SELECT Id, Name, Status, LengthWithoutComments FROM ApexClass ORDER BY Name"
    )
    records = result.get("records", [])
    if not records:
        return "Nenhuma Apex Class encontrada."
    return "\n".join(
        f"- {r['Name']} | Status: {r['Status']} | Tamanho: {r['LengthWithoutComments']} chars"
        for r in records
    )


@mcp.tool()
async def list_flows() -> str:
    """Lista todos os Flows ativos da org."""
    sf = get_sf_client()
    result = sf.query(
        "SELECT Id, ApiName, Label, Status, ProcessType FROM Flow ORDER BY Label"
    )
    records = result.get("records", [])
    if not records:
        return "Nenhum Flow encontrado."
    return "\n".join(
        f"- {r['Label']} ({r['ApiName']}) | Tipo: {r['ProcessType']} | Status: {r['Status']}"
        for r in records
    )


@mcp.tool()
async def trigger_github_deploy(
    branch: str,
    org_alias: str,
    source_path: str = "force-app/main/default",
    check_only: str = "false",
) -> str:
    """
    Dispara um workflow no GitHub Actions para fazer deploy na Salesforce.

    branch: branch do repositório (ex: 'main', 'staging')
    org_alias: ambiente alvo definido nos secrets (ex: 'production', 'sandbox')
    source_path: caminho do componente no repositório (ex: 'force-app/main/default/classes')
    check_only: 'true' para validar sem deployar de verdade, 'false' para deploy real
    """
    github_token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPO"]  # ex: "minha-empresa/salesforce-projeto"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/deploy.yml/dispatches",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "ref": branch,
                "inputs": {
                    "org_alias": org_alias,
                    "source_path": source_path,
                    "check_only": check_only,
                },
            },
        )

    if response.status_code == 204:
        return (
            f"✅ Deploy disparado com sucesso!\n"
            f"Branch: {branch} → Org: {org_alias}\n"
            f"Componente: {source_path}\n"
            f"Check only: {check_only}\n"
            f"Acompanhe em: https://github.com/{repo}/actions"
        )
    else:
        return f"❌ Erro ao disparar deploy: {response.status_code} - {response.text}"


@mcp.tool()
async def get_latest_deploy_status() -> str:
    """Retorna o status do último workflow de deploy no GitHub Actions."""
    github_token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPO"]

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com/repos/{repo}/actions/workflows/deploy.yml/runs?per_page=1",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    if response.status_code != 200:
        return f"❌ Erro ao buscar status: {response.text}"

    runs = response.json().get("workflow_runs", [])
    if not runs:
        return "Nenhum deploy encontrado."

    run = runs[0]
    return (
        f"📋 Último deploy:\n"
        f"Status: {run['status']} | Conclusão: {run.get('conclusion', 'em andamento')}\n"
        f"Branch: {run['head_branch']}\n"
        f"Iniciado em: {run['created_at']}\n"
        f"Link: {run['html_url']}"
    )


# ─── Suporte a HTTP/SSE ───────────────────────────────────────────────────────
def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    sse = SseServerTransport("/messages/")
    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        event_store=None,
        json_response=True,
        stateless=True,
    )

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream, write_stream, mcp_server.create_initialization_options()
            )

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            print("Salesforce MCP iniciado!")
            try:
                yield
            finally:
                print("Salesforce MCP encerrando...")

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/mcp", app=handle_streamable_http),
            Mount("/messages/", app=sse.handle_post_message),
        ],
        lifespan=lifespan,
    )


# ─── Entry point ─────────────────────────────────────────────────────────────
def main():
    import argparse

    mcp_server = mcp._mcp_server
    parser = argparse.ArgumentParser(description="Salesforce Org MCP Server")
    parser.add_argument("--http", action="store_true", help="Usar HTTP/SSE em vez de STDIO")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3001)
    args = parser.parse_args()

    if args.http:
        app = create_starlette_app(mcp_server, debug=True)
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
