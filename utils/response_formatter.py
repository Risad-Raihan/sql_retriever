"""Response formatting utilities for SQL retriever bot."""

import json
from typing import Any, Dict, List, Optional, Union
from tabulate import tabulate

from config import RESPONSE_CONFIG


class ResponseFormatter:
    """Formats SQL query results into human-readable responses."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize response formatter.
        
        Args:
            config: Configuration dictionary, defaults to RESPONSE_CONFIG
        """
        self.config = config or RESPONSE_CONFIG
    
    def format_query_results(
        self, 
        results: List[Dict[str, Any]], 
        query: str, 
        query_time: Optional[float] = None
    ) -> str:
        """Format SQL query results into a human-readable response.
        
        Args:
            results: List of dictionaries containing query results
            query: Original SQL query
            query_time: Query execution time in seconds
            
        Returns:
            Formatted response string
        """
        if not results:
            return self._format_empty_results()
        
        # Truncate results if too many
        display_results = results[:self.config['max_table_rows']]
        truncated = len(results) > self.config['max_table_rows']
        
        # Format the data
        formatted_data = self._format_data_table(display_results)
        
        # Build response
        response_parts = []
        
        # Add results summary
        if self.config['include_row_count']:
            count_text = f"Found {len(results)} result{'s' if len(results) != 1 else ''}"
            if truncated:
                count_text += f" (showing first {len(display_results)})"
            response_parts.append(count_text)
        
        # Add formatted data
        response_parts.append(formatted_data)
        
        # Add query time if available
        if query_time is not None and self.config['include_query_time']:
            response_parts.append(f"Query executed in {query_time:.3f} seconds")
        
        return "\n\n".join(response_parts)
    
    def format_update_results(
        self, 
        affected_rows: int, 
        operation: str, 
        query_time: Optional[float] = None
    ) -> str:
        """Format results from INSERT/UPDATE/DELETE operations.
        
        Args:
            affected_rows: Number of rows affected
            operation: Type of operation (INSERT, UPDATE, DELETE)
            query_time: Query execution time in seconds
            
        Returns:
            Formatted response string
        """
        response_parts = []
        
        # Main result message
        if affected_rows == 0:
            response_parts.append(f"No rows were {operation.lower()}ed")
        elif affected_rows == 1:
            response_parts.append(f"Successfully {operation.lower()}ed 1 row")
        else:
            response_parts.append(f"Successfully {operation.lower()}ed {affected_rows} rows")
        
        # Add query time if available
        if query_time is not None and self.config['include_query_time']:
            response_parts.append(f"Operation completed in {query_time:.3f} seconds")
        
        return "\n".join(response_parts)
    
    def format_error_response(self, error: Exception, query: Optional[str] = None) -> str:
        """Format error response.
        
        Args:
            error: Exception that occurred
            query: SQL query that caused the error (optional)
            
        Returns:
            Formatted error response
        """
        response_parts = []
        
        # Error message
        response_parts.append(f"Error: {str(error)}")
        
        # Query context if available
        if query:
            response_parts.append(f"Query: {query}")
        
        return "\n".join(response_parts)
    
    def format_schema_info(self, schema: Dict[str, Any]) -> str:
        """Format database schema information.
        
        Args:
            schema: Database schema dictionary
            
        Returns:
            Formatted schema information
        """
        response_parts = []
        
        # Database type
        response_parts.append(f"Database Type: {schema.get('database_type', 'Unknown')}")
        
        # Tables
        tables = schema.get('tables', {})
        if tables:
            response_parts.append(f"\nTables ({len(tables)}):")
            for table_name, table_info in tables.items():
                columns = table_info.get('columns', [])
                column_count = len(columns)
                response_parts.append(f"  • {table_name} ({column_count} columns)")
                
                # Show first few columns
                if columns:
                    for col in columns[:5]:  # Show first 5 columns
                        col_info = f"    - {col['name']} ({col['type']})"
                        if not col.get('nullable', True):
                            col_info += " NOT NULL"
                        if col.get('primary_key'):
                            col_info += " PRIMARY KEY"
                        response_parts.append(col_info)
                    
                    if len(columns) > 5:
                        response_parts.append(f"    ... and {len(columns) - 5} more columns")
        
        # Views
        views = schema.get('views', [])
        if views:
            response_parts.append(f"\nViews ({len(views)}):")
            for view in views:
                response_parts.append(f"  • {view}")
        
        return "\n".join(response_parts)
    
    def format_confirmation_prompt(self, query: str, operation: str) -> str:
        """Format confirmation prompt for dangerous operations.
        
        Args:
            query: SQL query to be executed
            operation: Type of operation (INSERT, UPDATE, DELETE)
            
        Returns:
            Formatted confirmation prompt
        """
        return f"""
⚠️  CONFIRMATION REQUIRED ⚠️

You are about to execute a {operation} operation:

{query}

This operation may modify your database. Are you sure you want to continue?
Type 'yes' to confirm, or 'no' to cancel:
"""
    
    def format_table_data(self, data: List[Dict[str, Any]]) -> str:
        """Format data as a table (public interface).
        
        Args:
            data: List of dictionaries containing row data
            
        Returns:
            Formatted table string
        """
        return self._format_data_table(data)
    
    def _format_empty_results(self) -> str:
        """Format empty results message."""
        return "No results found."
    
    def _format_data_table(self, data: List[Dict[str, Any]]) -> str:
        """Format data as a table.
        
        Args:
            data: List of dictionaries containing row data
            
        Returns:
            Formatted table string
        """
        if not data:
            return self._format_empty_results()
        
        # Truncate long text fields
        if self.config['truncate_long_text']:
            data = self._truncate_long_text(data)
        
        # Convert to table format
        headers = list(data[0].keys())
        rows = []
        
        for row in data:
            rows.append([self._format_cell_value(row.get(header)) for header in headers])
        
        return tabulate(
            rows, 
            headers=headers, 
            tablefmt=self.config['table_format'],
            numalign='right',
            stralign='left'
        )
    
    def _truncate_long_text(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Truncate long text fields in data.
        
        Args:
            data: List of dictionaries containing row data
            
        Returns:
            Data with truncated text fields
        """
        max_length = self.config['max_text_length']
        truncated_data = []
        
        for row in data:
            truncated_row = {}
            for key, value in row.items():
                if isinstance(value, str) and len(value) > max_length:
                    truncated_row[key] = value[:max_length] + "..."
                else:
                    truncated_row[key] = value
            truncated_data.append(truncated_row)
        
        return truncated_data
    
    def _format_cell_value(self, value: Any) -> str:
        """Format individual cell value.
        
        Args:
            value: Cell value to format
            
        Returns:
            Formatted string value
        """
        if value is None:
            return "NULL"
        elif isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        elif isinstance(value, (dict, list)):
            return json.dumps(value, default=str)
        else:
            return str(value)
    
    def format_natural_language_response(
        self, 
        results: List[Dict[str, Any]], 
        original_question: str,
        query: str
    ) -> str:
        """Format results into natural language response.
        
        Args:
            results: Query results
            original_question: Original user question
            query: SQL query that was executed
            
        Returns:
            Natural language response
        """
        if not results:
            return self._generate_empty_response(original_question)
        
        # Generate natural language response based on query type and results
        if len(results) == 1:
            return self._generate_single_result_response(results[0], original_question)
        else:
            return self._generate_multiple_results_response(results, original_question)
    
    def _generate_empty_response(self, question: str) -> str:
        """Generate response for empty results."""
        return f"I couldn't find any results for your query: '{question}'"
    
    def _generate_single_result_response(self, result: Dict[str, Any], question: str) -> str:
        """Generate response for single result."""
        # Simple implementation - can be enhanced with more sophisticated NLG
        return f"Here's what I found:\n\n{self._format_data_table([result])}"
    
    def _generate_multiple_results_response(self, results: List[Dict[str, Any]], question: str) -> str:
        """Generate response for multiple results."""
        # Simple implementation - can be enhanced with more sophisticated NLG
        return f"I found {len(results)} results:\n\n{self._format_data_table(results)}" 