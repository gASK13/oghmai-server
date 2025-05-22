# DynamoDB Schema Migration Tool

This folder contains a script for migrating DynamoDB items from V1 to V2 schema as described in the project's `schema.md` file.

For future migrations, add other steps (like V1>V2). 
Unfortunately, there is as of now no "generic" way to do this, so we have to hardcode the steps. 
The script is designed to be run in a single step, but it can be modified to handle multiple steps if needed.

## Purpose

The migration script (`db_migration.py`) performs the following tasks:
1. Scans DynamoDB for V1 items (those without a "schema" field)
2. Converts each item to V2 format by:
   - Moving translation, definition, and examples into a "meanings" array
   - Adding a default type (OTHER) to each meaning
   - Adding a "schema" field with value "v2"
3. Enriches each item with additional meanings using Amazon Bedrock
4. Updates the item in DynamoDB

## Schema Changes

### V1 Schema
```json
{
  "user_id": "string",
  "word": "string",
  "lang": "string",
  "translation": "string",
  "definition": "string",
  "examples": ["string"],
  "created_at": "number",
  "status": "string",
  "last_test": "number",
  "test_results": ["boolean"]
}
```

### V2 Schema
```json
{
  "user_id": "string",
  "word": "string",
  "lang": "string",
  "meanings": [
    {
      "translation": "string",
      "definition": "string",
      "examples": ["string"],
      "type": "string"
    }
  ],
  "created_at": "number",
  "status": "string",
  "last_test": "number",
  "test_results": ["boolean"],
  "schema": "v2"
}
```