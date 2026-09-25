import sys

with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

analytics_functions = [
    'def get_movement_network(',
    'def get_duplicates(',
    'def get_trajectory(',
    'def get_footfall(',
    'def get_age_distribution(',
    'def get_gender_distribution(',
    'def get_attendance('
]

analytics_lines = []
imports = """
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, text, case, select, or_
from datetime import datetime, timedelta
from typing import Optional, List
import uuid

from database import get_db
from models import (
    Camera, Profile, Detection, CameraTransition, Alert,
    ProfileRoleEnum, DetectionStatusEnum
)
from schemas import (
    MovementNetworkResponse, MovementEdgeResponse,
    DuplicateCandidateResponse, ProfileResponse,
    SubjectTrajectoryResponse, TrajectoryNodeResponse,
    FootfallBucketResponse, DemographicSliceResponse,
    AttendanceRecordFullResponse
)
from config import IST

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

"""
analytics_lines.append(imports)

indices_to_delete = []

for func_name in analytics_functions:
    start_idx = -1
    for i, line in enumerate(lines):
        if line.startswith(func_name):
            start_idx = i - 1 # include the @app decorator
            while not lines[start_idx].startswith('@app.'):
                start_idx -= 1
            break
            
    if start_idx != -1:
        end_idx = start_idx + 1
        while end_idx < len(lines):
            if lines[end_idx].startswith('@app.') or lines[end_idx].startswith('# ==') or (lines[end_idx].startswith('def ') and not lines[end_idx].startswith('def ' + func_name.replace('def ', ''))):
                # reached next function or section
                break
            end_idx += 1
            
        # extract
        func_lines = lines[start_idx:end_idx]
        # replace @app. with @router. and remove /api/analytics from the path
        for idx, fl in enumerate(func_lines):
            if fl.startswith('@app.'):
                fl = fl.replace('@app.', '@router.')
                fl = fl.replace('/api/analytics', '')
                func_lines[idx] = fl
                
        analytics_lines.extend(func_lines)
        analytics_lines.append('\n')
        indices_to_delete.extend(range(start_idx, end_idx))

# Remove the extracted lines from main.py
lines = [line for i, line in enumerate(lines) if i not in indices_to_delete]

# Add router inclusion
for i, line in enumerate(lines):
    if line.startswith('app = FastAPI('):
        j = i
        while not ')' in lines[j]:
            j += 1
        lines.insert(j + 1, '\nfrom routers.analytics import router as analytics_router\napp.include_router(analytics_router)\n')
        break

with open('routers/analytics.py', 'w', encoding='utf-8') as f:
    f.write(''.join(analytics_lines))

with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Analytics extracted successfully.')
