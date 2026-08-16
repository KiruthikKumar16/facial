"""
Ingest detections.csv into Supabase database.

Run locally to import historical detection data:
    python backend/tasks/ingest_csv.py --database-url "postgresql://..."
"""

import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def parse_bbox(bbox_str: str) -> str:
    """Parse bounding box string to JSON format."""
    try:
        if isinstance(bbox_str, str):
            bbox_str = bbox_str.strip().lstrip('[').rstrip(']')
            parts = [p.strip() for p in bbox_str.split(',')]
            return f"[{','.join(parts)}]"
    except Exception as e:
        logger.warning(f"Could not parse bbox {bbox_str}: {e}")
    return "[]"


def ingest_csv(database_url: str, csv_path: str = None) -> int:
    """
    Load detections.csv into database.
    
    Args:
        database_url: PostgreSQL connection string from Supabase
        csv_path: Path to detections.csv (default: ../detections.csv)
    
    Returns:
        Number of records ingested
    """
    
    # Find CSV file
    if csv_path is None:
        # Try common locations
        possible_paths = [
            Path(__file__).parent.parent.parent / 'detections.csv',
            Path('detections.csv'),
            Path('../detections.csv'),
        ]
        for p in possible_paths:
            if p.exists():
                csv_path = p
                break
        else:
            logger.error("Could not find detections.csv")
            return 0
    
    csv_path = Path(csv_path)
    logger.info(f"Loading {csv_path}...")
    
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        return 0
    
    logger.info(f"Loaded {len(df)} rows from {csv_path}")
    
    # Connect to database
    try:
        engine = create_engine(database_url)
        conn = engine.connect()
        logger.info("✓ Connected to database")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.error("Verify DATABASE_URL is correct")
        return 0
    
    # Insert records
    inserted = 0
    skipped = 0
    
    try:
        for idx, row in df.iterrows():
            try:
                # Generate UUID
                detection_id = str(uuid.uuid4())
                
                # Parse timestamp
                try:
                    timestamp = pd.to_datetime(row['timestamp'])
                except:
                    logger.warning(f"Row {idx}: Invalid timestamp {row['timestamp']}, skipping")
                    skipped += 1
                    continue
                
                # Determine status
                identity = str(row.get('identity', 'Unknown')).strip()
                status = 'unknown' if identity == 'Unknown' else 'recognized'
                
                # Parse confidence
                try:
                    confidence = float(row.get('confidence', 0.0))
                except:
                    confidence = 0.0
                
                # Parse bbox
                bbox = parse_bbox(str(row.get('bbox', '[]')))
                
                # Insert via SQL
                insert_query = text("""
                    INSERT INTO detections 
                    (id, camera_id, timestamp, status, confidence, bbox, created_at)
                    VALUES (:id, :camera_id, :timestamp, :status, :confidence, :bbox, :created_at)
                """)
                
                conn.execute(insert_query, {
                    'id': detection_id,
                    'camera_id': str(row.get('camera_id', 'unknown')).strip(),
                    'timestamp': timestamp,
                    'status': status,
                    'confidence': confidence,
                    'bbox': bbox,
                    'created_at': datetime.utcnow(),
                })
                
                inserted += 1
                
                # Progress indicator
                if (idx + 1) % 100 == 0:
                    logger.info(f"  Processed {idx + 1}/{len(df)} rows...")
                    
            except Exception as e:
                logger.warning(f"Row {idx}: {e}")
                skipped += 1
                continue
        
        # Commit all changes
        conn.commit()
        logger.info(f"✓ Committed {inserted} records to database")
        
    except Exception as e:
        logger.error(f"Batch insert failed: {e}")
        conn.rollback()
        return 0
    finally:
        conn.close()
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"✓ Ingestion complete!")
    logger.info(f"  Inserted:  {inserted}")
    logger.info(f"  Skipped:   {skipped}")
    logger.info(f"  Total:     {len(df)}")
    logger.info("=" * 60)
    
    return inserted


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Ingest detections.csv to Supabase')
    parser.add_argument(
        '--database-url',
        required=True,
        help='PostgreSQL connection string from Supabase'
    )
    parser.add_argument(
        '--csv-path',
        default=None,
        help='Path to detections.csv (auto-detected if not specified)'
    )
    
    args = parser.parse_args()
    
    # Validate URL
    if not args.database_url.startswith('postgresql://'):
        logger.error("❌ DATABASE_URL must start with 'postgresql://'")
        sys.exit(1)
    
    # Run ingestion
    result = ingest_csv(args.database_url, args.csv_path)
    sys.exit(0 if result > 0 else 1)
