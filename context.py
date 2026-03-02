#!/usr/bin/env python3
# ~/.local/lib/sovereign/context.py
# Axis Mundi Context Awareness Layer

import json
import os
import time
from datetime import datetime
from pathlib import Path
from difflib import get_close_matches
from collections import defaultdict
import sys

CONTEXT_DIR = Path.home() / ".config" / "axis-mundi"
CONTEXT_FILE = CONTEXT_DIR / "context.json"
MAX_INJECTED_TERMS = 20
AUTO_SUGGEST_THRESHOLD = 3

STOPWORDS = {
    "a","an","the","and","or","but","is","it","in","on","at","to","for",
    "of","with","by","from","as","be","was","are","has","have","had","do",
    "did","not","no","so","if","up","out","can","get","got","run","use",
    "my","me","i","you","we","he","she","they","that","this","what","how",
    "ok","yes","yep","nope","just","also","then","now","here","there","too",
    "hi","hey","yeah","ok","please","thanks","its","will","would","should",
    "could","let","make","show","tell","give","put","see","go","came","come",
}

class ContextDB:
    def __init__(self):
        self.data = self._load()
        self._unknown_log = defaultdict(int)
        self._session_start = time.time()

    def _load(self):
        if not CONTEXT_FILE.exists():
            return {"terms": {}}
        try:
            with open(CONTEXT_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"terms": {}}

    def _save(self):
        CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONTEXT_FILE, "w") as f:
            json.dump(self.data, f, indent=2, sort_keys=True)

    def get_term(self, term):
        return self.data["terms"].get(term)

    def fuzzy_find(self, query, cutoff=0.6):
        candidates = []
        for term, info in self.data["terms"].items():
            if info.get("deleted"):
                continue
            if get_close_matches(query, [term], n=1, cutoff=cutoff):
                candidates.append((term, info))
                continue
            aliases = info.get("aliases", [])
            if get_close_matches(query, aliases, n=1, cutoff=cutoff):
                candidates.append((term, info))
        return candidates

    def add_term(self, term, definition, aliases=None, category=None, auto=False):
        now = datetime.utcnow().isoformat() + "Z"
        entry = {"value": definition, "added": now, "last_used": now, "auto": auto}
        if aliases:
            entry["aliases"] = aliases
        if category:
            entry["category"] = category
        self.data["terms"][term] = entry
        self._save()

    def remove_term(self, term):
        if term in self.data["terms"]:
            del self.data["terms"][term]
            self._save()
            return True
        return False

    def forget_term(self, term):
        if term in self.data["terms"]:
            self.data["terms"][term]["deleted"] = True
            self.data["terms"][term]["deleted_at"] = datetime.utcnow().isoformat() + "Z"
            self._save()
            return True
        return False

    def list_terms(self, category=None, auto_only=False, manual_only=False, include_deleted=False):
        result = []
        for term, info in self.data["terms"].items():
            if not include_deleted and info.get("deleted"):
                continue
            if category and info.get("category") != category:
                continue
            if auto_only and not info.get("auto"):
                continue
            if manual_only and info.get("auto"):
                continue
            result.append((term, info))
        result.sort(key=lambda x: x[1].get("last_used", ""), reverse=True)
        return result

    def update_last_used(self, term):
        if term in self.data["terms"]:
            self.data["terms"][term]["last_used"] = datetime.utcnow().isoformat() + "Z"
            self._save()

    def log_unknown(self, term):
        """Log a term that might be unknown — skips stopwords and short tokens."""
        t = term.lower().strip(".,!?;:")
        if len(t) < 3 or t in STOPWORDS:
            return
        if not self.fuzzy_find(t):
            self._unknown_log[t] += 1

    def get_suggestions(self):
        return [(t, c) for t, c in self._unknown_log.items() if c >= AUTO_SUGGEST_THRESHOLD]

    def clear_unknown_log(self):
        self._unknown_log.clear()


_context = None

def get_context():
    global _context
    if _context is None:
        _context = ContextDB()
    return _context


def format_context_for_prompt():
    db = get_context()
    terms = db.list_terms(include_deleted=False)[:MAX_INJECTED_TERMS]
    if not terms:
        return ""
    lines = ["Marcus's personal context and terminology:"]
    for term, info in terms:
        line = f"- {term} = {info['value']}"
        if info.get("aliases"):
            line += f" (also: {', '.join(info['aliases'])})"
        if info.get("category"):
            line += f" [{info['category']}]"
        lines.append(line)
    return "\n".join(lines)


def add_from_command(cmd_name, cmd_value):
    get_context().add_term(cmd_name, cmd_value, category="command", auto=False)


def add_from_tool(tool_name, tool_desc):
    get_context().add_term(tool_name, tool_desc, category="tool", auto=False)


def resolve_to_action(phrase, cutoff=0.8):
    """Fuzzy-resolve a phrase to a known term's value. High cutoff for safety."""
    db = get_context()
    matches = db.fuzzy_find(phrase, cutoff=cutoff)
    if matches:
        term, info = matches[0]
        db.update_last_used(term)
        return info["value"]
    return None


def print_suggestions():
    db = get_context()
    suggestions = db.get_suggestions()
    if suggestions:
        print("\n  \033[38;2;255;200;50m[context]\033[0m  I noticed these terms this session — save any?")
        for term, count in suggestions:
            print(f"  \033[38;2;85;85;105m{term}\033[0m  (used {count}×)")
        print("  Use \033[38;2;57;255;100m/context add <term> = <definition>\033[0m to save.")
        db.clear_unknown_log()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Axis Mundi Context Manager")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("add");    p.add_argument("term"); p.add_argument("definition")
    p.add_argument("--alias", action="append"); p.add_argument("--category"); p.add_argument("--auto", action="store_true")

    p = sub.add_parser("list")
    p.add_argument("--category"); p.add_argument("--auto", action="store_true")
    p.add_argument("--manual", action="store_true"); p.add_argument("--deleted", action="store_true")

    p = sub.add_parser("remove");  p.add_argument("term")
    p = sub.add_parser("forget");  p.add_argument("term")
    p = sub.add_parser("search");  p.add_argument("query"); p.add_argument("--cutoff", type=float, default=0.6)
    sub.add_parser("export")

    args = parser.parse_args()
    db = get_context()

    if args.command == "add":
        db.add_term(args.term, args.definition, args.alias, args.category, args.auto)
        print(f"Added: {args.term}")
    elif args.command == "list":
        for term, info in db.list_terms(args.category, args.auto, args.manual, args.deleted):
            d = " (deleted)" if info.get("deleted") else ""
            print(f"{term}{d}: {info['value']}")
    elif args.command == "remove":
        print(f"Removed: {args.term}" if db.remove_term(args.term) else f"Not found: {args.term}")
    elif args.command == "forget":
        print(f"Forgot: {args.term}" if db.forget_term(args.term) else f"Not found: {args.term}")
    elif args.command == "search":
        for term, info in db.fuzzy_find(args.query, args.cutoff):
            print(f"{term}: {info['value']}")
    elif args.command == "export":
        json.dump(db.data, sys.stdout, indent=2)
    else:
        parser.print_help()
