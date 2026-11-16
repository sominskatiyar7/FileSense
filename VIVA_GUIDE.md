# FileSense – Viva Guide (explain it in your own words)

## The 60-second story
"FileSense scans a folder, finds files with identical content using SHA-256, lets me sort files into folders by type,
and moves duplicates to a quarantine instead of deleting them. A background thread does the heavy work so the window
never freezes; MySQL remembers every scan and every file move."

**Workflow:** start → choose folder → coordinator thread creates a `scan_sessions` row → discovers files → groups by size →
worker threads hash only same-size files → duplicates grouped by (size, hash) → files + totals saved in one transaction →
Results page shows them → I quarantine copies / organise → each move logged in `file_operations` → Quarantine page restores.

## The 20 topics
1. **Problem solved** – duplicate and messy files waste space and are hard to track. *Analogy: a cupboard full of repeated, unlabeled papers.*
2. **Why Python** – readable, rich standard library (`os`, `hashlib`, `threading`, `tkinter`), course language.
3. **Why Tkinter** – built into Python, no install, enough for desktop screens; ttk gives a modern look.
4. **Why MySQL** – required by the course; relational tables suit scans → files → operations; survives restarts.
5. **SHA-256** – a one-way fingerprint of content (`hashlib.sha256`). Same content → same 64 hex chars. *Not encryption.* (`scanner/hashing.py`)
6. **Why check size first** – files of different size can't be identical, so hashing them is wasted time. Hashing reads the whole file; size is free. (`duplicate_finder.get_hash_candidates`)
7. **Why chunks** – read 1 MB at a time so a 10 GB file doesn't fill RAM. (`handle.read(self.chunk_size)`)
8. **Multithreading** – several tasks progress at once. Hashing is I/O-heavy, so threads overlap disk waits. *Analogy: 4 cashiers instead of 1.*
9. **Why Tkinter needs the main thread** – Tk is not thread-safe; only one thread may touch widgets. Heavy work in the main thread would freeze the window.
10. **ThreadPoolExecutor** – keeps N worker threads and hands them tasks (`executor.submit`). Shut down in `finally`.
11. **queue.Queue** – thread-safe mailbox. Coordinator `put()`s events; the GUI `get_nowait()`s them inside `root.after()` (`ui/app.py::_poll_events`).
12. **threading.Event** – a shared on/off flag. Cancel button `set()`s it; workers check `is_set()` between chunks.
13. **Repository pattern** – all SQL in `database/repository.py`; GUI/business code call methods like `create_scan()`. Easier to test, change and explain.
14. **Why three tables** – each entity once: sessions, files, operations. Avoids repeating scan data on every file row.
15. **Primary / foreign keys** – PK identifies a row; FK links to another table's PK and keeps data consistent (can't add a file for a non-existent scan).
16. **lambda / filter / reduce** – `lambda` = small unnamed function (sort keys); `filter` keeps items meeting a condition (PDFs, large files); `reduce` folds a list into one value (total bytes). All in `analytics/analytics.py`.
17. **Quarantine** – a holding folder: file moved, original path stored in MySQL, restorable. *Analogy: recycle bin that I control.*
18. **Why not delete** – mistakes must be reversible; the "duplicate" might be the copy a program expects.
19. **If a scan is cancelled** – Event set → queued hashes cancelled → running ones stop → results so far saved → status `CANCELLED`, unfinished files `SKIPPED`.
20. **If MySQL fails** – startup shows a clear message (wrong password / DB missing / server down) instead of a traceback; errors during a scan become a `SCAN_FAILED` event and the scan row is marked `FAILED`.

## Likely viva questions
* **Can two different files have the same SHA-256?** Practically no (collision astronomically unlikely); we also compare size.
* **Why not use the file name?** Names can match with different content, or differ with the same content.
* **Why don't workers write to MySQL?** Connections aren't safely shared between threads; one coordinator owns DB writes. Each repository call opens its own connection anyway.
* **Why `root.after` and not `root.update`?** `after` schedules polling cooperatively on the main thread; `update()` forces re-entrant event processing and is a hack.
* **What happens if a file changes while hashing?** Size/mtime are compared before and after; mismatch → status `CHANGED`, hash ignored.
* **What prevents overwriting?** `unique_path()` adds ` (1)`; restore refuses and asks for another location (`CONFLICT`).
* **Why PENDING first?** If the app crashes mid-move the record exists; at next start `reconcile_pending_operations` decides SUCCESS or FAILED by looking at the disk.
* **How do you stop SQL injection?** Only `%s` parameterized queries; a test inserts a path containing `'; DROP TABLE` safely.
* **How is reclaimable space computed?** `(copies − 1) × size` per group, summed with `reduce`.
* **Where are the layers?** `ui/` → services (`scanner/ organizer/ analytics/`) → `database/`.

## Key code to be able to open and explain
`scanner/scan_manager.py::_run` and `_hash_candidates` · `scanner/hashing.py::calculate_hash` ·
`scanner/duplicate_finder.py::find_duplicates` · `ui/app.py::_poll_events` · `organizer/quarantine.py::restore` ·
`database/repository.py::get_quarantined_files` (the NOT EXISTS query) · `analytics/analytics.py`.
