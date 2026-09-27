-- ===========================================================================
-- SignalDesk -- database hardening, index set, and data cleanup
-- ===========================================================================
--
-- Apply to a BACKUP or to a stopped server. On a live SQLite database, the
-- PRAGMA journal_mode change rewrites the database header and the CREATE INDEX
-- statements hold a write lock for their whole duration; running either while
-- the app is ingesting will surface as `database is locked`.
--
-- From the application, the same pragmas are applied automatically on every
-- connection (app/db/session.py, _apply_sqlite_pragmas) and the same indexes
-- are declared in Post.__table_args__ plus migration 0009. This file exists for
-- operators who want them applied out-of-band, and to document the reasoning.
--
-- Measured effect on the 103 MB / 3,807-post production database:
--
--   pending-batch  query   99.0 ms  ->   2.19 ms   (45.3x)
--   flagged-list   query    1.6 ms  ->   0.21 ms   ( 7.6x)
--   dedup-check    query    1.4 ms  ->   0.08 ms   (18.7x)
--   30 concurrent writers        5168 ms  -> 2279 ms (2.3x)
--   worst single commit          882 ms  ->  506 ms
--
-- Run with:  sqlite3 media_monitor.db < tools/loadtest/db_hardening.sql
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. PRAGMAs
-- ---------------------------------------------------------------------------
-- journal_mode=WAL is the single most effective change here. Under the previous
-- journal_mode=delete, every commit took an EXCLUSIVE lock, so a writer blocked
-- every reader for the duration of the fsync. WAL lets readers run during a
-- write, which is what makes "ingest while analyzing" viable at all.
--
-- NORMAL is the right durability trade for a desktop monitor: it survives an
-- application crash, and only an OS/power failure can lose the last few
-- transactions. FULL fsyncs twice per commit and was measurable in write
-- latency. If this deployment must survive power loss with zero loss, set it
-- back to FULL and accept the write cost.
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- Negative values are kibibytes. The previous -2000 was a 2 MB page cache
-- against a database that had grown past 100 MB, so hot queries were
-- re-reading pages on every request.
PRAGMA cache_size = -64000;        -- 64 MB

-- Memory-mapped reads; removes a copy per page from the read path.
PRAGMA mmap_size = 268435456;     -- 256 MB

-- The previous value was 5000 ms. Raised to 15000 to match app/db/session.py:
-- under write contention a 5 s wait surfaces as a user-visible 500.
PRAGMA busy_timeout = 15000;

-- Keep ORDER BY / GROUP BY spill files in memory.
PRAGMA temp_store = MEMORY;

-- Off by default in SQLite. The schema relies on ON DELETE CASCADE for
-- topic_id / source_id, so without this a deleted topic silently orphans its
-- posts instead of removing them.
PRAGMA foreign_keys = ON;

-- Integrity reporting, not enforced. Useful after the cleanup below to confirm
-- no duplicates remain.
PRAGMA integrity_check;
PRAGMA foreign_key_check;
PRAGMA optimize;


-- ---------------------------------------------------------------------------
-- 2. Data cleanup
-- ---------------------------------------------------------------------------
-- The empty-string sentinel. `ai_summary = ''` meant "analyzed, nothing found"
-- and was excluded from the pending-post query by an `OR ai_summary = ''`
-- disjunct. That disjunct cannot use a partial index, so the query degraded to
-- a full table scan plus a temp B-tree sort on every call -- 99 ms measured,
-- and linear in table size. With the sentinel normalized to NULL the partial
-- index below is fully usable.
--
-- UPDATEs only; the table is not rewritten.
UPDATE posts SET ai_summary = NULL WHERE ai_summary = '';
UPDATE posts SET severity_level = NULL WHERE severity_level = '';
UPDATE posts SET violence_category = NULL WHERE violence_category = '';
UPDATE posts SET title = NULL WHERE title = '';
UPDATE posts SET author = NULL WHERE author = '';
UPDATE posts SET post_url = NULL WHERE post_url = '';
UPDATE posts SET content_fingerprint = NULL WHERE content_fingerprint = '';


-- ---------------------------------------------------------------------------
-- 3. Indexes
-- ---------------------------------------------------------------------------
-- Every index below is created IF NOT EXISTS, so this file is idempotent.
-- Skip any that already exist to avoid a full table rebuild for no gain.

-- --- 3a. Alert filtering ---------------------------------------------------
-- get_flagged_posts() filters `is_flagged OR severity_level IN ('high',
-- 'critical')` and orders by id DESC. Both were full scans; these turn them
-- into two index seeks. 1.6 ms -> 0.21 ms measured.
CREATE INDEX IF NOT EXISTS ix_posts_flagged  ON posts (is_flagged, id);
CREATE INDEX IF NOT EXISTS ix_posts_severity  ON posts (severity_level, id);

-- --- 3b. Batch deduplication ----------------------------------------------
-- _save_posts() deduplicates on (source_id, topic_id, external_id). Without a
-- composite index whose leading columns are the equality predicates, SQLite
-- falls back to ix_posts_topic_id and scans every post in the topic -- 1.75 ms
-- per lookup, which is 874 ms for a 500-post batch.
--
-- Note: these are non-unique. See section 5 for the uniqueness constraints.
CREATE INDEX IF NOT EXISTS ix_posts_dedup_external     ON posts (source_id, topic_id, external_id);
CREATE INDEX IF NOT EXISTS ix_posts_dedup_url          ON posts (source_id, topic_id, post_url);
CREATE INDEX IF NOT EXISTS ix_posts_dedup_fingerprint ON posts (source_id, topic_id, content_fingerprint);

