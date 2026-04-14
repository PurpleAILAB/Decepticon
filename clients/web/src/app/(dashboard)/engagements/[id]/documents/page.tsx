"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FileText, Shield, Target, AlertTriangle, ClipboardList, Loader2 } from "lucide-react";

interface EngagementDetail {
  id: string;
  workspacePath: string | null;
}

interface DocumentContent {
  roe: string | null;
  conops: string | null;
  deconfliction: string | null;
  opplan: string | null;
}

const docMeta = [
  { key: "roe" as const, label: "Rules of Engagement", icon: Shield, file: "roe.json" },
  { key: "conops" as const, label: "CONOPS", icon: Target, file: "conops.json" },
  { key: "deconfliction" as const, label: "Deconfliction Plan", icon: AlertTriangle, file: "deconfliction.json" },
  { key: "opplan" as const, label: "OPPLAN", icon: ClipboardList, file: "plan/opplan.json" },
];

export default function DocumentsPage() {
  const params = useParams();
  const id = params.id as string;
  const [docs, setDocs] = useState<DocumentContent>({ roe: null, conops: null, deconfliction: null, opplan: null });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadDocs() {
      try {
        const res = await fetch(`/api/engagements/${id}`);
        if (!res.ok) return;
        const eng: EngagementDetail = await res.json();
        if (!eng.workspacePath) return;

        // Load each document via API
        const opplanRes = await fetch(`/api/engagements/${id}/opplan`);
        const opplanData = opplanRes.ok ? await opplanRes.text() : null;

        setDocs({
          roe: null, // TODO: add API route for individual docs
          conops: null,
          deconfliction: null,
          opplan: opplanData && opplanData !== '{"objectives":[]}' ? opplanData : null,
        });
      } catch {
        // failed to load
      } finally {
        setLoading(false);
      }
    }
    loadDocs();
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const hasAnyDoc = Object.values(docs).some((v) => v !== null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Documents</h1>
        <p className="text-sm text-muted-foreground">
          Engagement documents generated from the Soundwave interview
        </p>
      </div>

      {!hasAnyDoc ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <FileText className="mb-3 h-10 w-10 text-muted-foreground/30" />
            <p className="text-sm font-medium">No documents generated yet</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Start a Soundwave interview from the Live tab to generate RoE, CONOPS, and OPPLAN
            </p>
          </CardContent>
        </Card>
      ) : (
        <Tabs defaultValue={docs.opplan ? "opplan" : docMeta.find((d) => docs[d.key])?.key ?? "roe"}>
          <TabsList>
            {docMeta.map((doc) => (
              <TabsTrigger key={doc.key} value={doc.key} disabled={!docs[doc.key]} className="gap-2">
                <doc.icon className="h-3.5 w-3.5" />
                {doc.label}
              </TabsTrigger>
            ))}
          </TabsList>

          {docMeta.map((doc) => (
            <TabsContent key={doc.key} value={doc.key}>
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <doc.icon className="h-4 w-4" />
                    {doc.label}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {docs[doc.key] ? (
                    <ScrollArea className="h-[60vh]">
                      <pre className="whitespace-pre-wrap text-sm text-muted-foreground">
                        {docs[doc.key]}
                      </pre>
                    </ScrollArea>
                  ) : (
                    <p className="py-8 text-center text-sm text-muted-foreground">
                      Not yet generated
                    </p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  );
}
