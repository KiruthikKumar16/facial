import { apiUrl, authFetch, handleResponse } from './config';
import type { ModelThresholds } from '../types';

import { adaptThresholds, reverseAdaptThresholds } from './adapters';

export const fetchThresholds = async (): Promise<ModelThresholds> => {
  const response = await authFetch('/api/thresholds')
  const raw = await handleResponse<unknown>(response)
  try {
    return adaptThresholds(raw)
  } catch (e) {
    console.error('fetchThresholds adapt failed:', e)
    return adaptThresholds({})
  }
}

export const saveThresholds = async (
  thresholds: ModelThresholds,
): Promise<ModelThresholds> => {
  const body = reverseAdaptThresholds(thresholds)
  const response = await authFetch('/api/thresholds', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const raw = await handleResponse<unknown>(response)
  try {
    return adaptThresholds(raw)
  } catch (e) {
    console.error('saveThresholds adapt failed:', e)
    return adaptThresholds({})
  }
}

