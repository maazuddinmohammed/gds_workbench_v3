# Starter prompts

One file per step: the global default prompt a new install starts with (design/overview/run.md). `scripts/local_db.py`
(and `scripts/db_install.py`) load them after the seed files: a prompt that is not there yet is added as the global
default, and a text that differs from the prompt's latest version becomes its next version. Nothing is ever changed or
removed, so a person's own versions stay.

Each file has a title line, a `mode:` line (`one_shot` or `tool_assisted`), then a `## System` and an `## Instruction`
section. In the instruction, `{{ name }}` is where an input goes (PROMPT-001: only the step's own inputs, once each).
`core/prompts.py` adds a guide to the inputs and the meaning of their fields after the system text, so the texts here
say only what the step must do and how to do it well.
