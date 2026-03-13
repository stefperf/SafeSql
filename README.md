# SafeSQL

**SafeSQL** is a SQL-first, type-annotated Python library for composing dynamic SQL **without introducing SQL injection vulnerabilities**.

It is designed for **legacy Python applications that execute large amounts of raw SQL**, where a full migration to an ORM or query builder would be more costly and more risky.

SafeSQL allows you as a developer - or your favorite AI coding assistant - to keep writing **plain SQL**, while safely composing dynamic fragments and parameters.
It is similar in spirit to the popular **Java SafeSQL library**.

Target use cases:

- Quickly removing SQL injection vulnerabilities in legacy codebases
- Refactoring unsafe string-interpolated SQL queries
- Working with **complex or performance-sensitive SQL** where raw SQL is preferable

SafeSQL is **not an ORM** and does not attempt to replace tools like SQLAlchemy.  
Instead, it provides a **lightweight and incremental path to safe SQL in existing codebases**.

---

## Requirements

- Python ≥ 3.11
- `pyodbc` or another database driver supporting **positional SQL parameters (`?`)**

---

## Database Support

For now, some features are specific to **MS SqlServer / T-SQL**, rather than being platform independent.  
See comments and unit tests for the details.
