"""Derived Wiki navigation; parent links never create evidence dependencies."""

from __future__ import annotations


def navigation_paths(pages):
    """Return each page's current ancestor titles and title, without storing copies.

    Page and block IDs remain stable when a page is renamed or moved. Callers
    include the returned path in derived retrieval fingerprints so descendants
    change when an ancestor changes. Navigation is a ranking feature, not a
    restriction on which branches may supply evidence or capabilities.
    """
    if not isinstance(pages, dict):
        pages = {page["page_id"]: page for page in pages}
    paths, visiting = {}, set()

    def resolve(pid):
        if pid in paths:
            return paths[pid]
        if pid in visiting:
            raise ValueError(f"Wiki navigation cycle at {pid}")
        visiting.add(pid)
        page = pages[pid]
        parent = page.get("parent_page_id")
        if parent is not None and parent not in pages:
            raise ValueError(f"Wiki page {pid}: missing parent {parent}")
        paths[pid] = (resolve(parent) if parent is not None else []) + [page.get("title", pid)]
        visiting.remove(pid)
        return paths[pid]

    for pid in pages:
        resolve(pid)
    return paths
