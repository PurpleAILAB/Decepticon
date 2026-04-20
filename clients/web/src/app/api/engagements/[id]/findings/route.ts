import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

interface Finding {
  id: string;
  title: string;
  severity: string;
  description: string;
  evidence: string;
  attackVector: string;
  affectedAssets: string[];
}

function parseFindingMarkdown(content: string, filename: string): Finding {
  const lines = content.split("\n");
  let title = filename;
  let severity = "medium";
  let description = "";
  let evidence = "";
  let attackVector = "";
  const affectedAssets: string[] = [];

  let currentSection = "";

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith("# ")) {
      title = trimmed.slice(2).trim();
      continue;
    }

    if (trimmed.startsWith("## ")) {
      currentSection = trimmed.slice(3).trim().toLowerCase();
      continue;
    }

    const severityMatch = trimmed.toLowerCase();
    if (severityMatch.includes("severity") && trimmed.includes(":")) {
      const val = trimmed.split(":")[1]?.trim().replace(/\*/g, "").toLowerCase();
      if (["critical", "high", "medium", "low", "informational"].includes(val)) {
        severity = val;
      }
    }

    if (currentSection === "description" && trimmed) {
      description += (description ? "\n" : "") + trimmed;
    }
    if (currentSection === "evidence" && trimmed) {
      evidence += (evidence ? "\n" : "") + trimmed;
    }
    if (
      (currentSection === "attack vector" ||
        currentSection === "attack-vector") &&
      trimmed
    ) {
      attackVector += (attackVector ? "\n" : "") + trimmed;
    }
    if (
      (currentSection === "affected" ||
        currentSection === "affected assets" ||
        currentSection === "assets") &&
      trimmed
    ) {
      if (trimmed.startsWith("-") || trimmed.startsWith("*")) {
        affectedAssets.push(trimmed.replace(/^[-*]\s*/, ""));
      }
    }
  }

  return {
    id: filename.replace(".md", ""),
    title,
    severity,
    description: description || "No description available.",
    evidence: evidence || "No evidence recorded.",
    attackVector: attackVector || "Unknown",
    affectedAssets,
  };
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  let userId: string;
  try {
    ({ userId } = await requireAuth());
  } catch (e) {
    if (e instanceof AuthError) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    throw e;
  }

  const { id } = await params;
  const engagement = await prisma.engagement.findFirst({
    where: { id, userId },
  });

  if (!engagement) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const findings: Finding[] = [];

  {
    const WORKSPACE = process.env.WORKSPACE_PATH ?? path.join(process.env.HOME ?? "", ".decepticon", "workspace");
    const wsPath = path.join(WORKSPACE, engagement.name);
    const findingsDir = path.join(wsPath, "findings");
    try {
      const files = await fs.readdir(findingsDir);
      for (const file of files.sort()) {
        if (file.startsWith("FIND-") && file.endsWith(".md")) {
          const content = await fs.readFile(
            path.join(findingsDir, file),
            "utf-8"
          );
          findings.push(parseFindingMarkdown(content, file));
        }
      }
    } catch {
      // Directory doesn't exist yet
    }
  }

  return NextResponse.json(findings);
}
