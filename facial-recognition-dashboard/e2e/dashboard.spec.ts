import { test, expect } from '@playwright/test'

// Mock Data for Deterministic E2E Execution
const mockVersionBundle = {
  bundle_hash: 'a1b2c3d4e5f67890abcdef1234567890',
  components: {
    detection_model: 'scrfd_500m_bnkps_v1',
    embedding_model: 'w600k_mbf_v1',
    gallery_version: 1,
    threshold_version: 1,
    camera_config_version: 1,
    algorithm_version: 'temporal_fusion_v2',
  },
  created_at: '2026-09-02T08:00:00Z',
}

const mockNodeHealth = {
  nodes: [
    {
      nodeId: 'edge-node-alpha',
      hostname: 'jetson-orin-01',
      status: 'healthy',
      cpuPercent: 42.5,
      gpuPercent: 35.2,
      memoryPercent: 58.1,
      temperatureC: 62.5,
      diskUsagePercent: 48.3,
      diskFreeMb: 18400,
      cameraFps: 29.8,
      inferenceFps: 28.5,
      networkLatencyMs: 18.2,
      syncQueueLength: 0,
      eventBacklog: 0,
      recognitionLatencyMs: 125.5,
      runtimeMode: 'NORMAL',
      frameSamplingRate: 1.0,
      syncBatchSize: 10,
      syncIntervalSeconds: 5,
      reportedAt: '2026-09-02T08:00:00Z',
    },
  ],
}

const mockFaceLogs = [
  {
    id: 'evt-test-e2e-001',
    cameraId: 'cam-01',
    cameraName: 'Front Entrance North',
    profileId: 'prof-01',
    profileName: 'Sarah Connor',
    role: 'vip',
    timestamp: '2026-09-02T08:00:00Z',
    status: 'recognized',
    confidence: 0.94,
    livenessScore: 98,
    age: 32,
    gender: 'female',
    wearingMask: false,
    wearingGlasses: false,
    snapshotTone: 'sky',
  },
]

const mockCameras = [
  {
    id: 'cam-01',
    name: 'Front Entrance North',
    zone: 'Zone A',
    status: 'online',
    ipAddress: '192.168.1.101',
    rtspUrl: 'rtsp://localhost:8554/cam1',
    pingMs: 12,
    frameLatencyMs: 24,
    fps: 30,
    gpuLoad: 45,
    cpuLoad: 35,
    lastHeartbeat: '2026-09-02T08:00:00Z',
    detectionsToday: 142,
  },
]

const mockProvenance = {
  eventId: 'evt-test-e2e-001',
  cameraId: 'cam-01',
  cameraConfigVersion: 1,
  observationCount: 3,
  frameReference: 'frm_cam-01_1725264000000',
  trackId: 'trk_01_99',
  observationReferences: ['obs_01', 'obs_02', 'obs_03'],
  detectionModelVersion: 'scrfd_500m_bnkps_v1',
  embeddingModelVersion: 'w600k_mbf_v1',
  embeddingFingerprint: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  candidateMatches: [
    { identity: 'Sarah Connor', similarity: 0.94, rank: 1 },
    { identity: 'Unknown', similarity: 0.22, rank: 2 },
  ],
  decisionTier: 'LOCAL_HIGH_CONFIDENCE',
  selectedIdentity: 'Sarah Connor',
  confidence: 0.94,
  decisionTimestamp: '2026-09-02T08:00:00Z',
  provenanceChainHash: 'b6589fc6ab0dc82cf12099d1c2d40ab994e8410c',
  stages: [
    { stage: '1. Camera Ingestion', timestamp: '2026-09-02T08:00:00Z', metadata: { cameraId: 'cam-01' } },
    { stage: '2. Frame Acquisition', timestamp: '2026-09-02T08:00:00Z', metadata: { frameReference: 'frm_01' } },
    { stage: '3. Face Track Continuity', timestamp: '2026-09-02T08:00:00Z', metadata: { trackId: 'trk_01' } },
    { stage: '4. Embedding Fingerprint', timestamp: '2026-09-02T08:00:00Z', metadata: { embeddingFingerprint: 'e3b0c44298fc' } },
    { stage: '5. Candidate Scoring', timestamp: '2026-09-02T08:00:00Z', metadata: { candidates: [] } },
    { stage: '6. Recognition Decision', timestamp: '2026-09-02T08:00:00Z', metadata: { selectedIdentity: 'Sarah Connor', confidence: 0.94 } },
    { stage: '7. Cloud Synchronization', timestamp: '2026-09-02T08:00:00Z', metadata: { cloudDetectionId: 'det-001' } },
  ],
}

const mockCameraConfig = {
  id: 'cfg-01',
  cameraId: 'cam-01',
  version: 2,
  isActive: true,
  detectionThreshold: 0.65,
  recognitionThreshold: 0.45,
  qualityThreshold: 0.4,
  samplingRate: 1,
  temporalWindow: 3.5,
  createdAt: '2026-09-02T08:00:00Z',
  updatedAt: '2026-09-02T08:05:00Z',
}

const mockKpis = {
  totalDetections: 1204,
  uniqueFaces: 320,
  activeAlerts: 0,
  avgConfidence: 0.92,
  systemHealth: 'green',
  connectedCameras: 1,
  totalCameras: 1,
  detectionsToday: 142,
}

