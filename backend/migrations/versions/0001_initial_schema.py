"""Initial database schema with pgvector, provenance, versioning, and idempotency constraints

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-02 08:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Cameras table
    op.create_table(
        'cameras',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('zone', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('rtsp_url', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('online', 'offline', 'degraded', name='camerastatus'), nullable=True),
        sa.Column('ping_ms', sa.Integer(), nullable=True),
        sa.Column('frame_latency_ms', sa.Integer(), nullable=True),
        sa.Column('fps', sa.Float(), nullable=True),
        sa.Column('gpu_load', sa.Float(), nullable=True),
        sa.Column('cpu_load', sa.Float(), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('detections_today', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cameras_id'), 'cameras', ['id'], unique=False)
    op.create_index(op.f('ix_cameras_name'), 'cameras', ['name'], unique=False)

    # 2. Profiles table
    op.create_table(
        'profiles',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('role', sa.Enum('visitor', 'contractor', 'employee', 'vip', 'blacklisted', name='profilerole'), nullable=True),
        sa.Column('department', sa.String(), nullable=True),
        sa.Column('embedding_status', sa.Enum('pending', 'active', 'failed', name='embeddingstatus'), nullable=True),
        sa.Column('embedding_count', sa.Integer(), nullable=True),
        sa.Column('enrolled_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_profiles_id'), 'profiles', ['id'], unique=False)
    op.create_index(op.f('ix_profiles_name'), 'profiles', ['name'], unique=False)

    # 3. Embeddings table
    op.create_table(
        'embeddings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('profile_id', sa.String(), nullable=False),
        sa.Column('vector', sa.Text(), nullable=False), # Vector(512) or serialized JSON fallback
        sa.Column('model_version', sa.String(), nullable=False, server_default='w600k_mbf_v1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['profile_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_embeddings_id'), 'embeddings', ['id'], unique=False)
    op.create_index(op.f('ix_embeddings_profile_id'), 'embeddings', ['profile_id'], unique=False)
    op.create_index(op.f('ix_embeddings_model_version'), 'embeddings', ['model_version'], unique=False)

    # 4. Detections table
    op.create_table(
        'detections',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('event_id', sa.String(), nullable=True),
        sa.Column('device_id', sa.String(), nullable=True),
        sa.Column('sequence_number', sa.Integer(), nullable=True),
        sa.Column('camera_id', sa.String(), nullable=False),
        sa.Column('profile_id', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('status', sa.Enum('recognized', 'unknown', 'flagged', name='detectionstatus'), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('liveness_score', sa.Float(), nullable=True),
        sa.Column('age', sa.Integer(), nullable=True),
        sa.Column('gender', sa.Enum('male', 'female', 'unknown', name='gender'), nullable=True),
        sa.Column('wearing_mask', sa.Boolean(), nullable=True),
        sa.Column('wearing_glasses', sa.Boolean(), nullable=True),
        sa.Column('bbox', sa.String(), nullable=True),
        sa.Column('priority', sa.Enum('normal', 'critical', name='eventpriority'), nullable=True),
        sa.Column('config_version', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('detection_model_version', sa.String(), nullable=True, server_default='scrfd_500m_bnkps_v1'),
        sa.Column('embedding_model_version', sa.String(), nullable=True, server_default='w600k_mbf_v1'),
        sa.Column('gallery_version', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('threshold_version', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('camera_config_version', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('algorithm_version', sa.String(), nullable=True, server_default='temporal_fusion_v2'),
        sa.Column('version_bundle_hash', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id']),
        sa.ForeignKeyConstraint(['profile_id'], ['profiles.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id')
    )
    op.create_index(op.f('ix_detections_id'), 'detections', ['id'], unique=False)
    op.create_index(op.f('ix_detections_event_id'), 'detections', ['event_id'], unique=True)
    op.create_index(op.f('ix_detections_device_id'), 'detections', ['device_id'], unique=False)
    op.create_index(op.f('ix_detections_sequence_number'), 'detections', ['sequence_number'], unique=False)
    op.create_index(op.f('ix_detections_camera_id'), 'detections', ['camera_id'], unique=False)
    op.create_index(op.f('ix_detections_profile_id'), 'detections', ['profile_id'], unique=False)
    op.create_index(op.f('ix_detections_timestamp'), 'detections', ['timestamp'], unique=False)
    op.create_index(op.f('ix_detections_status'), 'detections', ['status'], unique=False)
    op.create_index(op.f('ix_detections_priority'), 'detections', ['priority'], unique=False)

    # 5. Event Provenances table
    op.create_table(
        'event_provenances',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('camera_id', sa.String(), nullable=False),
        sa.Column('frame_reference', sa.String(), nullable=False),
        sa.Column('track_id', sa.String(), nullable=True),
        sa.Column('observation_references', sa.Text(), nullable=True),
        sa.Column('detection_model_version', sa.String(), nullable=False),
        sa.Column('embedding_model_version', sa.String(), nullable=False),
        sa.Column('embedding_fingerprint', sa.String(), nullable=False),
        sa.Column('candidate_matches', sa.Text(), nullable=True),
        sa.Column('decision_tier', sa.String(), nullable=False),
        sa.Column('selected_identity', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('decision_timestamp', sa.DateTime(), nullable=False),
        sa.Column('sync_event_id', sa.String(), nullable=True),
        sa.Column('provenance_chain_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['detections.event_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id')
    )
    op.create_index(op.f('ix_event_provenances_id'), 'event_provenances', ['id'], unique=False)
    op.create_index(op.f('ix_event_provenances_event_id'), 'event_provenances', ['event_id'], unique=True)
    op.create_index(op.f('ix_event_provenances_camera_id'), 'event_provenances', ['camera_id'], unique=False)

    # 6. Camera Configs table
    op.create_table(
        'camera_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('camera_id', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('detection_threshold', sa.Float(), nullable=True, server_default='0.50'),
        sa.Column('recognition_threshold', sa.Float(), nullable=True, server_default='0.35'),
        sa.Column('quality_thresholds', sa.Text(), nullable=True),
        sa.Column('sampling_rate', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('temporal_window', sa.Float(), nullable=True, server_default='3.0'),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_camera_configs_id'), 'camera_configs', ['id'], unique=False)
    op.create_index(op.f('ix_camera_configs_camera_id'), 'camera_configs', ['camera_id'], unique=False)
    op.create_index(op.f('ix_camera_configs_version'), 'camera_configs', ['version'], unique=False)
    op.create_index(op.f('ix_camera_configs_is_active'), 'camera_configs', ['is_active'], unique=False)

    # 7. Alerts table
    op.create_table(
        'alerts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('detection_id', sa.String(), nullable=True),
        sa.Column('camera_id', sa.String(), nullable=False),
        sa.Column('profile_id', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('severity', sa.String(), nullable=True),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('acknowledged', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id']),
        sa.ForeignKeyConstraint(['detection_id'], ['detections.id']),
        sa.ForeignKeyConstraint(['profile_id'], ['profiles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_alerts_id'), 'alerts', ['id'], unique=False)
    op.create_index(op.f('ix_alerts_camera_id'), 'alerts', ['camera_id'], unique=False)
    op.create_index(op.f('ix_alerts_detection_id'), 'alerts', ['detection_id'], unique=False)

    # 8. Camera Transitions table
    op.create_table(
        'camera_transitions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('profile_id', sa.String(), nullable=False),
        sa.Column('from_camera_id', sa.String(), nullable=False),
        sa.Column('to_camera_id', sa.String(), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('travel_seconds', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('transition_type', sa.String(), nullable=True, server_default='CONFIRMED'),
        sa.Column('similarity', sa.Float(), nullable=True),
        sa.Column('temporal_score', sa.Float(), nullable=True),
        sa.Column('reasoning_metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['from_camera_id'], ['cameras.id']),
        sa.ForeignKeyConstraint(['to_camera_id'], ['cameras.id']),
        sa.ForeignKeyConstraint(['profile_id'], ['profiles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_camera_transitions_id'), 'camera_transitions', ['id'], unique=False)
    op.create_index(op.f('ix_camera_transitions_from_camera_id'), 'camera_transitions', ['from_camera_id'], unique=False)
    op.create_index(op.f('ix_camera_transitions_to_camera_id'), 'camera_transitions', ['to_camera_id'], unique=False)
    op.create_index(op.f('ix_camera_transitions_profile_id'), 'camera_transitions', ['profile_id'], unique=False)

    # 9. Model Thresholds table
    op.create_table(
        'model_thresholds',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_model_thresholds_id'), 'model_thresholds', ['id'], unique=False)

    # 10. Sequence Acknowledgments table
    op.create_table(
        'sequence_acknowledgments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('camera_id', sa.String(), nullable=False),
        sa.Column('last_acknowledged_sequence', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_synced_event_id', sa.String(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['last_synced_event_id'], ['detections.event_id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sequence_acknowledgments_id'), 'sequence_acknowledgments', ['id'], unique=False)
    op.create_index(op.f('ix_sequence_acknowledgments_device_id'), 'sequence_acknowledgments', ['device_id'], unique=False)
    op.create_index(op.f('ix_sequence_acknowledgments_camera_id'), 'sequence_acknowledgments', ['camera_id'], unique=False)


def downgrade() -> None:
    op.drop_table('sequence_acknowledgments')
    op.drop_table('model_thresholds')
    op.drop_table('camera_transitions')
    op.drop_table('alerts')
    op.drop_table('camera_configs')
    op.drop_table('event_provenances')
    op.drop_table('detections')
    op.drop_table('embeddings')
    op.drop_table('profiles')
    op.drop_table('cameras')
