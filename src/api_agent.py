import logging
import yaml
import requests
import os
import re
import chainlit as cl
from chainlit import AskUserMessage
from langchain_openai import AzureChatOpenAI
from langchain_community.utilities import RequestsWrapper
from langchain_community.agent_toolkits.openapi.spec import reduce_openapi_spec
import api_planner
from setup_vectorstore import vector_store_manager
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

# Default settings
ALLOW_DANGEROUS_REQUEST = True

class APIAgent:
    """Class to handle API agent functionality"""
    def __init__(self, allow_dangerous_requests=ALLOW_DANGEROUS_REQUEST):
        """Initialize the API agent with an LLM"""
        self.llm = AzureChatOpenAI(api_version="2024-05-01-preview", azure_deployment="gpt-4o")
        self.allow_dangerous_requests = allow_dangerous_requests

    def _should_fake(self, query: str) -> bool:
        """Determine if we should return a simulated response instead of calling the API."""
        keywords = ["how", "example", "usage", "explain"]
        lower_q = query.lower()
        return any(k in lower_q for k in keywords)

    def _fake_response(self, tool_config, spec_data) -> str:
        """Generate a short instructional response instead of calling the API."""
        base_url = spec_data.servers[0]["url"] if spec_data.servers else ""
        example = spec_data.endpoints[0][0] if spec_data.endpoints else ""
        return (
            f"(Simulated response) You can interact with the {tool_config.id} API by"
            f" sending a request like `{example}` to `{base_url}`. "
            f"See {tool_config.spec_url} for full documentation."
        )

    async def _resolve_auth(self, auth: dict) -> dict:
        """Resolve authentication placeholders using env vars or user prompts."""
        resolved = {}
        for key, value in (auth or {}).items():
            placeholders = re.findall(r"{([^}]+)}", value)
            for ph in placeholders:
                stored = cl.user_session.get(ph)
                env_val = stored or os.getenv(ph)
                if not env_val:
                    ask = await AskUserMessage(
                        f"Please provide a value for {ph} (API Key)",
                        timeout=120,
                    ).send()
                    env_val = (ask or {}).get("output") if ask else None
                    if env_val:
                        cl.user_session.set(ph, env_val)
                if env_val:
                    value = value.replace(f"{{{ph}}}", env_val)
            resolved[key] = value
        return resolved
    
    async def execute_query(self, query: str) -> str:
        """Find and use the appropriate API to answer a query"""
        logger.info(f"Finding optimal API tool for: {query}")
        print(f"Finding optimal API tool for: {query}")
        try:
            # Find the best matching tool
            tool_config, score = vector_store_manager.find_tool_for_query(query)
            
            if not tool_config:
                return "No suitable API found for this query"
            
            logger.info(f"Selected API tool: {tool_config.id} with score: {score}")
            print(f"Selected API tool: {tool_config.id} with score: {score}")
            # Initialize environment for the tool
            headers = await self._resolve_auth(tool_config.header_auth or {})
            body = await self._resolve_auth(tool_config.body_auth or {})
            
            # Load and process API spec
            spec_data = self._load_api_spec(tool_config.spec_url)
            if not spec_data:
                return "Failed to load API specification"
            
            # If the query looks instructional, return a simulated response
            if self._should_fake(query):
                return self._fake_response(tool_config, spec_data)

            # Create requests wrapper with headers
            requests_wrapper = RequestsWrapper(headers=headers)

            # Create and run the agent
            agent = api_planner.create_openapi_agent(
                spec_data,
                requests_wrapper,
                self.llm,
                body_wrapper=body,
                allow_dangerous_requests=self.allow_dangerous_requests,
            )

            result = agent.run(query)
            return result
        
        except Exception as e:
            logger.error(f"Error using API tool: {str(e)}")
            return f"Error using API tool: {str(e)}"
    
    def _load_api_spec(self, spec_url: str):
        """Load and reduce an OpenAPI specification"""
        try:
            spec_file = requests.get(spec_url)
            print(spec_file)
            return reduce_openapi_spec(yaml.safe_load(spec_file.text))
        except Exception as e:
            logger.error(f"Error loading API spec: {str(e)}")
            return None

# Create a singleton instance
api_agent_manager = APIAgent() 
