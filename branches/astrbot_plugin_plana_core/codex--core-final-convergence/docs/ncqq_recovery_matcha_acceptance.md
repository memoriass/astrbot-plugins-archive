# NCQQ Recovery Matcha Acceptance

## Purpose

This experiment verifies Xiaowei-style NCQQ recovery conversations with real
AstrBot routing and plugin execution. It does not accept a synthetic capability
trace as evidence. Matcha injects ordinary group messages and displays outgoing
OneBot actions; the collector correlates those observations with a bounded,
operator-provided local AstrBot log artifact.

The experiment never accepts an arbitrary existing NCQQ instance name. The
dedicated alias must match `accept-ncqq-YYYYMMDD-xxxxxxxx`, where the final eight
lowercase alphanumeric characters are a random suffix. `arona`, `plana`, and
`codex-qr-test-07120029` are explicitly forbidden. Reports contain only a salted
hash and `<INSTANCE>`.

## Matrix

| Case | Natural-language property | Required evidence |
| --- | --- | --- |
| Discussion negative | General NCQQ disconnect discussion | Direct answer; no NCQQ tool or write proposal |
| Create then cancel | Oral request followed by a short cancellation | NCQQ plugin route, pending approval, cancellation, no instance mutation |
| Create then confirm | Oral request followed by reply confirmation | NCQQ plugin route, approval transition, new acceptance instance only |
| Context pronoun | “那就…弄好把码发我” continuation | Same target retained, diagnosis/recovery flow, private QR delivery |
| Ambiguous instance | No target name with multiple candidates | Clarification before approval or mutation |
| Reply anchor | Confirmation replying to the real bot proposal | Approval associated with the quoted proposal, restart/recheck, private QR delivery |

The utterances intentionally omit workflow names, capability names, read/write
labels, and ordered tool instructions. The discussion negative is retained from
reviewed QQ history. Recovery and correction shapes follow reviewed Xiaowei
records such as “让他重新登录” and “不是，这是重启啥了”.

## Prepare Matcha suites

Use only synthetic Matcha identities. Do not substitute production QQ IDs.

```powershell
C:\git\AstrBot\.venv\Scripts\python.exe scripts\run_ncqq_recovery_matcha.py prepare `
  --output-dir tmp\ncqq_recovery_matcha\run-001\suites `
  --manifest tmp\ncqq_recovery_matcha\run-001\manifest.json `
  --bot-id 10001 --user-id 10002 --group-id 10003 `
  --instance-alias accept-ncqq-20260719-7f3a9c2d
```

Import one generated `*.matcha-scenario.json` file into Matcha `/code`, run it,
and watch the group and step output. Export the scenario run or the Matcha
workspace after each case.

Steps requiring a reply anchor are disabled in the first generated suite. Read
the real bot reply `message_id` from Matcha, then regenerate that case:

```powershell
C:\git\AstrBot\.venv\Scripts\python.exe scripts\run_ncqq_recovery_matcha.py prepare `
  --output-dir tmp\ncqq_recovery_matcha\run-001\reply `
  --manifest tmp\ncqq_recovery_matcha\run-001\manifest.json `
  --case ncqq-reply-anchor-confirm-001 `
  --reply-message-id <MATCHA_MESSAGE_ID>
```

This two-pass rule prevents the acceptance asset from inventing an approval
anchor that the bot never emitted.

The first prepare writes the manifest. Every later prepare reuses its alias and
rejects a conflicting `--instance-alias`. Do not edit or replace the manifest
between prepare and collect.

## Provide the local evidence window

Export a bounded AstrBot log window outside this runner and place it under
`tmp/`. The runner has no SSH or remote-fetch command and must not connect to
`192.168.1.201` or any other host. Raw logs and Matcha workspace exports remain
under `tmp/`.

## Collect the redacted report

```powershell
C:\git\AstrBot\.venv\Scripts\python.exe scripts\run_ncqq_recovery_matcha.py collect `
  --astrbot-log tmp\ncqq_recovery_matcha\run-001\astrbot.log `
  --matcha-run tmp\ncqq_recovery_matcha\run-001\matcha-run.json `
  --manifest tmp\ncqq_recovery_matcha\run-001\manifest.json `
  --run-label gray-201-run001 `
  --report tmp\ncqq_recovery_matcha\run-001\report.json
```

The report records route profiles, tool names, NCQQ workflow labels, approval
state categories, QR observation, delivery channel, sanitized errors, source
hashes, and Matcha step status. It rejects URLs, long numeric IDs, credentials,
tokens, cookies, and raw instance names.

`needs_review` is intentional when evidence is missing. Do not convert it to a
pass by weakening the fixture. Fix routing, plugin intent parsing, target
resolution, approval continuation, recovery verification, or delivery policy,
then rerun the same natural utterance.

## Safety boundary

- Create a new acceptance instance; never select, restart, delete, or rename an existing instance.
- Prepare and collect must use the same unchanged manifest and fixture hash.
- Confirm the candidate target shown by the plugin before approving a write.
- Cancellation must leave no new instance and no pending executable approval.
- QR artifacts may be observed only as a boolean/channel classification in the report.
- Delete the temporary acceptance instance after the confirmed recovery case and record cleanup separately in the operator log.
- Keep administrator keys in AstrBot/NCQQ configuration; never pass them as command arguments or place them in reports.
