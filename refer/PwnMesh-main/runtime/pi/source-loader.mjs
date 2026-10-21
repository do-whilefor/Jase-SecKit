import { registerHooks } from "node:module";

const aliases = new Map([
  ["@earendil-works/pi-ai", new URL("./source-api.mjs", import.meta.url).href],
  ["@earendil-works/pi-ai/compat", new URL("./source-compat.mjs", import.meta.url).href],
]);

registerHooks({
  resolve(specifier, context, nextResolve) {
    const url = aliases.get(specifier);
    return url ? { url, shortCircuit: true } : nextResolve(specifier, context);
  },
});
