from django import template
from django.template.defaulttags import register

register = template.Library()

@register.simple_tag
def load_css_async(css_files):
    """
    Load CSS files asynchronously to prevent FOUC
    Usage: {% load_css_async "file1.css,file2.css" %}
    """
    if not css_files:
        return ""
    
    files = [f.strip() for f in css_files.split(',')]
    html = []
    
    for file in files:
        if file.startswith('http'):
            # External CSS
            html.append(f'''
                <link rel="preload" href="{file}" as="style" onload="this.onload=null;this.rel='stylesheet'">
                <noscript><link rel="stylesheet" href="{file}"></noscript>
            ''')
        else:
            # Local CSS
            html.append(f'''
                <link rel="preload" href="/static/css/{file}" as="style" onload="this.onload=null;this.rel='stylesheet'">
                <noscript><link rel="stylesheet" href="/static/css/{file}"></noscript>
            ''')
    
    return '\n'.join(html)

@register.simple_tag
def load_font_async(font_url):
    """
    Load Google Fonts asynchronously
    Usage: {% load_font_async "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" %}
    """
    return f'''
        <link rel="preload" href="{font_url}" as="style" onload="this.onload=null;this.rel='stylesheet'">
        <noscript><link rel="stylesheet" href="{font_url}"></noscript>
    '''
