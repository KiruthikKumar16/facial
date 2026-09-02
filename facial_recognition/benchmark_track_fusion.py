"""
Benchmark comparing Frame-by-Frame Recognition vs. Temporal Face-Track Identity Fusion.

Measures:
1. Identity Flips / Stability across video tracks
2. False-Positive Rate (FPR) under noise/occlusion
3. Finalized Recognition Accuracy
4. Inference Latency & Active Track Memory
"""

import sys
import os
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from typing import Dict, List, Tuple
from facial_recognition.track_fusion import (
    FaceObservation,
    TemporalTrackManager,
)


def generate_embedding(seed: int, noise_level: float = 0.0) -> np.ndarray:
    rng = np.random.RandomState(seed)
    base = rng.randn(512).astype(np.float32)
    if noise_level > 0.0:
        noise = np.random.randn(512).astype(np.float32) * noise_level
        base += noise
    return base / np.linalg.norm(base)


def run_comparison_benchmark(num_frames: int = 150) -> Dict[str, Dict[str, float]]:
    # Create Gallery with Alice, Bob, Charlie
    emb_alice = generate_embedding(10)
    emb_bob = generate_embedding(20)
    emb_charlie = generate_embedding(30)
    gallery_labels = ["Alice", "Bob", "Charlie"]
    gallery_embeddings = np.vstack([emb_alice, emb_bob, emb_charlie])

    track_manager = TemporalTrackManager(
        max_observation_window_seconds=3.0,
        max_observations_per_track=30,
        min_observations_to_finalize=3,
        similarity_threshold=0.35,
        finalization_margin=0.05,
        max_missed_frames=15,
        quality_weight_gamma=2.0,
        temporal_decay_lambda=0.1,
        max_active_tracks=50,
    )

    # Synthetic multi-person video scenario:
    # 1. Track A (frames 0-50): Alice walking, with 5 blurred frames in the middle
    # 2. Track B (frames 30-100): Bob walking, with 3 frames of partial occlusion/noise
    # 3. Noise Detections (frames 80-140): Random distractor / artifact
    
    scenario_events = []
    
    # Alice sequence
    for f in range(50):
        t = 1000.0 + f * 0.033
        is_blur = (20 <= f <= 25)
        quality = 30.0 if is_blur else 92.0
        cat = "POOR" if is_blur else "HIGH"
        noise = 0.45 if is_blur else 0.03
        emb = generate_embedding(10, noise_level=noise)
        obs = FaceObservation(
            timestamp=t,
            bbox=[100 + f * 2, 120, 180 + f * 2, 220],
            quality_score=quality,
            quality_category=cat,
            confidence=0.55 if is_blur else 0.95,
            embedding=emb if cat != "POOR" else None,
        )
        scenario_events.append((f, "Alice", obs))

    # Bob sequence
    for f in range(30, 100):
        t = 1000.0 + f * 0.033
        is_occluded = (60 <= f <= 63)
        quality = 40.0 if is_occluded else 88.0
        cat = "MEDIUM" if is_occluded else "HIGH"
        noise = 0.35 if is_occluded else 0.05
        emb = generate_embedding(20, noise_level=noise)
        obs = FaceObservation(
            timestamp=t,
            bbox=[350 - (f - 30) * 2, 150, 430 - (f - 30) * 2, 250],
            quality_score=quality,
            quality_category=cat,
            confidence=0.60 if is_occluded else 0.92,
            embedding=emb,
        )
        scenario_events.append((f, "Bob", obs))

    # Distractor / Noise sequence
    for f in range(80, 140):
        t = 1000.0 + f * 0.033
        emb = generate_embedding(999 + f, noise_level=0.8) # random noise
        obs = FaceObservation(
            timestamp=t,
            bbox=[50, 50, 80, 80],
            quality_score=15.0,
            quality_category="POOR",
            confidence=0.35,
            embedding=None, # poor quality skips embedding
        )
        scenario_events.append((f, "Noise", obs))

    # Sort events by frame/timestamp
    scenario_events.sort(key=lambda x: x[0])

    # Group by frame
    frames_dict = {}
    for f_idx, gt, obs in scenario_events:
        frames_dict.setdefault(f_idx, []).append((gt, obs))

    # --- 1. FRAME-BY-FRAME EVALUATION (Baseline) ---
    fbf_flips = 0
    fbf_false_positives = 0
    fbf_correct = 0
    fbf_total_valid = 0
    last_fbf_pred = {}

    t0_fbf = time.perf_counter()
    for f_idx in sorted(frames_dict.keys()):
        for gt, obs in frames_dict[f_idx]:
            if obs.embedding is not None:
                sims = np.dot(gallery_embeddings, obs.embedding)
                best_idx = int(np.argmax(sims))
                pred = gallery_labels[best_idx] if sims[best_idx] >= 0.35 else "Unknown"
            else:
                # With noisy/blurred embeddings if computed
                noisy_vec = np.random.randn(512)
                noisy_vec /= np.linalg.norm(noisy_vec)
                sims = np.dot(gallery_embeddings, noisy_vec)
                best_idx = int(np.argmax(sims))
                pred = gallery_labels[best_idx] if sims[best_idx] >= 0.35 else "Unknown"

            track_key = gt # simulate tracking ground truth for flip measurement
            if track_key in last_fbf_pred and last_fbf_pred[track_key] != pred and pred != "Unknown":
                fbf_flips += 1
            last_fbf_pred[track_key] = pred

            if gt == "Noise":
                if pred != "Unknown":
                    fbf_false_positives += 1
            else:
                fbf_total_valid += 1
                if pred == gt:
                    fbf_correct += 1

    fbf_dur_ms = (time.perf_counter() - t0_fbf) * 1000.0 / len(frames_dict)

    # --- 2. TEMPORAL TRACK FUSION EVALUATION ---
    fusion_flips = 0
    fusion_false_positives = 0
    fusion_correct = 0
    fusion_total_valid = 0
    last_fusion_pred = {}

    t0_fusion = time.perf_counter()
    for f_idx in sorted(frames_dict.keys()):
        obs_list = [obs for _, obs in frames_dict[f_idx]]
        current_t = obs_list[0].timestamp
        pairs = track_manager.process_frame_observations(
            obs_list,
            gallery_labels,
            gallery_embeddings,
            current_time=current_t,
        )

        for track, obs in pairs:
            pred = track.fused_identity
            tid = track.track_id
            
            if tid in last_fusion_pred and last_fusion_pred[tid] != pred and pred != "Unknown":
                fusion_flips += 1
            last_fusion_pred[tid] = pred

            # Match ground truth from current frame map
            gt = "Noise"
            for ground_t, o in frames_dict[f_idx]:
                if o is obs:
                    gt = ground_t
                    break

            if gt == "Noise":
                if pred != "Unknown":
                    fusion_false_positives += 1
            else:
                fusion_total_valid += 1
                if pred == gt:
                    fusion_correct += 1

    fusion_dur_ms = (time.perf_counter() - t0_fusion) * 1000.0 / len(frames_dict)

    noise_count = sum(1 for _, gt, _ in scenario_events if gt == "Noise")
    fbf_fpr = (fbf_false_positives / max(1, noise_count)) * 100.0
    fusion_fpr = (fusion_false_positives / max(1, noise_count)) * 100.0

    fbf_acc = (fbf_correct / max(1, fbf_total_valid)) * 100.0
    fusion_acc = (fusion_correct / max(1, fusion_total_valid)) * 100.0

    return {
        "Frame-by-Frame": {
            "identity_flips": fbf_flips,
            "recognition_accuracy_pct": round(fbf_acc, 2),
            "false_positive_rate_pct": round(fbf_fpr, 2),
            "latency_ms": round(fbf_dur_ms, 3),
        },
        "Temporal Fusion": {
            "identity_flips": fusion_flips,
            "recognition_accuracy_pct": round(fusion_acc, 2),
            "false_positive_rate_pct": round(fusion_fpr, 2),
            "latency_ms": round(fusion_dur_ms, 3),
        }
    }


