from flask import Blueprint, render_template, abort, current_app
import os
import markdown2

docs_bp = Blueprint('docs', __name__)

# List of Markdown files to display in the Docs Center
DOCS_DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_DOCS = {
    'readme': 'README.md',
    'design': 'SYSTEM_DESIGN.md',
    'deployment': 'deployment.md',
    'thesis': 'thesis.md',
    'cheatsheet': 'cheatsheet.md',
    'methodology': 'METHODOLOGY.md',
    'evaluation': 'EVALUATION.md',
    'security': 'SECURITY_ANALYSIS.md',
    'developer': 'BEGINNER_DEVELOPER_GUIDE.md'
}

@docs_bp.route('/docs')
@docs_bp.route('/docs/<doc_id>')
def view_doc(doc_id='readme'):
    doc_id = doc_id.lower()
    if doc_id not in ALLOWED_DOCS:
        abort(404)
    
    file_path = os.path.join(DOCS_DIRECTORY, ALLOWED_DOCS[doc_id])
    
    if not os.path.exists(file_path):
        abort(404)
        
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Convert Markdown to HTML with extras (tables, mermaid, etc.)
    html_content = markdown2.markdown(content, extras=[
        "tables", 
        "fenced-code-blocks", 
        "header-ids", 
        "code-friendly", 
        "metadata"
    ])
    
    # Generate navigation list
    nav_links = [
        {'id': k, 'title': v.replace('.md', '').replace('_', ' ').title()} 
        for k, v in ALLOWED_DOCS.items()
    ]
    
    current_title = ALLOWED_DOCS[doc_id].replace('.md', '').replace('_', ' ').title()
    
    return render_template('docs.html', 
                          content=html_content, 
                          nav_links=nav_links, 
                          active_doc=doc_id,
                          current_title=current_title)
