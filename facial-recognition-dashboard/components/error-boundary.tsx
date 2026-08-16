'use client'

import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { SectionHeading } from '@/components/dashboard/shared'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
  hasError: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { error: null, hasError: false }
  }

  static getDerivedStateFromError(error: Error): State {
    return { error, hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (typeof window !== 'undefined') {
      // eslint-disable-next-line no-console
      console.error('[ErrorBoundary] Caught render error:', error, info)
    }
  }

  reset = () => {
    this.setState({ error: null, hasError: false })
    if (typeof window !== 'undefined') {
      window.location.reload()
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-background px-4 py-12 lg:px-6">
          <div className="mx-auto w-full max-w-2xl">
            <Card className="border-destructive/30 bg-card/60">
              <CardHeader className="border-b border-border py-4">
                <SectionHeading
                  icon={AlertTriangle}
                  title="Dashboard Error"
                  description="A render error was caught automatically. Your data is safe — reload to continue."
                />
              </CardHeader>
              <CardContent className="flex flex-col gap-4 p-6">
                <div className="rounded-lg border border-border bg-muted/30 p-4 font-mono text-xs text-destructive">
                  {this.state.error?.message ?? 'Unexpected render error'}
                </div>
                <div className="flex gap-2">
                  <Button onClick={this.reset}>
                    <RefreshCcw /> Reload Dashboard
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
