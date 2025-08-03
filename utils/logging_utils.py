"""
Logging utility functions for handling Unicode encoding issues.
"""


def safe_log_text(text: str) -> str:
    """
    Convert text to ASCII-safe format for logging to avoid encoding errors.
    
    Args:
        text: Input text that may contain Unicode characters
        
    Returns:
        ASCII-safe version of the text with Unicode characters replaced
    """
    if text:
        return text.encode('ascii', 'replace').decode('ascii')
    return text