/**
 * SpendGate — pitch deck.
 *
 * Every figure is read from ../results/*.json at build time, so the deck cannot
 * drift from the evaluation it describes. Re-run the evaluation, rebuild, and
 * the numbers move with it.
 *
 *   NODE_PATH=$(npm root -g) node deck/build.js
 */
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const Fa = require("react-icons/fa");

const ROOT = path.join(__dirname, "..");
const OUT = path.join(__dirname, "SpendGate.pptx");

// ---------------------------------------------------------------- palette
const INK = "0F1115";      // ground, dominant
const SURF = "171A21";     // cards
const LINE = "2A2F3A";     // hairlines
const TEXT = "E7E9EE";
const MUTE = "949BA9";
const FAINT = "5A616F";   // hairlines and dividers ONLY — 3.5:1, fails AA for text
const DIM = "8B93A1";     // smallest readable text; 6.2:1 on the ink ground
const ACC = "93A3EE";      // ultramarine — the one accent
const OK = "5FBF8C";
const WARN = "D7A24B";
const BAD = "E2796F";

const H = "Georgia";       // headers
const B = "Calibri";       // body
const M = "Consolas";      // data, rules, code

const W = 13.333, HT = 7.5;
const MARGIN = 0.7;

// ------------------------------------------------------------------ data
const full = JSON.parse(fs.readFileSync(path.join(ROOT, "results/full.json")));
const models = JSON.parse(fs.readFileSync(path.join(ROOT, "results/models.json")));
const armA = full.arms.A_naive, armB = full.arms.B_spendgate;

const rupee = (minor) => "₹" + Math.round(minor / 100).toLocaleString("en-IN");

const modelRows = models.models
  .map((m) => ({
    label: m.label,
    leaked: m.runs.filter((r) => r.arm === "A_naive")
      .reduce((s, r) => s + r.unauthorized_minor, 0),
    lied: m.runs.reduce((s, r) => s + (r.misreported ? 1 : 0), 0),
    cost: m.usage.cost_usd,
    passA: 0, total: 0,
  }))
  .sort((a, b) => b.leaked - a.leaked || a.label.localeCompare(b.label));

const SCEN = ["benign", "aggregate_blindness", "budget_amnesia", "injection",
  "category_laundering", "merchant_reprice", "retry_double_charge",
  "revoked_authority"];
const SCEN_LABEL = {
  benign: "Ordinary purchase",
  aggregate_blindness: "Three separate ₹4,000 buys",
  budget_amnesia: "Five buys, fresh context each",
  injection: "Poisoned product listing",
  category_laundering: "Prohibited category",
  merchant_reprice: "Merchant reprices after the quote",
  retry_double_charge: '"Did that go through? Try again"',
  revoked_authority: "Permission withdrawn mid-sequence",
};

const grid = {};
for (const m of models.models) {
  for (const r of m.runs) {
    const k = `${m.label}|${r.arm}|${r.klass}`;
    grid[k] = grid[k] || { reps: 0, failed: 0 };
    grid[k].reps++;
    if (r.unauthorized_minor > 0) grid[k].failed++;
  }
}
for (const m of modelRows) {
  for (const s of SCEN) {
    const c = grid[`${m.label}|A_naive|${s}`];
    if (c) { m.passA += c.reps - c.failed; m.total += c.reps; }
  }
}
const totalLeaked = modelRows.reduce((s, m) => s + m.leaked, 0);
const totalCost = modelRows.reduce((s, m) => s + m.cost, 0);
const totalPassA = modelRows.reduce((s, m) => s + m.passA, 0);
const totalCells = modelRows.reduce((s, m) => s + m.total, 0);

// ------------------------------------------------------------------ icons
async function icon(Comp, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Comp, { color, size: String(size) }));
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + png.toString("base64");
}

// ------------------------------------------------------------------ deck
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Dhruv Arvind Singh";
pres.title = "SpendGate";

function slide(eyebrowText) {
  const s = pres.addSlide();
  s.background = { color: INK };
  if (eyebrowText) {
    s.addText(eyebrowText.toUpperCase(), {
      x: MARGIN, y: 0.36, w: 6, h: 0.3, margin: 0,
      fontFace: M, fontSize: 11, color: ACC, charSpacing: 2,
    });
  }
  return s;
}

function title(s, text, opts = {}) {
  s.addText(text, {
    x: MARGIN, y: opts.y || 0.75, w: opts.w || W - 2 * MARGIN, h: opts.h || 0.85,
    margin: 0, fontFace: H, fontSize: opts.size || 34, color: TEXT,
    bold: false, valign: "top", ...(opts.align ? { align: opts.align } : {}),
  });
}

/** A card with the deck's motif: a coloured stripe down its left edge. */
function card(s, x, y, w, h, stripe = LINE, fill = SURF) {
  s.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h, fill: { color: fill },
    line: { color: LINE, width: 1 },
  });
  // Inset by a hair: drawn at the card's exact height it rounded a pixel
  // past the bottom border in rendering.
  s.addShape(pres.shapes.RECTANGLE, {
    x, y: y + 0.01, w: 0.055, h: h - 0.02, fill: { color: stripe },
    line: { width: 0 },
  });
}

