# Product Guidelines

## Tone & Voice
- **Technical & Professional:** The communication should be precise and focused on technical accuracy.
- **Direct & Instructive:** Use the active voice and clear, imperative sentences for instructions and error messages.
- **Helpful:** Provide context in error messages and logs to help users debug workflow issues or LLM failures.

## Prose Style
- **Clarity First:** Avoid jargon where simpler terms suffice, but use standard NLP and ML terminology accurately.
- **Conciseness:** Keep documentation and CLI output brief but informative.
- **Consistency:** Use consistent terminology for "Templates", "Workflows", "Classifiers", and "QAS".

## User Experience (CLI & Library)
- **Informative Feedback:** Show progress during LLM calls or complex ML classifications.
- **Graceful Degradation:** If an LLM fails, provide clear errors and, if possible, fallback suggestions.
- **Configuration over Code:** Allow users to easily tune LLM parameters (temperature, model) via configuration files or environment variables.

## Branding & Identity
- **Name:** Always refer to the project as "NLP Template Engine" or "NLPTemplateEngine".
- **Mission-Driven:** Emphasize the goal of "making workflows executable".
