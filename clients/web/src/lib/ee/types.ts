import type { ComponentType } from "react";

/** Session object returned by EE auth module */
export interface EESession {
  user: {
    id: string;
    name?: string | null;
    email?: string | null;
    image?: string | null;
  };
  accessToken?: string;
  orgId?: string;
}

/** Audit event logged by EE */
export interface AuditEvent {
  action: string;
  resource: string;
  detail?: Record<string, unknown>;
}

/** Domain verification record */
export interface DomainVerificationRecord {
  id: string;
  domain: string;
  state: "pending" | "verified" | "expired" | "failed";
  txtRecordName: string;
  txtRecordValue: string;
  expiresAt: string;
  verifiedAt?: string | null;
}

export type VerificationStatus =
  | "verified"
  | "not_found"
  | "propagating"
  | "error";

/** Auth provider for SSO */
export interface EEAuthProvider {
  id: string;
  name: string;
}

/**
 * EE feature registry — `@decepticon/ee` implements this interface.
 * OSS mode: all fields are undefined (empty object from loader).
 */
export interface EEFeatures {
  // ── Auth ──
  auth?: {
    getSession: () => Promise<EESession | null>;
    SessionProvider: ComponentType<{ children: React.ReactNode }>;
    LoginPage: ComponentType;
    signOut: () => Promise<void>;
  };

  // ── Domain verification ──
  DomainVerificationPage?: ComponentType;
  domainAPI?: {
    initiate: (orgId: string, domain: string) => Promise<DomainVerificationRecord>;
    check: (orgId: string, domain: string) => Promise<VerificationStatus>;
    list: (orgId: string) => Promise<DomainVerificationRecord[]>;
  };
  scopeGate?: (orgId: string, targetDomain: string) => Promise<void>;

  // ── Organization / multi-tenancy ──
  OrganizationSettingsPage?: ComponentType;
  OrgSwitcher?: ComponentType;

  // ── Billing ──
  BillingPage?: ComponentType;

  // ── SSO ──
  ssoProviders?: EEAuthProvider[];

  // ── Audit log ──
  AuditLogPage?: ComponentType;
  auditLog?: (event: AuditEvent) => Promise<void>;
}
