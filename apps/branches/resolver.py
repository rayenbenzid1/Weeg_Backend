"""
apps/branches/resolver.py
─────────────────────────
Branch name resolver — used by every Excel importer.

Priority order per call to .resolve(raw):
  1. Exact match in BranchAlias cache (DB, loaded once at init)
  2. Exact match on Branch.name
  3. Fuzzy match via SequenceMatcher (threshold: FUZZY_THRESHOLD)
  4. Unresolved alias created in DB → returns None

Usage:
    resolver = BranchResolver(company)      # 2 DB queries, rest is in-memory
    branch   = resolver.resolve("فرع الكريمية")   # → Branch obj or None

One instance per import session (per company).
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Optional

from .models import Branch, BranchAlias


FUZZY_THRESHOLD = 0.72   # 0.0–1.0 — lower = more permissive


class BranchResolver:

    def __init__(self, company):
        self.company = company

        # alias string → Branch | None
        self._alias_cache: dict[str, Optional[Branch]] = {
            a.alias: a.branch
            for a in (
                BranchAlias.objects
                .filter(company=company)
                .select_related("branch")
            )
        }

        # canonical branch name → Branch
        self._branch_cache: dict[str, Branch] = {
            b.name: b
            for b in Branch.objects.filter(is_active=True)
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def resolve(self, raw: str | None) -> Optional[Branch]:
        """
        Return the canonical Branch for *raw*, or None if unresolvable.
        Side-effect: may write a BranchAlias row to DB.
        """
        if not raw:
            return None
        name = raw.strip()
        if not name:
            return None

        # 1. Known alias (cache hit — fastest path, no fuzzy needed)
        if name in self._alias_cache:
            return self._alias_cache[name]

        # 2. Exact branch name
        if name in self._branch_cache:
            branch = self._branch_cache[name]
            self._save_alias(name, branch, auto=False)
            return branch

        # 3. Fuzzy match across all canonical branch names
        branch, score = self._best_fuzzy(name)
        if branch and score >= FUZZY_THRESHOLD:
            self._save_alias(name, branch, auto=True)
            return branch

        # 4. No match — create unresolved placeholder for admin review
        self._save_alias(name, None, auto=False)
        return None

    def unresolved_aliases(self) -> list[str]:
        """Return alias strings that have no branch assigned yet."""
        return [alias for alias, branch in self._alias_cache.items() if branch is None]

    # ── Internals ─────────────────────────────────────────────────────────────

    def _best_fuzzy(self, name: str) -> tuple[Optional[Branch], float]:
        best_branch: Optional[Branch] = None
        best_score = 0.0
        for canonical, branch in self._branch_cache.items():
            score = SequenceMatcher(None, name, canonical).ratio()
            if score > best_score:
                best_branch, best_score = branch, score
        return best_branch, best_score

    def _save_alias(self, alias: str, branch: Optional[Branch], auto: bool) -> None:
        """Persist alias to DB and update in-memory cache."""
        obj, created = BranchAlias.objects.get_or_create(
            company=self.company,
            alias=alias,
            defaults={"branch": branch, "auto_matched": auto},
        )
        if not created and obj.branch is None and branch is not None:
            # Upgrade a previously unresolved alias
            obj.branch       = branch
            obj.auto_matched = auto
            obj.save(update_fields=["branch", "auto_matched"])
        self._alias_cache[alias] = branch