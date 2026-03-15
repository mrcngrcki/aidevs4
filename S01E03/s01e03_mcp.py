import os
import httpx
import logging
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Setup basic logging to stderr so it doesn't pollute stdout (which MCP uses)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
HUB_API_KEY = os.getenv("HUB_API_KEY")

if not HUB_API_KEY:
    logger.error("Missing HUB_API_KEY")
    exit(1)

HUB_API_URL = "https://hub.ag3nts.org/api/packages"

# Initialize FastMCP server
mcp = FastMCP("Packages Provider")

async def call_external_api(payload: dict) -> dict:
    async with httpx.AsyncClient() as http_client:
        try:
            logger.info(f"Calling external API with payload: {payload}")
            response = await http_client.post(HUB_API_URL, json=payload, timeout=10.0)
            res_json = response.json()
            return res_json
        except Exception as e:
            logger.error(f"Error calling external API: {e}")
            return {"error": str(e)}

@mcp.tool()
async def check_package(packageid: str) -> str:
    """Checks the status and location of a package."""
    payload = {
        "apikey": HUB_API_KEY,
        "action": "check",
        "packageid": packageid
    }
    res = await call_external_api(payload)
    import json
    return json.dumps(res)

@mcp.tool()
async def redirect_package(packageid: str, destination: str, code: str) -> str:
    """Redirects a package to a new destination."""
    payload = {
        "apikey": HUB_API_KEY,
        "action": "redirect",
        "packageid": packageid,
        "destination": destination,
        "code": code
    }
    res = await call_external_api(payload)
    import json
    return json.dumps(res)

if __name__ == "__main__":
    # Start the server using stdio
    mcp.run(transport='stdio')
