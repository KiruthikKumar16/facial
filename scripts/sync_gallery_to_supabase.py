#!/usr/bin/env python3
"""Upload local gallery.npz identities into Supabase via SQLAlchemy.

Usage (from repo root):
    python scripts/sync_gallery_to_supabase.py

Requires DATABASE_URL in backend/.env or environment.
Reads: facial_recognition/known_faces/gallery.npz
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
GALLERY_PATH = REPO_ROOT / "facial_recognition" / "known_faces" / "gallery.npz"

sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    Embedding,
    EmbeddingStatus as EmbeddingStatusEnum,
    Profile,
    ProfileRole as ProfileRoleEnum,
)


def main() -> None:
    if not GALLERY_PATH.exists():
        raise SystemExit(f"Gallery not found: {GALLERY_PATH}")

    data = np.load(GALLERY_PATH, allow_pickle=True)
    labels = list(data["labels"])
    embeddings = np.asarray(data["embeddings"], dtype=np.float32)
    if embeddings.ndim == 1:
        embeddings = embeddings.reshape(1, -1)

    db = SessionLocal()
    created_profiles = 0
    created_embeddings = 0

    try:
        for label, vector in zip(labels, embeddings):
            name = str(label)
            profile = db.query(Profile).filter(Profile.name == name).first()
            if profile is None:
                profile = Profile(
                    id=str(uuid.uuid4()),
                    name=name,
                    role=ProfileRoleEnum.visitor,
                    embedding_status=EmbeddingStatusEnum.pending,
                    embedding_count=0,
                )
                db.add(profile)
                db.commit()
                db.refresh(profile)
                created_profiles += 1

            emb = Embedding(
                id=str(uuid.uuid4()),
                profile_id=profile.id,
                vector=vector.tolist(),
            )
            db.add(emb)
            profile.embedding_count = (profile.embedding_count or 0) + 1
            profile.embedding_status = EmbeddingStatusEnum.indexed
            created_embeddings += 1

        db.commit()
        print(
            f"Synced gallery: {len(labels)} vectors, "
            f"{created_profiles} new profiles, {created_embeddings} embeddings written."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
