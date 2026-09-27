-- Migration number: 0004  書類管理（契約書・登記・口座開設・届出などの保管）
-- 会計の証憑とは別に、会社の書類を保管する。ファイル本体は R2（evidence バケットの documents/ 以下）に置く
CREATE TABLE documents (
  id                 TEXT PRIMARY KEY,
  title              TEXT NOT NULL,
  category           TEXT NOT NULL,         -- 契約書、登記・定款、口座開設、税務の届出、社会保険、保険、その他
  party              TEXT,                  -- 相手方（契約先・金融機関・提出先など）
  document_date      TEXT,                  -- 書類の日付（締結日・提出日など）
  expiry_date        TEXT,                  -- 期限・更新日（契約満了日など）
  notes              TEXT,
  r2_key             TEXT NOT NULL UNIQUE,
  original_filename  TEXT NOT NULL,
  content_type       TEXT NOT NULL,
  size_bytes         INTEGER NOT NULL,
  sha256             TEXT NOT NULL,
  archived_at        TEXT,                  -- 不要になった書類は非表示にする（ファイルは残す）
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL
);
CREATE INDEX idx_documents_category ON documents(category, document_date);