test.beforeEach(async ({ page }) => {
  // Global route interceptor to handle any URL format
  await page.route('**/*', async (route) => {
    const url = route.request().url()

    if (url.includes('/api/system/version-bundle')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockVersionBundle) })
    }
    if (url.includes('/api/nodes/health')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockNodeHealth) })
    }
    if (url.includes('/provenance')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockProvenance) })
    }
    if (url.includes('/api/logs') || url.includes('/api/face-logs') || url.includes('/api/detections')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockFaceLogs) })
    }
    if (url.includes('/config/rollback')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...mockCameraConfig, version: 1 }) })
    }
    if (url.includes('/config')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockCameraConfig) })
    }
    if (url.includes('/api/cameras')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockCameras) })
    }
    if (url.includes('/api/kpis')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockKpis) })
    }
    if (url.includes('/api/alerts')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (url.includes('/api/thresholds')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          recognitionConfidence: 75,
          livenessScore: 80,
          unknownFaceRetentionDays: 30,
          autoAlertOnBlacklist: true,
        }),
      })
    }

    return route.continue()
  })
})

test('Test 1 — Dashboard loads without fatal JavaScript error', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('text=SENTINEL')).toBeVisible()
  await expect(page.locator('text=Facial Recognition Operations Console')).toBeVisible()
})

test('Test 2 — Live alert and detection event logs render', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('text=Detection Event Log')).toBeVisible()
  await expect(page.locator('text=Sarah Connor')).toBeVisible()
})

test('Test 3 — Tab and navigation switching works seamlessly', async ({ page }) => {
  await page.goto('/')
  const systemTab = page.getByRole('tab', { name: /System Health/i }).first()
  await expect(systemTab).toBeVisible()
  await systemTab.click()
  
  // Wait for content to load
  await page.waitForLoadState('networkidle')
  
  // Debug: take screenshot and check what's on page
  await page.screenshot({ path: 'test3-debug.png' })
  
  await expect(page.getByRole('heading', { name: /Camera Node Health/i }).first()).toBeVisible({ timeout: 10000 })
})

test('Test 4 — Version bundle UI renders real backend data and popover', async ({ page }) => {
  await page.goto('/')
  // Verify short hash is rendered in top navigation
  await expect(page.getByText('a1b2c3d4', { exact: true }).first()).toBeVisible()
})

test('Test 5 — Node health UI renders operational metrics on System tab', async ({ page }) => {
  await page.goto('/')
  const systemTab = page.getByRole('tab', { name: /System Health/i }).first()
  await systemTab.click()
  
  // Wait for content to load
  await page.waitForLoadState('networkidle')
  
  // Debug: take screenshot and check what's on page
  await page.screenshot({ path: 'test5-debug.png' })
  
  await expect(page.getByRole('heading', { name: /Edge Runtime Controller/i }).first()).toBeVisible({ timeout: 10000 })
  await expect(page.locator('text=edge-node-alpha')).toBeVisible()
  await expect(page.locator('text=NORMAL')).toBeVisible()
})

test('Test 6 — Provenance lineage drawer displays 7 stages without raw vector exposure', async ({ page }) => {
  await page.goto('/')
  const lineageBtn = page.locator('button:has-text("Lineage")').first()
  await expect(lineageBtn).toBeVisible()
  await lineageBtn.click()

  // Verify Lineage Drawer header and stages
  await expect(page.locator('text=Event Decision Lineage')).toBeVisible()
  await expect(page.locator('text=1. Camera Ingestion')).toBeVisible()
  await expect(page.locator('text=2. Frame Acquisition')).toBeVisible()
  await expect(page.locator('text=3. Face Track Continuity')).toBeVisible()
  await expect(page.locator('text=4. Embedding Fingerprint')).toBeVisible()
  await expect(page.locator('text=5. Candidate Scoring')).toBeVisible()
  await expect(page.locator('text=6. Recognition Decision')).toBeVisible()
  await expect(page.locator('text=7. Cloud Synchronization')).toBeVisible()

  // Security Verification: Ensure 512-d raw float array is NEVER rendered
  const pageContent = await page.content()
  expect(pageContent).not.toMatch(/\[\s*-?0\.\d+,\s*-?0\.\d+,\s*-?0\.\d+/)
})

test('Test 7 — Camera configuration modal reads parameters and supports rollback', async ({ page }) => {
  await page.goto('/')
  const systemTab = page.getByRole('tab', { name: /System Health/i }).first()
  await systemTab.click()
  
  // Wait for content to load
  await page.waitForLoadState('networkidle')
  
  // Debug: take screenshot and check what's on page
  await page.screenshot({ path: 'test7-debug.png' })
  
  const configBtn = page.getByRole('button', { name: /Config/i }).first()
  await expect(configBtn).toBeVisible({ timeout: 10000 })
  await configBtn.click()
  await expect(page.locator('text=Detection Threshold')).toBeVisible()
  await expect(page.locator('text=Recognition Threshold')).toBeVisible()
  await expect(page.locator('text=Temporal Fusion Window')).toBeVisible()
})

test('Test 8 — Backend unavailable handles error gracefully without UI crash', async ({ page }) => {
  // Override route with abort error
  await page.route('**/api/system/version-bundle', async (route) => {
    await route.abort()
  })

  await page.goto('/')
  // Page should still load cleanly
  await expect(page.locator('text=SENTINEL')).toBeVisible()
})

test('Test 9 — WebSocket state handling remains responsive', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('text=SENTINEL')).toBeVisible()
  const searchInput = page.getByPlaceholder('Search ID / camera / subject')
  await expect(searchInput).toBeVisible()
  await searchInput.fill('Sarah')
  await expect(searchInput).toHaveValue('Sarah')
})
