-- Migration number: 0003  定型仕訳の生成記録（FR-14）。同じ月に二重に作らないため
CREATE TABLE recurring_runs (
  template_id       TEXT NOT NULL REFERENCES recurring_templates(id),
  year_month        TEXT NOT NULL,          -- 'YYYY-MM'
  journal_entry_id  TEXT NOT NULL REFERENCES journal_entries(id),
  created_at        TEXT NOT NULL,
  PRIMARY KEY (template_id, year_month)
);
