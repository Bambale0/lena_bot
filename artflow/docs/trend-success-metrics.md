# Completed trend and feed repeat metrics

- Curated trend cards show **successful completions** and **successful
  completions in the last seven days**. Both are displayed even when zero.
- Admin trends add an aggregate summary and a single cross-category
  weekly ranking. The expandable detailed view uses the authorized
  /api/v1/admin/trends API (all attempts, pending, failed, distinct successful
  user accounts).
- The old user_prompts.uses_count is a marketplace usage counter; it is
  retained unchanged for compatibility but is not a success metric.
- Read-only DB aggregation uses generations.input_params.trend_id (new
  /trends/{id}/run path), falling back to prompt_id (other studio flows).
  A generation referencing both contributes **once**. Only status=done
  qualifies as success; 7-day uses finished_at rather than submitted time.
- Feed remixes are counted once for status=done, grouping by
  COALESCE(source_feed_gen_id, parent_generation_id). This restores
  successful tasks whose feed source is present but their parent ID is not.
- Existing records are counted on demand; no DB rewrite, migrations or
  changes to billing/refunds are necessary.
- Historical tasks that never stored either the trend ID or the prompt ID
  cannot be attributed retroactively. Do not invent counts or substitute
  button clicks.
