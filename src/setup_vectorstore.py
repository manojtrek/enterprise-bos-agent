from typing import Optional, Dict, List
from pydantic import BaseModel
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
import logging
import yaml
import os
from pathlib import Path

from model.tokenrequest import ToolConfig

# Set up logging
logger = logging.getLogger(__name__)
class VectorStoreManager:
    """Class to manage the vector store for API tools"""
    
    def __init__(self, config_path=None):
        self._vector_store = None
        self.embeddings = OpenAIEmbeddings()
        self.config_path = config_path or Path(__file__).parent / "config" / "tools.yaml"
    
    def get_vector_store(self):
        """Get or initialize the vector store"""
        if self._vector_store is None:
            self._initialize_vector_store()
        return self._vector_store
    
    def _initialize_vector_store(self):
        """Initialize the vector store with tool configurations"""
        # Tool configurations
        tool_configs = self._load_tool_configs()
        
        # Create documents for each tool with descriptions
        documents = []
        metadatas = []
        
        for config in tool_configs:
            documents.append(config.description)
            metadatas.append(config.dict())
        
        # Create FAISS vector store (in-memory)
        self._vector_store = FAISS.from_texts(
            texts=documents,
            embedding=self.embeddings,
            metadatas=metadatas
        )
    
    def _load_tool_configs(self) -> List[ToolConfig]:
        """Load tool configurations from YAML file"""
        # Check if config file exists
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as file:
                    config_data = yaml.safe_load(file)
                    
                tool_configs = []
                for tool_data in config_data.get('tools', []):
                    tool_configs.append(ToolConfig(**tool_data))
                
                if tool_configs:
                    logger.info(f"Loaded {len(tool_configs)} tool configurations from {self.config_path}")
                    return tool_configs
            except Exception as e:
                logger.error(f"Error loading tool configurations from {self.config_path}: {str(e)}")
        
        # Fallback to hardcoded configuration if file doesn't exist or loading fails
        logger.warning(f"Using hardcoded tool configurations as fallback")
        return [
            ToolConfig(
                id="Client Engagements",
                spec_url="http://localhost:8000/openapi.json",
                description="API to manage and retrieve client engagement records.",
                header_auth={}
            )
        ]
    
    def find_tool_for_query(self, query: str, k: int = 1):
        """Find the most suitable tool for a given query"""
        print(f"Finding tool for query: {query}")
        vector_store = self.get_vector_store()
        results = vector_store.similarity_search_with_score(query, k=k)
        
        if not results:
            return None, None
        
        doc, score = results[0]
        tool_config = ToolConfig(**doc.metadata)
        
        return tool_config, score

# Create a singleton instance for easy import
vector_store_manager = VectorStoreManager()