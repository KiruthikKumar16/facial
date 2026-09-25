import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const isLoginPage = request.nextUrl.pathname === '/login'
  // Note: we can't easily check localStorage from middleware. But if we migrate to cookies in the future, we would check it here.
  // Since we rely on localStorage, we will do a client-side check in a wrapper instead, or just let API calls fail.
  // Actually, we can just let the API calls fail with 401 and redirect to login inside the generic error handler!
  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
