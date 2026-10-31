"""Use the existing audited runner with complete-context single-field inputs."""

import argparse
from pathlib import Path

import run_all_models
from all_models_protocol import PROVIDERS
from optimized_all_models_protocol import business_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--provider", choices=PROVIDERS, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18811")
    parser.add_argument("--s3-output")
    # Original runner simply drops other questions; this wrapper first restores
    # the complete catalog when it was represented across the full schema.
    run_all_models.business_payload = business_payload
    run_all_models.run(parser.parse_args())
