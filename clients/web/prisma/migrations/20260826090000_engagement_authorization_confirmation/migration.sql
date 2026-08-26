-- Autohunt requires an explicit persisted authorization signal before planning.
ALTER TABLE "Engagement" ADD COLUMN "authorizationConfirmed" BOOLEAN NOT NULL DEFAULT false;