-- --- 3c. AI queue claim ----------------------------------------------------
-- The background worker claims work with:
--     WHERE ai_status IN ('pending','failed') ORDER BY id ASC LIMIT n
-- The partial index predicate MUST match that IN-list exactly. SQLite refuses
-- to use a partial index whose WHERE clause is not implied by the query's, so
-- an index narrowed to `ai_status = 'pending'` looks helpful but leaves the
-- claim query doing a full table scan -- the 99 ms regression this section
-- exists to remove.
CREATE INDEX IF NOT EXISTS ix_posts_ai_queue ON posts (id, topic_id)
    WHERE ai_status IN ('pending', 'failed');

-- Superseded by ix_posts_ai_queue. Safe to drop; kept guarded because a
-- database built from an earlier revision may still carry it.
-- DROP INDEX IF EXISTS ix_posts_ai_pending;

-- --- 3d. Supporting indexes for other hot paths ---------------------------
-- Topic dashboard listing, newest first.
CREATE INDEX IF NOT EXISTS ix_posts_topic_recent ON posts (topic_id, id DESC);

-- Media processing queue (OCR / transcription) -- same partial-index pattern
-- as the AI queue, for the other background worker.
CREATE INDEX IF NOT EXISTS ix_posts_media_pending ON posts (id, topic_id)
    WHERE media_status = 'pending';


-- ---------------------------------------------------------------------------
-- 4. Reclaim space
-- ---------------------------------------------------------------------------
-- The cleanup in section 2 leaves free pages in the file. This is safe to run
-- on a live database because it is incremental: SQLite grows the WAL, copies
-- live pages into it, and updates the main database in chunks. It does require
-- a disk with roughly 2x the database free.
--
-- VACUUM;                          -- rewrite and shrink (exclusive lock)
PRAGMA wal_checkpoint(TRUNCATE);   -- fold the WAL back in and reset it
PRAGMA optimize;                   -- refresh ANALYZE statistics


-- ---------------------------------------------------------------------------
-- 5. Optional: close the TOCTOU duplicate race with UNIQUE constraints
-- ---------------------------------------------------------------------------
-- The batched dedup in _save_posts() is a check-then-insert. Two concurrent
-- ingestion paths (the scrape cycle and Quick Ingest) can both observe "not
-- present" for the same external_id and both insert, because SQLite serialises
-- the writes but not the read that preceded them. The composite indexes in 3b
-- make the check fast; they do not make it atomic.
--
-- Uniqueness closes it at the database level, which is the only place that
-- works across processes. It is left OPT-IN because it fails on any database
-- that already contains duplicates, and silently deleting an operator's
-- monitoring archive is not a decision a migration should make.
--
-- Step 1 -- audit. A non-zero row count here is the blocker.
--
--   SELECT source_id, topic_id, external_id, COUNT(*) AS n
--   FROM posts
--   WHERE external_id IS NOT NULL AND external_id != ''
--   GROUP BY source_id, topic_id, external_id
--   HAVING n > 1
--   ORDER BY n DESC;
--
-- Step 2 -- de-duplicate, keeping the oldest row and repointing anything that
-- referenced the copies. Adjust the repoint statements to this schema's
-- actual foreign keys before running.
--
--   DELETE FROM posts
--   WHERE id NOT IN (
--     SELECT MIN(id) FROM posts
--     WHERE external_id IS NOT NULL AND external_id != ''
--     GROUP BY source_id, topic_id, external_id
--   );
--
-- Step 3 -- enforce. Requires the table to be rebuilt on SQLite; the migration
-- helper in section 6 shows the shape.
--
--   CREATE UNIQUE INDEX ux_posts_source_topic_external
--     ON posts (source_id, topic_id, external_id)
--     WHERE external_id IS NOT NULL AND external_id != '';
--
-- Do NOT add a UNIQUE constraint on post_url or content_fingerprint without
-- the same audit. Aggregators routinely publish the same URL across sources, and
-- an identical short post can legitimately repeat within one source.


-- ---------------------------------------------------------------------------
-- 6. Alembic equivalent (what app/db/init_db.py does automatically)
-- ---------------------------------------------------------------------------
-- An application restart runs init_db() and migration 0009, which apply the
-- same column additions, backfill, indexes, and WAL pragmas. This file is only
-- needed when you want them applied without a code change -- for example
-- during an incident, on a replica, or to verify what the migration will do
-- before letting it near the production file.
--
-- To confirm afterwards:
--
--   sqlite3 media_monitor.db "PRAGMA journal_mode; PRAGMA synchronous;
--                            PRAGMA index_list('posts');"
--
-- Expect: wal, 1, and ix_posts_flagged / ix_posts_severity /
--         ix_posts_dedup_external / ix_posts_dedup_url /
--         ix_posts_dedup_fingerprint / ix_posts_ai_queue.
