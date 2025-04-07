# OghmAI Backend

A simple custom backend for OghmAI (a POC Android language learning AI app). Written to try couple things - creation of an Android app, creation of a AI enabled app in AWS and last but not least in AI assisted app creation (using AI as a partner).

## What is OghmAI?

Goal is a simple Android app for enriching my vocabulary in Italian.

The app will have a few modes:
- Mode "I am looking for a word that means what I describe" with an option to save or not save it for my vocabulary
- Mode "I learned a word and want to save it for later tests"
- Mode "view learned words with stored definition in target language and example sentences and be able to ask questions about it"
- Mode "Test me on words I already learned until I master them, Ie get them correct X times Y days apart"


In (distant) future, this could server for other users and languages.

## Tech stack
Frontend (Android thin client): Kotlin + Jetpack Compose.
Backend (Python): FastAPI on AWS Lambda (via API Gateway).
Data: DynamoDB.
AI: Bedrock (later ChatGPT API or something else)
IaC: Terraform
Security: API Key Auth + Usage Plans (AWS API Gateway)

## MVP Modes Breakdown (Phase 1)
### Mode 1: “Sto cercando una parola…”
_(User describes meaning, AI suggests target-language word)_

**Workflow:**

**User inputs a phrase like:**
“Quando una persona ha paura di stare con altra gente.”

**AI (Bedrock) suggests:**
“La parola che stai cercando è: timido.”
With definition + example in Italian only

**Buttons:** “Salva” / “Non salvare”

**API endpoint:** POST /find-word

**Bedrock prompt example:**
"L'utente sta cercando una parola italiana che descrive: 'Quando una persona ha paura di stare con altra gente.' Suggerisci la parola più adatta, la definizione e una frase d'esempio, tutto in italiano."

### Mode 2: “Ho imparato una parola”
_(User inputs a word, AI generates definition + sentence, and saves it)_

**Workflow:**

User inputs “affascinante”

**AI returns:**
“affascinante: che esercita un grande fascino o attrattiva. Es: Il film era così affascinante che non riuscivo a smettere di guardarlo.”

**Button:** “Salva”

**API endpoint:** POST /add-known-word

**Input:** word

**Output:** AI response with definition and example (Italian only)

**DynamoDB save:** word, definition, example, date_added

### Mode 3: “Visualizza parole imparate”
_(List of learned words, all in Italian, with ability to ask about any)_

**Workflow:**
List: Words + short preview of definition
Tap word: See full entry (definition + example)
Option: “Fai una domanda su questa parola” (uses AI to answer, e.g. grammar, usage, synonyms)
**API endpoints:**
- GET /my-words
- POST /ask-about-word (user asks a question, AI answers in Italian)

## MVP Summary of Endpoints
### POST /find-word	
Suggest word from description (AI)
### POST /add-known-word	
Save a word with AI-generated info
### GET /my-words	
Get all saved words
### POST /ask-about-word	
Ask something about a saved word (AI)

## Database Schema (DynamoDB)
Table: vocab_words
Partition Key: user_id
Sort Key: word
Other fields:

definition (Italian)
example_sentence (Italian)
date_added
Optionally source: "ai-suggested" / "user-input"

## UI Screens MVP
“Cerca parola” screen – input, result + Save/Not Save

“Ho imparato una parola” screen – input + Save

“Parole imparate” screen – list + detail + ask

## MVP Next Steps
- [ ] Set up Terraform base (Lambda, API Gateway, Dynamo)
- [ ] Build and test FastAPI backend locally
- [ ] Integrate Bedrock for Italian prompts
- [ ] Connect Android client to backend
- [ ] Basic UI for all 3 modes
- [ ] Deploy MVP to AWS and test live

## Why OghmAI?

Oghma is the Celtic goddess of knowledge and learning. The name is a play on "Ogham," an ancient Irish script, and "AI," representing the app's AI capabilities. The name reflects the app's goal of enhancing language learning through AI assistance.