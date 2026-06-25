import { describe, expect, it } from 'vitest'

import { summarizeShellCommand } from './summarize-command'

describe('summarizeShellCommand', () => {
  it('strips a leading cd and trailing tail + status echo', () => {
    expect(
      summarizeShellCommand(
        'cd /Users/me/www/bb-rainbows && pnpm run lint 2>&1 | tail -10; echo "lint_exit=${PIPESTATUS[0]}"'
      )
    ).toBe('pnpm run lint')
  })

  it('keeps flags on the surviving command', () => {
    expect(summarizeShellCommand('cd /x && pnpm run preview --port 4317 2>&1')).toBe(
      'pnpm run preview --port 4317'
    )
  })

  it('drops a source/activate prefix', () => {
    expect(summarizeShellCommand('source .venv/bin/activate && pytest -q')).toBe('pytest -q')
  })

  it('skips leading env assignments', () => {
    expect(summarizeShellCommand('cd /x && NODE_ENV=test FOO=bar vitest run 2>&1 | tail -5')).toBe(
      'NODE_ENV=test FOO=bar vitest run'
    )
  })

  it('leaves a genuine multi-command compound untouched', () => {
    const compound = 'git add -A && git commit -m "wip"'
    expect(summarizeShellCommand(compound)).toBe(compound)
  })

  it('leaves a single bare command untouched', () => {
    expect(summarizeShellCommand('git status --short')).toBe('git status --short')
  })

  it('does not split on operators inside quotes', () => {
    const cmd = 'git commit -m "fix: a | b && c"'
    expect(summarizeShellCommand(cmd)).toBe(cmd)
  })

  it('does not strip a redirection-looking char inside quotes', () => {
    expect(summarizeShellCommand('cd /x && echo "a > b"')).toBe('echo "a > b"')
  })

  it('handles empty / whitespace input', () => {
    expect(summarizeShellCommand('')).toBe('')
    expect(summarizeShellCommand('   ')).toBe('')
  })

  it('returns the original when every segment is plumbing', () => {
    const allSetup = 'cd /x && export FOO=1'
    expect(summarizeShellCommand(allSetup)).toBe(allSetup)
  })

  it('collapses 2>&1 redirection on a plain pipeline', () => {
    expect(summarizeShellCommand('cd /x && tsc --noEmit 2>&1 | tail -20')).toBe('tsc --noEmit')
  })
})
