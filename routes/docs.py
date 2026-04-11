from flask import Blueprint, render_template, abort, session
from core.middleware import login_required
import markdown
import os

docs_bp = Blueprint('docs', __name__)

ALLOWED_DOCS = {
    'readme': 'README.md',
    'thesis': 'thesis.md',
    'design': 'SYSTEM_DESIGN.md',
    'training': 'combined_training_data.md'
}

@docs_bp.route('/docs')
@docs_bp.route('/docs/<doc_id>')
@login_required
def view_doc(doc_id='readme'):
    # Normalize ID for case-insensitive lookup
    doc_id = doc_id.lower()
    
    if doc_id not in ALLOWED_DOCS:
        abort(404)
        
    filename = ALLOWED_DOCS[doc_id]
    filepath = os.path.join(os.getcwd(), filename)
    
    if not os.path.exists(filepath):
        # Gracefully handle missing files
        return render_template('docs.html', 
                             content=f"<h1>Error</h1><p>The document <code>{filename}</code> was not found on the server.</p>",
                             title="File Not Found",
                             active_id=doc_id)
                             
    with open(filepath, 'r', encoding='utf-8') as f:
        md_content = f.read()
        
    # Convert Markdown to HTML with extensions
    # 'fenced_code' for code blocks, 'tables' for tables
    html_content = markdown.markdown(md_content, extensions=['fenced_code', 'tables', 'toc'])
    
    # Capitalize the first letter of the doc_id for the title
    title = doc_id.replace('-', ' ').title()
    if doc_id == 'readme': title = 'Welcome Guide'
    if doc_id == 'thesis': title = 'Thesis Documentation'
    
    return render_template('docs.html', 
                         content=html_content, 
                         title=title,
                         active_id=doc_id)
