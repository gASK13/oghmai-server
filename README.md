# OghmAI Backend

A simple custom backend for OghmAI (a POC Android language learning AI app). 

Written to try couple things:
- creation of an Android app
- creation of a AI enabled app in AWS
- last but not least in AI assisted app creation (using AI as a partner and assistant)

> ℹ️ **Info:** Most of the code generated in this repo so far is AI generated based on continuous prompting (with manual changes where required or appropriate). This is an experiment both in development on those technologies and into trying "vibe coding".

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

## How to build (and run) locally
Assuming you have Python 3.10+, all packages needed, Terraform and AWS credentials setup.

1. Run FastAPI locally using uvicorn:
```bash
uvicorn lambda.main:app --reload
```

Now test the API using Postman or curl

For remote deployment, there is a CI/CD pipeline, you just need to setup your AWS credentials properly.

If you want to deploy to AWS from local (or test changes), you need to:
1. Run local.bat to produce necessary files (OpenAPI + layer)
2. Run terraform apply to deploy the changes to AWS (make sure to setup proper profile for AWS)
 
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

**API endpoint:** POST /describe-word

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
- GET /words
- POST /ask-about-word (user asks a question, AI answers in Italian)

## Summary of Endpoints

Endpoints can be found in FastAPI - everything is generated based on that and growing, so no need to keep them here

## Database Schema (DynamoDB)
Table: vocab_words
Partition Key: user_id
Sort Key: word
Other fields:

definition (Italian)
lanuage (IT for now)
example_sentence (Italian)
translation (English)

In future we can add source, date added and other metadata.

## UI Screens MVP
“Cerca parola” screen – input, result + Save/Not Save

“Ho imparato una parola” screen – input + Save

“Parole imparate” screen – list + detail + ask

## MVP Next Steps
- [x] Set up Terraform base (Lambda, API Gateway, Dynamo)
- [x] Build and test FastAPI backend locally
- [x] Integrate Bedrock for Italian prompts
- [x] Connect Android client to backend
- [ ] Basic UI for all 3 modes
- [ ] Deploy MVP to AWS and test live

## Why OghmAI?

Oghma is the Celtic goddess of knowledge and learning. The name is a play on "Ogham," an ancient Irish script, and "AI," representing the app's AI capabilities. The name reflects the app's goal of enhancing language learning through AI assistance.