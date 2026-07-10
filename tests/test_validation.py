#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def test_fixtures():
    # Paths
    titan_latest = Path("data/weekly/Titan/2026-07-10.json")
    unisan_latest = Path("data/weekly/UniSan/2026-07-10.json")
    
    titan_fixture = Path("tests/fixtures/expected_outokumpu.json")
    unisan_fixture = Path("tests/fixtures/expected_plan_b.json")
    
    # Check existence
    if not titan_latest.exists():
        print(f"FAIL: Latest Titan report not found at {titan_latest}", file=sys.stderr)
        sys.exit(1)
    if not unisan_latest.exists():
        print(f"FAIL: Latest UniSan report not found at {unisan_latest}", file=sys.stderr)
        sys.exit(1)
        
    # Load data
    titan_data = json.loads(titan_latest.read_text())
    unisan_data = json.loads(unisan_latest.read_text())
    
    titan_exp = json.loads(titan_fixture.read_text())
    unisan_exp = json.loads(unisan_fixture.read_text())
    
    # Validation helpers
    def validate(name, actual, expected):
        print(f"Validating {name}...")
        errors = []
        
        # Check project name
        if actual.get("project_name") != expected.get("project_name"):
            errors.append(f"Project Name mismatch: actual={actual.get('project_name')} expected={expected.get('project_name')}")
            
        # Check overall RAG
        if actual.get("overall_rag") != expected.get("overall_rag"):
            errors.append(f"Overall RAG mismatch: actual={actual.get('overall_rag')} expected={expected.get('overall_rag')}")
            
        # Check disagreement flag
        if actual.get("disagreement_flag") != expected.get("disagreement_flag"):
            errors.append(f"Disagreement flag mismatch: actual={actual.get('disagreement_flag')} expected={expected.get('disagreement_flag')}")
            
        # Check sub_scores
        act_sub = actual.get("sub_scores", {})
        exp_sub = expected.get("sub_scores", {})
        for dim, score in exp_sub.items():
            if act_sub.get(dim) != score:
                errors.append(f"Sub-score mismatch for {dim}: actual={act_sub.get(dim)} expected={score}")
                
        # Check reported status
        if actual.get("source_reported_rag") != expected.get("source_reported_rag"):
            errors.append(f"Reported RAG mismatch: actual={actual.get('source_reported_rag')} expected={expected.get('source_reported_rag')}")
            
        if errors:
            print(f"FAIL: {name} validation failed with errors:")
            for err in errors:
                print(f"  - {err}")
            return False
            
        print(f"PASS: {name} matches golden fixture perfectly.")
        return True

    s1 = validate("Titan (S2P Project)", titan_data, titan_exp)
    s2 = validate("UniSan (Project Plan)", unisan_data, unisan_exp)
    
    if s1 and s2:
        print("\nALL TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    test_fixtures()
