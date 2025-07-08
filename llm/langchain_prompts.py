"""Advanced prompt management with few-shot learning for SQL generation."""

from typing import Dict, Any, List, Optional
from langchain.prompts import PromptTemplate, FewShotPromptTemplate

from config import LANGCHAIN_CONFIG
from utils.logger import get_logger

logger = get_logger(__name__)


class SimpleLengthBasedSelector:
    """Simple length-based example selector for few-shot prompting."""
    
    def __init__(self, examples: List[Dict[str, str]], max_length: int = 1000):
        self.examples = examples
        self.max_length = max_length
    
    def select_examples(self, input_variables: Dict[str, str]) -> List[Dict[str, str]]:
        """Select examples based on total length constraint."""
        selected = []
        total_length = 0
        
        for example in self.examples:
            example_length = len(example['input']) + len(example['query'])
            if total_length + example_length <= self.max_length:
                selected.append(example)
                total_length += example_length
            else:
                break
        
        return selected[:5]  # Return max 5 examples


class SemanticSimilaritySelector:
    """Simple semantic similarity selector using basic string matching."""
    
    def __init__(self, examples: List[Dict[str, str]], k: int = 3):
        self.examples = examples
        self.k = k
    
    def select_examples(self, input_variables: Dict[str, str]) -> List[Dict[str, str]]:
        """Select examples based on keyword similarity."""
        query = input_variables.get('input', '').lower()
        
        # Score examples based on keyword overlap
        scored_examples = []
        for example in self.examples:
            score = self._calculate_similarity(query, example['input'].lower())
            scored_examples.append((score, example))
        
        # Sort by score and return top k
        scored_examples.sort(key=lambda x: x[0], reverse=True)
        return [example for _, example in scored_examples[:self.k]]
    
    def _calculate_similarity(self, query: str, example_input: str) -> float:
        """Calculate similarity score based on keyword overlap."""
        query_words = set(query.split())
        example_words = set(example_input.split())
        
        if not query_words or not example_words:
            return 0.0
        
        intersection = query_words.intersection(example_words)
        union = query_words.union(example_words)
        
        return len(intersection) / len(union) if union else 0.0


