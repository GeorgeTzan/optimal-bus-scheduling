import { NextRequest, NextResponse } from 'next/server';

export const maxDuration = 300; 
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300000); 
    
    const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    const authHeader = request.headers.get("authorization");
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (authHeader) {
      headers.authorization = authHeader;
    }

    const response = await fetch(`${backendUrl}/solve`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: `Backend error: ${response.status}`, details: errorText },
        { status: response.status }
      );
    }
    
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json(
        { error: 'Request timeout - solver took too long' },
        { status: 504 }
      );
    }
    console.error('Solve API error:', error);
    return NextResponse.json(
      { error: 'Failed to communicate with solver backend' },
      { status: 500 }
    );
  }
}
