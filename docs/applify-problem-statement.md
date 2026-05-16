# Applify
### Your Job Application Co-Pilot
**Problem Statement, Motivation, Requirements, and Scope — V1.0**

---

## Problem Statement

Job seekers who apply frequently and use AI tools to assist them have no dedicated space for that workflow. Instead, job-related conversations get buried inside general-purpose AI assistants alongside cooking questions, coding help, and personal tasks. There is no persistence, no structure, no memory of the role, and no way to track what was done per application.

The result is that the AI, which could genuinely help, ends up being used ineffectively. Every new conversation starts from scratch. The user re-pastes their resume, re-explains their background, and re-asks the same questions for every new job.

Applify solves this by giving the job application workflow its own dedicated, intelligent space.

---

## Motivation

The problem is not that AI tools are bad at helping with job applications. The problem is that they are not built for it. They are general tools being used for a specific, repeated, high-stakes task.

The motivation behind Applify is to build exactly the right tool for exactly this workflow:

- A persistent profile that remembers who you are so you never re-explain yourself
- A chat per job opening so every application is organized, focused, and accessible
- AI that analyzes how well you fit a role and tells you honestly where you are strong and where you fall short
- Outputs tailored to each specific role, not generic templates
- A tracker that gives you a clear view of your pipeline without manual data entry

The target user is anyone actively job hunting, from fresh graduates to senior professionals. The pain is universal. The solution is focused.

---

## Goals

| Goal | Description |
|---|---|
| Focused workspace | Give users a dedicated product for job applications, separate from general AI chat |
| Persistent profile | Store the user's full professional profile so it informs every interaction |
| Per-JD analysis | Analyze fit, gaps, and strengths for each specific job description |
| Tailored outputs | Generate resumes, cover letters, and application answers grounded in the user's profile and the JD |
| Application tracking | Maintain a clean tracker that auto-initializes on every new job chat |
| Progressive UX | Surface capabilities progressively — analysis first, then outputs on demand |

---

## Requirements

### Functional Requirements

**Profile**
- User can upload a resume (PDF or DOCX) and the system parses and stores the content
- Parsed profile is organized into: work experience, education, skills, certifications, projects, achievements
- User can manually add, edit, or enrich any field in their profile after parsing
- AI nudges the user when a profile section is missing or thin, but backs off if the user dismisses the suggestion
- Profile persists across all sessions

**Job Chats**
- User creates a new chat by pasting a job description and giving the opening a title
- Each chat is dedicated to one job opening and is isolated from all other chats
- Chats are listed in the sidebar, clean and easy to navigate

**JD Analysis**
- User chooses between quick snapshot or detailed breakdown before analysis is generated
- Quick snapshot: overall fit score, top 3 strengths, top 3 gaps, one-line verdict
- Detailed breakdown: skill-by-skill comparison against the JD, gap analysis with suggestions, fit score with reasoning
- Analysis is grounded in the user's stored profile — no re-uploading required
- After analysis, the AI is proactive but not overwhelming — it suggests next steps without forcing them

**Outputs (on demand)**
- Tailored resume: generated based on the user's profile and the specific JD
- Cover letter: generated based on the user's profile, the JD, and any context the user provides
- Application question help: user pastes a question, AI answers it drawing from the profile
- All outputs are generated only when the user asks — not automatically

**Job Tracker**
- A new tracker entry is auto-created when a new job chat is started
- Tracker captures: job title, company, date added, analysis type used, resume type (unaltered or AI-tailored)
- User manually updates application status: Not Applied, Applied, Interviewing, Offer, Rejected
- Resume type auto-updates to AI-Tailored if a resume is generated in that chat

### Non-Functional Requirements

| Requirement | Detail |
|---|---|
| Streaming responses | AI responses stream token by token for a conversational feel |
| Response speed | Quick analysis returns first token within 2 seconds |
| Profile security | User profile data is stored securely and tied to authenticated user only |
| Resume parsing accuracy | Parsed resume correctly extracts work history, skills, education, and projects |
| Mobile usability | App is usable on mobile but optimized for desktop |
| Reliability | Core flows (analysis, output generation) must work with clear error states if AI calls fail |

---

## Out of Scope — V1

| Out of Scope | Reason |
|---|---|
| Job listings / job board | Applify does not source jobs. The user brings the JD. |
| Auto-applying to jobs | Applify is an analysis and preparation tool only |
| ATS simulation | Not in V1. May be explored post-beta based on user feedback |
| Browser extension | Core web app first |
| Team or collaborative features | Single-user product in V1 |
| Interview preparation | Possible post-beta feature |
| Email or LinkedIn integration | Not in V1 |
| Monetization | Free during beta. Strategy determined post-launch |
| Mobile app (iOS / Android) | Responsive web only in V1 |
| Multiple saved resume versions | Only profile and per-chat AI-generated variants in V1 |

---

## Assumptions

- The user brings their own job descriptions — Applify does not fetch or aggregate listings
- The user has an existing resume to upload at onboarding
- AI capabilities are powered by Groq (speed) and Azure AI Foundry (quality) via API
- The product is free during beta with no usage limits enforced in V1
- Authentication is required from day one since profile data is personal and persistent

---

## Success Criteria for Beta

| Metric | Target |
|---|---|
| Profile setup completion | User can go from signup to complete profile in under 5 minutes |
| Analysis quality | User rates analysis as useful or very useful |
| Output usability | Generated resume and cover letter require minimal manual editing |
| Tracker adoption | Users return to the tracker to update status across multiple applications |
| Retention signal | Users create more than 3 job chats in their first week |
