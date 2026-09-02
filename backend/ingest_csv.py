"""Import CSV detections into PostgreSQL database."""
import csv
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def parse_bbox(bbox_str: str) -> list[int]:
    """Parse bbox from string format '[x1, y1, x2, y2]'."""
    try:
        bbox_str = bbox_str.strip().strip('[]')
        parts = [int(float(x.strip())) for x in bbox_str.split(',')]
        return parts[:4]
    except Exception:
        return [0, 0, 0, 0]


def ingest_csv_to_db(csv_path: str, db_url: str, batch_size: int = 100) -> None:
    """Load detections from CSV into PostgreSQL database."""
    
    # Import models here to avoid circular dependency
    from backend.models import Detection, DetectionStatus as DetectionStatusEnum
    
    # Setup database
    engine = create_engine(db_url, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"❌ CSV file not found: {csv_path}")
        return
    
    print(f"📥 Importing detections from {csv_file}...")
    
    try:
        # Read CSV
        df = pd.read_csv(csv_file)
        print(f"   Found {len(df)} records")
        
        # Batch insert
        batch = []
        for idx, row in df.iterrows():
            # Parse timestamp
            try:
                timestamp = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            except Exception:
                timestamp = datetime.now(timezone.utc)
            
            # Parse bbox
            bbox = parse_bbox(str(row.get('bbox', '[]')))
            
            # Determine status
            identity = str(row.get('identity', 'Unknown')).lower()
            status = DetectionStatusEnum.unknown
            profile_id = None
            
            if identity != 'unknown':
                status = DetectionStatusEnum.recognized
                profile_id = identity.replace(' ', '-')
            
            # Create detection
            detection = Detection(
                id=str(uuid4()),
                camera_id=str(row.get('camera_id', 'unknown')),
                profile_id=profile_id,
                timestamp=timestamp,
                status=status,
                confidence=float(row.get('confidence', 0.0)),
                bbox=f"[{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]",
                liveness_score=0.0,
                age=None,
                gender="unknown",
                wearing_mask=False,
                wearing_glasses=False,
            )
            batch.append(detection)
            
            # Commit in batches
            if len(batch) >= batch_size:
                db.add_all(batch)
                db.commit()
                print(f"   ✓ Imported {len(batch)} records")
                batch = []
        
        # Final batch
        if batch:
            db.add_all(batch)
            db.commit()
            print(f"   ✓ Imported {len(batch)} records")
        
        print(f"✅ Successfully imported {len(df)} detections to database")
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    # Configuration
    CSV_FILE = "detections.csv"
    DB_URL = "postgresql://postgres:postgres@localhost:5432/facial_recognition"
    
    print("=" * 60)
    print("CSV → PostgreSQL Ingestion Tool")
    print("=" * 60)
    print()
    
    # Allow CLI override
    if len(sys.argv) > 1:
        CSV_FILE = sys.argv[1]
    if len(sys.argv) > 2:
        DB_URL = sys.argv[2]
    
    print(f"CSV File: {CSV_FILE}")
    print(f"Database: {DB_URL}")
    print()
    
    ingest_csv_to_db(CSV_FILE, DB_URL)
