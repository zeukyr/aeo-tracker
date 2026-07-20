-- Migration 007: user-marked Reddit thread status (dead/open), replacing
-- api/knowledge/dead_reddit_threads.json with a DB-backed table the
-- dashboard writes to directly. Marking a thread dead in the UI now feeds
-- back into get_reddit_targets()'s ranking on the very next request - no
-- code change needed, unlike the old JSON-file approach (which needed a
-- commit every time outreach found a new dead thread). Additive & idempotent.
--
-- Reddit blocks this server's anonymous .json lookups (403 even with a
-- browser User-Agent), so archived/rule-blocked status can't be detected
-- live - a human confirms it during outreach and marks it here instead.

BEGIN;

CREATE TABLE IF NOT EXISTS reddit_thread_status (
    -- Reddit post ID (the comments/<id> segment) - stable across
    -- slug/query-param variants of the same thread URL, unlike the URL itself.
    post_id    text PRIMARY KEY,
    -- last-marked URL, kept for display/debugging only (post_id is the key).
    url        text NOT NULL,
    subreddit  text,
    status     text NOT NULL CHECK (status IN ('dead', 'open')),
    -- free text, e.g. "archived", "removed by mods", "against subreddit rules"
    reason     text,
    marked_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reddit_thread_status_status ON reddit_thread_status (status);

-- Seed: carries over the threads confirmed archived during the outreach pass
-- that motivated this table, so nothing already known is lost in the switch
-- from dead_reddit_threads.json. ON CONFLICT DO NOTHING - a later manual
-- re-mark in the dashboard always wins, this only fills in if still unset.
INSERT INTO reddit_thread_status (post_id, url, subreddit, status, reason, marked_at) VALUES
    ('1fq7b8x',  'https://reddit.com/r/opendogtraining/comments/1fq7b8x', 'opendogtraining', 'dead', 'archived', '2026-07-20'),
    ('15jrbe2',  'https://reddit.com/r/doggrooming/comments/15jrbe2',     'doggrooming',     'dead', 'archived', '2026-07-20'),
    ('18re61x',  'https://reddit.com/r/careerguidance/comments/18re61x',  'careerguidance',  'dead', 'archived', '2026-07-20'),
    ('3i4ijh',   'https://reddit.com/r/jobs/comments/3i4ijh',             'jobs',            'dead', 'archived', '2026-07-20'),
    ('egxxe2',   'https://reddit.com/r/doggrooming/comments/egxxe2',      'doggrooming',     'dead', 'archived', '2026-07-20'),
    ('dvigup',   'https://reddit.com/r/eventproduction/comments/dvigup',  'eventproduction', 'dead', 'archived', '2026-07-20'),
    ('agb5is',   'https://reddit.com/r/entrepreneur/comments/agb5is',     'entrepreneur',    'dead', 'archived', '2026-07-20'),
    ('ufk1j6',   'https://reddit.com/r/dogtraining/comments/ufk1j6',      'dogtraining',     'dead', 'archived', '2026-07-20'),
    ('2va4nz',   'https://reddit.com/r/dogtraining/comments/2va4nz',      'dogtraining',     'dead', 'archived', '2026-07-20'),
    ('10izty5',  'https://reddit.com/r/doggrooming/comments/10izty5',     'doggrooming',     'dead', 'archived', '2026-07-20'),
    ('1n0yeus',  'https://reddit.com/r/eventproduction/comments/1n0yeus', 'eventproduction', 'dead', 'archived', '2026-07-20'),
    ('rqx1w5',   'https://reddit.com/r/wedding/comments/rqx1w5',          'wedding',         'dead', 'archived', '2026-07-20'),
    ('12pgyqq',  'https://reddit.com/r/doggrooming/comments/12pgyqq',     'doggrooming',     'dead', 'archived', '2026-07-20')
ON CONFLICT (post_id) DO NOTHING;

COMMIT;