class FewShotSQLPromptManager:
    """Advanced prompt manager focused on few-shot learning for SQL generation."""
    
    def __init__(self):
        """Initialize the few-shot prompt manager."""
        self.config = LANGCHAIN_CONFIG
        self.examples = self._load_comprehensive_sql_examples()
        self.example_selector = SemanticSimilaritySelector(
            self.examples, 
            k=self.config['sql_chain']['top_k']
        )
        
        # Create prompt templates
        self.sql_generation_template = self._create_few_shot_sql_template()
        self.query_checker_template = self._create_query_checker_template()
        self.response_generation_template = self._create_response_generation_template()
    
    def _load_comprehensive_sql_examples(self) -> List[Dict[str, str]]:
        """Load comprehensive SQL examples for few-shot learning."""
        return [
            # Basic SELECT queries
            {
                "input": "Show me all artists",
                "query": "SELECT * FROM Artist;"
            },
            {
                "input": "List all customers",
                "query": "SELECT * FROM Customer;"
            },
            {
                "input": "Show all tracks",
                "query": "SELECT * FROM Track;"
            },
            
            # COUNT queries
            {
                "input": "How many tracks are there?",
                "query": "SELECT COUNT(*) FROM Track;"
            },
            {
                "input": "How many customers do we have?",
                "query": "SELECT COUNT(*) FROM Customer;"
            },
            {
                "input": "Count the number of artists",
                "query": "SELECT COUNT(*) FROM Artist;"
            },
            
            # JOIN queries
            {
                "input": "List all albums with their artist names",
                "query": "SELECT Artist.Name, Album.Title FROM Artist JOIN Album ON Artist.ArtistId = Album.ArtistId ORDER BY Artist.Name;"
            },
            {
                "input": "Show tracks with their album titles",
                "query": "SELECT Track.Name, Album.Title FROM Track JOIN Album ON Track.AlbumId = Album.AlbumId;"
            },
            {
                "input": "List customers with their invoices",
                "query": "SELECT Customer.FirstName, Customer.LastName, Invoice.Total FROM Customer JOIN Invoice ON Customer.CustomerId = Invoice.CustomerId;"
            },
            
            # WHERE clauses
            {
                "input": "Find tracks longer than 5 minutes",
                "query": "SELECT Name, Milliseconds FROM Track WHERE Milliseconds > 300000;"
            },
            {
                "input": "Show customers from USA",
                "query": "SELECT * FROM Customer WHERE Country = 'USA';"
            },
            {
                "input": "Find artists with name containing 'Rock'",
                "query": "SELECT * FROM Artist WHERE Name LIKE '%Rock%';"
            },
            
            # Aggregation queries
            {
                "input": "Get total sales by country",
                "query": "SELECT BillingCountry, SUM(Total) as TotalSales FROM Invoice GROUP BY BillingCountry ORDER BY TotalSales DESC;"
            },
            {
                "input": "Find the most popular genre",
                "query": "SELECT Genre.Name, COUNT(*) as TrackCount FROM Genre JOIN Track ON Genre.GenreId = Track.GenreId GROUP BY Genre.Name ORDER BY TrackCount DESC LIMIT 1;"
            },
            {
                "input": "Average track length by album",
                "query": "SELECT Album.Title, AVG(Track.Milliseconds) as AvgLength FROM Album JOIN Track ON Album.AlbumId = Track.AlbumId GROUP BY Album.Title;"
            },
            
            # Complex queries
            {
                "input": "Find customers who spent more than $40",
                "query": "SELECT Customer.FirstName, Customer.LastName, SUM(Invoice.Total) as TotalSpent FROM Customer JOIN Invoice ON Customer.CustomerId = Invoice.CustomerId GROUP BY Customer.CustomerId HAVING TotalSpent > 40;"
            },
            {
                "input": "Top 5 best selling artists",
                "query": "SELECT Artist.Name, SUM(InvoiceLine.Quantity) as TotalSold FROM Artist JOIN Album ON Artist.ArtistId = Album.ArtistId JOIN Track ON Album.AlbumId = Track.AlbumId JOIN InvoiceLine ON Track.TrackId = InvoiceLine.TrackId GROUP BY Artist.Name ORDER BY TotalSold DESC LIMIT 5;"
            },
            
            # Employee queries
            {
                "input": "List employees with their titles",
                "query": "SELECT FirstName, LastName, Title FROM Employee;"
            },
            {
                "input": "Show employees and their managers",
                "query": "SELECT e.FirstName, e.LastName, m.FirstName as ManagerFirstName, m.LastName as ManagerLastName FROM Employee e LEFT JOIN Employee m ON e.ReportsTo = m.EmployeeId;"
            },
            
            # Date-based queries
            {
                "input": "Show invoices from 2009",
                "query": "SELECT * FROM Invoice WHERE InvoiceDate LIKE '2009%';"
            },
            {
                "input": "Recent invoices in the last month",
                "query": "SELECT * FROM Invoice WHERE InvoiceDate >= DATE('now', '-1 month');"
            },
            
            # Specific field queries
            {
                "input": "Show only customer names and emails",
                "query": "SELECT FirstName, LastName, Email FROM Customer;"
            },
            {
                "input": "List track names and their prices",
                "query": "SELECT Name, UnitPrice FROM Track;"
            },
            
            # LIMIT queries
            {
                "input": "Show first 10 artists",
                "query": "SELECT * FROM Artist LIMIT 10;"
            },
            {
                "input": "Top 5 most expensive tracks",
                "query": "SELECT Name, UnitPrice FROM Track ORDER BY UnitPrice DESC LIMIT 5;"
            }
        ]
    
    def _create_few_shot_sql_template(self) -> FewShotPromptTemplate:
        """Create few-shot prompt template for SQL generation."""
        
        # Example template
        example_prompt = PromptTemplate(
            input_variables=["input", "query"],
            template="Human: {input}\nSQL: {query}"
        )
        
        # Main few-shot template
        few_shot_template = FewShotPromptTemplate(
            examples=[],  # Will be populated dynamically
            example_prompt=example_prompt,
            prefix="""You are an expert SQL query generator. Given a database schema and examples, generate precise SQL queries.

Database Schema:
{table_info}

Here are some examples of natural language questions and their corresponding SQL queries:

""",
            suffix="""Human: {input}
SQL: """,
            input_variables=["input", "table_info"]
        )
        
        return few_shot_template
    
    def _create_query_checker_template(self) -> PromptTemplate:
        """Create template for SQL query validation."""
        template = """You are a SQL query validator. Check if the following SQL query is valid and safe.

SQL Query: {query}
Database Type: {dialect}

Check for:
1. Syntax errors
2. Table and column name validity  
3. Dangerous operations (DROP, TRUNCATE, DELETE without WHERE)
4. SQL injection patterns

Respond with either:
- "VALID: [brief explanation]" if the query is safe and correct
- "INVALID: [detailed explanation of issues]" if there are problems

Response:"""
        
        return PromptTemplate(
            input_variables=["query", "dialect"],
            template=template
        )
    
    def _create_response_generation_template(self) -> PromptTemplate:
        """Create template for natural language response generation."""
        template = """Convert the SQL query results into a natural language response.

Original Question: {question}
SQL Query: {sql_query}
Query Results: {results}

Provide a clear, helpful response that answers the user's question.
If no results, provide a helpful message.

Response:"""
        
        return PromptTemplate(
            input_variables=["question", "sql_query", "results"],
            template=template
        )
    
    def build_few_shot_sql_prompt(
        self, 
        natural_language: str, 
        table_info: str,
        num_examples: int = 5
    ) -> str:
        """Build few-shot SQL generation prompt with relevant examples.
        
        Args:
            natural_language: User's natural language query
            table_info: Database schema information
            num_examples: Number of examples to include
            
        Returns:
            Formatted prompt string with examples
        """
        try:
            # Select relevant examples
            selected_examples = self.example_selector.select_examples({
                "input": natural_language
            })[:num_examples]
            
            # If no good matches, use first few examples
            if not selected_examples:
                selected_examples = self.examples[:num_examples]
            
            # Create few-shot template with selected examples
            few_shot_template = FewShotPromptTemplate(
                examples=selected_examples,
                example_prompt=PromptTemplate(
                    input_variables=["input", "query"],
                    template="Human: {input}\nSQL: {query}"
                ),
                prefix=f"""You are an expert SQL query generator. Given a database schema and examples, generate precise SQL queries.

Database Schema:
{table_info}

Here are some examples of natural language questions and their corresponding SQL queries:

""",
                suffix=f"""Human: {natural_language}
SQL: """,
                input_variables=["input", "table_info"]
            )
            
            # Format the prompt
            return few_shot_template.format(
                input=natural_language,
                table_info=table_info
            )
            
        except Exception as e:
            logger.error(f"Error building few-shot prompt: {e}")
            # Fallback to simple prompt with a few examples
            examples_text = "\n\n".join([
                f"Human: {ex['input']}\nSQL: {ex['query']}" 
                for ex in self.examples[:3]
            ])
            
            return f"""You are an expert SQL query generator.

Database Schema:
{table_info}

Examples:
{examples_text}```python
Human: {natural_language}
SQL: """
            
    def add_example(self, input_text: str, sql_query: str):
        """Add a new example to the few-shot learning set.
        
        Args:
            input_text: Natural language input
            sql_query: Corresponding SQL query
        """
        new_example = {"input": input_text, "query": sql_query}
        self.examples.append(new_example)
        
        # Recreate example selector with new examples
        self.example_selector = SemanticSimilaritySelector(
            self.examples, 
            k=self.config['sql_chain']['top_k']
        )
        logger.info("Added new example and updated selector")
    
    def get_similar_examples(self, query: str, k: int = 3) -> List[Dict[str, str]]:
        """Get similar examples for a given query.
        
        Args:
            query: Natural language query
            k: Number of examples to return
            
        Returns:
            List of similar examples
        """
        return self.example_selector.select_examples({"input": query})[:k]
    
    def build_query_checker_prompt(self, query: str, dialect: str = "sqlite") -> str:
        """Build query validation prompt.
        
        Args:
            query: SQL query to validate
            dialect: SQL dialect
            
        Returns:
            Formatted prompt string
        """
        return self.query_checker_template.format(
            query=query,
            dialect=dialect
        )
    
    def build_response_generation_prompt(
        self,
        question: str,
        sql_query: str,
        results: Any
    ) -> str:
        """Build response generation prompt.
        
        Args:
            question: Original user question
            sql_query: Executed SQL query
            results: Query results
            
        Returns:
            Formatted prompt string
        """
        # Format results for prompt
        if isinstance(results, list):
            if not results:
                results_text = "No results found"
            elif len(results) == 1:
                results_text = f"1 result: {results[0]}"
            else:
                results_text = f"{len(results)} results: {results[:3]}..." if len(results) > 3 else f"{len(results)} results: {results}"
        else:
            results_text = str(results)
        
        return self.response_generation_template.format(
            question=question,
            sql_query=sql_query,
            results=results_text
        )


# Example usage
if __name__ == "__main__":
    # Test the few-shot prompt manager
    prompt_manager = FewShotSQLPromptManager()
    
    # Test SQL generation prompt
    table_info = "CREATE TABLE Artist (ArtistId INTEGER, Name TEXT);"
    query = "Show me all artists"
    prompt = prompt_manager.build_few_shot_sql_prompt(query, table_info)
    print("Few-Shot SQL Generation Prompt:")
    print(prompt)
    print("\n" + "="*50 + "\n")
    
    # Test similar examples
    examples = prompt_manager.get_similar_examples(query)
    print("Similar Examples:")
    for ex in examples:
        print(f"Input: {ex['input']}")
        print(f"SQL: {ex['query']}")
        print()
