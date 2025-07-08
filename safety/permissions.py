"""Permission management for SQL retriever bot."""

from typing import Dict, List, Set, Any, Optional
from enum import Enum

from config import USER_ROLES, SAFETY_CONFIG
from utils.logger import get_logger

logger = get_logger(__name__)


class PermissionLevel(Enum):
    """Permission levels for different operations."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class PermissionManager:
    """Manages user permissions and access control."""
    
    def __init__(self):
        """Initialize permission manager."""
        self.user_roles = USER_ROLES
        self.safety_config = SAFETY_CONFIG
    
    def check_operation_permission(self, user_role: str, operation: str) -> bool:
        """Check if user role has permission for operation.
        
        Args:
            user_role: User role (viewer, user, admin)
            operation: SQL operation (SELECT, INSERT, UPDATE, DELETE, etc.)
            
        Returns:
            True if permission granted, False otherwise
        """
        try:
            role_config = self.user_roles.get(user_role, self.user_roles['user'])
            allowed_operations = role_config.get('allowed_operations', [])
            
            return operation.upper() in [op.upper() for op in allowed_operations]
            
        except Exception as e:
            logger.error(f"Permission check error: {e}")
            return False
    
    def get_user_permissions(self, user_role: str) -> Dict[str, Any]:
        """Get detailed permissions for a user role.
        
        Args:
            user_role: User role
            
        Returns:
            Dictionary containing user permissions
        """
        try:
            role_config = self.user_roles.get(user_role, self.user_roles['user'])
            
            return {
                'role': user_role,
                'allowed_operations': role_config.get('allowed_operations', []),
                'max_results': role_config.get('max_results', 1000),
                'requires_confirmation': role_config.get('requires_confirmation', []),
                'permission_level': self._get_permission_level(user_role)
            }
            
        except Exception as e:
            logger.error(f"Get permissions error: {e}")
            return self._get_default_permissions()
    
    def _get_permission_level(self, user_role: str) -> PermissionLevel:
        """Get permission level for user role.
        
        Args:
            user_role: User role
            
        Returns:
            PermissionLevel enum value
        """
        role_levels = {
            'viewer': PermissionLevel.READ,
            'user': PermissionLevel.WRITE,
            'admin': PermissionLevel.ADMIN
        }
        
        return role_levels.get(user_role, PermissionLevel.READ)
    
    def _get_default_permissions(self) -> Dict[str, Any]:
        """Get default permissions for fallback.
        
        Returns:
            Default permissions dictionary
        """
        return {
            'role': 'viewer',
            'allowed_operations': ['SELECT'],
            'max_results': 100,
            'requires_confirmation': [],
            'permission_level': PermissionLevel.READ
        }
    
    def can_execute_query(self, user_role: str, query: str) -> bool:
        """Check if user can execute a specific query.
        
        Args:
            user_role: User role
            query: SQL query to check
            
        Returns:
            True if query can be executed, False otherwise
        """
        try:
            # Simple check - look for SQL keywords at the start
            query_upper = query.strip().upper()
            
            # Extract operation
            operation = None
            for op in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER']:
                if query_upper.startswith(op):
                    operation = op
                    break
            
            if not operation:
                return False
            
            return self.check_operation_permission(user_role, operation)
            
        except Exception as e:
            logger.error(f"Query execution check error: {e}")
            return False
    
    def get_max_results(self, user_role: str) -> int:
        """Get maximum results allowed for user role.
        
        Args:
            user_role: User role
            
        Returns:
            Maximum number of results
        """
        try:
            role_config = self.user_roles.get(user_role, self.user_roles['user'])
            return role_config.get('max_results', 1000)
        except Exception as e:
            logger.error(f"Max results check error: {e}")
            return 100  # Conservative default
    
    def requires_confirmation(self, user_role: str, operation: str) -> bool:
        """Check if operation requires confirmation for user role.
        
        Args:
            user_role: User role
            operation: SQL operation
            
        Returns:
            True if confirmation required, False otherwise
        """
        try:
            role_config = self.user_roles.get(user_role, self.user_roles['user'])
            requires_confirmation = role_config.get('requires_confirmation', [])
            
            return operation.upper() in [op.upper() for op in requires_confirmation]
            
        except Exception as e:
            logger.error(f"Confirmation check error: {e}")
            return True  # Default to requiring confirmation
    
    def validate_role(self, user_role: str) -> bool:
        """Validate if user role is valid.
        
        Args:
            user_role: User role to validate
            
        Returns:
            True if valid, False otherwise
        """
        return user_role in self.user_roles
    
    def get_available_roles(self) -> List[str]:
        """Get list of available user roles.
        
        Returns:
            List of role names
        """
        return list(self.user_roles.keys())
    
    def escalate_permission(self, current_role: str, target_role: str) -> bool:
        """Check if permission escalation is allowed.
        
        Args:
            current_role: Current user role
            target_role: Target role to escalate to
            
        Returns:
            True if escalation allowed, False otherwise
        """
        try:
            # Define role hierarchy
            role_hierarchy = {
                'viewer': 0,
                'user': 1,
                'admin': 2
            }
            
            current_level = role_hierarchy.get(current_role, 0)
            target_level = role_hierarchy.get(target_role, 0)
            
            # Only allow escalation to same or lower level
            # (In practice, you'd implement proper authentication)
            return target_level <= current_level
            
        except Exception as e:
            logger.error(f"Permission escalation error: {e}")
            return False
    
    def audit_permission_check(self, user_role: str, operation: str, result: bool):
        """Audit permission check for logging.
        
        Args:
            user_role: User role
            operation: SQL operation
            result: Permission check result
        """
        try:
            logger.info(f"Permission check: role={user_role}, operation={operation}, result={result}")
        except Exception as e:
            logger.error(f"Permission audit error: {e}")
    
    def get_permission_summary(self, user_role: str) -> str:
        """Get human-readable permission summary.
        
        Args:
            user_role: User role
            
        Returns:
            Formatted permission summary
        """
        try:
            permissions = self.get_user_permissions(user_role)
            
            summary = f"""
Permission Summary for role '{user_role}':
- Allowed Operations: {', '.join(permissions['allowed_operations'])}
- Max Results: {permissions['max_results']}
- Requires Confirmation: {', '.join(permissions['requires_confirmation']) if permissions['requires_confirmation'] else 'None'}
- Permission Level: {permissions['permission_level'].value}
"""
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Permission summary error: {e}")
            return f"Error generating permission summary: {str(e)}" 