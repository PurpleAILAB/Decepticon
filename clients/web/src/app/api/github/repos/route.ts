import { getSession } from "@/lib/auth-bridge";
import { hasEE } from "@/lib/ee";
import { NextResponse } from "next/server";

/**
 * GitHub repos API — only available when EE auth provides a GitHub access token.
 * In OSS mode, returns an empty array (GitHub repo picker is hidden).
 */
export async function GET() {
  if (!hasEE()) {
    return NextResponse.json([]);
  }

  const session = await getSession();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const accessToken = session.accessToken;
  if (!accessToken) {
    return NextResponse.json(
      { error: "No GitHub access token. Please re-authenticate." },
      { status: 403 }
    );
  }

  const res = await fetch(
    "https://api.github.com/user/repos?sort=updated&per_page=100&type=owner",
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: "application/vnd.github+json",
      },
    }
  );

  if (!res.ok) {
    return NextResponse.json(
      { error: `GitHub API error: ${res.status}` },
      { status: res.status }
    );
  }

  const repos = await res.json();
  interface GitHubRepo {
    id: number;
    name: string;
    full_name: string;
    description: string | null;
    language: string | null;
    private: boolean;
    html_url: string;
    updated_at: string;
  }

  const simplified = (repos as GitHubRepo[]).map((repo) => ({
    id: repo.id,
    name: repo.name,
    full_name: repo.full_name,
    description: repo.description,
    language: repo.language,
    private: repo.private,
    html_url: repo.html_url,
    updated_at: repo.updated_at,
  }));

  return NextResponse.json(simplified);
}
