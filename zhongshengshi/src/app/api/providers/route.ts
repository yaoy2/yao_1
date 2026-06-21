import { NextResponse } from "next/server";
import { buildProviderConfigs } from "@/lib/providers";

export function GET() {
  return NextResponse.json({ providers: buildProviderConfigs(process.env) });
}
