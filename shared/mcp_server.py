import os
import httpx
import logging
from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp.server.fastmcp import FastMCP

# Setup basic logging to stderr so it doesn't pollute stdout (which MCP uses)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
HUB_API_KEY = os.getenv("HUB_API_KEY")
HUB_URL = os.getenv("HUB_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

if not HUB_API_KEY:
    logger.error("Missing HUB_API_KEY")
    exit(1)

HUB_API_URL = f"{HUB_URL}/api/packages"

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

@mcp.tool()
async def read_image(url: str) -> str:
    """Reads an image from the given URL and returns its textual content / description using vision AI."""
    try:
        logger.info(f"Reading image from URL: {url}")
        response = await openai_client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe the content of this image in detail. If there is any text in the image, extract it exactly as written. Return all text and visual content you can identify."
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": url}
                        }
                    ]
                }
            ]
        )
        result = response.choices[0].message.content
        logger.info(f"Image read successfully, response length: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"Error reading image: {e}")
        return f"Error reading image: {str(e)}"


@mcp.tool()
async def read_file(url: str) -> str:
    """Reads a text file from the given URL and returns its content."""
    async with httpx.AsyncClient() as http_client:
        try:
            logger.info(f"Reading file from URL: {url}")
            response = await http_client.get(url, timeout=15.0)
            response.raise_for_status()
            logger.info(f"File read successfully, length: {len(response.text)}")
            return response.text
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return f"Error reading file: {str(e)}"


if __name__ == "__main__":
    # Start the server using stdio
    mcp.run(transport='stdio')
