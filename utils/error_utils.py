"""
Error handling utility functions.
"""

from typing import List, Dict, Any


def create_result_dict(success: bool, errors: List[str] = None, **kwargs) -> Dict[str, Any]:
    """
    Create a standardized result dictionary.
    
    Args:
        success: Whether the operation was successful
        errors: List of error messages
        **kwargs: Additional fields to include in the result
        
    Returns:
        Standardized result dictionary
    """
    result = {
        "success": success,
        "errors": errors or [],
        **kwargs
    }
    return result


def handle_step_error(error_msg: str, errors: List[str], logger) -> None:
    """
    Handle an error in a processing step.
    
    Args:
        error_msg: Error message to log and track
        errors: List to append the error to
        logger: Logger instance for logging
    """
    logger.warning(error_msg)
    errors.append(error_msg)