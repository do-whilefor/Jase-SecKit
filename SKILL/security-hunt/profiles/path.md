---
id: path-canonicalization
group: normalize
reference: ../references/path.md
---

# Path Canonicalization

**Use for:** download/upload paths, static files and reverse proxies, archive extraction, object-storage keys, and build workspaces.

**Misalignment to find:** Validation uses a raw path string while the filesystem, router, proxy, archiver, or backend resolves the final target under a different canonicalization model.

## Baseline

- A path string is not the final filesystem or routing object.
- Look for multiple decoding, separators, dot segments, case, mounts, links, and frontend/backend canonicalization differences.
- Focus on a validated root directory that differs from the final real target.
- Record the raw path, every decoded form, canonical path, and realpath/handle object.

## Validation Order

1. Record path decoding and canonicalization at every layer.
2. Test encoding, mixed separators, absolute paths, links, mount points, and archive members.
3. When a proxy or gateway is present, compare the path before and after routing.
4. Verify the final object identity and root-directory constraint.

## Variant Axes

- Separators, dot segments, repeated slashes, absolute/relative paths
- Encoding, double decoding, Unicode, case, and trailing characters
- Symlinks, mount points, archive members, and platform path rules
- Relationship between the path at validation time and the object finally opened

## Combination Paths

- `file-chain`: File Processing Chain
- `fs-identity`: File-Object Identity
- `url-address`: URLs & Addresses
