"""LangChain-powered SQL client for advanced SQL generation and query handling."""

import os
from typing import Dict, Any, List, Optional, Union
from sqlalchemy import create_engine

# Updated LangChain imports
try:
    from langchain_community.agent_toolkits.sql.base import create_sql_agent
    from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
    from langchain_community.utilities import SQLDatabase
    from langchain.agents import AgentType, initialize_agent
    from langchain.memory import ConversationBufferWindowMemory, ConversationSummaryMemory
    from langchain.chains import LLMChain
    from langchain.prompts import PromptTemplate
    from langchain.schema import BaseOutputParser
    from langchain.tools import Tool
    from langchain_community.llms import VLLM
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    print(f"LangChain components not available: {e}")
    LANGCHAIN_AVAILABLE = False
    # Create dummy classes to prevent import errors
    class SQLDatabase: pass
    class SQLDatabaseToolkit: pass
    class ConversationBufferWindowMemory: pass
    class ConversationSummaryMemory: pass
    class LLMChain: pass
    class PromptTemplate: pass
    class BaseOutputParser: pass
    class Tool: pass
    class VLLM: pass

from config import LANGCHAIN_CONFIG, DATABASE_CONFIG, VLLM_CONFIG
from utils.logger import get_logger

logger = get_logger(__name__)


