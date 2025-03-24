import logging
import yaml
import requests
from langchain_openai import AzureChatOpenAI
from langchain_community.utilities import RequestsWrapper
from langchain_community.agent_toolkits.openapi.spec import reduce_openapi_spec
import api_planner
from setup_vectorstore import  vector_store_manager
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
            headers = tool_config.header_auth or {}
            body = tool_config.body_auth or {}
            
            # Load and process API spec
            spec_data = self._load_api_spec(tool_config.spec_url)
            if not spec_data:
                return "Failed to load API specification"
            
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