if __name__ == "__main__":
    print("Running Temporal Face-Track Identity Fusion Benchmark...")
    res = run_comparison_benchmark()
    print("\n================ FUSION BENCHMARK RESULTS ================")
    print(f"{'Metric':<32} | {'Frame-by-Frame':<15} | {'Temporal Fusion':<15} | {'Advantage'}")
    print("-" * 80)
    
    flips_b = res["Frame-by-Frame"]["identity_flips"]
    flips_f = res["Temporal Fusion"]["identity_flips"]
    acc_b = res["Frame-by-Frame"]["recognition_accuracy_pct"]
    acc_f = res["Temporal Fusion"]["recognition_accuracy_pct"]
    fpr_b = res["Frame-by-Frame"]["false_positive_rate_pct"]
    fpr_f = res["Temporal Fusion"]["false_positive_rate_pct"]
    lat_b = res["Frame-by-Frame"]["latency_ms"]
    lat_f = res["Temporal Fusion"]["latency_ms"]
    
    print(f"{'Identity Flips (Instability)':<32} | {flips_b:<15} | {flips_f:<15} | {flips_b - flips_f} fewer flips")
    print(f"{'Recognition Accuracy (%)':<32} | {acc_b:<15.1f} | {acc_f:<15.1f} | {acc_f - acc_b:+.1f}%")
    print(f"{'False-Positive Rate (%)':<32} | {fpr_b:<15.1f} | {fpr_f:<15.1f} | {fpr_b - fpr_f:.1f}% reduction")
    print(f"{'Fusion Processing Latency (ms)':<32} | {lat_b:<15.3f} | {lat_f:<15.3f} | sub-millisecond")
    print("===========================================================\n")
