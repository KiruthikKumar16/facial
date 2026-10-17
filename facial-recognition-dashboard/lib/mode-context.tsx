'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';

export type DashboardMode = 'live' | 'archive';

interface DashboardModeContextType {
  mode: DashboardMode;
  setMode: (m: DashboardMode) => void;
  selectedBatchId: string | null;
  setSelectedBatchId: (id: string | null) => void;
}

const DashboardModeContext = createContext<DashboardModeContextType>({
  mode: 'live',
  setMode: () => {},
  selectedBatchId: null,
  setSelectedBatchId: () => {},
});

export function DashboardModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<DashboardMode>('live');
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);

  // Sync mode preference from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem('sentinel_vms_mode') as DashboardMode;
      if (saved === 'live' || saved === 'archive') {
        setModeState(saved);
      }
    } catch {
      // ignore SSR/storage errors
    }
  }, []);

  const setMode = (newMode: DashboardMode) => {
    setModeState(newMode);
    try {
      localStorage.setItem('sentinel_vms_mode', newMode);
    } catch {
      // ignore
    }
  };

  return (
    <DashboardModeContext.Provider value={{ mode, setMode, selectedBatchId, setSelectedBatchId }}>
      {children}
    </DashboardModeContext.Provider>
  );
}

export function useDashboardMode() {
  return useContext(DashboardModeContext);
}
