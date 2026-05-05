const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  PageNumber, Header, Footer, LevelFormat
} = require("docx");
const fs = require("fs");

// Colours
const DARK   = "1A1A2E";
const BLUE   = "0F3460";
const TEAL   = "1B6CA8";
const GREY   = "666666";
const LIGHT  = "F0F4F8";
const WHITE  = "FFFFFF";
const GREEN  = "1A7A4A";
const AMBER  = "B8860B";
const RED    = "C0392B";

const BORDER = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const BORDERS = { top: BORDER, bottom: BORDER, left: BORDER, right: BORDER };

// Helpers
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 140 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: TEAL, space: 6 } },
    children: [new TextRun({ text, bold: true, size: 30, color: DARK, font: "Arial" })]
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 100 },
    children: [new TextRun({ text, bold: true, size: 24, color: BLUE, font: "Arial" })]
  });
}
function p(text) {
  return new Paragraph({
    spacing: { before: 60, after: 100 },
    children: [new TextRun({ text, size: 22, font: "Arial", color: DARK })]
  });
}
function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, size: 22, font: "Arial", color: DARK })]
  });
}
function spacer(n = 1) {
  return Array.from({ length: n }, () =>
    new Paragraph({ spacing: { before: 0, after: 0 }, children: [new TextRun("")] })
  );
}
function cell(text, bg = WHITE, bold = false, align = AlignmentType.LEFT, color = DARK) {
  return new TableCell({
    borders: BORDERS,
    shading: { fill: bg, type: ShadingType.CLEAR },
    margins: { top: 100, bottom: 100, left: 140, right: 140 },
    children: [new Paragraph({
      alignment: align,
      children: [new TextRun({ text, size: 20, font: "Arial", bold, color })]
    })]
  });
}
function headerCell(text, bg = BLUE) {
  return cell(text, bg, true, AlignmentType.CENTER, WHITE);
}

// Sections

const cover = [
  ...spacer(3),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 60 },
    children: [new TextRun({ text: "PROVENANCE", size: 64, bold: true, color: DARK, font: "Arial" })]
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 60 },
    children: [new TextRun({
      text: "A CLI tool that turns your git history into an answerable knowledge base.",
      size: 24, color: TEAL, font: "Arial", italics: true
    })]
  }),
  ...spacer(2),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: "Personal open-source project — looking for honest feedback",
      size: 22, color: GREY, font: "Arial"
    })]
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 20, after: 0 },
    children: [new TextRun({ text: "MIT License | Python 3.12 | Self-Hosted", size: 20, color: GREY, font: "Arial" })]
  }),
  ...spacer(3),
];

const overview = [
  h1("What This Is"),
  p("PROVENANCE is a small Python tool that reads the git history of a repository and builds an answerable knowledge base of architectural decisions. You ask it a plain-English question (\"why was Redis added?\") and it returns a cited answer pulled from commit messages, ADR files, and similar sources."),
  p("It runs locally. It works with Claude, Gemini, or local Ollama models. It plugs into editors like Cursor and Claude Code through MCP. It is open source under the MIT license."),
  p("This is a personal project. There is no company, no funding, no plan to monetize. The goal is to build something useful, share it, and learn."),
  ...spacer(1),
  h2("Example"),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [new TableRow({ children: [new TableCell({
      borders: BORDERS,
      shading: { fill: LIGHT, type: ShadingType.CLEAR },
      margins: { top: 140, bottom: 140, left: 200, right: 200 },
      children: [
        new Paragraph({ children: [new TextRun({ text: "$ provenance ask \"why was Redis added?\"", size: 20, font: "Courier New", color: DARK, bold: true })] }),
        new Paragraph({ children: [new TextRun({ text: "", size: 16 })] }),
        new Paragraph({ children: [new TextRun({ text: "Load testing showed /products timing out at 200 concurrent", size: 20, font: "Courier New", color: DARK })] }),
        new Paragraph({ children: [new TextRun({ text: "users. Redis added with a 5-minute TTL. Reduced p99 latency", size: 20, font: "Courier New", color: DARK })] }),
        new Paragraph({ children: [new TextRun({ text: "from 4,200ms to 180ms.", size: 20, font: "Courier New", color: DARK })] }),
        new Paragraph({ children: [new TextRun({ text: "", size: 16 })] }),
        new Paragraph({ children: [new TextRun({ text: "Source: commit a3f9c12 by alice (2024-03-15)", size: 20, font: "Courier New", color: GREY })] }),
      ]
    })] })]
  }),
];

