# Rules: Prompts

A prompt holds the instructions for one step. Every save makes a new version. How rules are written:
[rules.md](../rules.md).

## Checked in core/

### PROMPT-001 · Each placeholder in a prompt is one of its step's inputs, used once
*Refuses the request · Approved*

**What it means.** A placeholder such as `{{ from_table }}` must name one of the inputs of the prompt's step, and
each input appears at most once.

**Why.** Python puts each input in place of its placeholder. An unknown placeholder would stay in the prompt as text,
and an input used twice would double the prompt's size.

**What happens.** The prompt version is not saved, and the message names the placeholder.

**Example.** `{{ table }}` in an object enrichment prompt: fine. `{{ existing_operational_entities }}` in an
enrichment prompt: refused.

## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.
