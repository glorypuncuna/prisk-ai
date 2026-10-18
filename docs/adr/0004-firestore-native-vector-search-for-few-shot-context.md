# Firestore Native Vector Search for Few-Shot Corrected Context

To implement the human-in-the-loop feedback loop (`Story 3.3`, `FR-2.7`) under strict cloud budget constraints, Prisk AI stores 768-dimensional embeddings (`text-embedding-004`) of Adjudicator slider overrides (`Corrected Context`) directly in Firestore and retrieves the top-K semantically similar overrides using Firestore Native Vector Search (`find_nearest`) rather than provisioning a dedicated Vertex AI Vector Search index endpoint.

## Consequences

- Eliminates the always-on hourly node compute cost of dedicated Vertex AI Vector Search endpoints while maintaining sub-100ms K-NN retrieval and native pre-filtering by `project_id` and `group_name`.
