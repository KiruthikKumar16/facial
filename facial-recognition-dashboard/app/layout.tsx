import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { Providers } from '@/components/providers'
import './globals.css'

const geistSans = Geist({
  subsets: ['latin'],
  variable: '--font-geist-sans',
})

const geistMono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-geist-mono',
})

export const metadata: Metadata = {
  title: 'SENTINEL · Facial Recognition Operations Console',
  description:
    'Remote surveillance and facial recognition admin dashboard for security operators: event trails, forensic search, vector management, analytics and system health.',
  generator: 'v0.app',
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#0b0d10',
}

const analyticsEnabled =
  process.env.NODE_ENV === 'production' &&
  process.env.NEXT_PUBLIC_VERCEL_ANALYTICS_ENABLED === '1'

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`dark ${geistSans.variable} ${geistMono.variable}`}>
      <body className="bg-background font-sans antialiased">
        <Providers>{children}</Providers>
        {analyticsEnabled && <Analytics />}
      </body>
    </html>
  )
}
