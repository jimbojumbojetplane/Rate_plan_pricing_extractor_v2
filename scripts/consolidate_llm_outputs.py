#!/usr/bin/env python3
"""
Consolidate LLM extraction outputs into global JSON file.

Outputs:
- data/consolidated/final_consolidated_plans_YYYYMMDD_HHMMSS.json

The global consolidated includes:
- metadata
- brands: nested per-brand scenarios and raw plan arrays
- records: flat list of plan records the dashboards expect

Note: Per-brand consolidated files were previously created but are redundant
and not used by any dashboards, so their creation has been disabled.
"""
import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple
import re

PIPELINE_EVENT_ID = os.getenv("PIPELINE_EVENT_ID")


def normalize_freedom_plan_name(plan_name: str, data_amount: str = '', network: str = '') -> str:
    """Normalize Freedom plan names from 'plan-card-10gb-5g' to '10GB 5G+' format."""
    import re
    
    if not plan_name:
        return plan_name
    
    # Check if it's already in the correct format
    if re.match(r'^\d+\s*GB\s+(5G\+?|4G|LTE)', plan_name, re.I):
        return plan_name
    
    # Check if it's in plan-card format
    match = re.match(r'plan-card-(\d+)(gb|mb)-?(\d+g|5g\+?|4g|lte|data)?', plan_name, re.I)
    if match:
        data_num = match.group(1)
        data_unit = match.group(2).upper()
        network_part = match.group(3) or ''
        
        # Format network
        if network_part:
            network_part = network_part.upper()
            if network_part == '5G':
                network_part = '5G+'
            elif network_part == 'DATA':
                # For "plan-card-250gb-data", check network from other fields
                if network:
                    if '5G' in network.upper() or '5G+' in network.upper():
                        network_part = '5G+'
                    elif '4G' in network.upper() or 'LTE' in network.upper():
                        network_part = '4G LTE'
                    else:
                        network_part = '5G+'  # Default for Freedom
                else:
                    network_part = '5G+'  # Default for Freedom
        else:
            # Use network from plan data if available
            if network:
                if '5G' in network.upper() or '5G+' in network.upper():
                    network_part = '5G+'
                elif '4G' in network.upper() or 'LTE' in network.upper():
                    network_part = '4G LTE'
                else:
                    network_part = '5G+'  # Default for Freedom
            else:
                network_part = '5G+'  # Default for Freedom plans
        
        # Build formatted name
        if network_part:
            return f"{data_num}{data_unit} {network_part}"
        else:
            return f"{data_num}{data_unit}"
    
    return plan_name


