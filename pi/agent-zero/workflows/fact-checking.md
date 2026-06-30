# Workflow: Social Media Misinformation Fact-Checking

## Trigger
On-demand: User provides a claim/URL/article to verify
Telegram: `/check <claim or url>`

## What This Protects Against
- Fake news influencing market decisions
- Social media hype pumping/dumping assets
- Misleading economic data claims
- Deepfakes and AI-generated misinformation

## Pipeline

### 1. Claim Extraction
If URL provided:
- Eigent browser navigates to URL
- Extract full article/post text
- Identify core claim(s) being made

If text provided:
- Parse claim directly
- Identify claim type (economic, political, market-moving)

### 2. Source Verification
Cross-reference the claim against:
- **SAIIA** — for SA political/economic claims
- **Reuters Fact Check** — international
- **Africa Check** — Africa-focused fact-checking
- **Official sources** — government statistics, central bank data

### 3. Evidence Gathering (Browser Automation)
For each source:
1. Navigate to source
2. Search for related articles/data
3. Extract contradicting or supporting evidence
4. Capture screenshots of original sources

### 4. Analysis
Using Mistral (Agent Zero):
- Compare claim vs evidence
- Classify: True / False / Misleading / Unverifiable
- Explain reasoning with source citations

### 5. Report Generation
Output a brief with:
- Original claim
- Classification with confidence level
- Supporting evidence (with links/screenshots)
- Context (why this misinformation matters for markets)
- Suggested action (ignore, investigate further, warn others)

## Tools Used
- Eigent browser — navigate to sources, capture screenshots
- Agent Zero (Mistral) — analyze claims against evidence
- A0 CLI — file storage for reports
- Telegram — receive claims, send verdicts

## Checkpoints
1. **Claim identified** — auto
2. **Sources checked** — auto
3. **Verdict** — user reviews before sharing

## Push Right
All evidence gathering and initial analysis runs autonomously. Human reviews the final verdict.