const problem = [
  h1("The Problem It Tries To Solve"),
  p("Codebases accumulate two kinds of debt: technical debt (messy code) and knowledge debt (no one remembers why decisions were made). AI coding tools like Cursor and Copilot help with the first. The second is mostly ignored."),
  p("The reasoning behind decisions lives in commit messages, Jira tickets, Slack threads, and the heads of engineers who may have moved on. Six months later, a new engineer sees a Redis cache layer and has no idea whether it was added for performance, security, or a specific incident."),
  p("PROVENANCE is one attempt to make that knowledge queryable. It's not the first or only attempt — there's a 2026 academic paper called \"Lore\" proposing a similar idea, and tools like Backstage have ADR support. PROVENANCE differs in that it works with existing messy git history rather than requiring teams to adopt a new commit format."),
];

const honestLimits = [
  h1("Honest Limitations"),
  p("Before getting excited about this, here is what it does not do well:"),
  ...spacer(1),
  bullet("Output quality is bounded by commit message quality. If your team writes \"wip\" and \"fix bug,\" there is nothing useful to extract. AI cannot reliably reconstruct intent from a code diff alone."),
  bullet("Indexing large repos can be slow and cost a few dollars on paid LLM APIs. Free options (Gemini's free tier, Ollama) work but with quality tradeoffs."),
  bullet("It does not read your actual code — that is what Cursor and Copilot do. It only reads the history of why the code changed."),
  bullet("The MCP editor integration only works in editors that support MCP (Cursor, Claude Code, Cline). Most editors don't yet."),
  bullet("It is not a replacement for ADRs. It complements them."),
  bullet("Solo project. Bug reports may sit. Don't depend on this in production."),
];

const positioning = [
  h1("How It Compares To Existing Tools"),
  p("Honest comparison — not a marketing chart:"),
  ...spacer(1),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3120, 3120, 3120],
    rows: [
      new TableRow({ children: [headerCell("Tool"), headerCell("What It Does"), headerCell("Where PROVENANCE Differs")] }),
      new TableRow({ children: [
        cell("Cursor / Copilot"),
        cell("Reads code, suggests next lines, completes functions"),
        cell("Different problem. Could complement them via MCP.")
      ] }),
      new TableRow({ children: [
        cell("Confluence / Notion"),
        cell("Manual decision documents written by humans"),
        cell("Automated. Works without team discipline. Trade-off: less precise.")
      ] }),
      new TableRow({ children: [
        cell("Backstage ADRs"),
        cell("ADR pages stored in a developer portal"),
        cell("Same data type. Different access pattern (CLI + AI vs. portal browse).")
      ] }),
      new TableRow({ children: [
        cell("\"Lore\" protocol (arXiv 2603.15566)"),
        cell("Proposed git commit format for embedding decisions"),
        cell("PROVENANCE works with existing history. Lore requires new commits.")
      ] }),
      new TableRow({ children: [
        cell("Plain git log + grep"),
        cell("What most people actually do"),
        cell("Better recall via semantic search and LLM synthesis. Costs money.")
      ] }),
    ]
  }),
];

const realRisks = [
  h1("Real Risks To This Project"),
  ...spacer(1),
  new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3120, 1560, 4680],
    rows: [
      new TableRow({ children: [headerCell("Risk"), headerCell("Severity", AMBER), headerCell("Mitigation")] }),
      new TableRow({ children: [
        cell("Garbage commits = garbage output"),
        cell("High", LIGHT, true, AlignmentType.CENTER, RED),
        cell("Phase 2 'provenance commit' wraps git commit and prompts richer messages going forward.")
      ] }),
      new TableRow({ children: [
        cell("GitHub absorbs the feature into Copilot"),
        cell("Medium", LIGHT, true, AlignmentType.CENTER, AMBER),
        cell("Self-hosted positioning + MCP openness gives a niche. Solo project can pivot fast.")
      ] }),
      new TableRow({ children: [
        cell("Solo project, hard to maintain"),
        cell("Medium", LIGHT, true, AlignmentType.CENTER, AMBER),
        cell("Keep scope small. Reject feature creep. MIT license invites contributors.")
      ] }),
      new TableRow({ children: [
        cell("Setup friction kills adoption"),
        cell("High", LIGHT, true, AlignmentType.CENTER, RED),
        cell("'provenance init' wizard with free Gemini default — one command end-to-end.")
      ] }),
      new TableRow({ children: [
        cell("API cost on first index"),
        cell("Medium", LIGHT, true, AlignmentType.CENTER, AMBER),
        cell("Default to Gemini free tier. Aggressive trivial-commit filtering. Ollama for offline.")
      ] }),
      new TableRow({ children: [
        cell("Engineers don't feel the pain until later"),
        cell("Medium", LIGHT, true, AlignmentType.CENTER, AMBER),
        cell("Onboarding pain is immediate. Lead with the 'I just joined this codebase' use case.")
      ] }),
    ]
  }),
];

