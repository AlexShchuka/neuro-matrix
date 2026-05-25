# questions/ — held-out probes

Add your own probes here, one file per probe: `qNN.md` (numbered).

Format (see `../adversarial/adv01.md` for a worked example):

```markdown
# qNN — short title

## Source
(optional) where the question came from — channel, ticket, conversation.

## Prompt
The verbatim user prompt to feed into a fresh session under the plugin.

## Why this probe
1–3 sentences on what invariant(s) it tests and what failure modes it tries to expose.

## Expected shape
Bulleted list of structural properties the reply must satisfy (not a canonical text).

## Canary
`<random GUID — placed once inside the file; `scripts/check-canary-leak.py` greps repos for it to detect contamination via repo-grep>`
```

The runner picks up `q*.md` automatically via `eval/run_suite.py`. Empty directory is fine — only adversarial probes will run.
