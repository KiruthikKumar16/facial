#!/usr/bin/env python3
"""
Migrate existing CSV detection files to SQLite EventLedger.

This script:
1. Scans for detections-*.csv files
2. Migrates all events to facial_recognition.db
3. Backs up original CSV files
4. Verifies migration integrity
5. Provides statistics

Usage:
    python migrate_csv_to_ledger.py [--csv-dir DIR] [--db-path DB] [--backup]
"""

import argparse
import csv
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from facial_recognition.event_ledger import EventLedger, EventLedgerMigrator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate(csv_dir: str, db_path: str, backup: bool = True) -> None:
    """
    Migrate CSV files to SQLite ledger.
    
    Args:
        csv_dir: Directory containing CSV files
        db_path: Path to SQLite database
        backup: Whether to backup CSV files before migration
    """
    csv_path = Path(csv_dir)
    db_file = Path(db_path)
    
    # Ensure paths
    csv_path.mkdir(parents=True, exist_ok=True)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"CSV directory: {csv_path}")
    logger.info(f"Database: {db_file}")
    
    # Find CSV files
    csv_files = list(csv_path.glob("detections-*.csv"))
    if not csv_files:
        logger.warning("No CSV files found matching pattern 'detections-*.csv'")
        return
    
    logger.info(f"Found {len(csv_files)} CSV files to migrate")
    
    # Backup
    if backup:
        backup_dir = csv_path / "backup"
        backup_dir.mkdir(exist_ok=True)
        for csv_file in csv_files:
            backup_file = backup_dir / f"{csv_file.name}.bak-{datetime.now().timestamp()}"
            shutil.copy2(csv_file, backup_file)
            logger.info(f"Backed up {csv_file.name} to {backup_file}")
    
    # Create ledger
    ledger = EventLedger(db_path=str(db_file), device_id="edge-node")
    
    # Migrate
    try:
        results = EventLedgerMigrator.migrate_csv_files(
            str(csv_path),
            ledger,
            pattern="detections-*.csv"
        )
        
        logger.info("=" * 60)
        logger.info("Migration Results:")
        logger.info(f"  Total files processed: {results['total_files']}")
        logger.info(f"  Total events migrated: {results['total_events']}")
        logger.info(f"  Skipped events: {results['skipped_events']}")
        logger.info(f"  Migration errors: {results['errors']}")
        
        # Get final stats
        stats = ledger.get_stats()
        logger.info("=" * 60)
        logger.info("Database Statistics:")
        logger.info(f"  Total events: {stats['total_events']}")
        logger.info(f"  Pending sync: {stats['pending_events']}")
        logger.info(f"  Already synced: {stats['synced_events']}")
        logger.info(f"  Failed: {stats['failed_events']}")
        
        if results['errors'] > 0:
            logger.warning(f"⚠️  {results['errors']} events failed to migrate")
        else:
            logger.info("✓ Migration completed successfully")
        
    finally:
        ledger.close()


def main():
    """Parse arguments and run migration."""
    parser = argparse.ArgumentParser(
        description="Migrate CSV detection files to SQLite EventLedger"
    )
    parser.add_argument(
        "--csv-dir",
        default="facial_recognition",
        help="Directory containing CSV files (default: facial_recognition)"
    )
    parser.add_argument(
        "--db-path",
        default="facial_recognition.db",
        help="Path to SQLite database (default: facial_recognition.db)"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Backup CSV files before migration (default: True)"
    )
    parser.add_argument(
        "--no-backup",
        dest="backup",
        action="store_false",
        help="Skip backing up CSV files"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("CSV to EventLedger Migration Tool")
    logger.info("=" * 60)
    
    migrate(args.csv_dir, args.db_path, backup=args.backup)


if __name__ == "__main__":
    main()
