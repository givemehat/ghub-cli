import os
import re

def fix_f_strings(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Regex to find f-strings (f"..." or f'...') without curly braces
    # This is a naive regex but works for simple cases
    # We will look for f"text without braces"
    # To be safe, we just replace the known ones.
    new_content = content
    new_content = new_content.replace('f"Experiment : Sin experimento asociado"', '"Experiment : Sin experimento asociado"')
    new_content = new_content.replace('f"✗ La tarea falló."', '"✗ La tarea falló."')
    new_content = new_content.replace('f"No se encontró el archivo', '"No se encontró el archivo')
    new_content = new_content.replace('f"  detail: "', '"  detail: "')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

for root, _, files in os.walk('/tmp/ghub-cli/ghub_cli'):
    for file in files:
        if file.endswith('.py'):
            fix_f_strings(os.path.join(root, file))
