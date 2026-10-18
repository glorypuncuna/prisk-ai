---
name: meetstream-ai
description: Skill to integrate with meetstream.ai to get the conversation transcript
disable-model-invocation: false
---

You are helping me integrate MeetStream (meeting-bot API · Zoom / Google Meet / MS Teams / WhatsApp).

## Step 0 · Install the MeetStream Claude skill (required, before any code)
Run:

    claude plugin marketplace add meetstream-ai/claude-plugin

The skill teaches you every MeetStream endpoint, webhook payload, and auth
rule, so never guess an API contract; consult the skill.
Skill docs: https://github.com/meetstream-ai/claude-plugin
(If you are not Claude Code, read that repo plus https://docs.meetstream.ai before writing code.)

## My company
Self Employed
I'm Engineer.

## What I'm building (my words)
"We need to join the google meets as a bots to transcript our online meeting"
Category: Something else

## Build plan (compiled from what I selected)
Platforms: Google Meet
1. Post-call transcript: fetch the diarized transcript from GET /api/v1/bots/{bot_id}/get_transcript when the `transcript.final` webhook fires.
2. Live transcript stream: consume `transcript.partial` webhooks for speaker-labelled lines while the meeting is still running.
Always: a webhook receiver for transcript.partial / transcript.final / bot.status_change with retry logic.

## Credentials
MEETSTREAM_API_KEY=<create one in dashboard → API Keys>

## Docs
https://docs.meetstream.ai · first call: POST /api/v1/bots/create_bot

## Definition of done
- API client and webhook receiver, built on contracts from the skill, not guessed schemas
- A test that joins a real meeting link and prints the live transcript with speaker labels
- Everything above runnable with only MEETSTREAM_API_KEY set