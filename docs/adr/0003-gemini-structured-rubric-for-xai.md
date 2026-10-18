# Gemini Structured Rubric Outputs for Explainable AI

Instead of provisioning a separate custom text-classification model on a dedicated Vertex AI Prediction endpoint to invoke native Vertex Explainable AI (Integrated Gradients / Shapley attributions), Prisk AI implements on-demand Explainable AI (`FR-2.6`, `Story 3.2`) using Gemini 2.5 Flash with strict JSON Structured Outputs constrained by a deterministic Rubric Parameter framework. This keeps sentiment inference, few-shot calibration, and token/phrase attribution unified on a single serverless model while preventing hallucinated rationales.

## Consequences

- Zero idle hosting cost compared to always-on custom Vertex AI Prediction endpoints with Explainable AI enabled.
- The JSON schema must enforce that returned attribution substrings are exact verbatim substrings of the target `Dialogue Block` and map directly to defined rubric dimensions and weights.
