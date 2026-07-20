import ExcelJS from "exceljs";

const PLAY_LABEL = {
  reputation: "Reply & correct the record",
  discovery: "Answer & get discovered",
};

const HEADER_FILL = "FF2B2B2B";
const HEADER_FONT = "FFFFFFFF";

const COLUMNS = [
  { header: "Subreddit", key: "subreddit", width: 20 },
  { header: "Play", key: "category", width: 24 },
  { header: "URL", key: "url", width: 46 },
  { header: "Status", key: "status", width: 22 },
  { header: "Citations", key: "total_count", width: 11 },
  { header: "Reputation citations", key: "reputation_count", width: 13 },
  { header: "Discovery citations", key: "discovery_count", width: 13 },
  { header: "QC-branded subreddit", key: "is_qc_subreddit", width: 14 },
  { header: "Questions", key: "questions", width: 45 },
  { header: "How to participate", key: "strategy", width: 55 },
];

// Actionable-first, most-recently-cited-first is already the row order from
// the API - this just makes WHY visible in the sheet, so a dead/restricted
// lead can't be mistaken for a live one the way the un-annotated export was.
function statusLabel(t) {
  if (t.dead) return t.dead_reason === "archived" ? "Archived — can't comment" : "Against subreddit rules";
  if (t.restricted) return `Self-promo restricted${t.restriction_mechanism ? ` — ${t.restriction_mechanism}` : ""}`;
  return "Open";
}

// One line per numbered step, so the cell reads as a list rather than one
// run-on sentence - this is what actually makes it readable without opening
// the cell, once wrapText + a tall enough row height are applied below.
function numberedLines(items) {
  return (items || []).map((item, i) => `${i + 1}. ${item}`).join("\n");
}

export async function downloadRedditSpotlightXlsx(threads, strategy) {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("Reddit spotlight", {
    views: [{ state: "frozen", ySplit: 1 }],
  });
  sheet.columns = COLUMNS;

  sheet.getRow(1).eachCell((cell) => {
    cell.font = { bold: true, color: { argb: HEADER_FONT } };
    cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: HEADER_FILL } };
    cell.alignment = { vertical: "middle", wrapText: true };
  });

  for (const t of threads) {
    const questionLines = numberedLines(t.questions);
    const strategyLines = numberedLines(strategy?.[t.category]);

    const row = sheet.addRow({
      ...t,
      category: PLAY_LABEL[t.category] ?? PLAY_LABEL.discovery,
      status: statusLabel(t),
      is_qc_subreddit: t.is_qc_subreddit ? "Yes" : "",
      questions: questionLines,
      strategy: strategyLines,
    });

    row.eachCell((cell) => {
      cell.alignment = { vertical: "top", wrapText: true };
    });

    // Excel doesn't auto-fit row height for wrapped text on file open - size
    // it ourselves from the taller of the two multi-line columns, so every
    // line is visible without clicking into the cell.
    const lineCount = Math.max(
      t.questions?.length || 1,
      strategy?.[t.category]?.length || 1,
    );
    row.height = 15 * lineCount;
  }

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "reddit-spotlight.xlsx";
  a.click();
  URL.revokeObjectURL(url);
}
