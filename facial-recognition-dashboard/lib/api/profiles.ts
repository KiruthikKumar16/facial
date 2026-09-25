import { apiUrl, authFetch, handleResponse } from './config';
import type { Profile, ProfileRole } from '../types';

import { adaptProfile } from './adapters';

export const fetchProfiles = async (): Promise<Profile[]> => {
  const response = await authFetch('/api/profiles')
  const raw = await handleResponse<unknown>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.profiles ?? []
    return arr
      .map((item: unknown) => {
        try {
          return adaptProfile(item)
        } catch (e) {
          console.error('adaptProfile failed:', e)
          return null
        }
      })
      .filter(Boolean) as Profile[]
  } catch (e) {
    console.error('fetchProfiles adapter failed:', e)
    return []
  }
}

export const fetchProfile = async (profileId: string): Promise<Profile | null> => {
  const response = await authFetch(
    apiUrl(`/api/profiles/${encodeURIComponent(profileId)}`),
  )
  const raw = await handleResponse<unknown>(response)
  try {
    return raw ? adaptProfile(raw) : null
  } catch (e) {
    console.error('fetchProfile adapt failed:', e)
    return null
  }
}

export const createProfile = async (
  payload: CreateProfilePayload,
): Promise<Profile> => {
  const formData = new FormData()
  formData.append('name', payload.name)
  if (payload.role !== undefined) formData.append('role', payload.role)
  if (payload.department !== undefined)
    formData.append('department', payload.department)
  if (payload.age !== undefined)
    formData.append('age', String(payload.age))
  if (payload.gender !== undefined)
    formData.append('gender', payload.gender)
  if (payload.notes !== undefined && payload.notes !== '')
    formData.append('notes', payload.notes)
  if (payload.photos && payload.photos.length > 0) {
    for (const photo of payload.photos) {
      formData.append('photos', photo)
    }
  }

  const response = await authFetch('/api/profiles', {
    method: 'POST',
    body: formData,
  })
  const raw = await handleResponse<unknown>(response)
  try {
    return adaptProfile(raw)
  } catch (e) {
    console.error('createProfile adapt failed:', e)
    return adaptProfile({ id: '', name: payload.name })
  }
}

export const mergeProfiles = async (
  profileAId: string,
  profileBId: string,
  keepProfileId?: string,
  deleteMerged: boolean = true,
): Promise<MergeProfilesResult> => {
  const body: unknown = {
    profileAId,
    profileBId,
    deleteMerged,
  }
  if (keepProfileId !== undefined) {
    body.keepProfile = keepProfileId
    body.keepProfileId = keepProfileId
  }

  const response = await authFetch('/api/profiles/merge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const raw = await handleResponse<unknown>(response)
  try {
    return {
      merged: true,
      keptProfileId: strOrEmpty(
        raw.keptProfileId ?? raw.kept_profile_id ?? keepProfileId ?? profileAId,
      ),
      deletedProfileId: strOrEmpty(
        raw.deletedProfileId ?? raw.deleted_profile_id ??
          (keepProfileId === profileAId ? profileBId : profileAId),
      ),
    }
  } catch (e) {
    console.error('mergeProfiles adapt failed:', e)
    return {
      merged: true,
      keptProfileId: keepProfileId ?? profileAId,
      deletedProfileId: keepProfileId === profileAId ? profileBId : profileAId,
    }
  }
}

export const deleteProfile = async (profileId: string): Promise<void> => {
  const response = await authFetch(`/api/profiles/${encodeURIComponent(profileId)}`, {
    method: 'DELETE',
  })
  await handleResponse<unknown>(response)
}

export const deleteProfileEmbeddings = async (profileId: string): Promise<void> => {
  const response = await authFetch(`/api/profiles/${encodeURIComponent(profileId)}/embeddings`, {
    method: 'DELETE',
  })
  await handleResponse<unknown>(response)
}

export const updateProfile = async (profileId: string, { name, role, department }: { name: string; role: ProfileRole; department: string }): Promise<void> => {
  const response = await authFetch(`/api/profiles/${encodeURIComponent(profileId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, role, department }),
  })
  await handleResponse<unknown>(response)
}

