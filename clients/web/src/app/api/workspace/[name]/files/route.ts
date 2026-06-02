import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { resolveEngagementDir } from "@/lib/workspace";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

const WORKSPACE = process.env.WORKSPACE_PATH ?? path.join(process.env.HOME ?? "", ".decepticon", "workspace");

const FOLDERS = ["recon", "exploit", "post-exploit", "findings", "report"] as const;

interface FileEntry {
  name: string;
  folder: string;
  path: string;
  size: number;
}

interface FolderGroup {
  folder: string;
  files: FileEntry[];
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  let userId: string;
  try {
    ({ userId } = await requireAuth());
  } catch (e) {
    if (e instanceof AuthError) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    throw e;
  }

  const { name } = await params;
  const engagement = await prisma.engagement.findFirst({
    where: { name, userId },
  });

  if (!engagement) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  let engagementDir: string;
  try {
    engagementDir = resolveEngagementDir(engagement.name, WORKSPACE);
  } catch {
    return NextResponse.json({ folders: [] });
  }

  const folders: FolderGroup[] = [];

  for (const folder of FOLDERS) {
    const folderDir = path.join(engagementDir, folder);
    let entries;
    try {
      entries = await fs.readdir(folderDir, { withFileTypes: true });
    } catch {
      continue;
    }

    const files: FileEntry[] = [];
    for (const entry of entries) {
      if (!entry.isFile()) continue;
      let size = 0;
      try {
        const stat = await fs.stat(path.join(folderDir, entry.name));
        size = stat.size;
      } catch {
        continue;
      }
      files.push({ name: entry.name, folder, path: `${folder}/${entry.name}`, size });
    }

    if (files.length > 0) {
      folders.push({ folder, files });
    }
  }

  return NextResponse.json({ folders });
}