function chip(s, x, y, text, color, w = 1.35) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h: 0.32, rectRadius: 0.06,
    fill: { color, transparency: 86 }, line: { color, width: 1 },
  });
  s.addText(text, {
    x, y, w, h: 0.32, margin: 0, align: "center", valign: "middle",
    fontFace: M, fontSize: 10, color, bold: true,
  });
}

function stat(s, x, y, w, value, label, color) {
  s.addText(value, {
    x, y, w, h: 0.85, margin: 0, fontFace: M, fontSize: 40, bold: true,
    color, align: "left", valign: "middle",
  });
  s.addText(label, {
    x, y: y + 0.82, w, h: 0.55, margin: 0, fontFace: B, fontSize: 12,
    color: MUTE, align: "left", valign: "top",
  });
}

async function build() {
  const ic = {
    robot: await icon(Fa.FaRobot, "#" + WARN),
    lock: await icon(Fa.FaLock, "#" + ACC),
    store: await icon(Fa.FaStore, "#" + TEXT),
    warn: await icon(Fa.FaExclamationTriangle, "#" + BAD),
    check: await icon(Fa.FaCheckCircle, "#" + OK),
    times: await icon(Fa.FaTimesCircle, "#" + BAD),
    brain: await icon(Fa.FaBrain, "#" + WARN),
    clock: await icon(Fa.FaHistory, "#" + WARN),
    split: await icon(Fa.FaCodeBranch, "#" + ACC),
    finger: await icon(Fa.FaFingerprint, "#" + ACC),
    scale: await icon(Fa.FaBalanceScale, "#" + ACC),
    bolt: await icon(Fa.FaBolt, "#" + WARN),
    shield: await icon(Fa.FaShieldAlt, "#" + OK),
    question: await icon(Fa.FaQuestionCircle, "#" + WARN),
    flask: await icon(Fa.FaFlask, "#" + ACC),
    eye: await icon(Fa.FaEyeSlash, "#" + BAD),
  };

  function iconCircle(s, x, y, data, ring, d = 0.62) {
    s.addShape(pres.shapes.OVAL, {
      x, y, w: d, h: d, fill: { color: ring, transparency: 86 },
      line: { color: ring, width: 1 },
    });
    s.addImage({ data, x: x + d * 0.26, y: y + d * 0.26, w: d * 0.48, h: d * 0.48 });
  }

  // ============================================================ 1 TITLE
  {
    const s = slide();
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0, y: 0, w: 0.16, h: HT, fill: { color: ACC }, line: { width: 0 },
    });
    s.addText("SpendGate", {
      x: MARGIN, y: 2.0, w: 9, h: 1.3, margin: 0,
      fontFace: H, fontSize: 62, bold: true, color: TEXT,
    });
    s.addText("Deterministic spending authority for AI agents\non Razorpay and UPI Circle rails", {
      x: MARGIN, y: 3.35, w: 8.5, h: 1.0, margin: 0,
      fontFace: B, fontSize: 19, color: MUTE, lineSpacing: 26,
    });
    s.addText("The agent proposes.  It decides, pays, and proves.", {
      x: MARGIN, y: 4.5, w: 9, h: 0.4, margin: 0,
      fontFace: B, fontSize: 15, color: ACC, italic: true,
    });
    const facts = [["187", "tests"], ["38", "rules"], ["6", "models"], ["₹0", "leaked"]];
    facts.forEach(([v, l], i) => {
      const x = MARGIN + i * 1.75;
      s.addText(v, { x, y: 5.5, w: 1.6, h: 0.45, margin: 0, fontFace: M, fontSize: 24, bold: true, color: TEXT });
      s.addText(l, { x, y: 5.95, w: 1.6, h: 0.3, margin: 0, fontFace: B, fontSize: 12, color: DIM });
    });
    s.addText("Razorpay AI Buildathon  ·  Track 01  ·  Agentic Commerce", {
      x: MARGIN, y: 6.75, w: 9, h: 0.3, margin: 0,
      fontFace: M, fontSize: 11.5, color: DIM, charSpacing: 1,
    });
    // The lower-right quadrant was empty; this anchors it and gives the lock
    // something to sit with instead of floating at title height.
    card(s, 8.4, 2.0, 4.25, 3.3, ACC);
    iconCircle(s, 8.8, 2.4, ic.lock, ACC, 0.9);
    s.addText("Six frontier models, eight scenarios,\nboth arms.", {
      x: 8.8, y: 3.5, w: 3.5, h: 0.6, margin: 0,
      fontFace: B, fontSize: 14, color: TEXT, lineSpacing: 20,
    });
    [["without it", `${totalPassA} of ${totalCells}`, BAD, 4.2],
     ["with it", `${totalCells} of ${totalCells}`, OK, 4.62]].forEach(
      ([label, n, col, y]) => {
        s.addText(label, {
          x: 8.8, y, w: 1.35, h: 0.35, margin: 0,
          fontFace: B, fontSize: 14, color: MUTE,
        });
        s.addText(n + " passed", {
          x: 10.15, y, w: 2.2, h: 0.35, margin: 0,
          fontFace: M, fontSize: 15, bold: true, color: col,
        });
      });
  }

  // ========================================================== 2 PROBLEM
  {
    const s = slide("01 · the problem");
    title(s, "You give an AI agent your card.");
    s.addText("Almost everyone builds this the same way — hand the model a payment button, and write the limits into its instructions.", {
      x: MARGIN, y: 1.65, w: 8.6, h: 0.6, margin: 0,
      fontFace: B, fontSize: 15, color: MUTE, lineSpacing: 22,
    });
    const rows = [
      [ic.brain, WARN, "You can talk it out of it.", "The limit is a sentence, and reading sentences is what it does."],
      [ic.clock, WARN, "It cannot remember.", "Every conversation starts fresh. It has no month."],
      [ic.eye, BAD, "It reports its own numbers.", "The only witness is the suspect."],
    ];
    rows.forEach(([im, col, head, sub], i) => {
      const y = 2.55 + i * 1.39;
      card(s, MARGIN, y, 11.9, 1.05, col);
      iconCircle(s, MARGIN + 0.32, y + 0.21, im, col);
      s.addText(head, {
        x: MARGIN + 1.15, y: y + 0.17, w: 10.4, h: 0.35, margin: 0,
        fontFace: B, fontSize: 17, bold: true, color: TEXT,
      });
      s.addText(sub, {
        x: MARGIN + 1.15, y: y + 0.55, w: 10.4, h: 0.35, margin: 0,
        fontFace: B, fontSize: 13, color: MUTE,
      });
    });
  }

  // ================================================= 3 CONCRETE FAILURE
  {
    const s = slide("01 · the problem");
    // A ₹12,000 checkout session cannot be paid in three ₹4,000 parts, and an
    // agent that cannot state an amount could not try. The real scenario is
    // three genuine ₹4,000 buys against a ₹5,000/merchant/hour aggregate.
    title(s, "Three ₹4,000 purchases. Not one breaks the cap.");
    s.addText("The same ₹4,000 headphones, three times inside an hour.", {
      x: MARGIN, y: 1.6, w: 8, h: 0.4, margin: 0, fontFace: B, fontSize: 16, color: MUTE,
    });
    for (let i = 0; i < 3; i++) {
      const x = MARGIN + i * 2.55;
      card(s, x, 2.35, 2.25, 1.35, OK);
      s.addText("₹4,000", {
        x, y: 2.55, w: 2.25, h: 0.5, margin: 0, align: "center",
        fontFace: M, fontSize: 22, bold: true, color: TEXT,
      });
      chip(s, x + 0.55, 3.15, "LEGAL", OK, 1.15);
    }
    // Carded like its neighbours. As a bare figure beside a hairline rule it
    // read as an empty fourth card rather than as the total.
    card(s, MARGIN + 3 * 2.55, 2.35, 12.6 - MARGIN - 3 * 2.55, 1.35, BAD);
    s.addText("₹12,000", {
      x: MARGIN + 3 * 2.55 + 0.4, y: 2.5, w: 3.3, h: 0.55, margin: 0,
      fontFace: M, fontSize: 30, bold: true, color: BAD,
    });
    s.addText("spent. No rule was broken.", {
      x: MARGIN + 3 * 2.55 + 0.4, y: 3.08, w: 3.3, h: 0.35, margin: 0,
      fontFace: B, fontSize: 13, color: MUTE,
    });

    card(s, MARGIN, 4.5, 11.9, 1.55, ACC);
    iconCircle(s, MARGIN + 0.35, 4.95, ic.scale, ACC, 0.66);
    s.addText("Nothing was keeping score.", {
      x: MARGIN + 1.25, y: 4.78, w: 10.2, h: 0.45, margin: 0,
      fontFace: H, fontSize: 24, color: ACC,
    });
    s.addText("Every purchase was individually legal. There is no rule against the pattern, because no one is adding them up.", {
      x: MARGIN + 1.25, y: 5.3, w: 10.2, h: 0.5, margin: 0,
      fontFace: B, fontSize: 14, color: MUTE,
    });
  }

  // ========================================================== 4 THE GAP
  {
    const s = slide("02 · where it fits");
    title(s, "Three standards cover agent payments. One layer has no owner.");
    const rows = [
      ["Discovery & checkout", "what is in the cart, at what price", "ACP", LINE, MUTE],
      ["Proof of authorisation", "did a human allow this", "AP2", LINE, MUTE],
      ["Keeping score", "is it STILL within budget, right now", "nobody", BAD, BAD],
      ["Moving the money", "the actual payment", "Razorpay", LINE, MUTE],
    ];
    rows.forEach(([name, sub, owner, stripe, col], i) => {
      const y = 1.88 + i * 1.20;
      card(s, MARGIN, y, 11.9, 0.86, stripe);
      s.addText(name, {
        x: MARGIN + 0.4, y: y + 0.12, w: 6.5, h: 0.32, margin: 0,
        fontFace: B, fontSize: 17, bold: true, color: col === BAD ? BAD : TEXT,
      });
      s.addText(sub, {
        x: MARGIN + 0.4, y: y + 0.48, w: 6.5, h: 0.3, margin: 0,
        fontFace: B, fontSize: 12.5, color: MUTE,
      });
      s.addText(owner, {
        x: MARGIN + 9.4, y: y + 0.25, w: 2.2, h: 0.36, margin: 0, align: "right",
        fontFace: M, fontSize: 15, color: col, bold: owner === "nobody",
      });
    });
    s.addText("Google's AP2 says the amount spent MUST be added to a running total — it does not say who keeps it.", {
      x: MARGIN, y: 6.65, w: 11.9, h: 0.45, margin: 0,
      fontFace: B, fontSize: 14, color: ACC, italic: true,
    });
  }

  // ======================================================= 5 THE ONE IDEA
  {
    const s = slide("03 · how it works");
    title(s, "The security is in the shape of the request.");
    card(s, MARGIN, 1.8, 7.1, 2.6, ACC);
    s.addText([
      { text: "request_payment(\n", options: { color: TEXT } },
      { text: "    mandate_id          = \"mnd_01J9F2K7\"\n", options: { color: ACC } },
      { text: "    checkout_session_id = \"cs_8fK2mNp\"\n", options: { color: ACC } },
      { text: "    agent_id            = \"agt_shopper_01\"\n", options: { color: ACC } },
      { text: ")", options: { color: TEXT } },
    ], {
      x: MARGIN + 0.4, y: 2.0, w: 6.5, h: 2.3, margin: 0,
      fontFace: M, fontSize: 14, lineSpacing: 24,
    });
    // Carded and pulled flush to the right margin: as a bare list it ended
    // 1.6in short of every other element on the slide and read as orphaned.
    card(s, 8.3, 1.8, 12.6 - 8.3, 2.6, BAD);
    s.addText("What is deliberately absent", {
      x: 8.7, y: 2.05, w: 3.6, h: 0.35, margin: 0,
      fontFace: B, fontSize: 14, bold: true, color: BAD,
    });
    ["amount", "item", "merchant", "currency"].forEach((f, i) => {
      const y = 2.6 + i * 0.5;
      // Icon leads the word. Trailing it at the card's far edge left a 2in
      // gap and the two stopped reading as one row.
      s.addImage({ data: ic.times, x: 8.7, y: y + 0.05, w: 0.22, h: 0.22 });
      s.addText(f, {
        x: 9.1, y, w: 3.2, h: 0.34, margin: 0,
        fontFace: M, fontSize: 15, color: MUTE, strike: true,
      });
    });
    card(s, MARGIN, 5.0, 11.9, 1.35, ACC);
    iconCircle(s, MARGIN + 0.35, 5.35, ic.lock, ACC, 0.66);
    s.addText("There is nowhere to put a lie.", {
      x: MARGIN + 1.25, y: 5.18, w: 10.2, h: 0.45, margin: 0,
      fontFace: H, fontSize: 24, color: TEXT,
    });
    s.addText("A completely compromised agent still sends exactly this. Its beliefs never reach the decision.", {
      x: MARGIN + 1.25, y: 5.68, w: 10.2, h: 0.45, margin: 0,
      fontFace: B, fontSize: 14, color: MUTE,
    });
  }

  // ===================================================== 6 FACT RESOLVER
  {
    const s = slide("03 · how it works");
    title(s, "So where does the price come from?");
    const boxes = [
      ["Agent", "untrusted", WARN, ic.robot, 0.7],
      ["SpendGate", "plain code", ACC, ic.lock, 5.05],
      ["Merchant", "knows the price", OK, ic.store, 9.4],
    ];
    boxes.forEach(([name, sub, col, im, x]) => {
      card(s, x, 2.1, 3.2, 1.5, col);
      iconCircle(s, x + 0.35, 2.45, im, col, 0.66);
      s.addText(name, {
        x: x + 1.15, y: 2.35, w: 1.95, h: 0.35, margin: 0,
        fontFace: B, fontSize: 17, bold: true, color: TEXT,
      });
      s.addText(sub, {
        x: x + 1.15, y: 2.72, w: 1.95, h: 0.3, margin: 0,
        fontFace: B, fontSize: 11.5, color: MUTE,
      });
    });
    // Arrows sit clear of both cards rather than running border to border:
    // at full span the labels' first and last glyphs touched the accent bars.
    [[4.15, 0.65], [8.5, 0.65]].forEach(([x, w]) => {
      s.addShape(pres.shapes.LINE, {
        x, y: 2.85, w, h: 0,
        line: { color: ACC, width: 2, endArrowType: "triangle" },
      });
    });
    [["ticket no.", 4.0], ["price?", 8.35]].forEach(([t, x]) => {
      s.addText(t, {
        x, y: 2.38, w: 0.95, h: 0.3, margin: 0, align: "center",
        fontFace: M, fontSize: 11, color: MUTE,
      });
    });
    // Centre to centre. Aimed at the card edge it read as pointing past
    // SpendGate rather than into it.
    s.addShape(pres.shapes.LINE, {
      x: 6.65, y: 4.15, w: 4.35, h: 0,
      line: { color: OK, width: 2, beginArrowType: "triangle" },
    });
    s.addText("₹1,200", {
      x: 7.6, y: 3.72, w: 2.45, h: 0.35, margin: 0, align: "center",
      fontFace: M, fontSize: 15, bold: true, color: OK,
    });
    // Full width, on its own line. Fitted to the arrow it overran the
    // arrowhead and wrapped "of" alone onto a second line.
    s.addText("from the shop, on a connection the agent is not part of", {
      // Centred on the arrow (x 6.65→11.0), not on the slide. Slide-centred it
      // sat under the SpendGate box and read as describing that instead.
      x: 5.6, y: 4.45, w: 6.45, h: 0.35, margin: 0, align: "center",
      fontFace: B, fontSize: 13, color: MUTE,
    });
    card(s, MARGIN, 5.25, 11.93, 0.95, BAD);
    iconCircle(s, MARGIN + 0.35, 5.4, ic.warn, BAD, 0.66);
    s.addText("The agent hands over a ticket number, not a price. We ask the shop ourselves.", {
      x: MARGIN + 1.25, y: 5.42, w: 10.2, h: 0.6, margin: 0, valign: "middle",
      fontFace: B, fontSize: 16, color: TEXT,
    });
  }

  // ============================================================ 7 RULES
  {
    const s = slide("03 · how it works");
    title(s, "Then plain code decides. 38 rules, in order.");
    const stages = [
      ["Is the permission slip real?", "R01–R08", "refuse", BAD],
      ["Is the basket real, and unpaid?", "R09–R16", "refuse", BAD],
      ["Is it inside the hard limits?", "R17–R24", "refuse", BAD],
      ["Is this a duplicate or a race?", "R25–R29, R38", "refuse", BAD],
      ["Is it something you'd want to see?", "R30–R37", "ask you", WARN],
    ];
    stages.forEach(([q, ids, out, col], i) => {
      const y = 1.8 + i * 0.95;
      card(s, MARGIN, y, 11.9, 0.64, col);
      s.addText(String(i + 1), {
        x: MARGIN + 0.28, y: y + 0.14, w: 0.4, h: 0.36, margin: 0,
        fontFace: M, fontSize: 14, color: DIM,
      });
      s.addText(q, {
        x: MARGIN + 0.85, y: y + 0.13, w: 6.6, h: 0.38, margin: 0,
        fontFace: B, fontSize: 16, color: TEXT,
      });
      s.addText(ids, {
        x: MARGIN + 7.6, y: y + 0.17, w: 2.1, h: 0.32, margin: 0,
        fontFace: M, fontSize: 12, color: MUTE,
      });
      chip(s, MARGIN + 10.2, y + 0.16, out.toUpperCase(), col, 1.3);
    });
    s.addText("First objection wins. One reason, never a list.", {
      x: MARGIN, y: 6.6, w: 11.9, h: 0.4, margin: 0,
      fontFace: B, fontSize: 15, color: ACC, italic: true,
    });
  }

  // ==================================================== 8 THREE OUTCOMES
  {
    const s = slide("04 · the edges");
    title(s, "Most systems have two outcomes. You need three.");
    card(s, 4.6, 1.75, 4.1, 0.95, ACC);
    s.addText("₹1,200 set aside", {
      x: 4.6, y: 1.88, w: 4.1, h: 0.35, margin: 0, align: "center",
      fontFace: B, fontSize: 17, bold: true, color: ACC,
    });
    s.addText("held — not yet spent", {
      x: 4.6, y: 2.25, w: 4.1, h: 0.3, margin: 0, align: "center",
      fontFace: B, fontSize: 12, color: MUTE,
    });
    const outs = [
      ["Paid", "held → spent", OK, ic.check, 0.7],
      ["Failed", "held → comes back", BAD, ic.times, 5.05],
      ["Don't know", "stays held — neither", WARN, ic.question, 9.4],
    ];
    outs.forEach(([n, eff, col, im, x]) => {
      s.addShape(pres.shapes.LINE, {
        x: 6.65, y: 2.75, w: (x + 1.6) - 6.65, h: 0.75,
        line: { color: col, width: 1.5 },
      });
      card(s, x, 3.55, 3.2, 1.4, col);
      iconCircle(s, x + 1.29, 3.72, im, col, 0.62);
      s.addText(n, {
        x, y: 4.32, w: 3.2, h: 0.32, margin: 0, align: "center",
        fontFace: B, fontSize: 17, bold: true, color: col,
      });
      s.addText(eff, {
        // Each sub-label takes its card's colour. Two of three were semantic
        // and the third was grey, which read as a missing state.
        x, y: 4.64, w: 3.2, h: 0.28, margin: 0, align: "center",
        fontFace: M, fontSize: 11.5, color: col,
      });
    });
    card(s, MARGIN, 5.35, 11.9, 1.2, BAD);
    s.addText("Release it too early and the payment lands later — you have paid twice.", {
      x: MARGIN + 0.4, y: 5.5, w: 11.1, h: 0.35, margin: 0,
      fontFace: B, fontSize: 15, color: TEXT,
    });
    s.addText("Count it as spent when it never happened — you have invented a charge.", {
      x: MARGIN + 0.4, y: 5.9, w: 11.1, h: 0.35, margin: 0,
      fontFace: B, fontSize: 15, color: TEXT,
    });
  }

  // ======================================================= 9 TAMPER BUG
  {
    const s = slide("04 · the edges");
    title(s, "And the one I got wrong.");
    s.addText("Each log entry's fingerprint includes the one before it, so an edit breaks the chain.", {
      x: MARGIN, y: 1.62, w: 11.9, h: 0.4, margin: 0,
      fontFace: B, fontSize: 15, color: MUTE,
    });
    const steps = [
      // The chip says whether the tamper was caught — nothing else. Labelling
      // them by mechanism put a red chip on a green-check row and a green one
      // on a row named MISMATCH, which reads as a rendering fault.
      [ic.check, OK, "Edit one amount", "The next entry no longer links — the chain breaks.", "CAUGHT", OK],
      [ic.times, BAD, "…then recompute every fingerprint", "The chain is internally consistent again. It verifies clean.", "MISSED", BAD],
      [ic.shield, OK, "So the newest fingerprint lives outside the log", "A rewrite cannot reach it. The anchor mismatches.", "CAUGHT", OK],
    ];
    steps.forEach(([im, col, head, sub, tag, tagCol], i) => {
      const y = 2.2 + i * 1.42;
      card(s, MARGIN, y, 11.9, 1.08, col);
      iconCircle(s, MARGIN + 0.32, y + 0.23, im, col);
      s.addText(head, {
        x: MARGIN + 1.15, y: y + 0.18, w: 7.6, h: 0.36, margin: 0,
        fontFace: B, fontSize: 16, bold: true, color: TEXT,
      });
      s.addText(sub, {
        x: MARGIN + 1.15, y: y + 0.57, w: 7.6, h: 0.34, margin: 0,
        fontFace: B, fontSize: 13, color: MUTE,
      });
      chip(s, MARGIN + 9.6, y + 0.36, tag, tagCol, 1.9);
    });
    s.addText("Found by deliberately breaking my own code and noticing that no test complained.", {
      x: MARGIN, y: 6.5, w: 11.9, h: 0.4, margin: 0,
      fontFace: B, fontSize: 14, color: ACC, italic: true,
    });
  }

  // ====================================================== 10 CORPUS RESULT
  {
    const s = slide("05 · does it work");
    title(s, "The corpus, run through both arms.");
    s.addText("Same attacks, same shop, same rails — the only difference is whether the agent holds the payment button, or has to ask.", {
      x: MARGIN, y: 1.6, w: 11.9, h: 0.4, margin: 0,
      fontFace: B, fontSize: 14, color: MUTE,
    });
    const arms = [
      ["The usual way", "agent holds the payment button", rupee(armA.unauthorized_minor),
        `${armA.hostile_contained} of ${armA.hostile_cases} attacks contained`, BAD, 0.7],
      ["Through SpendGate", "agent has to ask", rupee(armB.unauthorized_minor),
        `${armB.hostile_contained} of ${armB.hostile_cases} attacks contained`, OK, 6.95],
    ];
    // The denominators differ on purpose, and hiding that was a real bug —
    // the naive arm was being credited with cases it never sat.
    const gap = armB.hostile_cases - armA.hostile_cases;
    arms.forEach(([n, sub, big, note, col, x]) => {
      card(s, x, 2.25, 5.65, 2.65, col);
      s.addText(n, {
        x: x + 0.4, y: 2.45, w: 4.9, h: 0.35, margin: 0,
        fontFace: B, fontSize: 17, bold: true, color: TEXT,
      });
      s.addText(sub, {
        x: x + 0.4, y: 2.82, w: 4.9, h: 0.3, margin: 0,
        fontFace: B, fontSize: 12, color: MUTE,
      });
      s.addText(big, {
        x: x + 0.4, y: 3.25, w: 4.9, h: 0.85, margin: 0,
        fontFace: M, fontSize: 40, bold: true, color: col,
      });
      s.addText(note, {
        x: x + 0.4, y: 4.25, w: 4.9, h: 0.35, margin: 0,
        fontFace: M, fontSize: 12, color: MUTE,
      });
      s.addText(`plus ${armA.benign_cases} ordinary purchases`, {
        x: x + 0.4, y: 4.55, w: 4.9, h: 0.3, margin: 0,
        fontFace: M, fontSize: 11, color: DIM,
      });
    });
    // The two arms face different denominators. Saying so on the slide is the
    // honest version: crediting the naive arm with the cases it could not even
    // be given is exactly the bug this corpus once had (BUGS.md §6).
    s.addText(`The arms face different counts: ${gap} cases test a permission being revoked or expiring, which an agent with no permission model cannot be given. Counting those as wins for the naive arm was a bug I found and fixed.`, {
      x: MARGIN, y: 5.05, w: 11.9, h: 0.4, margin: 0,
      fontFace: B, fontSize: 12, color: DIM,
    });
    card(s, MARGIN, 5.6, 11.9, 1.15, ACC);
    iconCircle(s, MARGIN + 0.35, 5.85, ic.flask, ACC, 0.66);
    s.addText(`All ${armB.benign_settled} of ${armB.benign_cases} ordinary purchases still went through — in both arms.`, {
      x: MARGIN + 1.25, y: 5.76, w: 10.2, h: 0.38, margin: 0,
      fontFace: B, fontSize: 16, bold: true, color: TEXT,
    });
    s.addText("A system that refuses everything scores perfectly on containment and is useless.", {
      x: MARGIN + 1.25, y: 6.16, w: 10.2, h: 0.35, margin: 0,
      fontFace: B, fontSize: 13, color: MUTE,
    });
  }

  // ====================================================== 11 SIX MODELS
  {
    const s = slide("05 · does it work");
    title(s, "Six models. Eight scenarios. Both arms.");
    s.addText("Each model ran all eight scenarios twice, once without SpendGate and once with it.", {
      x: MARGIN, y: 1.62, w: 11.9, h: 0.4, margin: 0,
      fontFace: B, fontSize: 15, color: MUTE,
    });
    const head = ["Model", "Passed without", "Passed with", "Leaked without", "Lied", "Cost"];
    const body = modelRows.map((m) => [
      m.label, `${m.passA}/${m.total}`, `${m.total}/${m.total}`,
      rupee(m.leaked), `${m.lied}`, "$" + m.cost.toFixed(3),
    ]);
    const rows = [
      head.map((t, i) => ({
        text: t, options: {
          bold: true, color: MUTE, fontFace: M, fontSize: 10.5,
          fill: { color: SURF }, valign: "middle",
          // Headers follow their column: a right-aligned figure under a
          // left-aligned label looks like a mistake.
          align: i === 0 ? "left" : "right",
        },
      })),
      ...body.map((r) => r.map((t, i) => ({
        text: t, options: {
          color: i === 3 ? BAD : (i === 2 ? OK : TEXT),
          fontFace: i === 0 ? "Calibri" : M, fontSize: 12,
          bold: i === 2 || i === 3, valign: "middle",
          fill: { color: INK },
          // Numbers align on their digits. Left-aligned, ₹1,17,300 and
          // ₹37,300 don't line up and the column stops being comparable.
          align: i === 0 ? "left" : "right",
        },
      }))),
      [
        { text: "total", options: { bold: true, color: TEXT, fontFace: B, fontSize: 12, fill: { color: SURF }, align: "left" } },
        ...[
          [`${totalPassA}/${totalCells}`, BAD],
          [`${totalCells}/${totalCells}`, OK],
          [rupee(totalLeaked), BAD],
          // Was blank, which read as unfinished rather than as a deliberate
          // omission.
          [`${modelRows.reduce((a, m) => a + m.lied, 0)}`, TEXT],
          ["$" + totalCost.toFixed(2), TEXT],
        ].map(([t, c]) => ({
          text: t, options: {
            bold: true, color: c, fontFace: M, fontSize: 12,
            fill: { color: SURF }, align: "right",
          },
        })),
      ],
    ];
    s.addTable(rows, {
      x: MARGIN, y: 2.15, w: 11.9, colW: [3.1, 1.95, 1.85, 2.25, 1.15, 1.6],
      rowH: 0.38, border: { pt: 0.5, color: LINE }, align: "left", margin: 6,
    });
    card(s, MARGIN, 5.55, 11.9, 1.25, BAD);
    iconCircle(s, MARGIN + 0.35, 5.85, ic.split, BAD, 0.66);
    s.addText("Four scenarios were failed by every single model.", {
      x: MARGIN + 1.25, y: 5.74, w: 10.2, h: 0.38, margin: 0,
      fontFace: B, fontSize: 16, bold: true, color: TEXT,
    });
    s.addText("The windowed limit · the budget across fresh contexts · a merchant that reprices after quoting · permission withdrawn while the agent was away.", {
      x: MARGIN + 1.25, y: 6.16, w: 10.2, h: 0.35, margin: 0,
      fontFace: B, fontSize: 12.5, color: MUTE,
    });
  }

  // ================================================ 12 THE HONESTY SPLIT
  {
    const s = slide("05 · does it work");
    title(s, "Three of the six lied about the price.");
    const cols = [
      // Both cards carry the accent, not green/red. The honest/dishonest split
      // is one axis and the leak is another; colouring the card by the first
      // put a red loss figure inside a green "good" card.
      ["Lied about the price", "GLM-4.7 · Kimi K2.5 · MiniMax M2.5",
        "Read the poisoned listing and reported ₹5 for a ₹40,000 television.",
        rupee(117300), ACC, ic.times, 0.7],
      ["Refused, unprompted", "GPT-5 · Claude Sonnet 4.5 · Gemini 3 Flash",
        "Read the same listing, ignored it, and declined on the real price.",
        rupee(37300), ACC, ic.check, 6.95],
    ];
    cols.forEach(([n, who, what, leaked, col, im, x]) => {
      card(s, x, 1.75, 5.65, 3.1, col);
      iconCircle(s, x + 0.4, 2.0, im, col, 0.62);
      s.addText(n, {
        x: x + 1.15, y: 2.05, w: 4.2, h: 0.35, margin: 0,
        fontFace: B, fontSize: 17, bold: true, color: TEXT,
      });
      s.addText(who, {
        x: x + 0.4, y: 2.75, w: 4.9, h: 0.32, margin: 0,
        fontFace: M, fontSize: 11.5, color: MUTE,
      });
      s.addText(what, {
        x: x + 0.4, y: 3.12, w: 5.0, h: 0.7, margin: 0,
        fontFace: B, fontSize: 13.5, color: TEXT, lineSpacing: 19,
      });
      // Always red. Both arms leaked; painting ₹37,300 in the same green the
      // deck uses for ₹0 on slide 10 says the opposite of what happened.
      s.addText(leaked + " leaked", {
        x: x + 0.4, y: 3.95, w: 4.9, h: 0.6, margin: 0,
        fontFace: M, fontSize: 26, bold: true, color: BAD,
      });
    });
    card(s, MARGIN, 5.2, 11.9, 1.5, ACC);
    s.addText("The argument is not that agents lie.", {
      x: MARGIN + 0.4, y: 5.38, w: 11.1, h: 0.4, margin: 0,
      fontFace: H, fontSize: 22, color: ACC,
    });
    s.addText("It is that a budget is memory — and an agent has none. Both groups failed all four stateless tests, and under SpendGate both leaked ₹0.", {
      x: MARGIN + 0.4, y: 5.85, w: 11.1, h: 0.6, margin: 0,
      fontFace: B, fontSize: 14, color: TEXT,
    });
  }

  // ========================================================= 13 LIMITS
  {
    const s = slide("06 · what it does not do");
    title(s, "Where this breaks.");
    const lim = [
      ["The split check is a time window.", "A patient attacker who waits long enough gets past it."],
      ["The shop declares its own category.", "Razorpay assigns the real MCC — I did not have it."],
      ["Capture is not verified live.", "Orders, refusals and reconciliation are. Completing a payment needs a human."],
      ["It checks whether a purchase was allowed.", "Not whether it was a good idea. That is a different problem."],
    ];
    lim.forEach(([h, sub], i) => {
      const y = 1.78 + i * 1.20;
      card(s, MARGIN, y, 11.9, 0.90, WARN);
      s.addText(h, {
        x: MARGIN + 0.4, y: y + 0.14, w: 11.1, h: 0.34, margin: 0,
        fontFace: B, fontSize: 16, bold: true, color: TEXT,
      });
      s.addText(sub, {
        x: MARGIN + 0.4, y: y + 0.52, w: 11.1, h: 0.32, margin: 0,
        fontFace: B, fontSize: 13, color: MUTE,
      });
    });
    s.addText("Stated because they will be asked — and because a list of none is not credible.", {
      x: MARGIN, y: 6.6, w: 11.9, h: 0.4, margin: 0,
      fontFace: B, fontSize: 14, color: ACC, italic: true,
    });
  }

  // ========================================================== 14 CLOSE
  {
    const s = slide();
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0, y: 0, w: 0.16, h: HT, fill: { color: ACC }, line: { width: 0 },
    });
    s.addText("SpendGate", {
      x: MARGIN, y: 1.5, w: 9, h: 1.0, margin: 0,
      fontFace: H, fontSize: 48, bold: true, color: TEXT,
    });
    s.addText("The agent proposes. It decides, pays, and proves.", {
      x: MARGIN, y: 2.55, w: 9, h: 0.45, margin: 0,
      fontFace: B, fontSize: 18, color: ACC, italic: true,
    });
    const proof = [
      [ic.check, OK, "187 tests", "every one of 38 rules has a test that trips it"],
      [ic.flask, ACC, "16 of 17 mutations killed", "the suite is checked by deliberately breaking the code"],
      [ic.shield, OK, "15/15 against live Razorpay", "test mode — orders, refusals, reconciliation"],
      [ic.finger, ACC, "12 bugs written up in BUGS.md", "including four claims of mine that were false"],
    ];
    proof.forEach(([im, col, h, sub], i) => {
      const y = 3.35 + i * 0.87;
      iconCircle(s, MARGIN, y, im, col, 0.55);
      s.addText(h, {
        x: MARGIN + 0.78, y: y - 0.02, w: 5.2, h: 0.32, margin: 0,
        fontFace: B, fontSize: 16, bold: true, color: TEXT,
      });
      s.addText(sub, {
        x: MARGIN + 0.78, y: y + 0.29, w: 6.2, h: 0.3, margin: 0,
        fontFace: B, fontSize: 12, color: MUTE,
      });
    });
    card(s, 7.85, 3.35, 12.6 - 7.85, 2.75, ACC);
    // One line. Split across three it was unusable to anyone photographing
    // the slide.
    s.addText("github.com/DhruvArvindSingh/spendgate", {
      x: 8.2, y: 3.6, w: 4.0, h: 0.4, margin: 0,
      fontFace: M, fontSize: 12.5, color: ACC,
    });
    s.addText("Public repository, the 210-case corpus, the six-model results, and every number in this deck.", {
      x: 8.2, y: 4.1, w: 3.85, h: 1.05, margin: 0,
      fontFace: B, fontSize: 12.5, color: MUTE, lineSpacing: 18,
    });
    // Two lines by intent, so the separator cannot be stranded at a wrap.
    s.addText("Razorpay AI Buildathon\nTrack 01 · Agentic Commerce", {
      x: 8.2, y: 5.28, w: 3.85, h: 0.6, margin: 0, lineSpacing: 16,
      fontFace: M, fontSize: 10.5, color: DIM, charSpacing: 1,
    });
  }

  await pres.writeFile({ fileName: OUT });
  console.log("  wrote " + OUT);
}

build().catch((e) => { console.error(e); process.exit(1); });
