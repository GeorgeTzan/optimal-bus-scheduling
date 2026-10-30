import { NextRequest, NextResponse } from 'next/server';
import http from 'http';

export const maxDuration = 600;
export const dynamic = 'force-dynamic';

function backendPost(path: string, payload: string, authHeader?: string | null): Promise<{ status: number; body: string }> {
  const backendUrl = new URL(process.env.BACKEND_URL || "http://127.0.0.1:8000");
  return new Promise((resolve, reject) => {
    const headers: Record<string, string | number> = {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(payload),
    };
    if (authHeader) {
      headers.authorization = authHeader;
    }

    const options: http.RequestOptions = {
      hostname: backendUrl.hostname,
      port: backendUrl.port ? Number(backendUrl.port) : 8000,
      path,
      method: 'POST',
      headers,
      timeout: 590000,
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => resolve({ status: res.statusCode ?? 500, body }));
    });

    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

export async function POST(request: NextRequest) {
  try {
    let body = {};
    try {
      body = await request.json();
    } catch {
      body = {};
    }

    const authHeader = request.headers.get("authorization");
    const { status, body: rawBody } = await backendPost('/solve/lahc', JSON.stringify(body), authHeader);

    if (status < 200 || status >= 300) {
      return NextResponse.json(
        { error: `Backend error: ${status}`, details: rawBody },
        { status }
      );
    }

    return NextResponse.json(JSON.parse(rawBody));
  } catch (error) {
    console.error('LAHC API error:', error);
    return NextResponse.json(
      { error: 'Failed to communicate with solver backend' },
      { status: 500 }
    );
  }
}
