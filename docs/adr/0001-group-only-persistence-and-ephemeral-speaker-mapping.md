# Ephemeral Speaker-to-Group Mapping and Speaker-Blind Sentiment Scoring

To prevent behavioral profiling of individuals and eliminate speaker-identity bias during AI scoring, Prisk AI never persists speaker-to-group mappings across meetings and strips `speaker_id` before running sentiment analysis. While raw speaker names and company names remain visible in the meeting transcript text for human readability, an Adjudicator's mapping of a `Speaker Account` to a `Group` (e.g., "Client Legal") applies automatically only within that single meeting's adjudication session and must be re-assigned in subsequent meetings. Each `Project` maintains a canonical list of `Group` names to prevent naming drift across longitudinal analytics.

## Consequences

- Sentiment analysis payloads sent to Gemini 2.5 Flash omit `speaker_id` so the model scores strictly what was said rather than who said it.
- Historical `Pulse Score` trends (`FR-4.1`, `FR-6.2`) aggregate strictly by canonical `Group`, `Project`, and `Company`, never by individual human participant.
