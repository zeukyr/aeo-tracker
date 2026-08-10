-- Migration 014: split blog_personas into three separate categories.
-- Additive & idempotent. Safe to run on existing Supabase data.
--
-- migrations/013_blog_personas.sql stored one free-form `content` blob per
-- school. In practice a person filling this in has three distinct kinds of
-- material (buyer persona narrative, survey/original-data stats, named
-- testimonial quotes) that get used differently downstream - ideation wants
-- all three, full-post drafting deliberately excludes testimonials (see
-- blog_ideas.py's _build_full_post_prompt). Splitting them into real columns
-- means that exclusion is structural instead of an instruction the model has
-- to remember to follow, and the dashboard can offer three labeled boxes
-- instead of one undifferentiated textarea.

BEGIN;

ALTER TABLE blog_personas
    ADD COLUMN IF NOT EXISTS buyer_persona text,
    ADD COLUMN IF NOT EXISTS stats text,
    ADD COLUMN IF NOT EXISTS testimonials text;

-- Backfill the QC Event Planning row seeded in migration 013 by splitting
-- its combined `content` at the testimonials heading - the only row that
-- migration ever seeded, and the only data that predates this split.
UPDATE blog_personas
SET stats = $STATS$# QC Event Planning — Original Data

Internal survey data for QC Event Planning students. Use as primary-source
evidence (Tier 1 original data) when generating content for this school - do
not extrapolate these figures to other QC schools.

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
$STATS$,
testimonials = $TESTIMONIALS$**Carisa Lockery** - Owner of Pink Olive Events and Pink Olive Consulting:
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
$TESTIMONIALS$
WHERE school = 'QC Event Planning' AND stats IS NULL AND testimonials IS NULL;

ALTER TABLE blog_personas DROP COLUMN IF EXISTS content;

COMMIT;
