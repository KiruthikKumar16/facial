import sys
import re

with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

routers = {
    'system': {
        'prefix': '/api/system',
        'tags': ['System'],
        'functions': ['health_check', 'get_kpis', 'get_system_version_bundle', 'report_node_health', 'get_all_nodes_health', 'get_thresholds', 'update_thresholds']
    },
    'forensic': {
        'prefix': '/api/forensic',
        'tags': ['Forensic'],
        'functions': ['get_detection_provenance', 'enforce_provenance_retention', 'run_forensic_vector_search', 'run_forensic_search']
    },
    'unregistered': {
        'prefix': '/api/unregistered-subjects',
        'tags': ['Unregistered Subjects'],
        'functions': ['get_unregistered_subjects', 'rename_unregistered_subject', 'register_unregistered_subject', 'assign_unregistered_subject', 'merge_unregistered_subject', 'delete_unregistered_event', 'delete_unregistered_subject']
    },
    'logs': {
        'prefix': '/api/logs',
        'tags': ['Logs & Alerts'],
        'functions': ['get_logs', 'get_alerts', 'acknowledge_alert']
    },
    'detections': {
        'prefix': '/api/detections',
        'tags': ['Detections'],
        'functions': ['create_detection', 'create_detections_batch', 'reconcile_sync']
    }
}

base_imports = """
from fastapi import APIRouter, Depends, Query, HTTPException, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, text, case, select, or_
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid
import json

from database import get_db
from models import *
from schemas import *
from config import settings, IST
from dependencies import verify_edge_node

"""

indices_to_delete = set()
new_routers = []

for router_name, config in routers.items():
    router_lines = []
    router_lines.append(base_imports)
    # The prefix logic is tricky if endpoints have different base paths.
    # We will just use router = APIRouter(tags=[...]) and keep the full paths in decorators!
    # That way we don't accidentally break paths like /health or /api/alerts.
    router_lines.append(f'router = APIRouter(tags={config["tags"]})\n\n')
    
    for func_name in config['functions']:
        start_idx = -1
        for i, line in enumerate(lines):
            # Find the def line
            if line.strip().startswith(f'def {func_name}(') or line.strip().startswith(f'async def {func_name}('):
                # Now trace upwards to find all decorators for this function
                j = i - 1
                while j >= 0 and (lines[j].strip().startswith('@app.') or lines[j].strip().startswith('@') or lines[j].strip() == '' or lines[j].strip().startswith('#')):
                    j -= 1
                start_idx = j + 1
                break
                
        if start_idx != -1:
            end_idx = start_idx
            # Move forward until the end of the function body
            # We can detect the end by looking for the next top-level def, @app, or # == separator
            # BUT we have to skip nested defs. A safe way is to find the next line that starts exactly with '@app.' or '# ==', or a non-indented 'def ' / 'async def '.
            in_func_body = False
            i = start_idx
            while i < len(lines):
                line = lines[i]
                if line.strip().startswith('def ') or line.strip().startswith('async def '):
                    if not line.startswith(' ') and not line.startswith('\t'):
                        if in_func_body:
                            # Reached the next function
                            break
                        else:
                            in_func_body = True
                elif in_func_body and not line.startswith(' ') and not line.startswith('\t') and line.strip() != '':
                    # Found a non-indented line after function body started
                    if line.startswith('@') or line.startswith('# ==') or line.startswith('def ') or line.startswith('async def ') or line.startswith('class '):
                        break
                i += 1
            end_idx = i
            
            func_lines = lines[start_idx:end_idx]
            for idx, fl in enumerate(func_lines):
                if fl.startswith('@app.'):
                    func_lines[idx] = fl.replace('@app.', '@router.')
                    
            router_lines.extend(func_lines)
            router_lines.append('\n')
            indices_to_delete.update(range(start_idx, end_idx))
            
    with open(f'routers/{router_name}.py', 'w', encoding='utf-8') as f:
        f.write(''.join(router_lines))
    new_routers.append(router_name)

# Remove the extracted lines
lines = [line for i, line in enumerate(lines) if i not in indices_to_delete]

# Add router inclusions
for i, line in enumerate(lines):
    if line.startswith('app = FastAPI('):
        j = i
        while not ')' in lines[j]:
            j += 1
        
        insert_code = ''
        for r in new_routers:
            insert_code += f'\nfrom routers.{r} import router as {r}_router\napp.include_router({r}_router)\n'
        
        lines.insert(j + 1, insert_code)
        break

with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Extracted routers successfully!')
