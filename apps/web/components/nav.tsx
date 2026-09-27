"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const GROUPS: { title: string; items: [string, string][] }[] = [
  { title: "", items: [["/", "ホーム"]] },
  {
    title: "日々の取引",
    items: [
      ["/expenses", "経費の入力"],
      ["/journals/new", "仕訳の入力（振替など）"],
      ["/journals", "仕訳の一覧・検索"],
      ["/attachments", "証憑（領収書・請求書）"],
      ["/imports", "明細CSVの取込"],
      ["/recurring", "定型仕訳"],
    ],
  },
  { title: "売上", items: [["/invoices", "請求書"]] },
  {
    title: "役員・給与",
    items: [
      ["/payroll", "役員報酬・給与"],
      ["/withholding", "源泉所得税"],
      ["/year-end", "年末調整"],
      ["/housing", "借上げ社宅"],
    ],
  },
  {
    title: "決算",
    items: [
      ["/assets", "固定資産"],
      ["/closing", "決算・締め"],
      ["/reports", "帳票"],
    ],
  },
  { title: "書類", items: [["/documents", "書類管理"]] },
  {
    title: "設定",
    items: [
      ["/setup", "初期設定"],
      ["/masters", "科目・取引先・口座"],
      ["/settings", "税率・基準額"],
      ["/backup", "バックアップ"],
      ["/help", "ヘルプ"],
    ],
  },
];

/** 左メニュー */
export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const all = GROUPS.flatMap((g) => g.items.map(([href]) => href));
  const activeHref = all
    .filter((h) => (h === "/" ? pathname === "/" : pathname === h || pathname.startsWith(h + "/")))
    .sort((a, b) => b.length - a.length)[0];
  return (
    <nav className={`sidebar${open ? " open" : ""}`}>
      <button className="nav-toggle" onClick={() => setOpen(!open)}>
        ☰ メニュー
      </button>
      <div className="nav-body" onClick={() => setOpen(false)}>
        {GROUPS.map((g) => (
          <div key={g.title || "home"} className="nav-group">
            {g.title ? <div className="nav-group-title">{g.title}</div> : null}
            {g.items.map(([href, label]) => (
              <Link key={href} href={href} className={href === activeHref ? "active" : undefined}>
                {label}
              </Link>
            ))}
          </div>
        ))}
      </div>
    </nav>
  );
}
