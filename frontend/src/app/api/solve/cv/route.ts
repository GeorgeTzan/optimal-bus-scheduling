import { NextRequest } from "next/server";
import { request as httpRequest } from "node:http";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const payload = JSON.stringify(body);

    const proxied = await new Promise<{ status: number; body: string }>((resolve, reject) => {
      const request = httpRequest(
        {
          hostname: "backend",
          port: 8000,
          path: "/solve/cv",
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(payload),
          },
        },
        (response) => {
          const chunks: Buffer[] = [];
          response.on("data", (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
          response.on("end", () => {
            resolve({
              status: response.statusCode ?? 502,
              body: Buffer.concat(chunks).toString("utf-8"),
            });
          });
        }
      );

      request.setTimeout(900_000, () => {
        request.destroy(new Error("CV proxy request timed out after 900000ms"));
      });
      request.on("error", reject);
      request.write(payload);
      request.end();
    });

    return new Response(proxied.body, {
      status: proxied.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown proxy error";
    return new Response(JSON.stringify({ detail: `CV proxy error: ${message}` }), {
      status: 504,
      headers: { "Content-Type": "application/json" },
    });
  }
}