def normalize_plan_record(brand: str, scenario: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a single plan into the dashboard-friendly flat record."""
    if plan is None:
        return {}

    # Normalize Freedom plan names
    plan_name = plan.get('planName') or ''
    if brand.lower() == 'freedom' and plan_name:
        plan_name = normalize_freedom_plan_name(
            plan_name,
            plan.get('dataAmount') or '',
            plan.get('networkSpeed') or plan.get('network') or ''
        )

    # Defensive copies and type normalization
    features_list = plan.get('features') or []
    if not isinstance(features_list, list):
        features_list = []

    roaming_data = plan.get('roaming') or {}
    if not isinstance(roaming_data, dict):
        roaming_data = {}
    
    # Extract roaming classification for easy access
    roaming_classification = roaming_data.get('classification') if isinstance(roaming_data, dict) else None

    bundled_price = plan.get('bundledPrice') or {}
    if not isinstance(bundled_price, dict):
        bundled_price = {}

    promotions_list = plan.get('promotions') or plan.get('bonusOffers') or []
    if not isinstance(promotions_list, list):
        promotions_list = []

    speed_features = plan.get('speedFeatures') or []
    roaming_features = plan.get('roamingFeatures') or []
    intl_text_features = plan.get('internationalTextFeatures') or []
    calling_features = plan.get('callingFeatures') or []
    other_features = plan.get('otherFeatures') or []
    features_list = plan.get('features') or other_features or []

    return {
        'brand': brand.title() if brand else 'Unknown',
        'scenario': scenario or 'Unknown',
        'name': plan_name or 'N/A',
        'price': plan.get('currentPrice') or 'N/A',
        'regular_price': plan.get('regularPrice') or '',
        'data': plan.get('dataAmount') or 'N/A',
        'network': plan.get('networkSpeed') or '',
        'features': features_list,
        'speed_features': speed_features,
        'roaming_features': roaming_features,
        'international_text_features': intl_text_features,
        'calling_features': calling_features,
        'other_features': other_features,
        'roaming': roaming_data,
        'roaming_classification': roaming_classification,
        'bundled_price': bundled_price,
        'promotions': promotions_list,
    }


def parse_filename_metadata(path: Path) -> Tuple[str, str]:
    """Extract scenario and timestamp-ish suffix from filename if present.
    Returns (scenario, timestamp_str) where scenario may be '' if unknown.
    """
    name = path.stem  # without extension
    # Expected patterns like: bell_1_line_mobile_only_YYYYMMDD_HHMMSS
    m = re.match(r"^[a-zA-Z]+_(.+?)_(\d{8}_\d{6})$", name)
    if m:
        return m.group(1), m.group(2)
    # Simpler pattern without timestamp
    m2 = re.match(r"^[a-zA-Z]+_(.+)$", name)
    if m2:
        return m2.group(1), ''
    return '', ''


def load_brand_llm_outputs(brand_dir: Path) -> List[Dict[str, Any]]:
    """Load brand-level LLM output JSONs only: <brand>_llm_output_all_plans_*.json."""
    results: List[Dict[str, Any]] = []

    out_dir = brand_dir / 'output'
    if not out_dir.exists():
        return results

    pattern = f"{brand_dir.name.lower()}_llm_output_all_plans_*.json"
    for f in out_dir.glob(pattern):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                # Enforce carrier-brand consistency when present
                carrier_in_payload = (data.get('carrier')
                                      or (data.get('data') or {}).get('carrier'))
                if carrier_in_payload and str(carrier_in_payload).lower() != brand_dir.name.lower():
                    continue
                if PIPELINE_EVENT_ID and data.get('event_id') != PIPELINE_EVENT_ID:
                    continue
                _, ts = parse_filename_metadata(f)
                results.append({'path': str(f), 'data': data, 'file_scenario': '', 'file_ts': ts})
        except Exception:
            continue

    return results


def consolidate_brand(brand: str, files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build per-brand consolidated structure with scenarios and flat records."""
    scenarios: Dict[str, Dict[str, Any]] = {}
    flat_records: List[Dict[str, Any]] = []

    # Expect files to already be brand-level all-plans. Keep latest by timestamp if multiple.
    files_sorted = sorted(files, key=lambda e: e.get('file_ts', ''), reverse=True)
    selected = files_sorted[:1] if files_sorted else []

    for entry in selected:
        data = entry.get('data', {})
        # Two accepted shapes:
        # 1) { "scenarios": { scenarioName: { plans: [...] } } }
        # 2) legacy per-scenario (not used anymore)
        scenarios_obj = data.get('scenarios')
        if isinstance(scenarios_obj, dict) and scenarios_obj:
            for scenario, sdata in scenarios_obj.items():
                plans = sdata.get('plans') or []
                if not isinstance(plans, list):
                    plans = []
                scenarios[scenario] = {
                    'source_files': [entry.get('path')],
                    'plans': []
                }
                seen_keys = set()
                for plan in plans:
                    # Filter out plans with unknown names - these are not valid plans
                    plan_name = str(plan.get('planName', '')).strip().lower()
                    if not plan_name or plan_name in ['unknown', 'none', 'n/a']:
                        # Skip plans without valid plan names
                        continue
                    
                    # Filter out promotional/discount text that got extracted as plans
                    promotional_keywords = ['after auto-pay', 'after autopay', 'auto-pay discount', 'autopay discount', 
                                            'workplace discount', 'accessibility', 'exclusively with']
                    if any(keyword in plan_name for keyword in promotional_keywords):
                        continue
                    
                    # Filter out plans without prices - these are not actual plans
                    current_price = plan.get('currentPrice') or ''
                    regular_price = plan.get('regularPrice') or ''
                    
                    # Check if price exists (must contain a dollar sign and number)
                    import re
                    has_price = bool(re.search(r'\$.*?\d+(?:\.\d+)?', str(current_price) + str(regular_price), re.I))
                    
                    if not has_price:
                        # Skip plans without prices (e.g., "Workplace discounts", "Accessibility", etc.)
                        continue
                    
                    oid = plan.get('otherIdentifiers') or {}
                    key = (
                        oid.get('ratePlanSoc')
                        or oid.get('productId')
                        or f"{plan.get('planName')}|{plan.get('dataAmount')}|{plan.get('currentPrice')}"
                    )
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    
                    # Normalize Freedom plan names before adding
                    if brand.lower() == 'freedom' and plan.get('planName'):
                        plan['planName'] = normalize_freedom_plan_name(
                            plan.get('planName'),
                            plan.get('dataAmount') or '',
                            plan.get('networkSpeed') or plan.get('network') or ''
                        )
                    
                    scenarios[scenario]['plans'].append(plan)
                    rec = normalize_plan_record(brand, scenario, plan)
                    if rec:
                        flat_records.append(rec)
        else:
            # Legacy fallback (single scenario in file)
            scenario = data.get('scenario') or 'unknown'
            payload = data.get('data') if isinstance(data.get('data'), dict) else data
            plans = payload.get('plans') or []
            if not isinstance(plans, list):
                plans = []
            scenarios[scenario] = {'source_files': [entry.get('path')], 'plans': []}
            seen_keys = set()
            for plan in plans:
                oid = plan.get('otherIdentifiers') or {}
                key = (
                    oid.get('ratePlanSoc')
                    or oid.get('productId')
                    or f"{plan.get('planName')}|{plan.get('dataAmount')}|{plan.get('currentPrice')}"
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                scenarios[scenario]['plans'].append(plan)
                rec = normalize_plan_record(brand, scenario, plan)
                if rec:
                    flat_records.append(rec)

    return {
        'brand': brand,
        'generated_at': datetime.now().isoformat(),
        'scenario_count': len(scenarios),
        'scenarios': scenarios,
        'records': flat_records,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def main() -> int:
    base = Path('data')
    timestamp = PIPELINE_EVENT_ID or datetime.now().strftime('%Y%m%d_%H%M%S')

    all_brand_consolidated: Dict[str, Any] = {}
    global_records: List[Dict[str, Any]] = []

    # Iterate over brand directories under data/
    for brand_dir in sorted([p for p in base.iterdir() if p.is_dir()]):
        brand = brand_dir.name.lower()
        if brand in {'pipeline_runs', 'consolidated'}:
            continue

        files = load_brand_llm_outputs(brand_dir)
        if not files:
            continue

        brand_cons = consolidate_brand(brand, files)
        all_brand_consolidated[brand] = {
            'scenarios': brand_cons['scenarios'],
            'scenario_count': brand_cons['scenario_count'],
        }
        global_records.extend(brand_cons['records'])

        # NOTE: Per-brand consolidated files are redundant and not used by dashboards
        # Keeping this commented out to prevent creation of unused files
        # brand_out = brand_dir / 'output' / f"{brand}_consolidated_{timestamp}.json"
        # write_json(brand_out, brand_cons)

    # Build global consolidated
    global_payload = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_brands': len(all_brand_consolidated),
            'brands': list(all_brand_consolidated.keys()),
            'record_count': len(global_records),
            'event_id': timestamp,
        },
        'brands': all_brand_consolidated,
        'records': global_records,
    }

    consolidated_dir = base / 'consolidated'
    consolidated_path = consolidated_dir / f"final_consolidated_plans_{timestamp}.json"
    write_json(consolidated_path, global_payload)

    # Backward-compatibility: write a copy at project root if prior file exists pattern
    legacy_copy = Path(f"final_consolidated_plans_{timestamp}.json")
    try:
        write_json(legacy_copy, global_payload)  # Optional convenience
    except Exception:
        pass

    print(f"Consolidated {len(all_brand_consolidated)} brands.")
    print(f"Global consolidated: {consolidated_path}")
    print(f"Records: {len(global_records)}")
    
    # Auto-push to GitHub if enabled
    auto_push = os.getenv("AUTO_PUSH_TO_GITHUB", "").lower() in ("true", "1", "yes")
    if auto_push:
        _push_consolidated_to_github(consolidated_path, legacy_copy, timestamp)
    
    return 0


def _push_consolidated_to_github(consolidated_path: Path, legacy_copy: Path, event_id: str):
    """Automatically commit and push the consolidated files to GitHub."""
    import subprocess
    
    print("\n  📤 Auto-pushing consolidated file to GitHub...")
    
    try:
        # Check if git is available
        git_check = subprocess.run(
            ['git', '--version'],
            capture_output=True,
            text=True
        )
        if git_check.returncode != 0:
            print("  ⚠️  Git not available, skipping GitHub push")
            return
        
        # Check if we're in a git repository
        git_repo_check = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            capture_output=True,
            text=True
        )
        if git_repo_check.returncode != 0:
            print("  ⚠️  Not in a git repository, skipping GitHub push")
            return
        
        files_to_add = []
        
        # Add consolidated file in data/consolidated/
        if consolidated_path.exists():
            rel_path = consolidated_path.relative_to(Path.cwd())
            if (Path.cwd() / rel_path).exists():
                files_to_add.append(str(rel_path))
        
        # Add legacy copy in root if it exists
        if legacy_copy.exists():
            files_to_add.append(str(legacy_copy))
        
        if not files_to_add:
            print(f"  ⚠️  Could not find consolidated files to add")
            return
        
        # Add the files
        add_result = subprocess.run(
            ['git', 'add'] + files_to_add,
            capture_output=True,
            text=True
        )
        
        if add_result.returncode != 0:
            print(f"  ⚠️  Failed to add files to git: {add_result.stderr}")
            return
        
        # Commit
        commit_msg = f"Auto-update: Consolidated plans data ({event_id})"
        commit_result = subprocess.run(
            ['git', 'commit', '-m', commit_msg],
            capture_output=True,
            text=True
        )
        
        if commit_result.returncode != 0:
            if "nothing to commit" in commit_result.stdout.lower():
                print("  ℹ️  No changes to commit (file already up to date)")
                return
            print(f"  ⚠️  Failed to commit: {commit_result.stderr}")
            return
        
        # Push to GitHub
        push_result = subprocess.run(
            ['git', 'push', 'origin', 'main'],
            capture_output=True,
            text=True
        )
        
        if push_result.returncode == 0:
            print(f"  ✅ Successfully pushed to GitHub!")
            print(f"     Files: {', '.join(files_to_add)}")
            print(f"     Streamlit Cloud will auto-redeploy in 1-2 minutes")
        else:
            # Try 'master' branch if 'main' fails
            push_result = subprocess.run(
                ['git', 'push', 'origin', 'master'],
                capture_output=True,
                text=True
            )
            if push_result.returncode == 0:
                print(f"  ✅ Successfully pushed to GitHub (master branch)!")
            else:
                print(f"  ⚠️  Failed to push to GitHub: {push_result.stderr}")
                print(f"     You may need to push manually: git push origin main")
    
    except Exception as e:
        print(f"  ⚠️  Error during GitHub push: {e}")
        print(f"     You can manually push with: git add {' '.join(files_to_add)} && git commit -m 'Update consolidated data' && git push")


if __name__ == '__main__':
    raise SystemExit(main())


