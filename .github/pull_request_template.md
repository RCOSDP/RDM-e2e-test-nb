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
- MFR_IMAGE: 
- WB_IMAGE:
- BINDERHUB_IMAGE:
<!-- BINDERHUB_IMAGE: BinderHub image for the BinderHub OAuth tests (default: gcr.io/nii-ap-ops/k8s-binderhub-binderhub:0.2.5-20261111) -->
- BINDERHUB_JUPYTERHUB_IMAGE:
<!-- BINDERHUB_JUPYTERHUB_IMAGE: JupyterHub image for the BinderHub OAuth tests (default: gcr.io/nii-ap-ops/k8s-hub:4.1.0-20261106) -->
- BINDERHUB_SOURCE:
- BINDERHUB_JUPYTERHUB_SOURCE:
<!-- BINDERHUB_*SOURCE: Build the images from owner/repo@branch (e.g. RCOSDP/CS-binderhub@master); they take precedence over the *_IMAGE settings -->
- EXCLUDE_NOTEBOOKS: 
<!-- EXCLUDE_NOTEBOOKS: Comma-separated list of notebooks to exclude from tests -->
