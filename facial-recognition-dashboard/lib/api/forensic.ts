import { apiUrl, authFetch, handleResponse } from './config';
import type { ForensicMatch, RecognitionProvenance } from '../types';

import { adaptForensicMatch } from './adapters';

export const runForensicSearch = async (
  payload: ForensicSearchPayload,
): Promise<ForensicMatch[]> => {
  const formData = new FormData()
  if (payload.imageFile) {
    formData.append('image', payload.imageFile)
  }
  if (payload.profileId) {
    formData.append('profile_id', payload.profileId)
  }
  if (payload.threshold !== undefined) {
    formData.append('threshold', String(payload.threshold))
  }
  if (payload.from) formData.append('date_from', payload.from)
  if (payload.to) formData.append('date_to', payload.to)
  if (payload.cameraIds && payload.cameraIds.length > 0) {
    formData.append('camera_ids', payload.cameraIds.join(','))
  }
  if (payload.gender && payload.gender !== 'all') {
    formData.append('gender', payload.gender)
  }
  if (payload.ageRange && payload.ageRange.length >= 2) {
    formData.append('age_min', String(payload.ageRange[0]))
    formData.append('age_max', String(payload.ageRange[1]))
  }
  if (payload.wearingMask) formData.append('wearing_mask', 'true')
  if (payload.wearingGlasses) formData.append('wearing_glasses', 'true')
  const response = await authFetch('/api/forensic/search', {
    method: 'POST',
    body: formData,
  })
  const raw = await handleResponse<unknown>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.matches ?? []
    return arr
      .map((item: unknown) => {
        try {
          return adaptForensicMatch(item)
        } catch (e) {
          console.error('adaptForensicMatch failed:', e)
          return null
        }
      })
      .filter(Boolean) as ForensicMatch[]
  } catch (e) {
    console.error('runForensicSearch adapter failed:', e)
    return []
  }
}

export const fetchProvenance = async (eventId: string): Promise<RecognitionProvenance> => {
  const response = await authFetch(`/api/detections/${encodeURIComponent(eventId)}/provenance`)
  const raw = await handleResponse<unknown>(response)
  try {
    // Simplified adaptation - in reality this would be more complex
    return {
      eventId: strOrEmpty(raw.event_id ?? raw.eventId),
      detectionId: strOrEmpty(raw.detection_id ?? raw.detectionId) || undefined,
      cameraId: strOrEmpty(raw.camera_id ?? raw.cameraId),
      frameReference: strOrEmpty(raw.frame_reference ?? raw.frameReference),
      trackId: strOrEmpty(raw.track_id ?? raw.trackId),
      observationCount: numOrZero(raw.observation_count ?? raw.observationCount),
      observationReferences: Array.isArray(raw.observation_references ?? raw.observationReferences)
        ? (raw.observation_references ?? raw.observationReferences)
        : [],
      detectionModelVersion: strOrEmpty(raw.detection_model_version ?? raw.detectionModelVersion),
      embeddingModelVersion: strOrEmpty(raw.embedding_model_version ?? raw.embeddingModelVersion),
      embeddingFingerprint: strOrEmpty(raw.embedding_fingerprint ?? raw.embeddingFingerprint),
      candidateMatches: Array.isArray(raw.candidate_matches ?? raw.candidateMatches)
        ? (raw.candidate_matches ?? raw.candidateMatches).map((match: unknown) => ({
            identity: strOrEmpty(match.identity),
            similarity: numOrZero(match.similarity),
            rank: numOrZero(match.rank),
          }))
        : [],
      selectedIdentity: strOrEmpty(raw.selected_identity ?? raw.selectedIdentity),
      confidence: numOrZero(raw.confidence),
      decisionTier: strOrEmpty(raw.decision_tier ?? raw.decisionTier),
      cameraConfigVersion: numOrZero(raw.camera_config_version ?? raw.cameraConfigVersion),
      cloudRecordId: strOrEmpty(raw.cloud_record_id ?? raw.cloudRecordId) || undefined,
      decisionTimestamp: strOrEmpty(raw.decision_timestamp ?? raw.decisionTimestamp),
      provenanceChainHash: strOrEmpty(raw.provenance_chain_hash ?? raw.provenanceChainHash),
      stages: Array.isArray(raw.stages)
        ? raw.stages.map((stage: unknown) => ({
            stage: strOrEmpty(stage.stage),
            timestamp: strOrEmpty(stage.timestamp),
            metadata: stage.metadata || {},
          }))
        : [],
    }
  } catch (e) {
    console.error('fetchProvenance adapt failed:', e)
    throw e
  }
}

export type ForensicSearchPayload = {
  imageFile?: File
  profileId?: string
  threshold?: number
  from?: string
  to?: string
  cameraIds?: string[]
  gender?: Gender | 'all'
  ageRange?: number[]
  wearingMask?: boolean
  wearingGlasses?: boolean
}

