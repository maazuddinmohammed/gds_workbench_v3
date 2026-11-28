-- 02_agent_provider_model.sql
-- Seed: AI providers and models (from v2's web_app/backend/atlas_platform/config/agent_capabilities.json).
-- Safe to run again: MERGE adds new rows and updates existing ones; it never adds duplicates or deletes.
-- v2 had one provider (microsoft_foundry) with an api_protocol per model; in v3 a provider is the calling code,
-- so Foundry's OpenAI models and Foundry's Anthropic models are two providers.
-- Prices: USD per million tokens, Foundry Global Standard, short context (looked up Nov 19, 2026 from price
-- trackers that quote the Azure price list). Sol and Luna charge more above 272K input tokens; one price per model
-- means very long prompts come out a little low, which is fine for an approximate cost. Opus cache write is the
-- 5-minute cache price. Update the numbers here and run this file again when prices change.

MERGE INTO reference.agent_provider AS t
USING (VALUES
    ('foundry_openai',    'Microsoft Foundry (OpenAI)',    'OpenAI models deployed in Microsoft Foundry, called with the official openai package (Responses API).'),
    ('foundry_anthropic', 'Microsoft Foundry (Anthropic)', 'Anthropic models deployed in Microsoft Foundry, called with the Anthropic Messages API.'),
    ('openai',            'OpenAI API (testing)',          'OpenAI models called on the OpenAI API, with the same calling code as Foundry. For testing while there is no Foundry endpoint (Nov 28, Maaz).')
) AS s (agent_provider_code, agent_provider_name, agent_provider_description)
ON lower(btrim(t.agent_provider_code)) = lower(btrim(s.agent_provider_code))
WHEN MATCHED THEN UPDATE SET
    agent_provider_name        = s.agent_provider_name,
    agent_provider_description = s.agent_provider_description,
    updated_time               = CURRENT_TIMESTAMP,
    updated_by                 = CURRENT_USER
WHEN NOT MATCHED THEN INSERT (agent_provider_code, agent_provider_name, agent_provider_description)
    VALUES (s.agent_provider_code, s.agent_provider_name, s.agent_provider_description);

-- agent_model_name is the Foundry deployment name, exactly as the API expects it.
MERGE INTO reference.agent_model AS t
USING (
    SELECT p.agent_provider_id, s.*
      FROM (VALUES
        ('foundry_openai', 'gpt-6.1-sol', 'OpenAI GPT-6.1 Sol',
         '["default", "low", "medium", "high", "xhigh", "max"]'::jsonb,
         2.00::numeric, 0.10::numeric, 2.50::numeric, 10.00::numeric),
        ('foundry_openai', 'gpt-6-luna', 'OpenAI GPT-6 Luna',
         '["default", "none", "low", "medium", "high", "xhigh", "max"]'::jsonb,
         0.10::numeric, 0.01::numeric, 0.125::numeric, 0.50::numeric),
        ('foundry_anthropic', 'claude-opus-5-5', 'Anthropic Claude Opus 5.5',
         '["default", "low", "medium", "high", "xhigh", "max"]'::jsonb,
         4.00::numeric, 0.20::numeric, 5.00::numeric, 20.00::numeric),
        -- The OpenAI API, for testing (Nov 28, Maaz): prices as on Foundry, cached input at a tenth of input.
        ('openai', 'gpt-6.2-sol', 'OpenAI GPT-6.2 Sol (OpenAI API)',
         '["none", "minimal", "low", "medium", "high", "xhigh", "max"]'::jsonb,
         2.00::numeric, 0.20::numeric, 2.50::numeric, 10.00::numeric),
        ('openai', 'gpt-6-luna', 'OpenAI GPT-6 Luna (OpenAI API)',
         '["none", "minimal", "low", "medium", "high", "xhigh", "max"]'::jsonb,
         0.10::numeric, 0.01::numeric, 0.125::numeric, 0.50::numeric)
      ) AS s (agent_provider_code, agent_model_name, agent_model_display_name, reasoning_effort_codes,
              input_usd_per_million, cached_input_usd_per_million, cache_write_input_usd_per_million, output_usd_per_million)
      JOIN reference.agent_provider AS p
        ON lower(btrim(p.agent_provider_code)) = lower(btrim(s.agent_provider_code))
) AS s
ON t.agent_provider_id = s.agent_provider_id
   AND lower(btrim(t.agent_model_name)) = lower(btrim(s.agent_model_name))
WHEN MATCHED THEN UPDATE SET
    agent_model_display_name          = s.agent_model_display_name,
    reasoning_effort_codes            = s.reasoning_effort_codes,
    input_usd_per_million             = s.input_usd_per_million,
    cached_input_usd_per_million      = s.cached_input_usd_per_million,
    cache_write_input_usd_per_million = s.cache_write_input_usd_per_million,
    output_usd_per_million            = s.output_usd_per_million,
    updated_time                      = CURRENT_TIMESTAMP,
    updated_by                        = CURRENT_USER
WHEN NOT MATCHED THEN INSERT (agent_provider_id, agent_model_name, agent_model_display_name, reasoning_effort_codes,
                              input_usd_per_million, cached_input_usd_per_million, cache_write_input_usd_per_million, output_usd_per_million)
    VALUES (s.agent_provider_id, s.agent_model_name, s.agent_model_display_name, s.reasoning_effort_codes,
            s.input_usd_per_million, s.cached_input_usd_per_million, s.cache_write_input_usd_per_million, s.output_usd_per_million);
