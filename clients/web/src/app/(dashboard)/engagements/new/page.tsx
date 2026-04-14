"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  FolderOpen,
  GitBranch,
  Upload,
  Globe,
  Server,
  Loader2,
} from "lucide-react";
import { hasEE } from "@/lib/ee";

export default function NewEngagementPage() {
  const router = useRouter();
  const [targetType, setTargetType] = useState("local_path");
  const [name, setName] = useState("");
  const [targetValue, setTargetValue] = useState("");
  const [gitBranch, setGitBranch] = useState("main");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const showGitHubTab = hasEE();

  async function handleSubmit() {
    if (!name.trim() || !targetValue.trim()) {
      setError("Please fill in all required fields");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      // For git_url, append branch info to the value
      const finalValue =
        targetType === "git_url" && gitBranch
          ? `${targetValue}#${gitBranch}`
          : targetValue;

      const res = await fetch("/api/engagements", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          targetType,
          targetValue: finalValue,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to create engagement");
      }

      const engagement = await res.json();
      router.push(`/engagements/${engagement.id}/chat?new=true`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  function handleFileDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      setTargetValue(file.name);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      setTargetValue(file.name);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">New Engagement</h1>
        <p className="text-sm text-muted-foreground">
          Configure a new red team testing operation
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Engagement Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Engagement Name</Label>
            <Input
              id="name"
              placeholder="e.g., Q2 Security Assessment"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Target Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs
            value={targetType}
            onValueChange={(v) => {
              setTargetType(v);
              setTargetValue("");
            }}
          >
            <TabsList className="w-full flex-wrap">
              <TabsTrigger value="local_path" className="flex-1 gap-2">
                <FolderOpen className="h-4 w-4" />
                Local Path
              </TabsTrigger>
              <TabsTrigger value="git_url" className="flex-1 gap-2">
                <GitBranch className="h-4 w-4" />
                Git URL
              </TabsTrigger>
              <TabsTrigger value="file_upload" className="flex-1 gap-2">
                <Upload className="h-4 w-4" />
                Upload
              </TabsTrigger>
              <TabsTrigger value="web_url" className="flex-1 gap-2">
                <Globe className="h-4 w-4" />
                Web URL
              </TabsTrigger>
              <TabsTrigger value="ip_range" className="flex-1 gap-2">
                <Server className="h-4 w-4" />
                IP Range
              </TabsTrigger>
              {showGitHubTab && (
                <TabsTrigger value="github_repo" className="flex-1 gap-2">
                  <GitBranch className="h-4 w-4" />
                  GitHub
                </TabsTrigger>
              )}
            </TabsList>

            <TabsContent value="local_path" className="mt-4 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="local-path">Local Directory Path</Label>
                <Input
                  id="local-path"
                  placeholder="/home/user/projects/myapp"
                  value={targetValue}
                  onChange={(e) => setTargetValue(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Absolute path to a project directory on this server
                </p>
              </div>
            </TabsContent>

            <TabsContent value="git_url" className="mt-4 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="git-url">Repository URL</Label>
                <Input
                  id="git-url"
                  placeholder="https://github.com/org/repo.git or git@gitlab.com:org/repo.git"
                  value={targetValue}
                  onChange={(e) => setTargetValue(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  HTTPS or SSH URL — uses credentials configured on this server
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="git-branch">Branch</Label>
                <Input
                  id="git-branch"
                  placeholder="main"
                  value={gitBranch}
                  onChange={(e) => setGitBranch(e.target.value)}
                />
              </div>
            </TabsContent>

            <TabsContent value="file_upload" className="mt-4 space-y-4">
              <div className="space-y-2">
                <Label>Upload Archive</Label>
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleFileDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
                    dragOver
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-muted-foreground/50"
                  }`}
                >
                  <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
                  {targetValue ? (
                    <p className="text-sm font-medium text-foreground">{targetValue}</p>
                  ) : (
                    <>
                      <p className="text-sm text-muted-foreground">
                        Drag & drop a <strong>.zip</strong> or <strong>.tar.gz</strong> file
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground/70">
                        or click to browse
                      </p>
                    </>
                  )}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".zip,.tar.gz,.tgz"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                </div>
              </div>
            </TabsContent>

            <TabsContent value="web_url" className="mt-4 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="url">Target URL</Label>
                <Input
                  id="url"
                  type="url"
                  placeholder="https://example.com"
                  value={targetValue}
                  onChange={(e) => setTargetValue(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  The web application URL to test
                </p>
              </div>
            </TabsContent>

            <TabsContent value="ip_range" className="mt-4 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="ip">IP Range</Label>
                <Input
                  id="ip"
                  placeholder="192.168.1.0/24 or 10.0.0.1-10.0.0.255"
                  value={targetValue}
                  onChange={(e) => setTargetValue(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  CIDR notation or IP range to scan
                </p>
              </div>
            </TabsContent>

            {showGitHubTab && (
              <TabsContent value="github_repo" className="mt-4">
                <div className="space-y-2">
                  <Label>Repository</Label>
                  <p className="text-sm text-muted-foreground">
                    GitHub repo picker loaded via EE
                  </p>
                </div>
              </TabsContent>
            )}
          </Tabs>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={() => router.back()}>
          Cancel
        </Button>
        <Button onClick={handleSubmit} disabled={submitting}>
          {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Create Engagement
        </Button>
      </div>
    </div>
  );
}
