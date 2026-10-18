import { readFileSync } from "node:fs";
import ts from "typescript";

const ALLOWED = /^\/[/*]\s*eslint-disable/;

function commentLines(path) {
  const text = readFileSync(path, "utf8");
  const kind = path.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const source = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, kind);
  const seen = new Set();
  const lines = [];
  const collect = (ranges) => {
    for (const range of ranges ?? []) {
      if (seen.has(range.pos)) continue;
      seen.add(range.pos);
      if (ALLOWED.test(text.slice(range.pos, range.end))) continue;
      lines.push(source.getLineAndCharacterOfPosition(range.pos).line + 1);
    }
  };
  const visit = (node) => {
    collect(ts.getLeadingCommentRanges(text, node.pos));
    collect(ts.getTrailingCommentRanges(text, node.end));
    ts.forEachChild(node, visit);
  };
  visit(source);
  collect(ts.getLeadingCommentRanges(text, source.endOfFileToken.pos));
  return lines;
}

for (const path of process.argv.slice(2)) {
  for (const line of commentLines(path)) {
    process.stdout.write(`${path}:${line}\n`);
  }
}