const realisticOutcomes = [
  h1("Realistic Outcomes"),
  p("Stripping away the hype, here are honest possibilities for this project:"),
  ...spacer(1),
  h2("Most Likely (60-70% probability)"),
  bullet("Gets 100-1,000 GitHub stars over 6-12 months."),
  bullet("Used regularly by 10-50 small teams who already write decent commit messages."),
  bullet("Becomes a portfolio piece that demonstrates strong engineering."),
  bullet("Generates a few interesting blog posts and conference talks."),
  ...spacer(1),
  h2("Possible Upside (15-25% probability)"),
  bullet("Becomes the default open-source answer when people ask 'how do I document decisions'."),
  bullet("Gets 5,000-20,000 stars."),
  bullet("Used by some recognizable companies."),
  bullet("Attracts a few regular contributors who help maintain it."),
  ...spacer(1),
  h2("Tail Outcomes (low probability)"),
  bullet("GitHub or Anthropic ships a similar feature, making this redundant."),
  bullet("The MCP ecosystem fizzles out and the integration loses value."),
  bullet("Project gets abandoned because solo maintenance is hard."),
  ...spacer(1),
  p("All three outcomes are fine for a personal project. Even \"abandoned in 12 months\" leaves a strong code sample on the GitHub profile and useful learning."),
];

const whatToFeedback = [
  h1("What I'd Like Feedback On"),
  p("If you are reviewing this, the most useful questions to me are:"),
  ...spacer(1),
  bullet("Does the demo (provenance ask) actually feel useful when you run it on the test repo?"),
  bullet("Is the WHY-layer concept clear, or do I need to explain it differently?"),
  bullet("On YOUR codebase — would it be useful, or would it produce nothing because of weak commit messages?"),
  bullet("What's the smallest change that would make you actually use this?"),
  bullet("What features in the roadmap are obviously over-engineered? I cut a lot but probably missed some."),
  bullet("Are the limitations clear and honestly stated, or do they read as sandbagging?"),
  ...spacer(1),
  p("Things I do NOT need feedback on:"),
  bullet("Marketing copy or branding."),
  bullet("Whether this can be a startup (it cannot — H1B, no monetization)."),
  bullet("Stack choices (already settled: Python, SQLite, ChromaDB, FastMCP)."),
];

const links = [
  h1("Links"),
  ...spacer(1),
  p("GitHub: github.com/venumittapalli576/provenance (private; access on request)"),
  p("License: MIT"),
  p("Status: v0.1.0 — core works, demo runs end-to-end with the test repo"),
  p("Author: Venu Mittapalli"),
];

// Document
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } }
      }]
    }]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22, color: DARK } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: "Arial", color: DARK },
        paragraph: { spacing: { before: 360, after: 140 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 240, after: 100 }, outlineLevel: 1 } },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: TEAL, space: 6 } },
          children: [
            new TextRun({ text: "PROVENANCE", size: 18, bold: true, color: TEAL, font: "Arial" }),
            new TextRun({ text: "  |  Honest project overview for review", size: 18, color: GREY, font: "Arial" }),
          ]
        })]
      })
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 6 } },
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Page ", size: 18, color: GREY, font: "Arial" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 18, color: GREY, font: "Arial" }),
            new TextRun({ text: "  |  Personal open-source project  |  MIT License", size: 18, color: GREY, font: "Arial" }),
          ]
        })]
      })
    },
    children: [
      ...cover,
      ...spacer(2),
      ...overview,
      ...spacer(1),
      ...problem,
      ...spacer(1),
      ...honestLimits,
      ...spacer(1),
      ...positioning,
      ...spacer(1),
      ...realRisks,
      ...spacer(1),
      ...realisticOutcomes,
      ...spacer(1),
      ...whatToFeedback,
      ...spacer(1),
      ...links,
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("PROVENANCE_Overview.docx", buffer);
  console.log("Created: PROVENANCE_Overview.docx");
});
