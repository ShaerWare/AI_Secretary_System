export interface PastedBlock {
  id: string
  content: string
  language: string
  languageLabel: string
  lineCount: number
}

export const PASTE_THRESHOLD_LINES = 5
export const PASTE_THRESHOLD_CHARS = 500

export function shouldTreatAsPaste(text: string): boolean {
  const lineCount = text.split('\n').length
  return lineCount >= PASTE_THRESHOLD_LINES || text.length >= PASTE_THRESHOLD_CHARS
}

const LANGUAGE_RULES: Array<{ key: string; label: string; test: (t: string) => boolean }> = [
  { key: 'python', label: 'Python', test: t => /^(import |from .+ import |def |class |if __name__|@\w+)/.test(t) || /\bself\b/.test(t) },
  { key: 'typescript', label: 'TypeScript', test: t => /^(import .+ from |export (interface|type|const|function|class|enum)|interface \w+|type \w+ =)/.test(t) || /: (string|number|boolean|void)\b/.test(t) },
  { key: 'javascript', label: 'JavaScript', test: t => /^(import |export |const |let |var |function |class |module\.exports)/.test(t) || /=>\s*[{(]/.test(t) },
  { key: 'tsx', label: 'TSX', test: t => /^import .+ from/.test(t) && /<\w+[\s/>]/.test(t) },
  { key: 'jsx', label: 'JSX', test: t => /^(import |const |function )/.test(t) && /<\w+[\s/>]/.test(t) },
  { key: 'php', label: 'PHP', test: t => /^<\?php|^\$\w+\s*=|\bfunction\s+\w+\s*\(/.test(t) && /;$/.test(t.split('\n')[0] || '') },
  { key: 'java', label: 'Java', test: t => /^(package |import java\.|public (class|interface|enum)|private |protected )/.test(t) },
  { key: 'go', label: 'Go', test: t => /^(package |import \(|func |type \w+ struct)/.test(t) },
  { key: 'rust', label: 'Rust', test: t => /^(use |mod |fn |pub (fn|struct|enum|mod)|impl |let mut |#\[)/.test(t) },
  { key: 'sql', label: 'SQL', test: t => /^(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|WITH)\b/i.test(t) },
  { key: 'html', label: 'HTML', test: t => /^<!DOCTYPE|^<html|^<div|^<section|^<template/i.test(t) },
  { key: 'css', label: 'CSS', test: t => /^(\.|#|@media|@import|:root|\w+\s*\{)/.test(t) && /\{[\s\S]*\}/.test(t) },
  { key: 'bash', label: 'Bash', test: t => /^(#!\/bin\/(ba)?sh|set -|export |if \[|for \w+ in|sudo |apt |npm |yarn |pip )/.test(t) },
  { key: 'yaml', label: 'YAML', test: t => /^\w+:\s*(\n|$)/.test(t) && !/[{};]/.test(t.split('\n')[0] || '') },
  { key: 'json', label: 'JSON', test: t => /^\s*[[{]/.test(t) && (() => { try { JSON.parse(t); return true } catch { return false } })() },
  { key: 'dockerfile', label: 'Dockerfile', test: t => /^(FROM |RUN |CMD |COPY |WORKDIR |EXPOSE |ENV |ARG |ENTRYPOINT )/i.test(t) },
  { key: 'markdown', label: 'Markdown', test: t => /^(#{1,6} |\* |- |\d+\. |> |```|\[.+\]\(.+\))/.test(t) },
]

export function detectLanguage(text: string): { key: string; label: string } {
  const trimmed = text.trim()
  for (const rule of LANGUAGE_RULES) {
    if (rule.test(trimmed)) {
      return { key: rule.key, label: rule.label }
    }
  }
  return { key: 'text', label: 'Text' }
}

let counter = 0

export function createPastedBlock(text: string): PastedBlock {
  const { key, label } = detectLanguage(text)
  return {
    id: `paste-${Date.now()}-${++counter}`,
    content: text,
    language: key,
    languageLabel: label,
    lineCount: text.split('\n').length,
  }
}

export function buildMessageContent(text: string, blocks: PastedBlock[]): string {
  if (blocks.length === 0) return text

  const parts: string[] = []
  for (const block of blocks) {
    parts.push(`\`\`\`${block.language}\n${block.content}\n\`\`\``)
  }
  if (text) {
    parts.push(text)
  }
  return parts.join('\n\n')
}