class SQLOutputParser(BaseOutputParser):
    """Custom output parser for SQL queries."""
    
    def parse(self, text: str) -> str:
        """Parse the LLM output to extract clean SQL."""
        import re
        
        # Remove common prefixes and suffixes
        text = text.strip()
        
        # Extract SQL from code blocks
        sql_blocks = re.findall(r'```(?:sql)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if sql_blocks:
            return sql_blocks[0].strip()
        
        # Look for SQL keywords and extract from that point
        sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WITH']
        for keyword in sql_keywords:
            if keyword in text.upper():
                start_idx = text.upper().find(keyword)
                sql_part = text[start_idx:]
                
                # Find end of SQL (semicolon or double newline)
                end_markers = [';', '\n\n', 'LIMIT']
                min_end = len(sql_part)
                for marker in end_markers:
                    if marker in sql_part:
                        marker_pos = sql_part.find(marker)
                        if marker == 'LIMIT':
                            # Include LIMIT clause
                            limit_end = sql_part.find('\n', marker_pos)
                            if limit_end == -1:
                                limit_end = len(sql_part)
                            marker_pos = limit_end
                        min_end = min(min_end, marker_pos + (1 if marker == ';' else 0))
                
                return sql_part[:min_end].strip()
        
        return text.strip()


class LangChainSQLClient:
    """Advanced SQL client using LangChain for intelligent SQL generation and execution."""
    
    def __init__(self, database_uri: str = None, llm_endpoint: str = None):
        """Initialize LangChain SQL client.
        
        Args:
            database_uri: Database connection URI
            llm_endpoint: VLLM server endpoint
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain components not available. Please install required packages.")
            
        self.database_uri = database_uri or self._build_database_uri()
        self.llm_endpoint = llm_endpoint or VLLM_CONFIG['endpoint']
        self.config = LANGCHAIN_CONFIG
        
        # Core components
        self.llm = None
        self.database = None
        self.memory = None
        self.sql_chain = None
        self.agent = None
        self.toolkit = None
        self.output_parser = SQLOutputParser()
        
        # Initialize components
        self._initialize_components()
    
    def _build_database_uri(self) -> str:
        """Build database URI from config."""
        db_path = DATABASE_CONFIG['path']
        if db_path.startswith('sqlite'):
            return db_path
        else:
            return f"sqlite:///{db_path}"
    
    def _initialize_components(self):
        """Initialize all LangChain components."""
        try:
            logger.info("Initializing LangChain SQL client...")
            
            # Initialize LLM
            self._initialize_llm()
            
            # Initialize database
            self._initialize_database()
            
            # Initialize memory
            self._initialize_memory()
            
            # Initialize toolkit and agent
            self._initialize_agent()
            
            logger.info("LangChain SQL client initialized successfully!")
            
        except Exception as e:
            logger.error(f"Failed to initialize LangChain SQL client: {e}")
            raise
    
    def _initialize_llm(self):
        """Initialize the LLM client."""
        try:
            # Try to use VLLM client
            self.llm = VLLM(
                openai_api_key="EMPTY",
                openai_api_base=self.llm_endpoint,
                model_name="llama-3b",
                max_tokens=VLLM_CONFIG['max_tokens'],
                temperature=VLLM_CONFIG['temperature']
            )
            logger.info("VLLM LLM initialized")
            
        except Exception as e:
            logger.warning(f"VLLM not available: {e}, using fallback")
            # Fallback to a mock LLM for demo purposes
            from langchain.llms.fake import FakeListLLM
            self.llm = FakeListLLM(responses=[
                "SELECT * FROM Artist LIMIT 10;",
                "SELECT COUNT(*) FROM Track;",
                "SELECT Name FROM Artist WHERE ArtistId = 1;"
            ])
    
    def _initialize_database(self):
        """Initialize the SQL database connection."""
        try:
            engine = create_engine(self.database_uri)
            self.database = SQLDatabase(
                engine=engine,
                sample_rows_in_table_info=self.config['sql_chain']['sample_rows_in_table_info'],
                custom_table_info=self.config['sql_chain']['custom_table_info']
            )
            logger.info("SQL database connection initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def _initialize_memory(self):
        """Initialize conversation memory."""
        memory_config = self.config['memory']
        memory_type = memory_config['type']
        
        try:
            if memory_type == 'conversation_buffer_window':
                self.memory = ConversationBufferWindowMemory(
                    k=memory_config['k'],
                    return_messages=memory_config['return_messages'],
                    ai_prefix=memory_config['ai_prefix'],
                    human_prefix=memory_config['human_prefix']
                )
            elif memory_type == 'conversation_summary':
                self.memory = ConversationSummaryMemory(
                    llm=self.llm,
                    max_token_limit=memory_config['max_token_limit'],
                    return_messages=memory_config['return_messages']
                )
            else:
                # Default to buffer memory
                from langchain.memory import ConversationBufferMemory
                self.memory = ConversationBufferMemory(
                    return_messages=memory_config['return_messages']
                )
            
            logger.info(f"Memory initialized: {memory_type}")
            
        except Exception as e:
            logger.error(f"Failed to initialize memory: {e}")
            # Continue without memory
            self.memory = None
    
    def _initialize_agent(self):
        """Initialize SQL agent with toolkit."""
        try:
            # Create SQL database toolkit
            self.toolkit = SQLDatabaseToolkit(
                db=self.database,
                llm=self.llm
            )
            
            # Get tools from toolkit
            tools = self.toolkit.get_tools()
            
            # Add custom tools
            custom_tools = self._create_custom_tools()
            tools.extend(custom_tools)
            
            # Create agent using the new approach
            agent_config = self.config['agent']
            self.agent = initialize_agent(
                tools=tools,
                llm=self.llm,
                agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                memory=self.memory,
                verbose=agent_config['verbose'],
                max_iterations=agent_config['max_iterations'],
                early_stopping_method=agent_config['early_stopping_method'],
                handle_parsing_errors=agent_config['handle_parsing_errors']
            )
            
            logger.info("SQL agent and toolkit initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            self.agent = None
            self.toolkit = None
    
    def _create_custom_tools(self) -> List[Tool]:
        """Create custom tools for the agent."""
        tools = []
        
        # Schema inspector tool
        if self.config['tools']['custom_tools']['schema_inspector']:
            schema_tool = Tool(
                name="schema_inspector",
                description="Get detailed information about database schema, tables, and columns",
                func=self._inspect_schema
            )
            tools.append(schema_tool)
        
        # Query explainer tool
        if self.config['tools']['custom_tools']['query_explainer']:
            explainer_tool = Tool(
                name="query_explainer",
                description="Explain what a SQL query does in plain English",
                func=self._explain_query
            )
            tools.append(explainer_tool)
        
        return tools
    
    def _inspect_schema(self, table_name: str = None) -> str:
        """Inspect database schema."""
        try:
            if table_name:
                return self.database.get_table_info_no_throw([table_name])
            else:
                return self.database.get_table_info()
        except Exception as e:
            return f"Error inspecting schema: {str(e)}"
    
    def _explain_query(self, query: str) -> str:
        """Explain a SQL query in plain English."""
        try:
            # Create a prompt for query explanation
            explanation_prompt = PromptTemplate(
                input_variables=["query"],
                template="Explain this SQL query in plain English: {query}"
            )
            
            explanation_chain = LLMChain(llm=self.llm, prompt=explanation_prompt)
            return explanation_chain.run(query=query)
        except Exception as e:
            return f"Error explaining query: {str(e)}"
    
    def generate_sql(self, natural_language_query: str, use_agent: bool = True) -> str:
        """Generate SQL from natural language using LangChain.
        
        Args:
            natural_language_query: Natural language question
            use_agent: Whether to use agent-based approach
            
        Returns:
            Generated SQL query
        """
        try:
            if use_agent and self.agent:
                # Use agent approach for more intelligent handling
                response = self.agent.run(natural_language_query)
                
                # Extract SQL from agent response
                sql_query = self.output_parser.parse(response)
                return sql_query
            
            else:
                # Simple SQL generation using database tools
                if self.toolkit:
                    tools = self.toolkit.get_tools()
                    # Use the query tool directly
                    for tool in tools:
                        if 'query' in tool.name.lower():
                            return tool.run(natural_language_query)
                
                raise Exception("No SQL generation method available")
                
        except Exception as e:
            logger.error(f"SQL generation error: {e}")
            raise
    
    def execute_sql_with_chain(self, natural_language_query: str) -> Dict[str, Any]:
        """Execute SQL query using LangChain with full pipeline.
        
        Args:
            natural_language_query: Natural language question
            
        Returns:
            Dictionary with query, result, and metadata
        """
        try:
            if self.agent:
                # Use agent which handles generation and execution
                result = self.agent.run(natural_language_query)
                
                return {
                    'query': 'Generated by agent',
                    'result': result,
                    'intermediate_steps': [],
                    'tokens_used': 0
                }
            else:
                raise Exception("Agent not available")
                
        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            raise
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get comprehensive database information."""
        try:
            info = {
                'dialect': self.database.dialect,
                'table_names': self.database.get_usable_table_names(),
                'table_info': self.database.get_table_info(),
                'database_uri': self.database_uri
            }
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting database info: {e}")
            return {}
    
    def add_memory_context(self, human_input: str, ai_output: str):
        """Add conversation to memory."""
        if self.memory:
            try:
                self.memory.save_context(
                    {"input": human_input},
                    {"output": ai_output}
                )
            except Exception as e:
                logger.error(f"Error saving to memory: {e}")
    
    def get_memory_context(self) -> str:
        """Get current memory context."""
        if self.memory:
            try:
                return self.memory.buffer
            except Exception as e:
                logger.error(f"Error getting memory context: {e}")
        return ""
    
    def reset_memory(self):
        """Reset conversation memory."""
        if self.memory:
            try:
                self.memory.clear()
                logger.info("Memory reset")
            except Exception as e:
                logger.error(f"Error resetting memory: {e}")
    
    def explain_database_schema(self) -> str:
        """Generate a natural language explanation of the database schema."""
        try:
            schema_info = self.get_database_info()
            table_info = schema_info.get('table_info', '')
            
            explanation_prompt = PromptTemplate(
                input_variables=["schema"],
                template="Explain this database schema in plain English: {schema}"
            )
            
            explanation_chain = LLMChain(llm=self.llm, prompt=explanation_prompt)
            return explanation_chain.run(schema=table_info)
            
        except Exception as e:
            logger.error(f"Error explaining schema: {e}")
            return f"Error explaining schema: {str(e)}"
    
    def close(self):
        """Clean up resources."""
        try:
            if self.database:
                # Close database connections
                if hasattr(self.database, '_engine'):
                    self.database._engine.dispose()
            
            logger.info("LangChain SQL client closed")
            
        except Exception as e:
            logger.error(f"Error closing client: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Example usage and testing
if __name__ == "__main__":
    # Test the LangChain SQL client
    try:
        if LANGCHAIN_AVAILABLE:
            client = LangChainSQLClient()
            
            # Test database info
            print("Database Info:")
            print(client.get_database_info())
            
            # Test SQL generation
            query = "Show me all artists"
            sql = client.generate_sql(query)
            print(f"\nGenerated SQL for '{query}': {sql}")
            
        else:
            print("LangChain not available for testing")
            
    except Exception as e:
        print(f"Test error: {e}") 