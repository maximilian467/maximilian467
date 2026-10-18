// Counts my Claude Code tokens from the local transcripts and writes data/tokens.json.
// Runs on my laptop (GitHub Actions cannot read these logs). With --push it also commits and pushes.
//
//   node scripts/sync-tokens.mjs [--push]
//
// Counted per assistant message: input + output + cache writes + cache reads. Claude Code repeats the
// usage block on every content block of a message (thinking, text, tool use), so events are de-duplicated by
// message.id + requestId, keeping the largest count when the output count grows across those lines.
// Summing every line instead roughly multiplies the total by 2.5.
// Claude Code deletes old transcripts after a while, so each day keeps the highest count ever seen
// instead of being recomputed from whatever is still on disk.
import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = join(root, 'data', 'tokens.json');
const transcripts = join(process.env.CLAUDE_CONFIG_DIR ?? join(homedir(), '.claude'), 'projects');
const timeZone = 'Europe/Berlin';

function jsonlFiles(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap(name => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? jsonlFiles(path) : path.endsWith('.jsonl') ? [path] : [];
  });
}

function countDays() {
  const messages = new Map();
  for (const file of jsonlFiles(transcripts)) {
    for (const line of readFileSync(file, 'utf8').split('\n')) {
      if (!line.includes('"usage"')) continue;
      let event;
      try { event = JSON.parse(line); } catch { continue; } // a line that is still being written
      const usage = event.message?.usage;
      if (!usage || !event.timestamp) continue;
      const key = `${event.message.id ?? ''}|${event.requestId ?? ''}`;
      const count = (usage.input_tokens ?? 0) + (usage.output_tokens ?? 0)
        + (usage.cache_creation_input_tokens ?? 0) + (usage.cache_read_input_tokens ?? 0);
      if (count > (messages.get(key)?.count ?? -1)) messages.set(key, { count, day: new Date(event.timestamp).toLocaleDateString('sv-SE', { timeZone }) });
    }
  }
  const days = {};
  for (const { day, count } of messages.values()) days[day] = (days[day] ?? 0) + count;
  return days;
}

const previous = existsSync(output) ? JSON.parse(readFileSync(output, 'utf8')) : { days: {} };
const days = { ...previous.days };
for (const [day, count] of Object.entries(countDays())) days[day] = Math.max(days[day] ?? 0, count);
const sorted = Object.fromEntries(Object.entries(days).sort(([a], [b]) => a.localeCompare(b)));
const total = Object.values(sorted).reduce((sum, count) => sum + count, 0);

if (total === previous.total) {
  console.log(`No change: ${total.toLocaleString('en')} tokens`);
} else {
  const data = { total, since: Object.keys(sorted)[0], updated: new Date().toISOString(), days: sorted };
  writeFileSync(output, JSON.stringify(data, null, 2) + '\n');
  console.log(`Synced: ${total.toLocaleString('en')} tokens since ${data.since}`);
  if (process.argv.includes('--push')) {
    const git = (...args) => execFileSync('git', args, { cwd: root, stdio: 'inherit' });
    git('add', 'data/tokens.json');
    git('commit', '-m', 'chore: sync Claude Code token count');
    git('pull', '--rebase');
    git('push');
  }
}
