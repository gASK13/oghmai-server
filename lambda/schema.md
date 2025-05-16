V1: 
The original DynamoDB schema for vocabulary words with the following structure:

```
{
  "user_id": string,         // Partition key - User identifier
  "word": string,            // Sort key - The vocabulary word (stored in lowercase)
  "lang": string,            // Language code (e.g., "IT" for Italian)
  "translation": string,     // Translation of the word
  "definition": string,      // Definition of the word
  "examples": [string],      // Array of example sentences
  "created_at": number,      // Unix timestamp of when the word was created
  "status": string,          // Word learning status (UNSAVED, NEW, LEARNED, KNOWN, MASTERED)
  "last_test": number,       // Unix timestamp of the last test
  "test_results": [boolean]  // Array of test results (true for correct, false for incorrect)
}
```

Key characteristics:
- Translation, definition, and examples were at the top level of the document
- No "type" field was present
- No explicit schema version field
- Single table design with user_id as partition key and word as sort key

V2:
The updated DynamoDB schema for vocabulary words with support for multiple meanings:

```
{
  "user_id": string,         // Partition key - User identifier
  "word": string,            // Sort key - The vocabulary word (stored in lowercase)
  "lang": string,            // Language code (e.g., "IT" for Italian)
  "meanings": [              // Array of word meanings
    {
      "translation": string, // Translation of the word
      "definition": string,  // Definition of the word
      "examples": [string],  // Array of example sentences
      "type": string         // Word type (NOUN, VERB, PRONOUN, ADJECTIVE, OTHER)
    },
    // Additional meaning objects can be included here
  ],
  "created_at": number,      // Unix timestamp of when the word was created
  "status": string,          // Word learning status (UNSAVED, NEW, LEARNED, KNOWN, MASTERED)
  "last_test": number,       // Unix timestamp of the last test
  "test_results": [boolean], // Array of test results (true for correct, false for incorrect)
  "schema": "v2"             // Schema version identifier
}
```

Key characteristics:
- The "meanings" field is set only when a word is first created and not updated afterward
- Explicit "schema" field with value "v2"
- Support for multiple meanings per word
- When updating an existing word, only status, last_test, and test_results are modified
