import re



def sanitize_code_content(content: str) -> str:
    """
    Sanitize code content for analysis.
    
    Args:
        content: Raw file content
        
    Returns:
        Sanitized content
    """
    if not isinstance(content, str):
        return ""
        
    # Truncate large files
    content = content[:5000] #todo add from config
    
    # Remove Unicode control characters
    content = re.sub(r'[\u0000-\u0008\u000B-\u000C\u000E-\u001F\uD800-\uDFFF]', '', content)
    
    # Normalize newlines
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    
    return content


def get_file_extension(filename: str) -> str:
    """
    Get language identifier from file extension.
    
    Args:
        filename: Filename including extension
        
    Returns:
        Language name for syntax highlighting
    """
    # Fast extension extraction
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    # Language mapping
    language_map = {
        'js': 'javascript',
        'ts': 'typescript',
        'py': 'python',
        'java': 'java',
        'go': 'go',
        'rs': 'rust',
        'cpp': 'cpp',
        'c': 'c',
        'jsx': 'javascript',
        'tsx': 'typescript',
        'vue': 'vue',
        'php': 'php',
        'rb': 'ruby',
        'sol': 'solidity',
        'cs': 'csharp',
        'html': 'html',
        'css': 'css',
        'scss': 'scss',
        'md': 'markdown',
        'json': 'json',
        'yml': 'yaml',
        'yaml': 'yaml'
    }
    
    return language_map.get(ext, ext)

def safe_add_field(embed, name, content, inline=False):
    # If content is too long, truncate with an indicator
    if len(content) > 1024:
        content = content[:1020] + "..."
    embed.add_field(name=name, value=content, inline=False)