'use client'

import React, { Component, ErrorInfo, ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'

interface Props {
  children?: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error in ErrorBoundary:', error, errorInfo)
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <div className="flex h-full min-h-[300px] w-full flex-col items-center justify-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-6 text-center text-destructive">
          <AlertCircle className="size-8" />
          <h3 className="text-lg font-semibold">Something went wrong</h3>
          <p className="text-sm opacity-80">{this.state.error?.message || "An unexpected error occurred in this module."}</p>
          <button 
            onClick={() => this.setState({ hasError: false, error: undefined })}
            className="mt-4 rounded-md bg-destructive/10 px-4 py-2 text-sm font-medium hover:bg-destructive/20 transition-colors"
          >
            Try again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
