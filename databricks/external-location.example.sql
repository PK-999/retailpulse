-- Replace STORAGE_ACCOUNT_NAME after Terraform apply.
-- Create the storage credential first with storage-credential.example.json.

CREATE EXTERNAL LOCATION IF NOT EXISTS retailpulse_dev_lake
URL 'abfss://retailpulse@STORAGE_ACCOUNT_NAME.dfs.core.windows.net/'
WITH (STORAGE CREDENTIAL retailpulse_dev_lake)
COMMENT 'RetailPulse dev medallion filesystem';

DESCRIBE EXTERNAL LOCATION retailpulse_dev_lake;
