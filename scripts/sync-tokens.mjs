// Counts my Claude Code tokens from the local transcripts and writes data/tokens.json.
// Runs on my laptop (GitHub Actions cannot read these logs).
//
//   node scripts/sync-tokens.mjs           writes the local data/tokens.json
//   node scripts/sync-tokens.mjs --push    updates data/tokens.json on GitHub directly
//
// --push goes through the GitHub contents API instead of the local clone, so a dirty, stale or broken
// checkout can never block the sync. It merges with the file on GitHub, so runs from any state are safe.
// The token comes from GITHUB_TOKEN or from `gh auth token`.
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
const repo = 'maximilian467/maximilian467';
const remotePath = 'data/tokens.json';

// The scheduled task appends to one log file, so every line carries its time
const log = message => console.log(`${new Date().toISOString()} ${message}`);

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

// Keeps the highest count per day from the previous file and from the transcripts
function merge(previous, counted) {
  const days = { ...previous.days };
  for (const [day, count] of Object.entries(counted)) days[day] = Math.max(days[day] ?? 0, count);
  const sorted = Object.fromEntries(Object.entries(days).sort(([a], [b]) => a.localeCompare(b)));
  const total = Object.values(sorted).reduce((sum, count) => sum + count, 0);
  return { total, since: Object.keys(sorted)[0], updated: new Date().toISOString(), days: sorted };
}

const serialize = data => JSON.stringify(data, null, 2) + '\n';

async function github(token, method, path, body) {
  const response = await fetch(`https://api.github.com/repos/${repo}/${path}`, {
    method,
    headers: { authorization: `Bearer ${token}`, accept: 'application/vnd.github+json', 'x-github-api-version': '2022-11-28' },
    body: body && JSON.stringify(body),
  });
  return { status: response.status, json: await response.json() };
}

async function push(counted) {
  const token = process.env.GITHUB_TOKEN ?? execFileSync('gh', ['auth', 'token'], { encoding: 'utf8' }).trim();
  // A 409 means the file changed between read and write (another run, a card redraw). Read again and retry.
  for (let attempt = 1; attempt <= 3; attempt++) {
    const current = await github(token, 'GET', `contents/${remotePath}?ref=main`);
    if (current.status !== 200) throw new Error(`GET ${remotePath}: ${current.status} ${current.json.message}`);
    const previous = JSON.parse(Buffer.from(current.json.content, 'base64').toString('utf8'));
    const data = merge(previous, counted);
    if (data.total === previous.total) return log(`No change: ${data.total.toLocaleString('en')} tokens`);
    const result = await github(token, 'PUT', `contents/${remotePath}`, {
      message: 'chore: sync Claude Code token count',
      content: Buffer.from(serialize(data)).toString('base64'),
      sha: current.json.sha,
      branch: 'main',
    });
    if (result.status === 200 || result.status === 201) {
      return log(`Pushed: ${data.total.toLocaleString('en')} tokens since ${data.since} (${result.json.commit.sha.slice(0, 7)})`);
    }
    if (result.status !== 409) throw new Error(`PUT ${remotePath}: ${result.status} ${result.json.message}`);
    log(`File changed on GitHub, retrying (${attempt}/3)`);
  }
  throw new Error('Gave up after 3 conflicts');
}

const counted = countDays();
if (process.argv.includes('--push')) {
  await push(counted);
} else {
  const previous = existsSync(output) ? JSON.parse(readFileSync(output, 'utf8')) : { days: {} };
  const data = merge(previous, counted);
  if (data.total === previous.total) log(`No change: ${data.total.toLocaleString('en')} tokens`);
  else {
    writeFileSync(output, serialize(data));
    log(`Synced: ${data.total.toLocaleString('en')} tokens since ${data.since}`);
  }
}
