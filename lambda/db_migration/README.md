# DynamoDB migration runbook

## Language-qualified key migration

`migrate_language_keys.py` copies vocabulary and recycle-bin records from the legacy tables to the v2 tables. It does not call Bedrock and never changes source items. Destination records retain every source attribute and add `word_key`, computed only from the existing `lang` and `word` values as `<UPPERCASE_LANG>#<NFC-normalized-casefolded-word>`. Recycle-bin `ttl` is copied unchanged.

The old `db_migration.py` script is a separate V1-to-V2 content-schema migration. It calls Bedrock and updates the legacy vocabulary table in place. It is not the language-key migration, must not be run as part of routine deployments, and is no longer invoked by CI.

## Preconditions

1. Schedule downtime and deliberately stop API traffic and all writers before merging/pushing to the main branch. Main-branch CI automatically deploys Terraform, which points Lambda at the v2 tables. Keep traffic stopped through that deployment, v2 table creation, migration, verification, and smoke tests. Do not run this migration against live writes.
2. Confirm the selected AWS profile/role and region independently. The examples below contain no account identifiers; replace every placeholder deliberately.
3. Create and record recoverable on-demand backups of both legacy tables: `oghmai_vocabulary_words` and `oghmai_vocabulary_recycle_bin`.
4. Review the Terraform plan before applying it. Confirm the existing legacy resources are unchanged and not replaced or destroyed; only the new `oghmai_vocabulary_words_v2` and `oghmai_vocabulary_recycle_bin_v2` tables should be added for this migration. Confirm the new recycle-bin table has TTL enabled on `ttl`.
5. After reviewing the Terraform plan, merge/push the change to the main branch to run the automatic CI deployment. That deployment creates the empty destination tables and configures Lambda to use them. Confirm their keys are `user_id` + `word_key`. Keep API traffic stopped.
6. Install the dependencies in `lambda/requirements.txt` in an isolated local environment, or use an environment that already has the required `boto3` package. Authenticate through the normal AWS credential chain with access to scan/get the legacy tables and scan/get/put the v2 tables.

## Commands

Run from the repository's `lambda` directory. These table names are the Terraform names in this repository; replace `us-east-1` only if the tables are deployed in a different region.

Dry run (reads both source and destination, writes nothing):

```powershell
python .\db_migration\migrate_language_keys.py `
  --region us-east-1 `
  --source-vocabulary-table oghmai_vocabulary_words `
  --destination-vocabulary-table oghmai_vocabulary_words_v2 `
  --source-recycle-bin-table oghmai_vocabulary_recycle_bin `
  --destination-recycle-bin-table oghmai_vocabulary_recycle_bin_v2 `
  --dry-run
```

Review the JSON report. Invalid source rows, source key collisions after normalization, and conflicting or unexpected destination data are reported and cause a nonzero exit. Missing destination records are listed as `would_write` during dry run.

Execute the idempotent copy only after reviewing the report:

```powershell
python .\db_migration\migrate_language_keys.py `
  --region us-east-1 `
  --source-vocabulary-table oghmai_vocabulary_words `
  --destination-vocabulary-table oghmai_vocabulary_words_v2 `
  --source-recycle-bin-table oghmai_vocabulary_recycle_bin `
  --destination-recycle-bin-table oghmai_vocabulary_recycle_bin_v2 `
  --execute
```

The CLI writes only missing destination items, using conditional puts. Existing identical items are counted as already present; conflicting items are reported and not overwritten. Save the JSON output with the maintenance record.

Run the verify-only pass after a successful execute. It performs full paginated scans and compares counts, derived keys, and every copied attribute (including recycle-bin TTL), reporting missing, extra, invalid, or differing items:

```powershell
python .\db_migration\migrate_language_keys.py `
  --region us-east-1 `
  --source-vocabulary-table oghmai_vocabulary_words `
  --destination-vocabulary-table oghmai_vocabulary_words_v2 `
  --source-recycle-bin-table oghmai_vocabulary_recycle_bin `
  --destination-recycle-bin-table oghmai_vocabulary_recycle_bin_v2 `
  --verify-only
```

Run the migration CLI manually from the operator environment; it is never run by CI. Do not reopen traffic unless the execute and verify-only reports have no invalid records, mismatches, or errors. While public traffic remains stopped, confirm Lambda environment variables point to the v2 table names and smoke-test existing Italian requests and German/Greek records (including identical spellings across languages) through a controlled operator path. Reopen traffic only after those checks pass. The existing challenge table/key is unchanged; downtime may expire its records naturally.

Keep the legacy tables and backups for the rollback window. Once writes occur in v2, switching the old code back to legacy tables would omit those new writes; preserve/reconcile v2 data before any rollback that points the application at the old tables. This migration and its Terraform apply are operator-invoked maintenance actions and are not part of CI.

## Previous content-schema migration

`db_migration.py` remains for the historical V1-content-schema conversion described in `schema.md`. It invokes Bedrock and writes into the configured vocabulary table. Do not run it for the language-qualified-key migration. It is deliberately absent from the deployment workflow.
