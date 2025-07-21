"""Query validation and safety checks for SQL retriever bot."""

import re
import sqlparse
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)


class QueryType(Enum):
    """Enumeration of SQL query types."""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CREATE = "CREATE"
    DROP = "DROP"
    ALTER = "ALTER"
    TRUNCATE = "TRUNCATE"
    GRANT = "GRANT"
    REVOKE = "REVOKE"
    UNKNOWN = "UNKNOWN"


class ValidationResult:
    """Result of query validation."""
    
    def __init__(self, is_valid: bool, error_message: str = None, warnings: List[str] = None):
        self.is_valid = is_valid
        self.error_message = error_message
        self.warnings = warnings or []
        
    def __bool__(self):
        return self.is_valid


class QueryValidator:
    """Validates SQL queries for safety and permissions."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize query validator.
        
        Args:
            config: Configuration dictionary, defaults to SAFETY_CONFIG
        """
        self.config = config or {
            'forbidden_keywords': ['DROP', 'EXEC', 'EXECUTE', 'SP_EXECUTESQL', 'XP_CMDSHELL', 'OPENROWSET', 'OPENDATASOURCE'],
            'require_confirmation': ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE']
        }
        self.forbidden_keywords = set(kw.upper() for kw in self.config['forbidden_keywords'])
        
    def validate_query(self, query: str, user_role: str = 'user') -> ValidationResult:
        """Validate a SQL query for safety and permissions.
        
        Args:
            query: SQL query string
            user_role: User role (viewer, user, admin)
            
        Returns:
            ValidationResult object
        """
        try:
            # Basic syntax validation
            syntax_result = self.validate_syntax(query)
            if not syntax_result.is_valid:
                return syntax_result
            
            # Query type detection
            query_type = self.detect_query_type(query)
            
            # Permission validation
            permission_result = self.check_permissions(query_type, user_role)
            if not permission_result.is_valid:
                return permission_result
            
            # Safety checks
            safety_result = self.check_safety(query)
            if not safety_result.is_valid:
                return safety_result
            
            # Additional checks based on query type
            if query_type in [QueryType.INSERT, QueryType.UPDATE, QueryType.DELETE]:
                modification_result = self.validate_modification_query(query)
                if not modification_result.is_valid:
                    return modification_result
            
            # Collect all warnings
            all_warnings = []
            all_warnings.extend(syntax_result.warnings)
            all_warnings.extend(safety_result.warnings)
            
            return ValidationResult(True, warnings=all_warnings)
            
        except Exception as e:
            logger.error(f"Query validation error: {e}")
            return ValidationResult(False, f"Validation error: {str(e)}")
    
    def validate_syntax(self, query: str) -> ValidationResult:
        """Validate SQL syntax.
        
        Args:
            query: SQL query string
            
        Returns:
            ValidationResult object
        """
        try:
            if not query.strip():
                return ValidationResult(False, "Query cannot be empty")
            
            # Parse the query
            parsed = sqlparse.parse(query)
            
            if not parsed:
                return ValidationResult(False, "Invalid SQL syntax")
            
            warnings = []
            
            # Check for multiple statements
            statements = [stmt for stmt in parsed if stmt.ttype is None]
            if len(statements) > 1:
                warnings.append("Multiple statements detected - only the first will be executed")
            
            # Check for comments that might contain dangerous content
            for token in parsed[0].flatten():
                if token.ttype in sqlparse.tokens.Comment:
                    if any(keyword in token.value.upper() for keyword in self.forbidden_keywords):
                        return ValidationResult(False, "Dangerous content detected in comments")
            
            return ValidationResult(True, warnings=warnings)
            
        except Exception as e:
            return ValidationResult(False, f"Syntax validation error: {str(e)}")
    
    def detect_query_type(self, query: str) -> QueryType:
        """Detect the type of SQL query.
        
        Args:
            query: SQL query string
            
        Returns:
            QueryType enum value
        """
        try:
            # Normalize query
            normalized = query.strip().upper()
            
            # Check for each query type
            if normalized.startswith('SELECT'):
                return QueryType.SELECT
            elif normalized.startswith('INSERT'):
                return QueryType.INSERT
            elif normalized.startswith('UPDATE'):
                return QueryType.UPDATE
            elif normalized.startswith('DELETE'):
                return QueryType.DELETE
            elif normalized.startswith('CREATE'):
                return QueryType.CREATE
            elif normalized.startswith('DROP'):
                return QueryType.DROP
            elif normalized.startswith('ALTER'):
                return QueryType.ALTER
            elif normalized.startswith('TRUNCATE'):
                return QueryType.TRUNCATE
            elif normalized.startswith('GRANT'):
                return QueryType.GRANT
            elif normalized.startswith('REVOKE'):
                return QueryType.REVOKE
            else:
                return QueryType.UNKNOWN
                
        except Exception as e:
            logger.error(f"Query type detection error: {e}")
            return QueryType.UNKNOWN
    
    def check_permissions(self, query_type: QueryType, user_role: str) -> ValidationResult:
        """Check user permissions for query type.
        
        Args:
            query_type: Type of query
            user_role: User role
            
        Returns:
            ValidationResult object
        """
        try:
            # In a real application, USER_ROLES would be defined elsewhere
            # For now, we'll use a placeholder or a default role
            role_config = {
                'viewer': {'allowed_operations': ['SELECT']},
                'user': {'allowed_operations': ['SELECT', 'INSERT', 'UPDATE', 'DELETE']},
                'admin': {'allowed_operations': ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE']}
            }
            role_config = role_config.get(user_role, role_config['user'])
            allowed_operations = role_config['allowed_operations']
            
            if query_type.value not in allowed_operations:
                return ValidationResult(
                    False, 
                    f"Operation {query_type.value} not allowed for role '{user_role}'"
                )
            
            return ValidationResult(True)
            
        except Exception as e:
            logger.error(f"Permission check error: {e}")
            return ValidationResult(False, f"Permission check failed: {str(e)}")
    
    def check_safety(self, query: str) -> ValidationResult:
        """Check query for safety issues.
        
        Args:
            query: SQL query string
            
        Returns:
            ValidationResult object
        """
        try:
            warnings = []
            
            # Check for forbidden keywords
            query_upper = query.upper()
            for keyword in self.forbidden_keywords:
                if keyword in query_upper:
                    return ValidationResult(False, f"Forbidden keyword '{keyword}' detected")
            
            # Check for dangerous patterns
            dangerous_patterns = [
                r'--.*DROP',  # Comments with DROP
                r'\/\*.*DROP.*\*\/',  # Multi-line comments with DROP
                r';\s*DROP',  # DROP after semicolon
                r'UNION.*SELECT.*FROM.*INFORMATION_SCHEMA',  # Information schema access
                r'EXEC\s*\(',  # Stored procedure execution
                r'EXECUTE\s*\(',  # Stored procedure execution
                r'SP_EXECUTESQL',  # Dynamic SQL execution
                r'XP_CMDSHELL',  # Command execution
                r'OPENROWSET',  # External data access
                r'OPENDATASOURCE',  # External data access
            ]
            
            for pattern in dangerous_patterns:
                if re.search(pattern, query_upper, re.IGNORECASE | re.MULTILINE):
                    return ValidationResult(False, f"Dangerous pattern detected: {pattern}")
            
            # Check for suspicious conditions
            suspicious_patterns = [
                r'WHERE\s+1\s*=\s*1',  # Always true conditions
                r'WHERE\s+.*\s+OR\s+.*\s*=\s*.*',  # Potential SQL injection
                r'UNION\s+SELECT',  # Union-based injection
                r'\/\*.*\*\/',  # Multi-line comments (might hide malicious code)
            ]
            
            for pattern in suspicious_patterns:
                if re.search(pattern, query_upper, re.IGNORECASE):
                    warnings.append(f"Suspicious pattern detected: {pattern}")
            
            # Check for missing WHERE clause in UPDATE/DELETE
            if query_upper.strip().startswith(('UPDATE', 'DELETE')):
                if 'WHERE' not in query_upper:
                    warnings.append("UPDATE/DELETE without WHERE clause affects all rows")
            
            return ValidationResult(True, warnings=warnings)
            
        except Exception as e:
            logger.error(f"Safety check error: {e}")
            return ValidationResult(False, f"Safety check failed: {str(e)}")
    
    def validate_modification_query(self, query: str) -> ValidationResult:
        """Validate queries that modify data (INSERT, UPDATE, DELETE).
        
        Args:
            query: SQL query string
            
        Returns:
            ValidationResult object
        """
        try:
            warnings = []
            
            # Parse the query
            parsed = sqlparse.parse(query)
            if not parsed:
                return ValidationResult(False, "Cannot parse modification query")
            
            query_type = self.detect_query_type(query)
            
            # Check for batch operations
            if query_type == QueryType.INSERT:
                # Check for bulk inserts
                if 'VALUES' in query.upper():
                    values_match = re.search(r'VALUES\s*\(.*?\)', query, re.IGNORECASE | re.DOTALL)
                    if values_match:
                        values_count = query.upper().count('VALUES')
                        if values_count > 1 or query.count('),(') > 10:
                            warnings.append("Bulk insert operation detected")
            
            elif query_type == QueryType.UPDATE:
                # Check for updates without specific conditions
                if 'WHERE' not in query.upper():
                    return ValidationResult(False, "UPDATE queries must include WHERE clause")
                
                # Check for updates to primary key columns
                pk_patterns = [r'SET\s+id\s*=', r'SET\s+.*_id\s*=']
                for pattern in pk_patterns:
                    if re.search(pattern, query, re.IGNORECASE):
                        warnings.append("Updating primary key column detected")
            
            elif query_type == QueryType.DELETE:
                # Check for deletes without specific conditions
                if 'WHERE' not in query.upper():
                    return ValidationResult(False, "DELETE queries must include WHERE clause")
                
                # Check for potential cascade deletes
                if 'CASCADE' in query.upper():
                    warnings.append("Cascade delete operation detected")
            
            return ValidationResult(True, warnings=warnings)
            
        except Exception as e:
            logger.error(f"Modification query validation error: {e}")
            return ValidationResult(False, f"Modification validation failed: {str(e)}")
    
    def estimate_query_impact(self, query: str) -> Dict[str, Any]:
        """Estimate the potential impact of a query.
        
        Args:
            query: SQL query string
            
        Returns:
            Dictionary with impact estimation
        """
        try:
            query_type = self.detect_query_type(query)
            
            impact = {
                'query_type': query_type.value,
                'risk_level': 'LOW',
                'estimated_rows_affected': 'UNKNOWN',
                'requires_confirmation': False,
                'reversible': True
            }
            
            # Assess risk based on query type
            if query_type == QueryType.SELECT:
                impact['risk_level'] = 'NONE'
                impact['reversible'] = True
            elif query_type == QueryType.INSERT:
                impact['risk_level'] = 'LOW'
                impact['reversible'] = True  # Can be undone with DELETE
            elif query_type == QueryType.UPDATE:
                impact['risk_level'] = 'MEDIUM'
                impact['reversible'] = False  # Original values lost
                if 'WHERE' not in query.upper():
                    impact['risk_level'] = 'HIGH'
                    impact['estimated_rows_affected'] = 'ALL'
            elif query_type == QueryType.DELETE:
                impact['risk_level'] = 'HIGH'
                impact['reversible'] = False  # Data lost
                if 'WHERE' not in query.upper():
                    impact['risk_level'] = 'CRITICAL'
                    impact['estimated_rows_affected'] = 'ALL'
            elif query_type in [QueryType.DROP, QueryType.TRUNCATE]:
                impact['risk_level'] = 'CRITICAL'
                impact['reversible'] = False
                impact['estimated_rows_affected'] = 'ALL'
            
            # Check if confirmation is required
            if query_type.value in self.config['require_confirmation']:
                impact['requires_confirmation'] = True
            
            return impact
            
        except Exception as e:
            logger.error(f"Query impact estimation error: {e}")
            return {
                'query_type': 'UNKNOWN',
                'risk_level': 'HIGH',
                'estimated_rows_affected': 'UNKNOWN',
                'requires_confirmation': True,
                'reversible': False
            }
    
    def get_query_suggestions(self, query: str) -> List[str]:
        """Get suggestions for improving query safety.
        
        Args:
            query: SQL query string
            
        Returns:
            List of suggestion strings
        """
        suggestions = []
        
        try:
            query_type = self.detect_query_type(query)
            query_upper = query.upper()
            
            # Suggestions for SELECT queries
            if query_type == QueryType.SELECT:
                if 'LIMIT' not in query_upper:
                    suggestions.append("Consider adding LIMIT clause to restrict result size")
                if 'ORDER BY' not in query_upper and 'GROUP BY' not in query_upper:
                    suggestions.append("Consider adding ORDER BY clause for consistent results")
            
            # Suggestions for modification queries
            elif query_type in [QueryType.UPDATE, QueryType.DELETE]:
                if 'WHERE' not in query_upper:
                    suggestions.append("Add WHERE clause to avoid affecting all rows")
                if 'LIMIT' not in query_upper:
                    suggestions.append("Consider adding LIMIT clause to restrict affected rows")
            
            # Suggestions for INSERT queries
            elif query_type == QueryType.INSERT:
                if 'SELECT' in query_upper:
                    suggestions.append("Verify INSERT ... SELECT query affects expected rows")
            
            # General suggestions
            if len(query) > 1000:
                suggestions.append("Consider breaking complex queries into smaller parts")
            
            if query.count('JOIN') > 5:
                suggestions.append("Review complex JOIN operations for performance")
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Query suggestions error: {e}")
            return ["Unable to provide suggestions due to parsing error"] 