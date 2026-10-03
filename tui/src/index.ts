import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { runDashboard } from "./app.js";
import { renderDashboardText } from "./layout.js";
import { groupByStage, loadRegistryFile, orderedScreeners, SelectionModel } from "./registry.js";
import { blankRunState } from "./events.js";
import { joinPath, layoutForWidth, resolveRuntime } from "./runtime.js";

const here = dirname(new URL(import.meta.url).pathname);
const tuiDir = resolve(here, "..");
const { root, python } = resolveRuntime(process.env as Record<string, string | undefined>, tuiDir);

function arg(name: string): string | undefined {
  const idx = process.argv.indexOf(name);
  return idx >= 0 ? process.argv[idx + 1] : undefined;
}

function hasFlag(name: string): boolean {
  return process.argv.includes(name);
}

async function snapshot(): Promise<void> {
  const width = Number(arg("--width") ?? 110);
  const height = Number(arg("--height") ?? 32);
  const registry = loadRegistryFile(joinPath(root, "screeners.json"));
  const groups = groupByStage(registry);
  const flat = orderedScreeners(registry);
  const selection = SelectionModel.fromRegistry(registry);
  const text = renderDashboardText(
    {
      groups,
      flat,
      focusedIndex: selection.focusedIndex,
      selected: selection.selected,
      run: blankRunState(),
      showDetails: true,
      refreshEnabled: false,
      overall: `snapshot · ${layoutForWidth(width)} · root=${root}`,
    },
    { width, height },
  );
  process.stdout.write(text + "\n");
}

async function main(): Promise<void> {
  if (hasFlag("--snapshot")) {
    await snapshot();
    return;
  }
  const registryPath = joinPath(root, "screeners.json");
  if (!existsSync(registryPath)) {
    console.error(`screeners.json not found at ${registryPath}. Set META_SCREENER_ROOT to the repo root.`);
    process.exit(1);
  }
  const registry = loadRegistryFile(registryPath);
  await runDashboard({ registry, root, python });
}

await main();
