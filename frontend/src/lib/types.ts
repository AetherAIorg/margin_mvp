export interface MetricSpec {
  id: string;
  required_inputs: Record<string, unknown>;
  transformation_plan: string[];
  calculation_function_id: string | null;
  validation_rules: string[] | null;
  approved_by: string | null;
  approved_at: string | null;
}

export interface Metric {
  id: string;
  canonical_name: string;
  description: string;
  domain: string;
  entity: string;
  grain: string;
  owner: string | null;
  status: string;
  version: string;
  tag_count: number;
  latest_tag: string | null;
  latest_digest: string | null;
  updated_at: string | null;
  specs: MetricSpec[];
}

export interface MetricTag {
  id: string;
  tag: string;
  digest: string;
  digest_short: string;
  published_by: string | null;
  published_at: string;
  status: string;
}

export interface MetricTagDetail extends MetricTag {
  manifest: Record<string, unknown>;
}

export interface Dataset {
  id: string;
  filename: string;
  detected_columns: string[] | null;
  row_count: number;
  uploaded_at: string;
}

export interface MetricRun {
  id: string;
  metric_id: string;
  dataset_id: string;
  status: string;
  transformation_plan_used: string[] | null;
  audit_log: Record<string, unknown> | null;
  warnings: string[] | null;
  errors: string[] | null;
  started_at: string;
  finished_at: string | null;
}

export interface SearchResult {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  snippet: string;
  score: number;
  href: string;
}

export interface FunctionDef {
  id: string;
  name: string;
  function_type: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  owner: string | null;
  status: string;
  version: string;
  implementations: { id: string; runtime: string; code_location: string | null; version: string; status: string }[];
}
