-- 02_agent_provider_model.sql
-- Seed: AI providers and models (from v2's web_app/backend/atlas_platform/config/agent_capabilities.json).
-- Safe to run again: MERGE adds new rows and updates existing ones; it never adds duplicates or deletes.
-- v2 had one provider (microsoft_foundry) with an api_protocol per model; in v3 a provider is the calling code,
-- so Foundry's OpenAI models and Foundry's Anthropic models are two providers.
-- Prices: v2 kept them outside the repo (GDS_WEB_FOUNDRY_PRICING_JSON), so they are empty here. Fill in the
-- USD per million token prices from the Foundry pricing page and run this file again.

MERGE INTO reference.agent_provider AS t
USING (VALUES
    ('foundry_openai',    'Microsoft Foundry (OpenAI)',    'OpenAI models deployed in Microsoft Foundry, called with the OpenAI Agents SDK.'),
    ('foundry_anthropic', 'Microsoft Foundry (Anthropic)', 'Anthropic models deployed in Microsoft Foundry, called with the Anthropic Messages API.')
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
         NULL::numeric, NULL::numeric, NULL::numeric, NULL::numeric),
        ('foundry_openai', 'gpt-6-luna', 'OpenAI GPT-6 Luna',
         '["default", "none", "low", "medium", "high", "xhigh", "max"]'::jsonb,
         NULL::numeric, NULL::numeric, NULL::numeric, NULL::numeric),
        ('foundry_anthropic', 'claude-opus-5-5', 'Anthropic Claude Opus 5.5',
         '["default", "low", "medium", "high", "xhigh", "max"]'::jsonb,
         NULL::numeric, NULL::numeric, NULL::numeric, NULL::numeric)
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
