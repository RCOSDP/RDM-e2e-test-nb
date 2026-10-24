## Purpose

## Changes

## Ticket

## Custom Test Configuration
<!-- Leave empty to use default settings. Specify custom settings to test with specific versions or fixes. -->
- RDM_REPOSITORY: 
- RDM_BRANCH: 
- RDM_MERGE:
<!-- RDM_MERGE: Set to false to test against the custom branch without merging -->
- OSF_IMAGE: 
- EMBER_IMAGE: 
- CAS_IMAGE: 
<!-- CAS_IMAGE specifies real CAS, not FakeCAS, and takes precedence over CAS source settings. -->
- CAS_REPOSITORY:
- CAS_BRANCH:
- SP_REPOSITORY:
- SP_BRANCH:
<!-- CAS/SP source settings apply to Shibboleth login tests; blank values use RCOSDP/RDM-cas-overlay@develop and RCOSDP/RDM-Shibboleth-SP@main. -->
- MFR_IMAGE: 
- WB_IMAGE:
- EXCLUDE_NOTEBOOKS: 
<!-- EXCLUDE_NOTEBOOKS: Comma-separated list of notebooks to exclude from tests -->
