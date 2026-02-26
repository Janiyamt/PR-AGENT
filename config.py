# config.py
# =========
# ALL settings live here. When you want to change something,
# this is the ONLY file you need to touch.


# ── OCI Generative AI Settings ───────────────────────────
# OCI authenticates using your local ~/.oci/config file
# instead of a plain API key. The SDK reads it automatically.
OCI_CONFIG_FILE = "~/.oci/config"     # Default location — don't change unless yours is elsewhere
OCI_CONFIG_PROFILE = "DEFAULT"        # Which profile inside the config file to use

# Your OCI compartment OCID
# Find it: OCI Console → Identity & Security → Compartments
# Looks like: ocid1.compartment.oc1..aaaaaxxxxx
OCI_COMPARTMENT_ID = "ocid1.tenancy.oc1..aaaaaaaahqvb2kliqi35z57qalhpr4dyqbjprclszdcoar2wgc7q6nl36aba"

# Region-specific Gen AI endpoint

OCI_ENDPOINT = "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"

# Grok model ID on OCI — verify exact string in OCI Console → Gen AI → Models
OCI_MODEL_ID = "ocid1.generativeaimodel.oc1.us-chicago-1.amaaaaaask7dceya3eub3uksacl5q35mrigancv6rbppihlg7ihhjofyc22q"          # or "xai.grok-3-fast" depending on what's available

# ── Output Settings ───────────────────────────────────────
OUTPUT_FILE = "pr_report.docx"