#!/bin/bash
# Claude Code status line: model name, context usage bar, session (5 hour) usage %,
# week (7 day) usage % and spend: spend limit usage % when supplied, otherwise the
# estimated cost of the current session in USD.
#
# Created using: Claude Sonnet-v5-date: 210926
#
# Inputs:  JSON on stdin from Claude Code. Fields used:
#            model.display_name
#            context_window.used_percentage
#            rate_limits.five_hour.used_percentage
#            rate_limits.seven_day.used_percentage
#            rate_limits.spend_limit.used_percentage
#            cost.total_cost_usd
#          rate_limits appears only for claude.ai Pro and Max subscribers (or behind a
#          gateway that sets a spend limit), and only after the first API response.
#          Each window may be absent. An absent value is shown as "--".
# Output:  one line on stdout, with ANSI colours. Colour thresholds: green below 50,
#          yellow from 50, red from 80.
# Notes:   Claude Code supplies no remaining credit value. The spend limit percentage
#          is absent for most claude.ai subscribers, so the session cost (an estimate,
#          current session only, USD) is shown in its place. Uses node for JSON parsing
#          (jq is not installed in this Git Bash environment).

node -e '
let data = "";
process.stdin.on("data", c => data += c);
process.stdin.on("end", () => {
  let j = {};
  try { j = JSON.parse(data); } catch (e) {}

  const num = v => (typeof v === "number" && !Number.isNaN(v)) ? v : null;
  const rl = j.rate_limits || {};
  const pick = w => num(rl[w] && rl[w].used_percentage);

  const model = (j.model && j.model.display_name) || "Claude";
  const ctx = num(j.context_window && j.context_window.used_percentage);
  const five = pick("five_hour");
  const week = pick("seven_day");
  const spend = pick("spend_limit");
  const cost = num(j.cost && j.cost.total_cost_usd);

  const esc = "\x1b[";
  const reset = esc + "0m";
  const colour = p => p === null ? esc + "90m" : p >= 80 ? esc + "31m" : p >= 50 ? esc + "33m" : esc + "32m";
  const fmt = p => p === null ? "--" : Math.round(p) + "%";

  // Context bar, clamped to 0-100
  const used = Math.min(100, Math.max(0, Math.round(ctx === null ? 0 : ctx)));
  const width = 10;
  const filled = Math.floor(used * width / 100);
  const bar = "#".repeat(filled) + "-".repeat(width - filled);

  const part = (label, p) => label + " " + colour(p) + fmt(p) + reset;
  const sep = " " + esc + "90m|" + reset + " ";

  const out = [
    esc + "36m" + model + reset + " " + colour(used) + "[" + bar + "]" + reset + " " + used + "%",
    part("5h", five),
    part("7d", week),
    spend !== null ? part("spend", spend)
      : cost !== null ? "cost " + esc + "36m$" + cost.toFixed(2) + reset
      : part("spend", null)
  ].join(sep);
  process.stdout.write(out + "\n");
});
'
