// Leading "setup" commands that aren't the point of the line.
const SILENT_HEADS = new Set(['cd', 'pushd', 'popd', 'export', 'set', 'unset', 'source', '.', 'true', 'false', ':'])

// Trailing pager/wrapper commands that only reshape output for display.
const PAGER_HEADS = new Set(['tail', 'head', 'cat', 'less', 'more'])

// Top-level control operators that separate one command from the next. A bare
// `&` is intentionally NOT here — it would split a `2>&1` redirection at its `&`.
const SEPARATORS = ['&&', '||', '|&', ';;', ';', '|', '\n']

const basename = (head: string): string => head.split('/').pop() || head

// Split on control operators at the top level only — runs of text inside single
// or double quotes are left intact so a `|` or `;` in an argument never splits.
function splitTopLevel(input: string): string[] {
  const segments: string[] = []
  let buf = ''
  let quote: '"' | "'" | null = null

  for (let i = 0; i < input.length; i += 1) {
    const ch = input[i]!

    if (quote) {
      buf += ch

      if (ch === quote && input[i - 1] !== '\\') {
        quote = null
      }

      continue
    }

    if (ch === '"' || ch === "'") {
      quote = ch
      buf += ch

      continue
    }

    const op = SEPARATORS.find(sep => input.startsWith(sep, i))

    if (op) {
      segments.push(buf)
      buf = ''
      i += op.length - 1

      continue
    }

    buf += ch
  }

  segments.push(buf)

  return segments.map(segment => segment.trim()).filter(Boolean)
}

// The command word of a segment, skipping any `FOO=bar` env assignments.
function headWord(segment: string): string {
  const tokens = segment.split(/\s+/)
  let index = 0

  while (index < tokens.length && /^[A-Za-z_]\w*=/.test(tokens[index]!)) {
    index += 1
  }

  return basename(tokens[index] ?? '')
}

// A trailing `echo "..._exit=$?"` / `echo $?` the agent appends to surface the
// real exit code through a pipe — pure plumbing, never the point of the command.
const isStatusEcho = (segment: string): boolean =>
  headWord(segment) === 'echo' && /(?:_exit=|\$\?|\$\{?PIPESTATUS)/.test(segment)

// Drop redirections (`2>&1`, `> log`, `>> out`, `< in`) from the chosen segment.
// Skipped when the segment contains quotes, so a `>` inside an argument is safe.
function stripRedirections(segment: string): string {
  if (/["']/.test(segment)) {
    return segment
  }

  return segment
    .replace(/\s*\d*>>?(?:&\d+|\s*\S+)/g, '')
    .replace(/\s*\d*<\s*\S+/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * Reduce a verbose shell command to the "main" command, for display only.
 *
 * Agents wrap real work in plumbing — `cd <dir> && <cmd> 2>&1 | tail -N; echo
 * "x_exit=${PIPESTATUS[0]}"` — which buries the command the user actually cares
 * about. This peels that wrapper off using small head-word allowlists instead of
 * one giant regex:
 *
 *   1. split into segments on top-level `&&` `||` `;` `|` (quote-aware)
 *   2. drop leading setup segments (`cd`, `export`, `source`, env assignments…)
 *   3. drop trailing pager / status-echo segments (`tail`, `head`, `echo $?`…)
 *   4. strip redirections from the one segment that's left
 *
 * Deliberately conservative: if more than one "real" command survives (a genuine
 * compound like `git add -A && git commit -m …`), the original is returned
 * untouched. We only simplify when exactly one meaningful command remains, so we
 * never hide work. The full command is always still available via Copy / detail.
 */
export function summarizeShellCommand(raw: string): string {
  const original = (raw ?? '').trim()

  if (!original) {
    return ''
  }

  const segments = splitTopLevel(original)

  if (segments.length <= 1) {
    return original
  }

  let start = 0
  let end = segments.length

  while (start < end && SILENT_HEADS.has(headWord(segments[start]!))) {
    start += 1
  }

  while (
    end > start &&
    (PAGER_HEADS.has(headWord(segments[end - 1]!)) ||
      isStatusEcho(segments[end - 1]!) ||
      SILENT_HEADS.has(headWord(segments[end - 1]!)))
  ) {
    end -= 1
  }

  const core = segments.slice(start, end)

  // Nothing meaningful, or a real multi-command compound — leave it alone.
  if (core.length !== 1) {
    return original
  }

  return stripRedirections(core[0]!) || original
}
