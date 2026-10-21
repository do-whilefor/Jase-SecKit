// Compaction always receives the host's StreamFn. Do not silently introduce
// another provider transport or credential owner through Pi's optional fallback.
export function completeSimple() {
  throw new Error("PwnMesh requires the host model stream for Pi compaction");
}
