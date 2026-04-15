#!/usr/bin/env node

/**
 * GLB Model Compression Script
 *
 * Applies Draco geometry compression + texture WebP conversion + dedup + prune.
 * Targets 80-90%+ total size reduction.
 *
 * Usage: node scripts/compress-models.mjs
 */

import { readdir, stat } from "node:fs/promises";
import { join, resolve } from "node:path";
import { NodeIO } from "@gltf-transform/core";
import {
  ALL_EXTENSIONS,
} from "@gltf-transform/extensions";
import {
  dedup,
  draco,
  prune,
  weld,
  textureCompress,
} from "@gltf-transform/functions";
import draco3d from "draco3dgltf";
import sharp from "sharp";

const MODELS_DIR = resolve(import.meta.dirname, "../public/models");

async function compressModel(io, filePath) {
  const fileName = filePath.split("/").pop();
  const beforeSize = (await stat(filePath)).size;

  console.log(
    `\n  Processing ${fileName} (${(beforeSize / 1024 / 1024).toFixed(1)} MB)...`,
  );

  const document = await io.read(filePath);

  // Pipeline: dedup → weld → draco → texture compress → prune
  await document.transform(
    dedup(),
    weld(),
    draco(),
    textureCompress({ encoder: sharp, targetFormat: "webp", quality: 75 }),
    prune(),
  );

  await io.write(filePath, document);

  const afterSize = (await stat(filePath)).size;
  const ratio = ((1 - afterSize / beforeSize) * 100).toFixed(1);
  console.log(
    `   ${fileName}: ${(beforeSize / 1024 / 1024).toFixed(1)} MB -> ${(afterSize / 1024 / 1024).toFixed(1)} MB (${ratio}% reduction)`,
  );

  return { fileName, beforeSize, afterSize };
}

async function main() {
  console.log("=== GLB Model Compression ===");
  console.log(`Models directory: ${MODELS_DIR}\n`);

  // Initialize IO with ALL extensions (including KHR_draco_mesh_compression,
  // KHR_materials_volume, etc.) so nothing is silently dropped.
  const io = new NodeIO()
    .registerExtensions(ALL_EXTENSIONS)
    .registerDependencies({
      "draco3d.decoder": await draco3d.createDecoderModule(),
      "draco3d.encoder": await draco3d.createEncoderModule(),
    });

  const files = (await readdir(MODELS_DIR))
    .filter((f) => f.endsWith(".glb"))
    .map((f) => join(MODELS_DIR, f));

  if (files.length === 0) {
    console.log("No .glb files found.");
    return;
  }

  console.log(`Found ${files.length} GLB file(s)`);

  const results = [];
  for (const file of files) {
    results.push(await compressModel(io, file));
  }

  // Summary
  console.log("\n=== Summary ===");
  let totalBefore = 0;
  let totalAfter = 0;
  for (const r of results) {
    totalBefore += r.beforeSize;
    totalAfter += r.afterSize;
  }
  console.log(
    `Total: ${(totalBefore / 1024 / 1024).toFixed(1)} MB -> ${(totalAfter / 1024 / 1024).toFixed(1)} MB (${((1 - totalAfter / totalBefore) * 100).toFixed(1)}% reduction)`,
  );
}

main().catch((err) => {
  console.error("Compression failed:", err);
  process.exit(1);
});
