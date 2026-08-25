"""End-to-end tour of the jottermem API: remember, recall, dedup,
key-based staleness, and forget. Run with:

    python examples/quickstart.py
"""

from jottermem import Memory

with Memory("example_agent.db") as mem:
    print("== remember() extracts atomic facts and stores each one ==")
    for record in mem.remember(
        "I live in Boston. I work at Acme Corp. My favorite drink is coffee."
    ):
        print(f"  stored: {record.text!r} (id={record.id[:8]})")

    print("\n== recall() does hybrid semantic + keyword search ==")
    for result in mem.recall("Where does the user live?", k=2):
        print(f"  {result.score:.3f}  {result.memory.text!r}")

    print("\n== remembering the same fact again is a no-op (dedup) ==")
    before = len(mem.list_memories())
    mem.remember("I work at Acme Corp.")
    after = len(mem.list_memories())
    print(f"  memory count before={before} after={after} (unchanged)")

    print("\n== facts tagged with a key supersede their prior value ==")
    mem.remember("My favorite drink is coffee.", key="drink")
    mem.remember("My favorite drink is green tea now.", key="drink")
    print("  active:", [r.text for r in mem.list_memories(filter=None) if r.key == "drink"])
    print(
        "  history:",
        [
            (r.text, r.status)
            for r in mem.list_memories(include_superseded=True)
            if r.key == "drink"
        ],
    )

    print("\n== forget() permanently removes a memory ==")
    [to_forget] = [r for r in mem.list_memories() if "Boston" in r.text]
    mem.forget(to_forget.id)
    print(f"  forgot {to_forget.text!r}; forget() again returns:", mem.forget(to_forget.id))

print("\nDone. Data persisted to example_agent.db in the current directory.")
