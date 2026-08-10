-- Migration 013: user-editable blog personas.
-- Additive & idempotent. Safe to run on existing Supabase data.
--
-- Buyer persona / survey stats / named testimonials used to ground blog idea
-- generation (api/recommendations/blog_ideas.py) lived only as one hardcoded
-- file (api/knowledge/qc_event_planning_persona.md) for one school. This
-- table makes that input user-editable per school from the dashboard's Blog
-- Ideas tab instead, so a person can paste in their own persona/testimonials/
-- stats for any school before generating ideas. One free-form markdown blob
-- per school; NULL school = General, mirroring questions.school's existing
-- convention (see migrations/011_blog_ideas_school.sql).
--
-- Seeded with the former QC Event Planning file's content so behavior
-- doesn't regress on upgrade - from here on it's editable/removable through
-- the UI like any other school's persona.

BEGIN;

CREATE TABLE IF NOT EXISTS blog_personas (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    school     text,
    content    text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Postgres unique constraints treat NULL as distinct from NULL, which would
-- allow multiple "General" rows - index the coalesced value instead so
-- there's still exactly one row per school (including General).
CREATE UNIQUE INDEX IF NOT EXISTS idx_blog_personas_school
    ON blog_personas (COALESCE(school, ''));

INSERT INTO blog_personas (school, content)
VALUES ('QC Event Planning', $PERSONA$# QC Event Planning — Buyer Persona & Original Data

Internal survey data and testimonials for QC Event Planning students. Use as
primary-source evidence (Tier 1 original data) and named-source EEAT material
when generating content for this school - do not extrapolate these figures to
other QC schools.

## Why students take the course
- To start my own business (56%)
- To upskill
- For personal interest
- To get a good job

56% of students want to start their own business - the largest single motivation.

## Age
- 20 and under / 21-30 / 30-39 / 40-49 / 50-59 / 60-69

75% of students are between 21 and 49 years old. The desire to start a business
varies little by age band - it isn't concentrated in younger students.

## Why students choose this course (format/logistics)
- Self-paced learning
- Reputation of the school
- Budget-friendly payment plans
- Online course format
- Support from a professional

Students favor self-paced, online learning above all other factors.

## How students prefer to learn
- Visual learner / Learn by doing / Learn by reading / Learn by listening

Most students prefer visual content and learning by doing. This holds fairly
evenly across all age bands.

## How quickly students want to finish
- Under 3 months / 3-6 months / 6-12 months

Over 90% of students want to complete their course in 6 months or less.

## Preferred social platform
- Snapchat, LinkedIn, Instagram, Facebook, Reddit, TikTok, YouTube, Pinterest

Most students prefer Instagram and Facebook.

## Testimonials / case-study quotes (named sources)

**Carisa Lockery** - Owner of Pink Olive Events and Pink Olive Consulting:
- What made you want to become an event planner? "As a kid, I was always
  organizing everything... I woke up one day with the thought, 'Could I
  actually make a living doing this?'"
- Advice for prospective QC Event School students: "Do it! It was a great
  experience for me and really helped guide the process so that I could be
  successful when I finally started my business."
- What excites you most about creating events for people? "I love how
  different every event is, and I love creating the perfect team to bring it
  all together... seeing the look on our clients' faces is the best feeling
  ever!"

Website testimonials:
- Madyson Bell: "I can definitely say that I would not have gotten off to
  nearly as strong of a start, had it not been for my training through QC."
- Neena McConnell: "Attending an online school allowed me to learn at my own
  pace in the comfort of my own home. I was able to work full-time, train a
  young puppy, plan my own wedding, and travel with my now-husband."
- Tamesha Squire: "The IEDP™ certification is amazing and definitely has a
  competitive edge. Being connected to thousands of thriving and inspiring
  professionals has been the biggest perk for me!"
- Tyler Reid: "My experiences were 10/10 overall. As a QC Event School
  graduate, I would definitely recommend these courses!"
- Jenny Alperin: "I like that QC has a community you can connect with and get
  help from while working on the course. It's also very valuable to have a
  reputable certification that I can now hand to clients."
$PERSONA$)
ON CONFLICT (COALESCE(school, '')) DO NOTHING;

COMMIT;
