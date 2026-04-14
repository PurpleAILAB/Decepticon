"use client";

import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Lock, Search } from "lucide-react";

interface Repo {
  id: number;
  name: string;
  full_name: string;
  description: string | null;
  language: string | null;
  private: boolean;
  html_url: string;
  updated_at: string;
}

interface GitHubRepoPickerProps {
  value: string;
  onChange: (value: string) => void;
}

export function GitHubRepoPicker({ value, onChange }: GitHubRepoPickerProps) {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("/api/github/repos")
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to fetch repos: ${res.status}`);
        return res.json();
      })
      .then(setRepos)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = repos.filter(
    (repo) =>
      repo.name.toLowerCase().includes(search.toLowerCase()) ||
      repo.full_name.toLowerCase().includes(search.toLowerCase())
  );

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search repositories..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      <ScrollArea className="h-64 rounded-lg border border-border">
        {loading ? (
          <div className="space-y-2 p-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex items-center justify-center p-8 text-sm text-muted-foreground">
            No repositories found
          </div>
        ) : (
          <div className="p-1">
            {filtered.map((repo) => (
              <button
                key={repo.id}
                type="button"
                onClick={() => onChange(repo.full_name)}
                className={`flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left transition-colors ${
                  value === repo.full_name
                    ? "bg-primary/10 text-primary"
                    : "hover:bg-accent"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {repo.full_name}
                    </span>
                    {repo.private && (
                      <Lock className="h-3 w-3 shrink-0 text-muted-foreground" />
                    )}
                  </div>
                  {repo.description && (
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {repo.description}
                    </p>
                  )}
                </div>
                {repo.language && (
                  <Badge variant="secondary" className="shrink-0 text-xs">
                    {repo.language}
                  </Badge>
                )}
              </button>
            ))}
          </div>
        )}
      </ScrollArea>

      {value && (
        <p className="text-xs text-muted-foreground">
          Selected: <span className="font-medium text-foreground">{value}</span>
        </p>
      )}
    </div>
  );
}
